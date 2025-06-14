# handlers/group_handlers.py
# import aiohttp # Removed
from aiogram import Router, types, F, Bot
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import config
# from database import Database # db accessed via bot["db"]
from utils import send_long_message # Changed from api_helpers to utils
# from api_helpers import execute_chat_request # Removed, using APIService

group_router = Router()

group_router.message.filter(F.chat.type.in_({'group', 'supergroup'}))

@group_router.message(Command('start', 'new'))
async def group_start_redirect(message: types.Message, bot: Bot, user_level: int): # user_level from middleware
    if user_level == 0:
        await message.reply(
            "Взаимодействие с ботом в группах доступно только для пользователей с подпиской. "
            "Пожалуйста, оформите подписку в личном чате с ботом."
        )
        return

    bot_info = await bot.get_me()
    bot_username = bot_info.username
    url = f"https://t.me/{bot_username}?start=group_interaction" # Added a payload for context if needed

    text = (
        "Для использования меню и персональных команд, пожалуйста, "
        "перейдите в личный чат со мной. В группах я отвечаю только на запросы "
        f"через триггер `{config.GROUP_TRIGGER}`."
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Перейти в личный чат", url=url)]
    ])

    await message.reply(text, reply_markup=keyboard)


@group_router.message(F.text.startswith(config.GROUP_TRIGGER))
async def handle_group_trigger(message: types.Message, bot: Bot, user_level: int): # user_level from middleware
    db = bot["db"] # Get db from bot context
    api_service = bot["api_service"] # Get APIService from bot context

    if user_level == 0:
        await message.reply(
            "К сожалению, общение в группах доступно только для пользователей с платной подпиской (Standard или Premium). "
            "Вы можете оформить ее в личном чате с ботом."
        )
        return

    try:
        # Ensure GROUP_TRIGGER is a string and then split
        trigger_command = str(config.GROUP_TRIGGER)
        if not message.text.startswith(trigger_command): # Should not happen due to filter, but defensive
             return
        prompt = message.text[len(trigger_command):].lstrip() # Get text after trigger
        if not prompt: # Check if prompt is empty after stripping trigger and spaces
            await message.reply(f"Пожалуйста, укажите ваш вопрос после триггера `{trigger_command}`.")
            return
    except ValueError: # Should not happen with lstrip and check
        await message.reply(f"Пожалуйста, укажите ваш вопрос после триггера `{trigger_command}`.")
        return

    user_id = message.from_user.id
    # Use db from bot context
    last_selected_model = await db.get_last_selected_model(user_id)
    model_name = last_selected_model or config.DEFAULT_GROUP_MODEL

    notification = ""
    if not last_selected_model: # Check if a model was explicitly selected by user before
        notification = f"Вы еще не выбирали модель в личном чате. Использую модель по умолчанию: `{model_name}`\n\n"

    msg = await message.reply("🧠 Думаю...")

    # Payload for APIService
    messages_payload = [{'role': 'user', 'content': prompt}]

    # Call APIService's chat_completion method
    answer_text, api_error = await api_service.chat_completion(
        model=model_name,
        messages=messages_payload,
        temperature=config.DEFAULT_TEMPERATURE
        # max_tokens can be added if needed by APIService
    )

    await msg.delete()

    if answer_text:
        if user_id not in config.ADMIN_IDS: # Use db from bot context
            await db.add_request(user_id, model_name)

        final_text = f"{notification}<b>Модель: {model_name}</b>\n\n{answer_text}"
        # Use send_long_message from utils
        await send_long_message(bot, message.chat.id, final_text, reply_to_message_id=message.message_id)
    else:
        error_text = f"❌ Ошибка для админа: {api_error}" if user_id in config.ADMIN_IDS else "❌ Произошла непредвиденная ошибка. Попробуйте позже."
        await message.reply(error_text)


@group_router.message(Command('help'))
async def group_help(message: types.Message):
    text = (
        f"Я отвечаю на запросы по триггеру `{config.GROUP_TRIGGER}`.\n\n"
        "Для просмотра всех команд, смены модели или настроек, "
        "пожалуйста, напишите мне в личном чате."
    )
    await message.reply(text)
