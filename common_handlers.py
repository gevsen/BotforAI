# handlers/common_handlers.py
import asyncio
from aiogram import Router, types, F, Bot
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from datetime import datetime, timezone, timedelta

import keyboards as kb
from database import Database
import config
from .user_handlers import get_user_level

common_router = Router()
db = Database(config.DATABASE_PATH)

async def notify_admins_new_user(bot: Bot, user: types.User):
    """Отправляет уведомление о новом пользователе всем администраторам."""
    user_link = f'<a href="tg://user?id={user.id}">{user.full_name}</a>'
    text = (f"🎉 <b>Новый пользователь!</b>\n\n"
            f"Пользователь: {user_link}\n"
            f"ID: <code>{user.id}</code>\n"
            f"Username: @{user.username if user.username else 'Отсутствует'}")
    
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text)
        except Exception:
            # Можно добавить логирование ошибки, если нужно
            pass

@common_router.message(Command('start'), StateFilter("*"), F.chat.type == 'private')
@common_router.callback_query(F.data == 'back_main', StateFilter("*"))
async def universal_start_handler(event: types.Message | types.CallbackQuery, state: FSMContext, bot: Bot, model_status_cache: dict):
    if await state.get_state() is not None:
        await state.clear()
        message_source = event.message if isinstance(event, types.CallbackQuery) else event
        await message_source.answer("Действие отменено.")

    user = event.from_user
    is_new_user = await db.add_user(user.id, user.username)

    if is_new_user and user.id not in config.ADMIN_IDS:
        # <<< ИЗМЕНЕНИЕ ЗДЕСЬ: ЗАПУСК В ФОНОВОМ РЕЖИМЕ >>>
        asyncio.create_task(notify_admins_new_user(bot, user))
    
    welcome_text = f'Привет, я Arima.AI\n\nТекущее время: {datetime.now(timezone(timedelta(hours=3))).strftime("%H:%M МСК")}\n\nВыберите действие:'
    reply_markup = kb.get_main_menu(user.id, model_status_cache)

    if isinstance(event, types.CallbackQuery):
        try:
            await event.message.edit_text(welcome_text, reply_markup=reply_markup)
        except:
            # Если сообщение не изменилось, просто отвечаем новым
            await event.message.answer(welcome_text, reply_markup=reply_markup)
    else:
        await event.answer(welcome_text, reply_markup=reply_markup)
    
    if isinstance(event, types.CallbackQuery):
        await event.answer()

@common_router.callback_query(F.data == 'cancel_action', StateFilter("*"))
async def cancel_handler(callback: types.CallbackQuery, state: FSMContext, bot: Bot, model_status_cache: dict):
    current_state = await state.get_state()
    await state.clear()
    await callback.message.edit_text("Действие отменено.")
    await callback.answer()
    
    # После отмены возвращаем пользователя в соответствующее меню
    if current_state and current_state.startswith("AdminActions"):
        await callback.message.answer("Админ-панель:", reply_markup=kb.get_admin_menu())
    else:
        await universal_start_handler(callback, state, bot, model_status_cache)