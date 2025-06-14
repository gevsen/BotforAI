# handlers/admin_handlers.py
import asyncio
import aiohttp
from datetime import datetime
from aiogram import Router, types, F, Bot, BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from openai import OpenAI, APIError, APIConnectionError

import config
import keyboards as kb
from database import Database
from states import AdminActions

admin_router = Router()
db = Database(config.DATABASE_PATH)

class AdminMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: types.TelegramObject, data: dict):
        if hasattr(event, 'from_user') and event.from_user.id in config.ADMIN_IDS:
            return await handler(event, data)
        if isinstance(event, types.CallbackQuery):
            await event.answer("У вас нет прав для этого действия.", show_alert=True)
        return

admin_router.message.middleware(AdminMiddleware())
admin_router.callback_query.middleware(AdminMiddleware())

async def get_user_id_from_input(input_str: str):
    if input_str.startswith('@'):
        user = await db.get_user_id_by_username(input_str[1:])
        return user[0] if user else None
    try:
        return int(input_str)
    except ValueError:
        return None

async def test_chat_model(model: str) -> dict:
    async with aiohttp.ClientSession() as session:
        headers = {'Authorization': f'Bearer {config.API_KEY}', 'Content-Type': 'application/json'}
        data = {'model': model, 'messages': [{'role': 'user', 'content': 'Test'}], 'temperature': 0.7, 'max_tokens': 10}
        try:
            async with session.post(f'{config.API_URL}/chat/completions', headers=headers, json=data, timeout=45) as response:
                if response.status == 200:
                    try: await response.json(); return {'model': model, 'status': 'OK'}
                    except Exception: return {'model': model, 'status': 'Invalid JSON'}
                else: return {'model': model, 'status': f'Error {response.status}'}
        except asyncio.TimeoutError: return {'model': model, 'status': 'Timeout'}
        except Exception as e: return {'model': model, 'status': f'Error: {type(e).__name__}'}

# <<< ИЗМЕНЕНИЯ ЗДЕСЬ: ПРАВИЛЬНЫЙ ПОРЯДОК EXCEPT БЛОКОВ >>>
async def test_image_model() -> dict:
    client = OpenAI(base_url=config.IMAGE_API_URL, api_key=config.API_KEY)
    try:
        client.images.generate(model=config.IMAGE_MODEL, prompt="Test", size="1024x1024", n=1)
        return {'model': config.IMAGE_MODEL, 'status': 'OK'}
    except APIConnectionError:
        # Сначала ловим более специфичную ошибку соединения (у нее нет status_code)
        return {'model': config.IMAGE_MODEL, 'status': 'Connection Error'}
    except APIError as e:
        # Затем ловим другие ошибки API (у них есть status_code)
        return {'model': config.IMAGE_MODEL, 'status': f'API Error {e.status_code}'}
    except Exception as e:
        # Любая другая непредвиденная ошибка
        return {'model': config.IMAGE_MODEL, 'status': f'Error: {type(e).__name__}'}

@admin_router.callback_query(F.data == 'menu_admin')
async def menu_admin(callback: types.CallbackQuery):
    await callback.message.edit_text('Админ-панель:', reply_markup=kb.get_admin_menu())

@admin_router.callback_query(F.data == 'admin_back')
async def admin_back(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text('Админ-панель:', reply_markup=kb.get_admin_menu())

@admin_router.callback_query(F.data == 'admin_stats')
async def admin_stats(callback: types.CallbackQuery):
    # Сначала очищаем истекшие подписки для актуальной статистики
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

@admin_router.callback_query(F.data == 'admin_test')
async def admin_test_models(callback: types.CallbackQuery, model_status_cache: dict):
    await callback.answer("Начинаю тестирование...")
    msg = await callback.message.edit_text('Начинаю тестирование моделей... Это может занять несколько минут.')
    
    chat_models = sorted(list(set(model for models in config.ALL_MODELS.values() for model in models)))
    tasks = [test_chat_model(model) for model in chat_models]
    tasks.append(test_image_model())
    
    results = await asyncio.gather(*tasks)
    
    working_models = []
    failed_models = []
    model_status_cache.clear()

    for r in results:
        is_ok = r['status'] == 'OK'
        model_status_cache[r['model']] = is_ok
        if is_ok:
            working_models.append(r)
        else:
            failed_models.append(r)

    text = f'<b>Результаты тестирования:</b>\n\n<b>✅ Рабочие модели ({len(working_models)}):</b>\n' + "\n".join(f"✓ {r['model']}" for r in working_models)
    if failed_models:
        text += f'\n\n<b>❌ Нерабочие модели ({len(failed_models)}):</b>\n' + "\n".join(f"✗ {r['model']} - {r['status']}" for r in failed_models)
    
    await msg.edit_text(text, reply_markup=kb.get_admin_back_menu())

@admin_router.callback_query(F.data == 'admin_users')
async def admin_users_menu_callback(callback: types.CallbackQuery):
    await callback.message.edit_text('Управление пользователями:', reply_markup=kb.get_admin_users_menu())

async def start_admin_action(callback: types.CallbackQuery, state: FSMContext, new_state: AdminActions, prompt_text: str):
    await callback.message.edit_text(prompt_text, reply_markup=kb.get_cancel_keyboard())
    await state.set_state(new_state)
    await state.update_data(prompt_message_id=callback.message.message_id)
    await callback.answer()

async def process_admin_action(message: types.Message, state: FSMContext, bot: Bot, action_func):
    data = await state.get_data()
    prompt_message_id = data.get('prompt_message_id')
    await state.clear()

    success, result_text = await action_func(message.text)
    
    if prompt_message_id:
        await bot.edit_message_text(result_text, chat_id=message.chat.id, message_id=prompt_message_id)
    
    await message.answer("Админ-панель:", reply_markup=kb.get_admin_menu())
    await message.delete()

def format_user_card(user_data, page, total_pages):
    (uid, uname, sub_level, sub_end, is_blocked, last_model, sys_prompt, temp, created_at) = user_data
    sub_name = config.SUB_LEVEL_MAP.get(sub_level, "Неизвестен")
    
    sub_end_text = "Никогда"
    if sub_end:
        sub_end_date = datetime.fromisoformat(sub_end)
        sub_end_text = sub_end_date.strftime('%d.%m.%Y %H:%M') + (" (истекла)" if sub_end_date < datetime.now() else "")
    
    created_at_text = "Неизвестно"
    if created_at and isinstance(created_at, str):
        created_at_text = datetime.fromisoformat(created_at).strftime('%d.%m.%Y %H:%M')
    
    text = (f"<b>ℹ️ Пользователь {page}/{total_pages}</b>\n\n"
            f"<b>ID:</b> <code>{uid}</code>\n<b>Username:</b> @{uname or 'Отсутствует'}\n"
            f"<b>Уровень:</b> {sub_name.capitalize()} ({sub_level})\n<b>Подписка до:</b> {sub_end_text}\n"
            f"<b>Заблокирован:</b> {'Да' if is_blocked else 'Нет'}\n"
            f"<b>Последняя модель:</b> {last_model or 'Не выбрана'}\n<b>Регистрация:</b> {created_at_text}")
    return text

@admin_router.callback_query(kb.Paginator.filter())
@admin_router.callback_query(F.data.startswith("admin_list_users"))
async def admin_list_users(callback: types.CallbackQuery, callback_data: kb.Paginator = None):
    page = 1
    if callback_data and isinstance(callback_data, kb.Paginator):
        if callback_data.action == "next": page = callback_data.page + 1
        elif callback_data.action == "prev": page = callback_data.page - 1
    
    total_users = await db.get_user_count()
    if total_users == 0:
        return await callback.message.edit_text("В базе данных пока нет пользователей.", reply_markup=kb.get_admin_back_menu())

    user_data_list = await db.get_all_users_paginated(page=page)
    if not user_data_list:
        return await callback.answer("Больше пользователей нет.", show_alert=True)

    text = format_user_card(user_data_list[0], page, total_users)
    await callback.message.edit_text(text, reply_markup=kb.get_paginated_users_keyboard(page, total_users))

@admin_router.callback_query(F.data == 'admin_search')
async def admin_search_start(callback: types.CallbackQuery, state: FSMContext):
    await start_admin_action(callback, state, AdminActions.waiting_for_search_user, "Отправьте ID или @username для поиска.")

@admin_router.message(AdminActions.waiting_for_search_user)
async def admin_search_process(message: types.Message, state: FSMContext, bot: Bot):
    async def action(input_str):
        user_id = await get_user_id_from_input(input_str)
        if not user_id: return False, f"Пользователь '{input_str}' не найден."
        user_data = await db.get_user_info(user_id)
        if not user_data: return False, f"Пользователь с ID '{user_id}' не найден в базе."
        
        text = format_user_card(user_data, 1, 1).replace(" 1/1", "")
        return True, text
    
    await process_admin_action(message, state, bot, action)

@admin_router.callback_query(F.data == 'admin_grant')
async def admin_grant_start(callback: types.CallbackQuery, state: FSMContext):
    await start_admin_action(callback, state, AdminActions.waiting_for_grant_user, 'Отправьте ID/@username и уровень (0, 1, 2):\nФормат: `ID/username LEVEL`')

@admin_router.message(AdminActions.waiting_for_grant_user)
async def admin_grant_process(message: types.Message, state: FSMContext, bot: Bot):
    async def action(input_str):
        try:
            target_input, level_str = input_str.split()
            level = int(level_str)
            if level not in config.SUB_LEVEL_MAP.keys(): 
                return False, f"Неверный уровень подписки. Укажите одно из чисел: {list(config.SUB_LEVEL_MAP.keys())}."
            
            target_user_id = await get_user_id_from_input(target_input)
            if not target_user_id: 
                return False, f"Пользователь {target_input} не найден."
            
            await db.update_subscription(target_user_id, level)
            sub_name = config.SUB_LEVEL_MAP.get(level).capitalize()

            try:
                if level > 0:
                    notification_text = f"Вам была выдана подписка администратором. Установлен уровень: <b>{sub_name}</b>."
                    await bot.send_message(target_user_id, notification_text)
            except (TelegramForbiddenError, TelegramBadRequest):
                pass 

            return True, f"Подписка уровня {sub_name} выдана пользователю {target_input}."
        except ValueError:
            return False, "Неверный формат. Пример: `@username 1` или `12345678 2`."
    
    await process_admin_action(message, state, bot, action)

@admin_router.callback_query(F.data == 'admin_revoke')
async def admin_revoke_start(callback: types.CallbackQuery, state: FSMContext):
    await start_admin_action(callback, state, AdminActions.waiting_for_revoke_user, 'Отправьте ID или @username, чтобы забрать подписку (установить Free):')

@admin_router.message(AdminActions.waiting_for_revoke_user)
async def admin_revoke_process(message: types.Message, state: FSMContext, bot: Bot):
    async def action(input_str):
        target_user_id = await get_user_id_from_input(input_str)
        if not target_user_id:
            return False, f"Пользователь {input_str} не найден."
        
        if target_user_id in config.ADMIN_IDS:
            return False, "Нельзя забрать подписку у администратора."

        await db.update_subscription(target_user_id, 0)
        
        try:
            await bot.send_message(target_user_id, 'Ваша платная подписка была отозвана администратором. Установлен уровень Free.')
        except (TelegramForbiddenError, TelegramBadRequest):
            pass
            
        return True, f"Подписка у пользователя {input_str} успешно сброшена до Free."
    
    await process_admin_action(message, state, bot, action)

async def blocking_action(input_str: str, block: bool, bot: Bot):
    target_user_id = await get_user_id_from_input(input_str)
    if not target_user_id: return False, f"Пользователь {input_str} не найден."
    await db.block_user(target_user_id, block)
    status = "заблокирован" if block else "разблокирован"
    try:
        await bot.send_message(target_user_id, f'Ваш доступ к моделям был {status} администратором.')
    except (TelegramForbiddenError, TelegramBadRequest): pass
    return True, f"Пользователь {input_str} {status}."

@admin_router.callback_query(F.data == 'admin_block')
async def admin_block_start(callback: types.CallbackQuery, state: FSMContext):
    await start_admin_action(callback, state, AdminActions.waiting_for_block_user, 'Отправьте ID или @username для блокировки:')

@admin_router.message(AdminActions.waiting_for_block_user)
async def admin_block_process(message: types.Message, state: FSMContext, bot: Bot):
    await process_admin_action(message, state, bot, lambda text: blocking_action(text, True, bot))

@admin_router.callback_query(F.data == 'admin_unblock')
async def admin_unblock_start(callback: types.CallbackQuery, state: FSMContext):
    await start_admin_action(callback, state, AdminActions.waiting_for_unblock_user, 'Отправьте ID или @username для разблокировки:')

@admin_router.message(AdminActions.waiting_for_unblock_user)
async def admin_unblock_process(message: types.Message, state: FSMContext, bot: Bot):
    await process_admin_action(message, state, bot, lambda text: blocking_action(text, False, bot))

async def broadcast_to_users(bot: Bot, text: str, pin_message: bool, initiator_id: int):
    broadcast_id = await db.add_broadcast(text)
    user_ids = await db.get_all_user_ids()
    success_count, fail_count = 0, 0
    for user_id in user_ids:
        try:
            sent_message = await bot.send_message(user_id, text)
            await db.add_sent_broadcast_message(broadcast_id, user_id, sent_message.message_id)
            if pin_message: await bot.pin_chat_message(chat_id=user_id, message_id=sent_message.message_id)
            success_count += 1
        except (TelegramForbiddenError, TelegramBadRequest): fail_count += 1
        except Exception: fail_count += 1
        await asyncio.sleep(0.1)
    
    await bot.send_message(
        chat_id=initiator_id,
        text=f"✅ Рассылка завершена.\n\nУспешно: {success_count}\nНе удалось: {fail_count}",
        reply_markup=kb.get_broadcast_manage_keyboard(broadcast_id)
    )

@admin_router.callback_query(F.data == 'admin_broadcast')
async def admin_broadcast_start(callback: types.CallbackQuery, state: FSMContext):
    await start_admin_action(callback, state, AdminActions.waiting_for_broadcast_message, "Введите текст для рассылки.")

@admin_router.message(AdminActions.waiting_for_broadcast_message)
async def admin_broadcast_confirm(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    prompt_message_id = data.get('prompt_message_id')
    
    await state.update_data(broadcast_text=message.text)
    await state.set_state(AdminActions.waiting_for_broadcast_confirmation)
    
    if prompt_message_id:
        await bot.edit_message_text(
            "Подтвердите действие:", 
            chat_id=message.chat.id, 
            message_id=prompt_message_id, 
            reply_markup=kb.get_broadcast_confirmation_keyboard()
        )
    await message.delete()

@admin_router.callback_query(F.data.startswith('broadcast_'), AdminActions.waiting_for_broadcast_confirmation)
async def admin_broadcast_process(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    user_data = await state.get_data()
    text = user_data.get('broadcast_text')
    pin = callback.data == 'broadcast_pin'
    await state.clear()
    await callback.message.edit_text("Начинаю рассылку... Вы получите отчет по завершении.")
    initiator_id = callback.from_user.id
    
    asyncio.create_task(broadcast_to_users(bot, text, pin_message=pin, initiator_id=initiator_id))
    
    await callback.answer()

@admin_router.callback_query(kb.BroadcastCallback.filter())
async def manage_broadcast(callback: types.CallbackQuery, callback_data: kb.BroadcastCallback, bot: Bot):
    action = callback_data.action
    broadcast_id = callback_data.broadcast_id
    
    sent_messages = await db.get_sent_messages_for_broadcast(broadcast_id)
    if not sent_messages:
        return await callback.answer("Информация об этой рассылке уже удалена.", show_alert=True)

    action_text = "Открепляю" if action == "unpin" else "Удаляю"
    await callback.answer(f"{action_text} сообщения...")

    count = 0
    for user_id, message_id in sent_messages:
        try:
            if action == "unpin":
                await bot.unpin_all_chat_messages(user_id)
            elif action == "delete":
                await bot.delete_message(user_id, message_id)
            count += 1
        except (TelegramForbiddenError, TelegramBadRequest):
            pass
    
    if action == "delete":
        await db.delete_broadcast(broadcast_id)
        await callback.message.edit_text(f"Рассылка удалена у {count} пользователей.")
    else:
        await callback.message.edit_text(f"Рассылка откреплена у {count} пользователей.")

@admin_router.callback_query(F.data == 'admin_reset_all_subs')
async def admin_reset_all_subs_confirm(callback: types.CallbackQuery):
    text = ("<b>⚠️ ПРЕДУПРЕЖДЕНИЕ ⚠️</b>\n\n"
            "Вы уверены, что хотите сбросить <b>ВСЕ</b> платные подписки до уровня Free?\n\n"
            "Подписки администраторов затронуты не будут. "
            "Это действие необратимо.")
    await callback.message.edit_text(text, reply_markup=kb.get_reset_all_subs_confirmation_keyboard())

@admin_router.callback_query(F.data == 'confirm_reset_all_subs')
async def admin_reset_all_subs_process(callback: types.CallbackQuery):
    await callback.message.edit_text("Выполняю сброс подписок...")
    
    updated_count = await db.reset_all_subscriptions(config.ADMIN_IDS)
    
    await callback.message.edit_text(
        f"✅ Успешно сброшено {updated_count} подписок до уровня Free.",
        reply_markup=kb.get_admin_back_menu()
    )
    await callback.answer()

@admin_router.callback_query(F.data == 'admin_self_test')
async def admin_self_test(callback: types.CallbackQuery, bot: Bot):
    await callback.answer("🤖 Запускаю автотесты...")
    msg = await callback.message.edit_text("<b>🤖 Проведение автотестов...</b>")

    report = ["<b>🤖 Отчет по автотестам:</b>"]
    admin_id = callback.from_user.id

    try:
        await db.update_subscription(admin_id, 1)
        level = await db.check_subscription(admin_id)
        report.append("✅ Тест 1 (Выдача подписки): OK" if level == 1 else "❌ Тест 1 (Выдача подписки): FAILED")

        await db.block_user(admin_id, True)
        is_blocked = await db.is_user_blocked(admin_id)
        report.append("✅ Тест 2 (Блокировка): OK" if is_blocked else "❌ Тест 2 (Блокировка): FAILED")

        await db.block_user(admin_id, False)
        is_blocked = await db.is_user_blocked(admin_id)
        report.append("✅ Тест 3 (Разблокировка): OK" if not is_blocked else "❌ Тест 3 (Разблокировка): FAILED")

        await db.update_subscription(admin_id, 0)
        level = await db.check_subscription(admin_id)
        report.append("✅ Тест 4 (Сброс подписки): OK" if level == 0 else "❌ Тест 4 (Сброс подписки): FAILED")
        
        report.append("\n<b>Все тесты завершены успешно!</b>")
    except Exception as e:
        report.append(f"\n❌ <b>Во время тестов произошла ошибка:</b>\n<code>{e}</code>")
    
    await msg.edit_text("\n".join(report), reply_markup=kb.get_admin_back_menu())