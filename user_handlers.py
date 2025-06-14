# handlers/user_handlers.py
import asyncio
import aiohttp
import time
from datetime import datetime
from aiogram import Router, types, F, Bot
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from openai import OpenAI

import config
import keyboards as kb
from database import Database
from keyboards import SubDetailCallback
from states import ImageGeneration, UserSettings, Chatting
from utils import send_long_message
from .utils import get_user_level, get_user_limit, prepare_api_payload, execute_chat_request

user_router = Router()

user_router.message.filter(F.chat.type == 'private')

# --- Обработчики генерации изображений ---

@user_router.callback_query(F.data == 'menu_image_gen')
async def image_gen_start(callback: types.CallbackQuery, state: FSMContext, model_status_cache: dict, user_level: int):
    if config.IMAGE_MODEL in model_status_cache and not model_status_cache[config.IMAGE_MODEL]:
        await callback.answer("⚠️ Эта функция временно недоступна.", show_alert=True)
        return

    if user_level == 0:
        await callback.answer("⚠️ Эта функция доступна только для платных подписчиков.", show_alert=True)
        return

    await state.set_state(ImageGeneration.waiting_for_prompt)
    await callback.message.edit_text(
        "Отправьте ваш запрос (промпт) для генерации изображения.",
        reply_markup=kb.get_cancel_keyboard()
    )
    await callback.answer()

@user_router.message(ImageGeneration.waiting_for_prompt, F.text)
async def process_image_prompt(message: types.Message, state: FSMContext, bot: Bot, db: Database):
    await state.clear()
    prompt = message.text
    msg = await message.answer("🎨 Создаю шедевр... Это может занять до минуты.")

    client = OpenAI(base_url=config.IMAGE_API_URL, api_key=config.API_KEY)
    try:
        response = client.images.generate(
            model=config.IMAGE_MODEL, prompt=prompt, size="1024x1024", quality="standard", n=1
        )
        image_url = response.data[0].url
        await bot.send_photo(chat_id=message.chat.id, photo=image_url, caption=f"✅ Ваш шедевр по запросу: `{prompt}`")
        await msg.delete()
        if message.from_user.id not in config.ADMIN_IDS:
            await db.add_request(message.from_user.id, config.IMAGE_MODEL)
    except Exception as e:
        error_text = f"❌ Ошибка для админа: {e}" if message.from_user.id in config.ADMIN_IDS else "❌ Произошла ошибка. Попробуйте изменить запрос или обратитесь в поддержку."
        await msg.edit_text(error_text)

# --- Обработчики выбора модели и чата ---

@user_router.callback_query(F.data == 'menu_models')
async def models_categories_menu(callback: types.CallbackQuery, state: FSMContext, user_level: int):
    await state.clear()
    await callback.message.edit_text('Выберите категорию:', reply_markup=kb.get_models_categories_menu(user_level))

@user_router.callback_query(F.data.startswith('cat_'))
async def category_models_menu(callback: types.CallbackQuery, model_status_cache: dict, user_level: int):
    category = callback.data.split('_', 1)[1]
    disabled_models = {model for model, status in model_status_cache.items() if not status}
    await callback.message.edit_text(f'Модели {category}:', reply_markup=kb.get_category_models_menu(category, user_level, disabled_models))

@user_router.callback_query(kb.ModelCallback.filter())
async def select_model(callback: types.CallbackQuery, callback_data: kb.ModelCallback, state: FSMContext, model_status_cache: dict, db: Database):
    model = callback_data.model_name
    if model in model_status_cache and not model_status_cache[model]:
        await callback.answer("⚠️ Эта модель временно недоступна.", show_alert=True)
        return
            
    await state.set_state(Chatting.in_chat)
    await state.update_data(model=model, chat_history=[])
    await db.update_last_selected_model(callback.from_user.id, model)
    
    await callback.message.answer(f'<b>Модель: {model}</b>\nОтправьте ваш запрос. Для сброса контекста используйте /new.')
    await callback.answer()

@user_router.message(Command('new'), StateFilter(Chatting.in_chat))
async def new_chat_handler(message: types.Message, state: FSMContext):
    await state.update_data(chat_history=[])
    await message.answer("Контекст диалога очищен. Можете задавать новый вопрос.")

@user_router.callback_query(F.data == 'chat_new', StateFilter(Chatting.in_chat))
async def new_chat_callback(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(chat_history=[])
    await callback.answer("Контекст диалога очищен.")
    await callback.message.answer("Контекст диалога очищен. Можете задавать новый вопрос.")

@user_router.message(F.text, StateFilter(Chatting.in_chat))
async def handle_chat(message: types.Message, state: FSMContext, bot: Bot, db: Database):
    user_id = message.from_user.id
    msg = await message.answer('🧠 Думаю...')
    start_time = time.monotonic()

    user_data = await state.get_data()
    model = user_data.get('model')
    payload = await prepare_api_payload(db, user_id, message.text, model, state)
    
    async with aiohttp.ClientSession() as session:
        answer_text, api_error = await execute_chat_request(session, payload)
    
    await msg.delete()

    if answer_text:
        end_time = time.monotonic()
        duration = round(end_time - start_time, 2)
        
        final_text = f"{answer_text}\n\n<b>Модель: {payload['model']} | Время: {duration} сек.</b>"
        
        await send_long_message(bot, user_id, final_text, reply_markup=kb.get_chat_menu())

        if user_id not in config.ADMIN_IDS:
            await db.add_request(user_id, payload['model'])
        
        new_history = payload['messages']
        new_history.append({'role': 'assistant', 'content': answer_text})
        await state.update_data(chat_history=new_history[-config.CHAT_HISTORY_MAX_LEN:])
    else:
        error_text = f"❌ Ошибка для админа: {api_error}" if user_id in config.ADMIN_IDS else "❌ Произошла непредвиденная ошибка. Попробуйте позже или обратитесь в поддержку."
        await message.answer(error_text, reply_markup=kb.get_chat_menu())

@user_router.message(F.text, StateFilter(None))
async def handle_text_outside_chat(message: types.Message):
    await message.answer("Для начала работы выберите команду /start или воспользуйтесь меню.")

# --- Обработчики настроек ---

@user_router.callback_query(F.data == 'menu_settings')
async def menu_settings(callback: types.CallbackQuery, db: Database):
    settings = await db.get_user_settings(callback.from_user.id)
    prompt, temp = settings if settings else (None, None)
    
    prompt_text = prompt or config.DEFAULT_SYSTEM_PROMPT
    temp_val = temp or config.DEFAULT_TEMPERATURE

    text = (
        "<b>Ваши текущие настройки:</b>\n\n"
        f"<b>🌡️ Температура:</b> {temp_val}\n\n"
        f"<b>📝 Системный промпт:</b>\n"
        f"<i>{prompt_text}</i>"
    )
    await callback.message.edit_text(text, reply_markup=kb.get_user_settings_menu({'temp': temp_val}))

@user_router.callback_query(F.data == "settings_prompt")
async def settings_prompt_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(UserSettings.waiting_for_prompt)
    await callback.message.edit_text("Отправьте новый системный промпт (инструкцию для AI).", reply_markup=kb.get_cancel_keyboard())

@user_router.message(UserSettings.waiting_for_prompt, F.text)
async def settings_prompt_process(message: types.Message, state: FSMContext, bot: Bot, db: Database, model_status_cache: dict):
    from .common_handlers import universal_start_handler
    await db.update_user_settings(message.from_user.id, prompt=message.text)
    await state.clear()
    await message.answer("✅ Системный промпт обновлен!")
    await universal_start_handler(message, state, bot, model_status_cache)

@user_router.callback_query(F.data == "settings_temp")
async def settings_temp_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(UserSettings.waiting_for_temperature)
    await callback.message.edit_text("Отправьте новое значение температуры (число от 0.0 до 2.0).", reply_markup=kb.get_cancel_keyboard())

@user_router.message(UserSettings.waiting_for_temperature, F.text)
async def settings_temp_process(message: types.Message, state: FSMContext, bot: Bot, db: Database, model_status_cache: dict):
    from .common_handlers import universal_start_handler
    try:
        temp = float(message.text.replace(',', '.'))
        if not 0.0 <= temp <= 2.0:
            raise ValueError
        await db.update_user_settings(message.from_user.id, temp=temp)
        await state.clear()
        await message.answer(f"✅ Температура установлена на {temp}!")
        await universal_start_handler(message, state, bot, model_status_cache)
    except ValueError:
        await message.answer("❌ Неверный формат. Пожалуйста, введите число от 0.0 до 2.0.")

# --- Обработчики подписки и помощи ---

@user_router.callback_query(F.data == 'menu_subscription')
async def subscription_menu(callback: types.CallbackQuery, db: Database, user_level: int):
    user_id = callback.from_user.id
    if user_id in config.ADMIN_IDS:
        await callback.message.edit_text('У вас максимальный доступ (Premium) как у администратора.', reply_markup=kb.get_back_to_main_menu())
        await callback.answer()
        return

    sub_name = config.SUB_LEVEL_MAP.get(user_level, 'free')
    sub_info = config.SUBSCRIPTION_MODELS[sub_name]
    
    requests_today = await db.get_user_requests_today(user_id)
    limit = await get_user_limit(db, user_id)
    
    sub_end_text = ""
    subscription_end = await db.get_subscription_end(user_id)
    if subscription_end and user_level > 0:
        remaining = subscription_end - datetime.now()
        if remaining.days >= 0:
            sub_end_text = f'<b>Подписка до:</b> {subscription_end.strftime("%d.%m.%Y")}\n'

    text = (
        f"<b>Ваш текущий план:</b> {sub_info['name']}\n"
        f"<b>Использовано запросов:</b> {requests_today}/{'Безлимит' if limit == float('inf') else limit}\n"
        f"{sub_end_text}\n"
        f"<b>Описание:</b>\n{sub_info['description']}\n\n"
        "Для просмотра деталей и покупки выберите один из планов ниже:"
    )
    await callback.message.edit_text(text, reply_markup=kb.get_subscription_menu())
    await callback.answer()

@user_router.callback_query(SubDetailCallback.filter())
async def show_subscription_details(callback: types.CallbackQuery, callback_data: SubDetailCallback):
    level = callback_data.level
    sub_name = config.SUB_LEVEL_MAP.get(level)
    if not sub_name:
        await callback.answer("Неизвестный уровень подписки.", show_alert=True)
        return
        
    sub_info = config.SUBSCRIPTION_MODELS[sub_name]

    text = (
        f"<b>Подписка: {sub_info['name']} ({sub_info['price']}₽)</b>\n\n"
        f"{sub_info['description']}\n\n"
        "<b>Доступные модели:</b>"
    )

    available_models = set(sub_info['models'])
    
    for provider, models_in_provider in config.ALL_MODELS.items():
        included_models = [model for model in models_in_provider if model in available_models]
        if included_models:
            text += f"\n\n<b>{provider}</b>\n"
            text += " • " + "\n • ".join(included_models)
    
    reply_markup = kb.get_subscription_details_keyboard(level)
    
    await callback.message.edit_text(text, reply_markup=reply_markup)
    await callback.answer()

@user_router.callback_query(F.data == 'menu_help')
async def help_menu(callback: types.CallbackQuery):
    text = (
        '<b>Доступные команды:</b>\n'
        '/start - главное меню\n'
        '/new - начать новый диалог (очистить контекст)\n\n'
        '<b>Планы подписки:</b>\n'
    )
    for sub_info in config.SUBSCRIPTION_MODELS.values():
        limit = config.LIMITS[sub_info['level']]
        text += f"<b>{sub_info['name']}:</b> {limit} запросов/день\n"
        
    await callback.message.edit_text(text, reply_markup=kb.get_back_to_main_menu())

@user_router.callback_query(F.data.startswith('buy_'))
async def buy_subscription(callback: types.CallbackQuery):
    level = int(callback.data.split('_')[1])
    sub_name = config.SUB_LEVEL_MAP.get(level, 'free')
    sub_info = config.SUBSCRIPTION_MODELS[sub_name]
    
    text = (
        f"Для покупки подписки <b>{sub_info['name']} ({sub_info['price']}₽)</b> свяжитесь с администратором: @{config.PAYMENT_USERNAME}\n\n"
        "Пожалуйста, отправьте ему следующее сообщение:"
    )
    
    request_text = f"Здравствуйте, хочу приобрести подписку {sub_info['name']}. Мой Telegram ID: {callback.from_user.id}"
    
    await callback.message.edit_text(
        f"{text}\n\n<code>{request_text}</code>",
        reply_markup=kb.get_back_to_main_menu()
    )
    await callback.answer()