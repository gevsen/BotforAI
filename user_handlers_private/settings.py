# user_handlers_private/settings.py
from aiogram import Router, types, F, Bot
from aiogram.fsm.context import FSMContext

import config
import keyboards as kb
from states import UserSettings

settings_router = Router(name="user_settings")

# Note: Global private chat filter (F.chat.type == 'private') is applied in user_handlers_private/__init__.py

# --- Обработчики настроек ---

@settings_router.callback_query(F.data == 'menu_settings')
async def menu_settings(callback: types.CallbackQuery, bot: Bot):
    user_service = bot["user_service"]
    settings = await user_service.get_user_settings(callback.from_user.id)
    prompt, temp = settings if settings else (None, None)

    prompt_text = prompt if prompt is not None else config.DEFAULT_SYSTEM_PROMPT # Handle None explicitly
    temp_val = temp if temp is not None else config.DEFAULT_TEMPERATURE # Handle None explicitly

    text = (
        "<b>Ваши текущие настройки:</b>\n\n"
        f"<b>🌡️ Температура:</b> {temp_val}\n\n"
        f"<b>📝 Системный промпт:</b>\n"
        f"<i>{prompt_text}</i>" # Make sure prompt_text is properly escaped if it can contain HTML special chars
                               # or use MarkdownV2 and escape. For HTML, aiogram usually handles it.
    )
    await callback.message.edit_text(text, reply_markup=kb.get_user_settings_menu({'temp': temp_val})) # Assuming get_user_settings_menu exists
    await callback.answer()


@settings_router.callback_query(F.data == "settings_prompt")
async def settings_prompt_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(UserSettings.waiting_for_prompt)
    await callback.message.edit_text("Отправьте новый системный промпт (инструкцию для AI). Для сброса на стандартный, отправьте `-`.", reply_markup=kb.get_cancel_keyboard())
    await callback.answer()

@settings_router.message(UserSettings.waiting_for_prompt, F.text)
async def settings_prompt_process(message: types.Message, state: FSMContext, bot: Bot):
    user_service = bot["user_service"]
    new_prompt = message.text

    if new_prompt == "-": # Command to reset to default
        await user_service.update_user_settings(message.from_user.id, prompt=config.DEFAULT_SYSTEM_PROMPT)
        await message.answer("✅ Системный промпт сброшен на стандартный!")
    else:
        await user_service.update_user_settings(message.from_user.id, prompt=new_prompt)
        await message.answer("✅ Системный промпт обновлен!")

    await state.clear()
    # Consider redirecting to main menu or settings menu.
    # For now, matching previous behavior of just sending confirmation.
    # from common_handlers import universal_start_handler # Avoid direct cross-imports if possible
    # A common pattern is to emit a custom event or use a shared utility function if needed.


@settings_router.callback_query(F.data == "settings_temp")
async def settings_temp_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(UserSettings.waiting_for_temperature)
    await callback.message.edit_text("Отправьте новое значение температуры (число от 0.0 до 2.0). Для сброса на стандартное, отправьте `-`.", reply_markup=kb.get_cancel_keyboard())
    await callback.answer()

@settings_router.message(UserSettings.waiting_for_temperature, F.text)
async def settings_temp_process(message: types.Message, state: FSMContext, bot: Bot):
    user_service = bot["user_service"]

    if message.text == "-":
        await user_service.update_user_settings(message.from_user.id, temp=config.DEFAULT_TEMPERATURE)
        await message.answer(f"✅ Температура сброшена на стандартное значение ({config.DEFAULT_TEMPERATURE})!")
    else:
        try:
            temp_val = float(message.text.replace(',', '.'))
            if not 0.0 <= temp_val <= 2.0:
                raise ValueError("Temperature must be between 0.0 and 2.0")
            await user_service.update_user_settings(message.from_user.id, temp=temp_val)
            await message.answer(f"✅ Температура установлена на {temp_val}!")
        except ValueError:
            await message.answer("❌ Неверный формат. Пожалуйста, введите число от 0.0 до 2.0, или `-` для сброса.")

    await state.clear()
    # See comment in settings_prompt_process about universal_start_handler
