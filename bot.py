import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import BotCommand

import config
from database import Database
from handlers.common_handlers import common_router
from handlers.user_handlers import user_router
from handlers.admin_handlers import admin_router
from handlers.group_handlers import group_router
from handlers.middleware import AccessControlMiddleware

logging.basicConfig(level=logging.INFO)

MODEL_STATUS_CACHE = {}

async def main():
    if not config.BOT_TOKEN:
        logging.critical("Ошибка: BOT_TOKEN не найден. Проверьте .env файл.")
        return

    db = Database(config.DATABASE_PATH)
    await db.init_db()

    bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher()
    
    dp["model_status_cache"] = MODEL_STATUS_CACHE
    dp["db"] = db # Передаем экземпляр БД в диспатчер для доступа из хэндлеров

    # Создаем и регистрируем мидлварь для контроля доступа
    access_middleware = AccessControlMiddleware(db)
    user_router.message.middleware(access_middleware)
    user_router.callback_query.middleware(access_middleware)
    group_router.message.middleware(access_middleware)

    commands = [
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="new", description="Начать новый диалог")
    ]
    await bot.set_my_commands(commands)

    dp.include_router(common_router)
    dp.include_router(admin_router)
    dp.include_router(group_router)
    dp.include_router(user_router)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())