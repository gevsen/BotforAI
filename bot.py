import os
import aiohttp
import asyncio
from datetime import datetime, timezone, timedelta

from aiogram import Bot, Dispatcher, types, F, Router, BaseMiddleware
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramForbiddenError
from aiogram.client.default import DefaultBotProperties

from dotenv import load_dotenv
from database import Database
from states import AdminActions

from aiogram.filters.callback_data import CallbackData

class ModelCallback(CallbackData, prefix="model"):
    model_name: str

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
API_KEY = os.getenv('API_KEY')
API_URL = os.getenv('API_URL')
DATABASE = os.getenv('DATABASE')
ADMIN_ID = int(os.getenv('ADMIN_ID'))

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()
db = Database(DATABASE)

admin_router = Router()
user_router = Router()

MODEL_CATEGORIES = {
    'OpenAI': ['gpt-4.5-preview', 'gpt-4.1', 'o1-pro', 'o4-mini', 'chatgpt-4o-latest'],
    'DeepSeek': ['deepseek-chat-v3-0324', 'deepseek-r1-0528'],
    'Meta': ['llama-3.1-nemotron-ultra-253b-v1'],
    'Alibaba': ['qwen3-235b-a22b'],
    'Google': ['gemini-2.5-pro-exp-03-25'],
    'Microsoft': ['phi-4-reasoning-plus'],
    'xAI': ['grok-3', 'grok-3-mini'],
    'Anthropic': ['claude-3.7-sonnet']
}
MODELS = {
    'free': ['deepseek-chat-v3-0324', 'gpt-4.1', 'chatgpt-4o-latest'],
    'standard': ['deepseek-chat-v3-0324', 'gpt-4.1', 'chatgpt-4o-latest', 'llama-3.1-nemotron-ultra-253b-v1', 'qwen3-235b-a22b', 'gemini-2.5-pro-exp-03-25', 'phi-4-reasoning-plus', 'grok-3-mini'],
    'premium': ['gpt-4.5-preview', 'gpt-4.1', 'o1-pro', 'o4-mini', 'chatgpt-4o-latest', 'deepseek-chat-v3-0324', 'llama-3.1-nemotron-ultra-253b-v1', 'qwen3-235b-a22b', 'gemini-2.5-pro-exp-03-25', 'phi-4-reasoning-plus', 'deepseek-r1-0528', 'grok-3', 'grok-3-mini', 'claude-3.7-sonnet']
}
LIMITS = {0: 3, 1: 40, 2: 100}
PRICES = {1: 150, 2: 350}

class AdminMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: types.TelegramObject, data: dict):
        if hasattr(event, 'from_user') and event.from_user.id == ADMIN_ID:
            return await handler(event, data)
        if isinstance(event, types.CallbackQuery):
            await event.answer("У вас нет прав для этого действия.", show_alert=True)
        return

admin_router.message.middleware(AdminMiddleware())
admin_router.callback_query.middleware(AdminMiddleware())

def get_main_menu(user_id):
    buttons = [
        [InlineKeyboardButton(text='Модели', callback_data='menu_models')],
        [InlineKeyboardButton(text='Подписка', callback_data='menu_subscription')],
        [InlineKeyboardButton(text='Помощь', callback_data='menu_help')]
    ]
    if user_id == ADMIN_ID:
        buttons.append([InlineKeyboardButton(text='Админ-панель', callback_data='menu_admin')])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_chat_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='Сменить модель', callback_data='menu_models')],
        [InlineKeyboardButton(text='Главное меню', callback_data='back_main')]
    ])

def get_admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='Статистика', callback_data='admin_stats')],
        [InlineKeyboardButton(text='Пользователи', callback_data='admin_users')],
        [InlineKeyboardButton(text='Рассылка', callback_data='admin_broadcast')],
        [InlineKeyboardButton(text='Тест моделей', callback_data='admin_test')],
        [InlineKeyboardButton(text='Назад', callback_data='back_main')]
    ])

def get_admin_users_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='Выдать подписку', callback_data='admin_grant')],
        [InlineKeyboardButton(text='Блокировка', callback_data='admin_block')],
        [InlineKeyboardButton(text='Разблокировка', callback_data='admin_unblock')],
        [InlineKeyboardButton(text='Назад', callback_data='admin_back')]
    ])

async def get_user_level(user_id):
    if user_id == ADMIN_ID: return 2
    return await db.check_subscription(user_id)

async def get_user_limit(user_id):
    if user_id == ADMIN_ID: return float('inf')
    level = await get_user_level(user_id)
    return LIMITS.get(level, 0)

async def test_chat_model(model: str) -> dict:
    async with aiohttp.ClientSession() as session:
        headers = {'Authorization': f'Bearer {API_KEY}', 'Content-Type': 'application/json'}
        data = {'model': model, 'messages': [{'role': 'user', 'content': 'Test'}], 'temperature': 0.7, 'max_tokens': 10}
        try:
            async with session.post(f'{API_URL}/chat/completions', headers=headers, json=data, timeout=45) as response:
                if response.status == 200:
                    try:
                        await response.json()
                        return {'model': model, 'status': 'OK'}
                    except Exception:
                        return {'model': model, 'status': 'Invalid JSON'}
                else:
                    return {'model': model, 'status': f'Error {response.status}'}
        except asyncio.TimeoutError:
            return {'model': model, 'status': 'Timeout'}
        except Exception as e:
            return {'model': model, 'status': f'Error: {type(e).__name__}'}

@user_router.message(Command('start'))
async def start_handler(message: types.Message, state: FSMContext):
    await state.clear()
    await db.add_user(message.from_user.id, message.from_user.username)
    await message.answer(f'Yup, я G.AI\n\nТекущее время: {datetime.now(timezone(timedelta(hours=3))).strftime("%H:%M МСК")}\n\nВыберите действие:', reply_markup=get_main_menu(message.from_user.id))

@user_router.message(Command('menu'))
async def menu_handler(message: types.Message, state: FSMContext):
    await state.clear()
    user_data = await state.get_data()
    if 'model' in user_data:
        await message.answer('Меню диалога:', reply_markup=get_chat_menu())
    else:
        await message.answer('Выберите действие:', reply_markup=get_main_menu(message.from_user.id))

@user_router.callback_query(F.data == 'back_main')
async def back_to_main(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text('Выберите действие:', reply_markup=get_main_menu(callback.from_user.id))

@user_router.callback_query(F.data == 'menu_models')
async def models_categories_menu(callback: types.CallbackQuery):
    user_level = await get_user_level(callback.from_user.id)
    available_models = MODELS[['free', 'standard', 'premium'][min(user_level, 2)]]
    buttons = [[InlineKeyboardButton(text=cat, callback_data=f'cat_{cat}')] for cat, models in MODEL_CATEGORIES.items() if any(m in available_models for m in models)]
    buttons.append([InlineKeyboardButton(text='Назад', callback_data='back_main')])
    await callback.message.edit_text('Выберите категорию:', reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@user_router.callback_query(F.data.startswith('cat_'))
async def category_models_menu(callback: types.CallbackQuery):
    category = callback.data.split('_', 1)[1]
    user_level = await get_user_level(callback.from_user.id)
    available_models = MODELS[['free', 'standard', 'premium'][min(user_level, 2)]]
    category_models = [m for m in MODEL_CATEGORIES.get(category, []) if m in available_models]
    buttons = [[InlineKeyboardButton(text=model, callback_data=ModelCallback(model_name=model).pack())] for model in category_models]
    buttons.append([InlineKeyboardButton(text='Назад', callback_data='menu_models')])
    await callback.message.edit_text(f'Модели {category}:', reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@user_router.callback_query(ModelCallback.filter())
async def select_model(callback: types.CallbackQuery, callback_data: ModelCallback, state: FSMContext):
    model = callback_data.model_name
    user_id = callback.from_user.id
    if await db.is_user_blocked(user_id):
        return await callback.answer('Ваш доступ к моделям заблокирован', show_alert=True)
    if user_id != ADMIN_ID:
        limit = await get_user_limit(user_id)
        requests_today = await db.get_user_requests_today(user_id)
        if requests_today >= limit:
            return await callback.answer('Достигнут дневной лимит', show_alert=True)
    await state.update_data(model=model)
    await callback.message.answer(f'<b>Модель: {model}</b>\nОтправьте ваш запрос\n\nДля вызова меню используйте /menu')
    await callback.answer()

@user_router.callback_query(F.data == 'menu_subscription')
async def subscription_menu(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if user_id == ADMIN_ID:
        await callback.message.edit_text('У вас безлимитный доступ как у администратора', reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Назад', callback_data='back_main')]]))
        return
    user_level = await db.check_subscription(user_id)
    requests_today = await db.get_user_requests_today(user_id)
    limit = await get_user_limit(user_id)
    text = f'Текущий план: {["Free", "Standard", "Premium"][user_level]}\nИспользовано запросов: {requests_today}/{limit}\n'
    subscription_end = await db.get_subscription_end(user_id)
    if subscription_end and user_level > 0:
        remaining = subscription_end - datetime.now()
        text += f'До конца подписки: {remaining.days}д {remaining.seconds // 3600}ч\n'
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f'Standard - {PRICES[1]}₽', callback_data='buy_1')], [InlineKeyboardButton(text=f'Premium - {PRICES[2]}₽', callback_data='buy_2')], [InlineKeyboardButton(text='Назад', callback_data='back_main')]])
    await callback.message.edit_text(text, reply_markup=keyboard)

@user_router.callback_query(F.data == 'menu_help')
async def help_menu(callback: types.CallbackQuery):
    text = '<b>Доступные команды:</b>\n/start - главное меню\n/menu - меню в любой момент\n\n<b>Free план:</b> 3 запроса/день\n<b>Standard план:</b> 40 запросов/день\n<b>Premium план:</b> 100 запросов/день'
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Назад', callback_data='back_main')]]))

@user_router.callback_query(F.data.startswith('buy_'))
async def buy_subscription(callback: types.CallbackQuery):
    level = int(callback.data.split('_')[1])
    await callback.message.answer(f'Для оплаты подписки {["", "Standard", "Premium"][level]} ({PRICES[level]}₽) свяжитесь с @gevsen')
    await callback.answer()

@admin_router.callback_query(F.data == 'menu_admin')
async def menu_admin(callback: types.CallbackQuery):
    await callback.message.edit_text('Админ-панель:', reply_markup=get_admin_menu())

@admin_router.callback_query(F.data == 'admin_users')
async def admin_users_menu_callback(callback: types.CallbackQuery):
    await callback.message.edit_text('Управление пользователями:', reply_markup=get_admin_users_menu())

@admin_router.callback_query(F.data == 'admin_back')
async def admin_back(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text('Админ-панель:', reply_markup=get_admin_menu())

@admin_router.callback_query(F.data == 'admin_stats')
async def admin_stats(callback: types.CallbackQuery):
    total_users = await db.get_user_count()
    stats = await db.get_subscription_stats()
    text = f'<b>Статистика:</b>\nВсего пользователей: {total_users}\nFree: {stats.get(0, 0)}\nStandard: {stats.get(1, 0)}\nPremium: {stats.get(2, 0)}'
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Назад', callback_data='admin_back')]]))

@admin_router.callback_query(F.data == 'admin_test')
async def admin_test_models(callback: types.CallbackQuery):
    await callback.answer("Начинаю тестирование...")
    await callback.message.edit_text('Начинаю тестирование моделей... Это может занять несколько минут.')
    all_models = sorted(list(set(model for models in MODEL_CATEGORIES.values() for model in models)))
    results = await asyncio.gather(*[test_chat_model(model) for model in all_models])
    working_models = [r for r in results if r['status'] == 'OK']
    failed_models = [r for r in results if r['status'] != 'OK']
    text = f'<b>Результаты тестирования:</b>\n\n<b>✅ Рабочие модели ({len(working_models)}):</b>\n' + "\n".join(f"✓ {r['model']}" for r in working_models)
    if failed_models:
        text += f'\n\n<b>❌ Нерабочие модели ({len(failed_models)}):</b>\n' + "\n".join(f"✗ {r['model']} - {r['status']}" for r in failed_models)
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Назад', callback_data='admin_back')]]))

async def broadcast_to_users(text: str):
    user_ids = await db.get_all_user_ids()
    success_count = 0
    fail_count = 0
    for user_id in user_ids:
        try:
            sent_message = await bot.send_message(user_id, text)
            await bot.pin_chat_message(chat_id=user_id, message_id=sent_message.message_id)
            success_count += 1
        except TelegramForbiddenError:
            fail_count += 1
        except Exception:
            fail_count += 1
        await asyncio.sleep(0.1)
    
    await bot.send_message(ADMIN_ID, f"✅ Рассылка завершена.\n\nУспешно отправлено: {success_count}\nНе удалось отправить: {fail_count}")

@admin_router.callback_query(F.data == 'admin_broadcast')
async def admin_broadcast_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminActions.waiting_for_broadcast_message)
    await callback.message.answer("Введите текст для рассылки. Он будет отправлен всем пользователям и закреплен.")
    await callback.answer()

@admin_router.message(AdminActions.waiting_for_broadcast_message)
async def admin_broadcast_process(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Начинаю рассылку...")
    asyncio.create_task(broadcast_to_users(message.text))

@admin_router.callback_query(F.data == 'admin_grant')
async def admin_grant_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminActions.waiting_for_grant_user)
    await callback.message.answer('Отправьте ID или @username пользователя и уровень подписки (1 или 2):\nФормат: `ID/username LEVEL`', parse_mode="Markdown")
    await callback.answer()

@admin_router.callback_query(F.data == 'admin_block')
async def admin_block_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminActions.waiting_for_block_user)
    await callback.message.answer('Отправьте ID или @username пользователя для блокировки:')
    await callback.answer()

@admin_router.callback_query(F.data == 'admin_unblock')
async def admin_unblock_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminActions.waiting_for_unblock_user)
    await callback.message.answer('Отправьте ID или @username пользователя для разблокировки:')
    await callback.answer()

async def get_user_id_from_input(input_str: str):
    if input_str.startswith('@'):
        user = await db.get_user_by_username(input_str[1:])
        return user[0] if user else None
    try: return int(input_str)
    except ValueError: return None

@admin_router.message(AdminActions.waiting_for_grant_user)
async def admin_grant_process(message: types.Message, state: FSMContext):
    try:
        parts = message.text.split()
        target_input, level = parts[0], int(parts[1])
        target_user_id = await get_user_id_from_input(target_input)
        if target_user_id:
            await db.update_subscription(target_user_id, level)
            await message.answer(f'Подписка уровня {level} выдана пользователю {target_input}')
        else:
            await message.answer(f'Пользователь {target_input} не найден. Он должен сначала запустить бота.')
    except (ValueError, IndexError):
        await message.answer('Неверный формат. Пожалуйста, проверьте данные и попробуйте снова.')
    finally:
        await state.clear()

async def process_blocking(message: types.Message, state: FSMContext, block: bool):
    target_input = message.text.strip()
    target_user_id = await get_user_id_from_input(target_input)
    if target_user_id:
        await db.block_user(target_user_id, block)
        status = "заблокирован" if block else "разблокирован"
        await message.answer(f'Пользователь {target_input} {status}')
        try:
            await bot.send_message(target_user_id, f'Ваш доступ к моделям был {status} администратором')
        except Exception: pass
    else:
        await message.answer(f'Пользователь {target_input} не найден.')
    await state.clear()

@admin_router.message(AdminActions.waiting_for_block_user)
async def admin_block_process(message: types.Message, state: FSMContext):
    await process_blocking(message, state, block=True)

@admin_router.message(AdminActions.waiting_for_unblock_user)
async def admin_unblock_process(message: types.Message, state: FSMContext):
    await process_blocking(message, state, block=False)

@user_router.message()
async def handle_chat(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if await db.is_user_blocked(user_id):
        return await message.answer('Ваш доступ к моделям заблокирован администратором')
    
    user_data = await state.get_data()
    model = user_data.get('model')
    
    if not model:
        return await message.answer('Сначала выберите модель:', reply_markup=get_main_menu(user_id))
    
    msg = await message.answer('Обрабатываю запрос...')
    async with aiohttp.ClientSession() as session:
        headers = {'Authorization': f'Bearer {API_KEY}', 'Content-Type': 'application/json'}
        data = {'model': model, 'messages': [{'role': 'user', 'content': message.text}], 'temperature': 0.7}
        try:
            async with session.post(f'{API_URL}/chat/completions', headers=headers, json=data, timeout=120) as response:
                if response.status == 200:
                    result = await response.json()
                    if user_id != ADMIN_ID:
                        await db.add_request(user_id, model)
                    await msg.edit_text(result['choices'][0]['message']['content'])
                else:
                    await msg.edit_text(f'Ошибка {response.status}: {await response.text()}')
        except Exception as e:
            await msg.edit_text(f'Произошла ошибка: {e}')

async def set_bot_commands(bot_instance: Bot):
    commands = [
        BotCommand(command="start", description="Перезапустить бота / Главное меню"),
        BotCommand(command="menu", description="Показать меню")
    ]
    await bot_instance.set_my_commands(commands)

async def main():
    await db.init_db()
    await set_bot_commands(bot)
    dp.include_router(admin_router)
    dp.include_router(user_router)
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())