# user_handlers_private/misc.py
from aiogram import Router, types, F, Bot
from aiogram.filters import StateFilter

import config # For LIMITS and SUBSCRIPTION_MODELS if needed for help_menu
import keyboards as kb

misc_router = Router(name="user_misc")

# Note: Global private chat filter (F.chat.type == 'private') is applied in user_handlers_private/__init__.py

@misc_router.callback_query(F.data == 'menu_help')
async def help_menu(callback: types.CallbackQuery, bot: Bot): # Added bot for potential future use
    # user_service = bot["user_service"] # Not strictly needed here unless fetching dynamic info
    text = (
        '<b>Доступные команды:</b>\n'
        '/start - главное меню\n'
        '/new - начать новый диалог (очистить контекст)\n\n'
        '<b>Планы подписки:</b>\n'
    )
    # Iterate through defined subscription models in config to display limits
    for sub_key, sub_details in config.SUBSCRIPTION_MODELS.items():
        level = sub_details.get('level') # Assuming 'level' key exists in sub_details
        limit_for_level = config.LIMITS.get(level, "N/A") # Get limit based on level

        limit_text = "N/A"
        if limit_for_level == float('inf'):
            limit_text = "Безлимит"
        elif limit_for_level != "N/A":
            limit_text = f"{int(limit_for_level)} запросов/день"

        text += f"<b>{sub_details['name']}:</b> {limit_text}\n"

    await callback.message.edit_text(text, reply_markup=kb.get_back_to_main_menu()) # Assuming kb.get_back_to_main_menu exists
    await callback.answer()

@misc_router.message(F.text, StateFilter(None)) # Handles any text when no specific state is active
async def handle_text_outside_chat(message: types.Message):
    # This handler catches messages that are not commands and are sent when the user is not in a specific chat state.
    # It's a fallback for general text input in private chat.
    await message.answer(
        "Для начала работы выберите команду /start или воспользуйтесь меню. "
        "Если вы хотите пообщаться с AI, выберите модель в меню 'Модели / Чат'."
    )
