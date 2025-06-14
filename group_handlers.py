# handlers/group_handlers.py
import aiohttp
from aiogram import Router, types, F, Bot
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import config
from database import Database
from utils import send_long_message
from .utils import execute_chat_request

group_router = Router()

group_router.message.filter(F.chat.type.in_({'group', 'supergroup'}))

@group_router.message(Command('start', 'new'))
async def group_start_redirect(message: types.Message, bot: Bot, user_level: int):
    if user_level == 0:
        await message.reply(
            "Взаимодействие с ботом в группах доступно только для пользователей с подпиской. "
            "Пожалуйста, оформите подписку в личном чате с ботом."
        )
        return

    bot_info = await bot.get_me()
    bot_username = bot_info.username
    url = f"https://t.me/{bot_username}?start=1"
    
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
async def handle_group_trigger(message: types.Message, bot: Bot, db: Database, user_level: int):
    if user_level == 0:
        await message.reply(
            "К сожалению, общение в группах доступно только для пользователей с платной подпиской (Standard или Premium). "
            "Вы можете оформить ее в личном чате с ботом."
        )
        return

    try:
        _, prompt = message.text.split(maxsplit=1)
    except ValueError:
        await message.reply(f"Пожалуйста, укажите ваш вопрос после триггера `{config.GROUP_TRIGGER}`.")
        return
        
    user_id = message.from_user.id
    model_name = await db.get_last_selected_model(user_id) or config.DEFAULT_GROUP_MODEL
    notification = ""
    if not await db.get_last_selected_model(user_id):
        notification = f"Вы еще не выбирали модель в личном чате. Использую модель по умолчанию: `{model_name}`\n\n"
    
    msg = await message.reply("🧠 Думаю...")

    # В группах нет истории и персональных настроек, используем дефолтные
    payload = {
        'model': model_name,
        'messages': [{'role': 'user', 'content': prompt}],
        'temperature': config.DEFAULT_TEMPERATURE
    }

    async with aiohttp.ClientSession() as session:
        answer_text, api_error = await execute_chat_request(session, payload)

    await msg.delete()

    if answer_text:
        if user_id not in config.ADMIN_IDS:
            await db.add_request(user_id, model_name)
        
        final_text = f"{notification}<b>Модель: {model_name}</b>\n\n{answer_text}"
        await send_long_message(bot, message.chat.id, final_text)
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