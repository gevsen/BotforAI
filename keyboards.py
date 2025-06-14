# keyboards.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters.callback_data import CallbackData
import config

class ModelCallback(CallbackData, prefix="model"):
    model_name: str

class Paginator(CallbackData, prefix="pag"):
    action: str
    page: int

class BroadcastCallback(CallbackData, prefix="brd"):
    action: str
    broadcast_id: int

class SubDetailCallback(CallbackData, prefix="show_sub"):
    level: int

def get_main_menu(user_id: int, model_status_cache: dict) -> InlineKeyboardMarkup:
    is_image_model_disabled = config.IMAGE_MODEL in model_status_cache and not model_status_cache[config.IMAGE_MODEL]
    image_gen_text = "⚠️ Генерация изображений" if is_image_model_disabled else "🖼️ Генерация изображений"
    
    buttons = [
        [InlineKeyboardButton(text='💬 Выбрать модель', callback_data='menu_models')],
        [InlineKeyboardButton(text=image_gen_text, callback_data='menu_image_gen')],
        [InlineKeyboardButton(text='⭐ Подписка', callback_data='menu_subscription')],
        [InlineKeyboardButton(text='⚙️ Настройки', callback_data='menu_settings')],
        [InlineKeyboardButton(text='👨‍💻 Поддержка', url=f'https://t.me/{config.SUPPORT_USERNAME}')],
        [InlineKeyboardButton(text='❓ Помощь', callback_data='menu_help')]
    ]
    if user_id in config.ADMIN_IDS:
        buttons.insert(5, [InlineKeyboardButton(text='👑 Админ-панель', callback_data='menu_admin')])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='📊 Статистика', callback_data='admin_stats')],
        [InlineKeyboardButton(text='👥 Пользователи', callback_data='admin_users')],
        [InlineKeyboardButton(text='📢 Рассылка', callback_data='admin_broadcast')],
        [InlineKeyboardButton(text='🧪 Тест моделей', callback_data='admin_test')],
        [InlineKeyboardButton(text='🤖 Автотесты', callback_data='admin_self_test')],
        [InlineKeyboardButton(text='🔥 Сбросить все подписки', callback_data='admin_reset_all_subs')],
        [InlineKeyboardButton(text='↩️ Назад', callback_data='back_main')]
    ])

def get_admin_users_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='📋 Список пользователей', callback_data='admin_list_users_1')],
        [InlineKeyboardButton(text='🔍 Найти пользователя', callback_data='admin_search')],
        [InlineKeyboardButton(text='✅ Выдать подписку', callback_data='admin_grant')],
        [InlineKeyboardButton(text='💔 Забрать подписку', callback_data='admin_revoke')],
        [InlineKeyboardButton(text='🚫 Блокировка', callback_data='admin_block')],
        [InlineKeyboardButton(text='🟢 Разблокировка', callback_data='admin_unblock')],
        [InlineKeyboardButton(text='↩️ Назад', callback_data='admin_back')]
    ])

def get_paginated_users_keyboard(page: int, total_pages: int) -> InlineKeyboardMarkup:
    buttons = []
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton(text="◀️ Назад", callback_data=Paginator(action="prev", page=page).pack()))
    nav_buttons.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton(text="Вперед ▶️", callback_data=Paginator(action="next", page=page).pack()))
    
    buttons.append(nav_buttons)
    buttons.append([InlineKeyboardButton(text="↩️ В админ-панель", callback_data="admin_back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_user_settings_menu(settings: dict) -> InlineKeyboardMarkup:
    temp_btn_text = f"🌡️ Изменить температуру ({settings.get('temp', 'N/A')})"
    buttons = [
        [InlineKeyboardButton(text="📝 Изменить системный промпт", callback_data="settings_prompt")],
        [InlineKeyboardButton(text=temp_btn_text, callback_data="settings_temp")],
        [InlineKeyboardButton(text="↩️ Назад в меню", callback_data="back_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_broadcast_manage_keyboard(broadcast_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="📌 Открепить у всех", callback_data=BroadcastCallback(action="unpin", broadcast_id=broadcast_id).pack()),
            InlineKeyboardButton(text="🗑️ Удалить у всех", callback_data=BroadcastCallback(action="delete", broadcast_id=broadcast_id).pack())
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_category_models_menu(category: str, user_sub_level: int, disabled_models: set) -> InlineKeyboardMarkup:
    sub_name = config.SUB_LEVEL_MAP.get(user_sub_level, 'free')
    sub_info = config.SUBSCRIPTION_MODELS[sub_name]
    
    available_for_sub = sub_info['models']
    category_models = config.ALL_MODELS.get(category, [])
    
    buttons = []
    for model in category_models:
        if model in available_for_sub:
            text = f"⚠️ {model}" if model in disabled_models else model
            buttons.append([InlineKeyboardButton(text=text, callback_data=ModelCallback(model_name=model).pack())])
            
    buttons.append([InlineKeyboardButton(text='↩️ Назад', callback_data='menu_models')])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_chat_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🔄 Сменить модель', callback_data='menu_models')],
        [InlineKeyboardButton(text='🗑️ Новый диалог', callback_data='chat_new')],
        [InlineKeyboardButton(text='↩️ Главное меню', callback_data='back_main')]
    ])

def get_models_categories_menu(user_sub_level: int) -> InlineKeyboardMarkup:
    sub_name = config.SUB_LEVEL_MAP.get(user_sub_level, 'free')
    sub_info = config.SUBSCRIPTION_MODELS[sub_name]
    available_for_sub = sub_info['models']

    buttons = []
    for provider, models in config.ALL_MODELS.items():
        if any(model in available_for_sub for model in models):
            buttons.append([InlineKeyboardButton(text=provider, callback_data=f'cat_{provider}')])

    buttons.append([InlineKeyboardButton(text='↩️ Назад', callback_data='back_main')])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_subscription_menu() -> InlineKeyboardMarkup:
    buttons = []
    for sub_name, sub_info in config.SUBSCRIPTION_MODELS.items():
        if sub_info['price'] > 0:
            buttons.append([
                InlineKeyboardButton(
                    text=f"Подробнее о {sub_info['name']} - {sub_info['price']}₽",
                    callback_data=SubDetailCallback(level=sub_info['level']).pack()
                )
            ])
    buttons.append([InlineKeyboardButton(text='↩️ Назад', callback_data='back_main')])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_subscription_details_keyboard(level: int) -> InlineKeyboardMarkup:
    """Создает клавиатуру для экрана с деталями подписки."""
    sub_name = config.SUB_LEVEL_MAP.get(level)
    sub_info = config.SUBSCRIPTION_MODELS[sub_name]
    
    buttons = [
        [InlineKeyboardButton(
            text=f"✅ Купить {sub_info['name']} - {sub_info['price']}₽",
            callback_data=f"buy_{level}"
        )],
        [InlineKeyboardButton(text='↩️ Назад к планам', callback_data='menu_subscription')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_back_to_main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='↩️ Назад', callback_data='back_main')]])

def get_admin_back_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='↩️ Назад', callback_data='admin_back')]])

def get_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='❌ Отмена', callback_data='cancel_action')]])

def get_broadcast_confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='✅ Отправить всем', callback_data='broadcast_send')],
        [InlineKeyboardButton(text='📌 Отправить и закрепить', callback_data='broadcast_pin')],
        [InlineKeyboardButton(text='❌ Отмена', callback_data='cancel_action')]
    ])

def get_reset_all_subs_confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='✅ Да, сбросить все', callback_data='confirm_reset_all_subs')],
        [InlineKeyboardButton(text='❌ Отмена', callback_data='admin_back')]
    ])