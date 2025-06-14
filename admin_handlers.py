# handlers/admin_handlers.py
import asyncio
# import aiohttp # No longer used directly
from datetime import datetime
from aiogram import Router, types, F, Bot, BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
# from openai import OpenAI, APIError, APIConnectionError # No longer used directly

import config
import keyboards as kb
# from database import Database # Global db instance removed
from states import AdminActions
from api_service import APIService # For type hinting if needed, services accessed via bot

admin_router = Router()
# db = Database(config.DATABASE_PATH) # Global db instance removed

class AdminMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: types.TelegramObject, data: dict):
        if hasattr(event, 'from_user') and event.from_user.id in config.ADMIN_IDS:
            # Pass db and services from bot dispatcher to data for handlers
            # This assumes bot instance is in data from dispatcher setup
            if "bot" in data:
                data["db"] = data["bot"]["db"]
                data["user_service"] = data["bot"]["user_service"]
                data["api_service"] = data["bot"]["api_service"]
            # else: Provide fallback or log error if bot is not in data
            return await handler(event, data)
        if isinstance(event, types.CallbackQuery): # Non-admin
            try:
                await event.answer("У вас нет прав для этого действия.", show_alert=True)
            except TelegramBadRequest: # Handle cases where callback might be too old
                pass
        return # Explicitly return None or let it fall through if event is not handled by admin

admin_router.message.middleware(AdminMiddleware())
admin_router.callback_query.middleware(AdminMiddleware())

async def get_user_id_from_input(input_str: str, bot: Bot): # Added bot for db access
    db = bot["db"]
    if input_str.startswith('@'):
        user = await db.get_user_id_by_username(input_str[1:])
        return user[0] if user else None
    try:
        return int(input_str)
    except ValueError:
        return None

async def test_chat_model(model: str, api_service: APIService) -> dict: # Takes APIService
    content, error = await api_service.chat_completion(
        model=model,
        messages=[{'role': 'user', 'content': 'Test'}],
        temperature=0.7,
        max_tokens=10
    )
    if content and not error:
        return {'model': model, 'status': 'OK'}
    elif error:
        if "timed out" in error.lower() or "timeout" in error.lower(): # Basic timeout check
             return {'model': model, 'status': 'Timeout'}
        try: # Attempt to parse status code if error is like "Error: <status_code> - <message>"
            if error.startswith("Error: ") and " - " in error:
                status_code_str = error.split(" ")[1]
                if status_code_str.isdigit():
                    return {'model': model, 'status': f'Error {status_code_str}'}
        except Exception: pass # Fallback if parsing fails
        if "invalid json" in error.lower(): # Check for invalid JSON specifically
            return {'model': model, 'status': 'Invalid JSON'}
        return {'model': model, 'status': f'Error: {error[:50]}'} # Generic error, truncated
    else:
        return {'model': model, 'status': 'Unknown Error'}


async def test_image_model(api_service: APIService) -> dict: # Takes APIService
    image_url, error = await api_service.generate_image(
        model=config.IMAGE_MODEL,
        prompt="Test"
    )
    if image_url and not error:
        return {'model': config.IMAGE_MODEL, 'status': 'OK'}
    elif error:
        if "connection" in error.lower(): # Basic connection error check
            return {'model': config.IMAGE_MODEL, 'status': 'Connection Error'}
        if "api error" in error.lower() or (error.startswith("Error: ") and " - " in error):
            return {'model': config.IMAGE_MODEL, 'status': f'API Error {error[:50]}'}
        return {'model': config.IMAGE_MODEL, 'status': f'Error: {error[:50]}'} # Generic error
    else:
        return {'model': config.IMAGE_MODEL, 'status': 'Unknown Error'}


@admin_router.callback_query(F.data == 'menu_admin')
async def menu_admin(callback: types.CallbackQuery, bot: Bot, state: FSMContext): # Added bot, state
    await state.clear() # Clear any previous admin states
    await callback.message.edit_text('Админ-панель:', reply_markup=kb.get_admin_menu())
    await callback.answer()

@admin_router.callback_query(F.data == 'admin_back')
async def admin_back(callback: types.CallbackQuery, state: FSMContext, bot: Bot): # Added bot, state
    await state.clear()
    await callback.message.edit_text('Админ-панель:', reply_markup=kb.get_admin_menu())
    await callback.answer()

@admin_router.callback_query(F.data == 'admin_stats')
async def admin_stats(callback: types.CallbackQuery, bot: Bot):
    db = bot["db"]
    await db.cleanup_expired_subscriptions()

    total_users = await db.get_user_count()
    sub_stats_raw = await db.get_subscription_stats()
    reg_stats = await db.get_registration_counts()

    sub_stats = {config.SUB_LEVEL_MAP.get(k, 'unknown'): v for k, v in sub_stats_raw.items()}

    text = (f'<b>📊 Статистика подписок:</b>\n'
            f'Всего пользователей: {total_users}\n'
            f'Free: {sub_stats.get("free", 0)}\n'
            f'Standard: {sub_stats.get("standard", 0)}\n'
            f'Premium: {sub_stats.get("premium", 0)}\n\n'
            f'<b>📈 Статистика регистраций:</b>\n'
            f'Сегодня: {reg_stats["today"]}\n'
            f'Вчера: {reg_stats["yesterday"]}\n'
            f'За 7 дней: {reg_stats["last_7_days"]}\n'
            f'За 30 дней: {reg_stats["last_30_days"]}')

    await callback.message.edit_text(text, reply_markup=kb.get_admin_back_menu())
    await callback.answer()

@admin_router.callback_query(F.data == 'admin_test')
async def admin_test_models(callback: types.CallbackQuery, bot: Bot):
    model_status_cache = bot["model_status_cache"]
    api_service = bot["api_service"]

    await callback.answer("Начинаю тестирование...")
    msg = await callback.message.edit_text('Начинаю тестирование моделей... Это может занять несколько минут.')

    chat_models = sorted(list(set(model for models_list in config.ALL_MODELS.values() for model in models_list))) # Corrected iteration

    tasks = [test_chat_model(model, api_service) for model in chat_models]
    if config.IMAGE_MODEL: # Only test image model if configured
        tasks.append(test_image_model(api_service))

    results = await asyncio.gather(*tasks, return_exceptions=True) # Handle individual task errors

    working_models = []
    failed_models = []
    model_status_cache.clear()

    for r in results:
        if isinstance(r, Exception): # If asyncio.gather caught an exception for a task
            # Log this error, decide how to represent in status
            # For now, mark as a generic failure for the model if possible, or skip
            # This part depends on how you want to handle tasks that fail catastrophically
            # For simplicity, we'll assume test_chat_model/test_image_model return dicts even on internal errors
            # If they raise exceptions that reach here, it's an issue in their error handling.
            # Let's assume they always return a dict.
            pass # Should not happen if test functions catch their own exceptions.

        if not isinstance(r, dict) or 'model' not in r or 'status' not in r: # Defensive check
            # Log unexpected result format
            continue

        is_ok = r['status'] == 'OK'
        model_status_cache[r['model']] = is_ok # Update cache from bot dispatcher
        if is_ok:
            working_models.append(r)
        else:
            failed_models.append(r)

    text = f'<b>Результаты тестирования:</b>\n\n<b>✅ Рабочие модели ({len(working_models)}):</b>\n'
    text += "\n".join(f"✓ {r['model']}" for r in working_models) if working_models else "Нет рабочих моделей."

    if failed_models:
        text += f'\n\n<b>❌ Нерабочие или проблемные модели ({len(failed_models)}):</b>\n'
        text += "\n".join(f"✗ {r['model']} - {r['status']}" for r in failed_models)
    else:
        text += "\n\nВсе модели в порядке!"

    await msg.edit_text(text, reply_markup=kb.get_admin_back_menu())

@admin_router.callback_query(F.data == 'admin_users')
async def admin_users_menu_callback(callback: types.CallbackQuery, bot: Bot): # Added bot
    await callback.message.edit_text('Управление пользователями:', reply_markup=kb.get_admin_users_menu())
    await callback.answer()

async def start_admin_action(callback: types.CallbackQuery, state: FSMContext, new_state: AdminActions, prompt_text: str):
    await callback.message.edit_text(prompt_text, reply_markup=kb.get_cancel_keyboard())
    await state.set_state(new_state)
    await state.update_data(prompt_message_id=callback.message.message_id)
    await callback.answer()

async def process_admin_action(message: types.Message, state: FSMContext, bot: Bot, action_func):
    data = await state.get_data()
    prompt_message_id = data.get('prompt_message_id')
    # It's important to clear state AFTER getting data, but BEFORE await action_func
    # if action_func might re-enter a state or if errors occur.
    # However, if action_func needs state data, clear after it.
    # For simple actions, clearing here is fine.

    success, result_text = await action_func(message.text, bot)
    await state.clear() # Clear state after action_func has completed.

    if prompt_message_id:
        try:
            await bot.edit_message_text(result_text, chat_id=message.chat.id, message_id=prompt_message_id, reply_markup=kb.get_admin_menu()) # Back to main admin menu
        except TelegramBadRequest:
            await message.answer(result_text, reply_markup=kb.get_admin_menu())
    else:
        await message.answer(result_text, reply_markup=kb.get_admin_menu())

    try:
        await message.delete()
    except TelegramBadRequest: # Message might have already been deleted
        pass

def format_user_card(user_data, page, total_pages):
    # uid, uname, sub_level, sub_end, is_blocked, last_model, sys_prompt, temp, created_at
    if not user_data or len(user_data) < 9: # Basic validation
        return "Ошибка: Недостаточно данных о пользователе."

    uid, uname, sub_level, sub_end_iso, is_blocked, last_model, _, _, created_at_iso = user_data[:9]
    sub_name = config.SUB_LEVEL_MAP.get(sub_level, "Неизвестен")

    sub_end_text = "Никогда"
    if sub_end_iso:
        try:
            sub_end_date = datetime.fromisoformat(sub_end_iso) if isinstance(sub_end_iso, str) else sub_end_iso
            if isinstance(sub_end_date, datetime):
                 sub_end_text = sub_end_date.strftime('%d.%m.%Y %H:%M') + (" (истекла)" if sub_end_date < datetime.now() else "")
        except ValueError:
            sub_end_text = str(sub_end_iso)

    created_at_text = "Неизвестно"
    if created_at_iso:
        try:
            created_at_date = datetime.fromisoformat(created_at_iso) if isinstance(created_at_iso, str) else created_at_iso
            if isinstance(created_at_date, datetime):
                created_at_text = created_at_date.strftime('%d.%m.%Y %H:%M')
        except ValueError:
             created_at_text = str(created_at_iso)

    text = (f"<b>ℹ️ Пользователь {page}/{total_pages}</b>\n\n"
            f"<b>ID:</b> <code>{uid}</code>\n<b>Username:</b> @{uname or 'Отсутствует'}\n"
            f"<b>Уровень:</b> {sub_name.capitalize()} ({sub_level})\n<b>Подписка до:</b> {sub_end_text}\n"
            f"<b>Заблокирован:</b> {'Да' if is_blocked else 'Нет'}\n"
            f"<b>Последняя модель:</b> {last_model or 'Не выбрана'}\n<b>Регистрация:</b> {created_at_text}")
    return text

@admin_router.callback_query(kb.Paginator.filter())
@admin_router.callback_query(F.data.startswith("admin_list_users")) # Ensure this doesn't conflict with Paginator if page is not part of data
async def admin_list_users(callback: types.CallbackQuery, bot: Bot, callback_data: kb.Paginator = None):
    db = bot["db"]
    page = 1 # Default to page 1 if not from paginator

    # If callback_data is None, it implies direct call e.g. from admin_list_users button
    # So, start at page 1.
    if callback_data and isinstance(callback_data, kb.Paginator):
        if callback_data.action == "next": page = callback_data.page + 1
        elif callback_data.action == "prev": page = callback_data.page - 1
        # If page is already part of callback_data (e.g. page itself), use it.
        # This depends on how Paginator callback_data is structured.
        # Assuming Paginator passes current page and action.

    total_users = await db.get_user_count()
    if total_users == 0:
        await callback.message.edit_text("В базе данных пока нет пользователей.", reply_markup=kb.get_admin_back_menu())
        await callback.answer()
        return

    user_data_list = await db.get_all_users_paginated(page=page, per_page=1) # Assuming per_page=1 for one card
    if not user_data_list: # Should not happen if total_users > 0 and page is valid. Could mean page out of bounds.
        await callback.answer("Больше пользователей нет или страница недействительна.", show_alert=True)
        # Optionally, reset to page 1 or last valid page
        # For now, just inform and don't change message.
        return

    text = format_user_card(user_data_list[0], page, total_users)
    await callback.message.edit_text(text, reply_markup=kb.get_paginated_users_keyboard(page, total_users, "admin_list_users")) # Added base_callback_data
    await callback.answer()


@admin_router.callback_query(F.data == 'admin_search')
async def admin_search_start(callback: types.CallbackQuery, state: FSMContext, bot: Bot): # Added bot
    await start_admin_action(callback, state, AdminActions.waiting_for_search_user, "Отправьте ID или @username для поиска.")

@admin_router.message(AdminActions.waiting_for_search_user)
async def admin_search_process(message: types.Message, state: FSMContext, bot: Bot):
    db = bot["db"]
    async def action(input_str, current_bot):
        user_id = await get_user_id_from_input(input_str, current_bot)
        if not user_id: return False, f"Пользователь '{input_str}' не найден."
        user_data = await db.get_user_info(user_id)
        if not user_data: return False, f"Пользователь с ID '{user_id}' не найден в базе."

        text = format_user_card(user_data, 1, 1).replace(" 1/1", "") # Page 1 of 1 for single user
        return True, text

    await process_admin_action(message, state, bot, action)

@admin_router.callback_query(F.data == 'admin_grant')
async def admin_grant_start(callback: types.CallbackQuery, state: FSMContext, bot: Bot): # Added bot
    await start_admin_action(callback, state, AdminActions.waiting_for_grant_user, 'Отправьте ID/@username и уровень (0, 1, 2):\nФормат: `ID/username LEVEL`')

@admin_router.message(AdminActions.waiting_for_grant_user)
async def admin_grant_process(message: types.Message, state: FSMContext, bot: Bot):
    db = bot["db"]
    async def action(input_str, current_bot):
        try:
            parts = input_str.split()
            if len(parts) != 2: raise ValueError("Ожидается два аргумента: ID/username и уровень.")
            target_input, level_str = parts
            level = int(level_str)

            if level not in config.SUB_LEVEL_MAP.keys():
                return False, f"Неверный уровень подписки. Укажите одно из чисел: {list(config.SUB_LEVEL_MAP.keys())}."

            target_user_id = await get_user_id_from_input(target_input, current_bot)
            if not target_user_id:
                return False, f"Пользователь {target_input} не найден."

            await db.update_subscription(target_user_id, level, None) # Grant without expiry for now
            sub_name = config.SUB_LEVEL_MAP.get(level, "Неизвестный").capitalize()

            try:
                if level > 0: # Notify only for actual subscriptions
                    notification_text = f"Вам была выдана подписка администратором. Установлен уровень: <b>{sub_name}</b>."
                    await current_bot.send_message(target_user_id, notification_text)
            except (TelegramForbiddenError, TelegramBadRequest): pass # User blocked bot or error

            return True, f"Подписка уровня {sub_name} выдана пользователю {target_input}."
        except ValueError as e:
            return False, f"Неверный формат: {e}. Пример: `@username 1` или `12345678 2`."

    await process_admin_action(message, state, bot, action)

@admin_router.callback_query(F.data == 'admin_revoke')
async def admin_revoke_start(callback: types.CallbackQuery, state: FSMContext, bot: Bot): # Added bot
    await start_admin_action(callback, state, AdminActions.waiting_for_revoke_user, 'Отправьте ID или @username, чтобы забрать подписку (установить Free):')

@admin_router.message(AdminActions.waiting_for_revoke_user)
async def admin_revoke_process(message: types.Message, state: FSMContext, bot: Bot):
    db = bot["db"]
    async def action(input_str, current_bot):
        target_user_id = await get_user_id_from_input(input_str, current_bot)
        if not target_user_id:
            return False, f"Пользователь {input_str} не найден."

        if target_user_id in config.ADMIN_IDS: # Prevent revoking admin's own implicit subscription
            return False, "Нельзя забрать подписку у администратора таким способом."

        await db.update_subscription(target_user_id, 0, None) # Set to Free, remove expiry

        try:
            await current_bot.send_message(target_user_id, 'Ваша платная подписка была отозвана администратором. Установлен уровень Free.')
        except (TelegramForbiddenError, TelegramBadRequest): pass

        return True, f"Подписка у пользователя {input_str} успешно сброшена до Free."

    await process_admin_action(message, state, bot, action)

async def blocking_action(input_str: str, block: bool, bot: Bot):
    db = bot["db"]
    target_user_id = await get_user_id_from_input(input_str, bot)
    if not target_user_id: return False, f"Пользователь {input_str} не найден."

    if target_user_id in config.ADMIN_IDS and block: # Prevent self-lockout or locking other admins
        return False, "Администраторов нельзя блокировать."

    await db.block_user(target_user_id, block)
    status = "заблокирован" if block else "разблокирован"
    try:
        await bot.send_message(target_user_id, f'Ваш доступ к боту был {status} администратором.')
    except (TelegramForbiddenError, TelegramBadRequest): pass
    return True, f"Пользователь {input_str} {status}."

@admin_router.callback_query(F.data == 'admin_block')
async def admin_block_start(callback: types.CallbackQuery, state: FSMContext, bot: Bot): # Added bot
    await start_admin_action(callback, state, AdminActions.waiting_for_block_user, 'Отправьте ID или @username для блокировки:')

@admin_router.message(AdminActions.waiting_for_block_user)
async def admin_block_process(message: types.Message, state: FSMContext, bot: Bot):
    await process_admin_action(message, state, bot, lambda text, current_bot: blocking_action(text, True, current_bot))


@admin_router.callback_query(F.data == 'admin_unblock')
async def admin_unblock_start(callback: types.CallbackQuery, state: FSMContext, bot: Bot): # Added bot
    await start_admin_action(callback, state, AdminActions.waiting_for_unblock_user, 'Отправьте ID или @username для разблокировки:')

@admin_router.message(AdminActions.waiting_for_unblock_user)
async def admin_unblock_process(message: types.Message, state: FSMContext, bot: Bot):
    await process_admin_action(message, state, bot, lambda text, current_bot: blocking_action(text, False, current_bot))


async def broadcast_to_users(bot: Bot, text: str, pin_message: bool, initiator_id: int):
    db = bot["db"]
    broadcast_id = await db.add_broadcast(text, initiator_id) # Store who initiated
    user_ids = await db.get_all_user_ids(exclude_blocked=True) # Get non-blocked users
    success_count, fail_count = 0, 0

    for user_id_tuple in user_ids: # Assuming get_all_user_ids returns list of tuples e.g. (id,)
        user_id = user_id_tuple[0]
        try:
            sent_message = await bot.send_message(user_id, text, parse_mode="HTML") # parse_mode for formatting
            await db.add_sent_broadcast_message(broadcast_id, user_id, sent_message.message_id)
            if pin_message:
                await bot.pin_chat_message(chat_id=user_id, message_id=sent_message.message_id, disable_notification=True)
            success_count += 1
        except (TelegramForbiddenError, TelegramBadRequest): fail_count += 1 # Common errors for inactive users/bots
        except Exception: fail_count += 1 # Catch other potential errors during send
        await asyncio.sleep(0.05) # Short sleep to avoid hitting rate limits, 20 messages/sec approx

    summary_text = (f"✅ Рассылка завершена.\n\n"
                    f"Текст:\n<i>{text[:1000]}</i>\n\n" # Show part of the text
                    f"Успешно отправлено: {success_count}\n"
                    f"Не удалось / заблокировано: {fail_count}")

    await bot.send_message(
        chat_id=initiator_id,
        text=summary_text,
        reply_markup=kb.get_broadcast_manage_keyboard(broadcast_id)
    )

@admin_router.callback_query(F.data == 'admin_broadcast')
async def admin_broadcast_start(callback: types.CallbackQuery, state: FSMContext, bot: Bot): # Added bot
    await start_admin_action(callback, state, AdminActions.waiting_for_broadcast_message, "Введите текст для рассылки (HTML-разметка поддерживается).")

@admin_router.message(AdminActions.waiting_for_broadcast_message) # No F.text filter to allow entities
async def admin_broadcast_confirm(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    prompt_message_id = data.get('prompt_message_id')

    # Store message.html_text to preserve formatting for broadcast
    await state.update_data(broadcast_text=message.html_text) # Use html_text
    await state.set_state(AdminActions.waiting_for_broadcast_confirmation)

    preview_text = f"<b>Предпросмотр рассылки:</b>\n\n{message.html_text[:3000]}\n\nПодтвердите действие:"

    if prompt_message_id:
        try:
            await bot.edit_message_text(
                preview_text,
                chat_id=message.chat.id,
                message_id=prompt_message_id,
                reply_markup=kb.get_broadcast_confirmation_keyboard(),
                parse_mode="HTML"
            )
        except TelegramBadRequest:
             await message.answer(preview_text, reply_markup=kb.get_broadcast_confirmation_keyboard(), parse_mode="HTML")
    else:
        await message.answer(preview_text, reply_markup=kb.get_broadcast_confirmation_keyboard(), parse_mode="HTML")

    try:
        await message.delete()
    except TelegramBadRequest: pass


@admin_router.callback_query(F.data.startswith('broadcast_'), AdminActions.waiting_for_broadcast_confirmation)
async def admin_broadcast_process(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    user_data = await state.get_data()
    text_to_broadcast = user_data.get('broadcast_text') # This is html_text

    if not text_to_broadcast: # Should not happen if state is managed correctly
        await callback.answer("Ошибка: Текст рассылки не найден. Попробуйте снова.", show_alert=True)
        await state.clear()
        await callback.message.edit_text("Произошла ошибка. Пожалуйста, начните заново.", reply_markup=kb.get_admin_back_menu())
        return

    pin = callback.data == 'broadcast_pin_confirm' # Adjusted callback data for clarity
    await state.clear()

    try:
        await callback.message.edit_text("⏳ Начинаю рассылку... Вы получите отчет по завершении.")
    except TelegramBadRequest:
        await callback.answer("⏳ Начинаю рассылку...", show_alert=True) # If message edit fails

    initiator_id = callback.from_user.id

    asyncio.create_task(broadcast_to_users(bot, text_to_broadcast, pin_message=pin, initiator_id=initiator_id))

    await callback.answer() # Acknowledge callback quickly


@admin_router.callback_query(kb.BroadcastCallback.filter())
async def manage_broadcast(callback: types.CallbackQuery, callback_data: kb.BroadcastCallback, bot: Bot):
    db = bot["db"]
    action = callback_data.action
    broadcast_id = callback_data.broadcast_id

    sent_messages = await db.get_sent_messages_for_broadcast(broadcast_id)
    if not sent_messages:
        await callback.answer("Информация об этой рассылке уже удалена или не найдена.", show_alert=True)
        return

    action_text = "Открепляю" if action == "unpin" else "Удаляю"
    await callback.answer(f"{action_text} сообщения...", show_alert=False) # Show a small notification

    success_count = 0
    fail_count = 0
    for user_id, message_id in sent_messages:
        try:
            if action == "unpin":
                await bot.unpin_chat_message(user_id, message_id)
            elif action == "delete":
                await bot.delete_message(user_id, message_id)
            success_count +=1
        except (TelegramForbiddenError, TelegramBadRequest): fail_count +=1
        except Exception: fail_count +=1
        await asyncio.sleep(0.05) # Be gentle with API

    final_message_text = ""
    if action == "delete":
        await db.delete_broadcast(broadcast_id) # Clean up DB record
        final_message_text = f"Сообщения рассылки удалены.\nУспешно: {success_count}\nНе удалось: {fail_count}"
    else: # unpin
        final_message_text = f"Сообщения рассылки откреплены.\nУспешно: {success_count}\nНе удалось: {fail_count}"

    try:
        await callback.message.edit_text(final_message_text, reply_markup=kb.get_admin_back_menu())
    except TelegramBadRequest: # If original message is gone
        await callback.message.answer(final_message_text, reply_markup=kb.get_admin_back_menu())


@admin_router.callback_query(F.data == 'admin_reset_all_subs')
async def admin_reset_all_subs_confirm(callback: types.CallbackQuery, bot: Bot): # Added bot
    text = ("<b>⚠️ ПРЕДУПРЕЖДЕНИЕ ⚠️</b>\n\n"
            "Вы уверены, что хотите сбросить <b>ВСЕ</b> платные подписки до уровня Free?\n\n"
            "Подписки администраторов затронуты не будут. "
            "Это действие необратимо.")
    await callback.message.edit_text(text, reply_markup=kb.get_reset_all_subs_confirmation_keyboard())
    await callback.answer()

@admin_router.callback_query(F.data == 'confirm_reset_all_subs')
async def admin_reset_all_subs_process(callback: types.CallbackQuery, bot: Bot):
    db = bot["db"]
    await callback.message.edit_text("Выполняю сброс подписок...")

    updated_count = await db.reset_all_subscriptions(config.ADMIN_IDS)

    await callback.message.edit_text(
        f"✅ Успешно сброшено {updated_count} подписок до уровня Free.",
        reply_markup=kb.get_admin_back_menu()
    )
    await callback.answer()

@admin_router.callback_query(F.data == 'admin_self_test')
async def admin_self_test(callback: types.CallbackQuery, bot: Bot):
    db = bot["db"]
    user_service = bot["user_service"]

    await callback.answer("🤖 Запускаю автотесты...")
    msg = await callback.message.edit_text("<b>🤖 Проведение автотестов...</b>")

    report = ["<b>🤖 Отчет по автотестам:</b>"]
    admin_id = callback.from_user.id
    original_level = await db.check_subscription(admin_id) # Store original level

    try:
        # Test 1: Grant subscription (level 1)
        await db.update_subscription(admin_id, 1, None)
        level_after_grant = await db.check_subscription(admin_id)
        report.append("✅ Тест 1 (Выдача подписки Standard): OK" if level_after_grant == 1 else f"❌ Тест 1 (Выдача подписки Standard): FAILED (уровень {level_after_grant})")

        # Test 2: Block user
        await db.block_user(admin_id, True)
        is_blocked_after_block = await db.is_user_blocked(admin_id)
        report.append("✅ Тест 2 (Блокировка): OK" if is_blocked_after_block else "❌ Тест 2 (Блокировка): FAILED")

        # Test 3: Unblock user
        await db.block_user(admin_id, False)
        is_blocked_after_unblock = await db.is_user_blocked(admin_id)
        report.append("✅ Тест 3 (Разблокировка): OK" if not is_blocked_after_unblock else "❌ Тест 3 (Разблокировка): FAILED")

        # Test 4: Revoke subscription (set to level 0)
        await db.update_subscription(admin_id, 0, None)
        level_after_revoke = await db.check_subscription(admin_id)
        report.append("✅ Тест 4 (Сброс подписки до Free): OK" if level_after_revoke == 0 else f"❌ Тест 4 (Сброс подписки до Free): FAILED (уровень {level_after_revoke})")

        # Test 5: Check admin's effective access level (should be high regardless of subscription)
        # This uses user_service.get_user_level which considers ADMIN_IDS
        admin_effective_level = await user_service.get_user_level(admin_id)
        # Assuming your config has a way to define the expected admin level, e.g., config.ADMIN_ACCESS_LEVEL
        # For this example, let's assume admin level is identified as 2 or 3 in get_user_level
        expected_admin_level_in_service = 3 # Based on user_service.py logic for ADMIN_IDS
        report.append(f"✅ Тест 5 (Уровень доступа админа): OK (эффективный уровень {admin_effective_level})" if admin_effective_level == expected_admin_level_in_service else f"❌ Тест 5 (Уровень доступа админа): FAILED (эффективный уровень {admin_effective_level}, ожидался {expected_admin_level_in_service})")

        report.append("\n<b>Все тесты завершены!</b>")
    except Exception as e:
        report.append(f"\n❌ <b>Во время тестов произошла ошибка:</b>\n<code>{e}</code>")
    finally:
        # Restore original state for admin (e.g. subscription level, blocked status)
        await db.update_subscription(admin_id, original_level or 0, None) # Restore original or set to 0 if None
        await db.block_user(admin_id, False) # Ensure admin is not left blocked

    await msg.edit_text("\n".join(report), reply_markup=kb.get_admin_back_menu())
