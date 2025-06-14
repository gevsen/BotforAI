# user_handlers_private/subscription.py
from datetime import datetime
from aiogram import Router, types, F, Bot

import config
import keyboards as kb
from keyboards import SubDetailCallback # Assuming this is for subscription detail callbacks

subscription_router = Router(name="user_subscription")

# Note: Global private chat filter (F.chat.type == 'private') is applied in user_handlers_private/__init__.py

# --- Обработчики подписки ---

@subscription_router.callback_query(F.data == 'menu_subscription')
async def subscription_menu(callback: types.CallbackQuery, bot: Bot, user_level: int, limit: int | float): # user_level & limit from middleware
    user_id = callback.from_user.id
    db = bot["db"]
    # user_service = bot["user_service"] # Not strictly needed if limit is passed by middleware

    if user_id in config.ADMIN_IDS:
        await callback.message.edit_text(
            'У вас максимальный доступ (Premium) как у администратора.',
            reply_markup=kb.get_back_to_main_menu() # Assuming this keyboard exists
        )
        await callback.answer()
        return

    sub_name_key = config.SUB_LEVEL_MAP.get(user_level, 'free') # 'free' is a fallback key
    sub_info = config.SUBSCRIPTION_MODELS.get(sub_name_key, config.SUBSCRIPTION_MODELS['free']) # Fallback to free model info

    requests_today = await db.get_user_requests_today(user_id)
    # limit is passed directly from middleware

    sub_end_text = ""
    # get_subscription_end might not exist or might be part of a user object from db.get_user_info
    # For now, assuming db.get_subscription_end(user_id) exists and returns a datetime object or None.
    subscription_end_date = await db.get_subscription_end(user_id)
    if subscription_end_date and user_level > 0: # Only show for actual subscriptions
        if isinstance(subscription_end_date, datetime):
            now = datetime.now()
            # Ensure timezones are handled correctly if one is aware and other is naive.
            # If subscription_end_date is timezone-aware, make 'now' timezone-aware (e.g. UTC).
            if subscription_end_date.tzinfo:
                now = datetime.now(subscription_end_date.tzinfo)

            remaining_days = (subscription_end_date - now).days
            if remaining_days >= 0:
                sub_end_text = f'<b>Подписка до:</b> {subscription_end_date.strftime("%d.%m.%Y")}\n'
            else:
                sub_end_text = f'<b>Подписка истекла:</b> {subscription_end_date.strftime("%d.%m.%Y")}\n'

        else: # Fallback if it's not a datetime object (e.g. string)
            sub_end_text = f'<b>Подписка до:</b> {str(subscription_end_date)}\n'


    text = (
        f"<b>Ваш текущий план:</b> {sub_info['name']}\n"
        f"<b>Использовано запросов сегодня:</b> {requests_today}/{'Безлимит' if limit == float('inf') else int(limit)}\n"
        f"{sub_end_text}"
        f"<b>Описание:</b>\n{sub_info['description']}\n\n"
        "Для просмотра деталей и покупки выберите один из планов ниже:"
    )
    await callback.message.edit_text(text, reply_markup=kb.get_subscription_menu()) # Assuming kb.get_subscription_menu() exists
    await callback.answer()

@subscription_router.callback_query(SubDetailCallback.filter()) # Assuming SubDetailCallback is correctly defined
async def show_subscription_details(callback: types.CallbackQuery, callback_data: SubDetailCallback, bot: Bot): # Added bot for potential future use
    level = callback_data.level
    sub_name_key = config.SUB_LEVEL_MAP.get(level)
    if not sub_name_key:
        await callback.answer("Неизвестный уровень подписки.", show_alert=True)
        return

    sub_info = config.SUBSCRIPTION_MODELS.get(sub_name_key)
    if not sub_info: # Should not happen if SUB_LEVEL_MAP and SUBSCRIPTION_MODELS are consistent
        await callback.answer("Информация о подписке не найдена.", show_alert=True)
        return

    text = (
        f"<b>Подписка: {sub_info['name']} ({sub_info['price']}₽)</b>\n\n"
        f"{sub_info['description']}\n\n"
        "<b>Доступные модели:</b>"
    )

    available_models_for_level = set(sub_info['models'])

    # Assuming config.ALL_MODELS is a dict like {'ProviderName': ['model1', 'model2'], ...}
    for provider, models_in_provider_list in config.ALL_MODELS.items():
        included_models = [model for model in models_in_provider_list if model in available_models_for_level]
        if included_models:
            text += f"\n\n<b>{provider}</b>\n"
            text += " • " + "\n • ".join(included_models)

    reply_markup = kb.get_subscription_details_keyboard(level) # Assuming this keyboard exists

    await callback.message.edit_text(text, reply_markup=reply_markup)
    await callback.answer()

@subscription_router.callback_query(F.data.startswith('buy_'))
async def buy_subscription(callback: types.CallbackQuery, bot: Bot): # Added bot for potential future use
    try:
        level = int(callback.data.split('_')[1])
    except (ValueError, IndexError):
        await callback.answer("Ошибка при выборе подписки. Попробуйте снова.", show_alert=True)
        return

    sub_name_key = config.SUB_LEVEL_MAP.get(level)
    if not sub_name_key:
        await callback.answer("Неизвестный уровень подписки.", show_alert=True)
        return

    sub_info = config.SUBSCRIPTION_MODELS.get(sub_name_key)
    if not sub_info:
        await callback.answer("Информация о подписке не найдена.", show_alert=True)
        return

    text = (
        f"Для покупки подписки <b>{sub_info['name']} ({sub_info['price']}₽)</b> свяжитесь с администратором: @{config.PAYMENT_USERNAME}\n\n"
        "Пожалуйста, отправьте ему следующее сообщение (нажмите, чтобы скопировать):"
    )

    request_text = f"Здравствуйте, хочу приобрести подписку {sub_info['name']}. Мой Telegram ID: {callback.from_user.id}"

    # Using a simple message, as copy-to-clipboard needs client-side support or specific inline query setup.
    # message.reply with code block is a common way.
    await callback.message.edit_text(
        f"{text}\n\n<code>{request_text}</code>", # code block for easy copying
        reply_markup=kb.get_back_to_main_menu() # Assuming this keyboard exists
    )
    await callback.answer()
