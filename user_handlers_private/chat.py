# user_handlers_private/chat.py
import time
from aiogram import Router, types, F, Bot
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext # Ensure this is imported

import config # Ensure this is imported
import keyboards as kb
from states import Chatting
from utils import send_long_message
# from api_helpers import prepare_api_payload # Removed this import

chat_router = Router(name="user_chat")

# Note: Global private chat filter (F.chat.type == 'private') is applied in user_handlers_private/__init__.py


# --- Definition of prepare_api_payload moved here ---
async def prepare_api_payload(
    user_settings_tuple: tuple | None,
    system_prompt_default: str,
    temperature_default: float,
    user_id: int,
    user_text: str,
    model: str,
    state: FSMContext
) -> dict:
    """Готовит данные для запроса к API, включая историю и настройки."""
    system_prompt = system_prompt_default
    temperature = temperature_default

    if user_settings_tuple:
        if user_settings_tuple[0] is not None:
            system_prompt = user_settings_tuple[0]
        if user_settings_tuple[1] is not None:
            temperature = user_settings_tuple[1]

    user_data = await state.get_data()
    history = user_data.get("chat_history", [])

    current_messages = []
    if not history or history[0].get("role") != "system":
        current_messages.append({"role": "system", "content": system_prompt})
        current_messages.extend([msg for msg in history if msg.get("role") != "system"])
    else:
        if history[0]["content"] != system_prompt:
            history[0]["content"] = system_prompt
        current_messages.extend(history)

    if not current_messages or current_messages[-1].get("role") != "user" or current_messages[-1].get("content") != user_text:
        current_messages.append({"role": "user", "content": user_text})

    if len(current_messages) > (config.CHAT_HISTORY_MAX_LEN + 1):
        final_history = [current_messages[0]] + current_messages[-(config.CHAT_HISTORY_MAX_LEN):]
    else:
        final_history = current_messages

    await state.update_data(chat_history=final_history)

    return {
        "model": model,
        "messages": final_history,
        "temperature": temperature
    }

# --- Обработчики выбора модели и чата ---

@chat_router.callback_query(F.data == 'menu_models')
async def models_categories_menu(callback: types.CallbackQuery, state: FSMContext, user_level: int):
    await state.clear()
    await callback.message.edit_text('Выберите категорию:', reply_markup=kb.get_models_categories_menu(user_level))
    await callback.answer()

@chat_router.callback_query(F.data.startswith('cat_'))
async def category_models_menu(callback: types.CallbackQuery, bot: Bot, user_level: int):
    model_status_cache = bot["model_status_cache"]
    category = callback.data.split('_', 1)[1]
    disabled_models = {model for model, status in model_status_cache.items() if not status}
    await callback.message.edit_text(f'Модели {category}:', reply_markup=kb.get_category_models_menu(category, user_level, disabled_models))
    await callback.answer()

@chat_router.callback_query(kb.ModelCallback.filter())
async def select_model(callback: types.CallbackQuery, callback_data: kb.ModelCallback, state: FSMContext, bot: Bot):
    model_status_cache = bot["model_status_cache"]
    db = bot["db"]
    model = callback_data.model_name

    if model in model_status_cache and not model_status_cache[model]:
        await callback.answer("⚠️ Эта модель временно недоступна.", show_alert=True)
        return

    await state.set_state(Chatting.in_chat)
    await state.update_data(model=model, chat_history=[])
    await db.update_last_selected_model(callback.from_user.id, model)

    await callback.message.answer(f'<b>Модель: {model}</b>\nОтправьте ваш запрос. Для сброса контекста используйте /new или соответствующую кнопку.')
    await callback.answer()

@chat_router.message(Command('new'), StateFilter(Chatting.in_chat))
async def new_chat_handler(message: types.Message, state: FSMContext):
    await state.update_data(chat_history=[])
    await message.answer("Контекст диалога очищен. Можете задавать новый вопрос.")

@chat_router.callback_query(F.data == 'chat_new', StateFilter(Chatting.in_chat))
async def new_chat_callback(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(chat_history=[])
    await callback.answer("Контекст диалога очищен.")
    await callback.message.answer("Контекст диалога очищен. Можете задавать новый вопрос.")


@chat_router.message(F.text, StateFilter(Chatting.in_chat))
async def handle_chat(message: types.Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    msg = await message.answer('🧠 Думаю...')
    start_time = time.monotonic()

    user_service = bot["user_service"]
    api_service = bot["api_service"]
    db = bot["db"]

    user_data = await state.get_data()
    model_name = user_data.get('model')

    if not model_name:
        await msg.edit_text("Произошла ошибка: модель не выбрана. Пожалуйста, выберите модель снова.")
        await state.clear()
        return

    user_settings_tuple = await user_service.get_user_settings(user_id)

    # prepare_api_payload is now a local function in this module
    payload = await prepare_api_payload(
        user_settings_tuple=user_settings_tuple,
        system_prompt_default=config.DEFAULT_SYSTEM_PROMPT,
        temperature_default=config.DEFAULT_TEMPERATURE,
        user_id=user_id,
        user_text=message.text,
        model=model_name,
        state=state
    )

    answer_text, api_error = await api_service.chat_completion(
        model=payload['model'],
        messages=payload['messages'],
        temperature=payload['temperature']
    )

    await msg.delete()

    if answer_text:
        end_time = time.monotonic()
        duration = round(end_time - start_time, 2)

        # Add assistant's response to history for the next turn
        current_history = payload['messages'] # This history already includes current user's message
        current_history.append({'role': 'assistant', 'content': answer_text})
        # Trim again if necessary (though prepare_api_payload does one trim)
        if len(current_history) > (config.CHAT_HISTORY_MAX_LEN + 1 if current_history[0]['role'] == 'system' else config.CHAT_HISTORY_MAX_LEN):
            if current_history[0]['role'] == 'system':
                 current_history = [current_history[0]] + current_history[-(config.CHAT_HISTORY_MAX_LEN):]
            else: # Should not happen if prepare_api_payload ensures system prompt
                 current_history = current_history[-config.CHAT_HISTORY_MAX_LEN:]
        await state.update_data(chat_history=current_history)


        final_text = f"{answer_text}\n\n<b>Модель: {payload['model']} | Время: {duration} сек.</b>"
        await send_long_message(bot, user_id, final_text, reply_markup=kb.get_chat_menu())

        if user_id not in config.ADMIN_IDS:
            await db.add_request(user_id, payload['model'])

    else:
        error_text = f"❌ Ошибка для админа: {api_error}" if user_id in config.ADMIN_IDS else "❌ Произошла непредвиденная ошибка. Попробуйте позже или обратитесь в поддержку."
        await message.answer(error_text, reply_markup=kb.get_chat_menu())
