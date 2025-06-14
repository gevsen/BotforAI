# handlers/middleware.py
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

from database import Database
from .utils import get_user_level, get_user_limit

class AccessControlMiddleware(BaseMiddleware):
    def __init__(self, db: Database):
        self.db = db

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        # Проверяем, что это событие от пользователя (сообщение или колбэк)
        if not isinstance(event, (Message, CallbackQuery)):
            return await handler(event, data)

        user_id = event.from_user.id

        # 1. Проверка на блокировку
        if await self.db.is_user_blocked(user_id):
            await event.answer("Ваш доступ к моделям заблокирован администратором.", show_alert=isinstance(event, CallbackQuery))
            return

        # 2. Получение уровня и лимита
        user_level = await get_user_level(self.db, user_id)
        limit = await get_user_limit(self.db, user_id)
        
        # 3. Проверка лимитов
        requests_today = await self.db.get_user_requests_today(user_id)
        if requests_today >= limit:
            await event.answer("Достигнут дневной лимит. Возвращайтесь завтра!", show_alert=isinstance(event, CallbackQuery))
            return

        # 4. Передаем полезные данные в хэндлер
        data['user_level'] = user_level
        data['db'] = self.db

        return await handler(event, data)