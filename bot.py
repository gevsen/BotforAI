import asyncio
import logging
import aiohttp # Added
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import BotCommand

import config
from database import Database
from handlers.common_handlers import common_router
# from handlers.user_handlers import user_router # Old user router
from user_handlers_private import user_private_router # New user router
from handlers.admin_handlers import admin_router
from handlers.group_handlers import group_router
from handlers.middleware import AccessControlMiddleware
from api_service import APIService # Added
from user_service import UserService # Added

logging.basicConfig(level=logging.INFO)

MODEL_STATUS_CACHE = {}

# Added shutdown handler
async def on_shutdown(dispatcher: Dispatcher):
    client_session = dispatcher.get("client_session")
    if client_session and not client_session.closed:
        await client_session.close()
        logging.info("Aiohttp client session closed.")

async def main():
    if not config.BOT_TOKEN:
        logging.critical("Ошибка: BOT_TOKEN не найден. Проверьте .env файл.")
        return

    db = Database(config.DATABASE_PATH)
    await db.init_db()

    # Instantiate aiohttp.ClientSession and services
    client_session = aiohttp.ClientSession()
    # Ensure API_KEY, API_URL, IMAGE_API_URL are in config and .env
    api_service = APIService(
        api_key=getattr(config, "API_KEY", "YOUR_DEFAULT_API_KEY_IF_NOT_SET"),
        chat_api_url=getattr(config, "API_URL", "YOUR_DEFAULT_CHAT_API_URL_IF_NOT_SET"),
        image_api_url=getattr(config, "IMAGE_API_URL", "YOUR_DEFAULT_IMAGE_API_URL_IF_NOT_SET"),
        session=client_session
    )
    user_service = UserService(db=db)

    bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher()

    dp["model_status_cache"] = MODEL_STATUS_CACHE
    dp["db"] = db # Передаем экземпляр БД в диспатчер для доступа из хэндлеров
    # Pass services and session to dispatcher
    dp["api_service"] = api_service
    dp["user_service"] = user_service
    dp["client_session"] = client_session

    # Создаем и регистрируем мидлварь для контроля доступа
    access_middleware = AccessControlMiddleware(user_service=user_service) # Changed: pass user_service
    user_private_router.message.middleware(access_middleware) # Apply to new router
    user_private_router.callback_query.middleware(access_middleware) # Apply to new router
    group_router.message.middleware(access_middleware)

    commands = [
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="new", description="Начать новый диалог")
    ]
    await bot.set_my_commands(commands)

    dp.include_router(common_router)
    dp.include_router(admin_router)
    dp.include_router(group_router)
    dp.include_router(user_private_router) # Include new router

    # Register shutdown handler
    dp.shutdown.register(on_shutdown)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
