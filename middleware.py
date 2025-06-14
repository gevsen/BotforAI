# middleware.py
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery, User

# from database import Database # No longer directly needed by middleware
# from api_helpers import get_user_level, get_user_limit # These are now in UserService
from user_service import UserService # Import UserService

class AccessControlMiddleware(BaseMiddleware):
    def __init__(self, user_service: UserService): # Changed constructor
        self.user_service = user_service

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        if not isinstance(event, (Message, CallbackQuery)):
            return await handler(event, data)

        # data from dispatcher should contain 'bot' instance
        # bot = data.get('bot') # Not strictly needed here if user_service is self-contained

        current_user: User | None = data.get('event_from_user')
        if not current_user: # Should always be present for Message/CallbackQuery based on aiogram internals
            # If it can be None, this is a potential issue or needs specific handling.
            # For now, assume it's populated by aiogram for these event types.
            return await handler(event, data)

        user_id = current_user.id

        # 1. Проверка на блокировку (using UserService)
        if await self.user_service.is_user_blocked(user_id):
            if isinstance(event, Message):
                # It's generally better to avoid answering directly in middleware if it's just a block
                # and let a handler do it, or have a specific "you are blocked" handler.
                # However, for simplicity and matching original behavior:
                await event.answer("Ваш доступ к боту заблокирован администратором.")
            elif isinstance(event, CallbackQuery):
                await event.answer("Ваш доступ к боту заблокирован администратором.", show_alert=True)
            return # Stop processing further handlers in this chain

        # 2. Получение уровня и лимита (using UserService)
        user_level = await self.user_service.get_user_level(user_id)
        limit = await self.user_service.get_user_limit(user_id)

        # 3. Проверка лимитов (using UserService)
        # Admins (user_level 3 or where limit is inf) should bypass this check.
        # get_user_limit already returns float('inf') for admins.
        if limit != float('inf'): # Check if limit is not infinite
            requests_today = await self.user_service.get_user_requests_today(user_id)
            if requests_today >= limit:
                if isinstance(event, Message):
                    await event.answer("Достигнут дневной лимит запросов. Возвращайтесь завтра!")
                elif isinstance(event, CallbackQuery):
                    await event.answer("Достигнут дневной лимит запросов. Возвращайтесь завтра!", show_alert=True)
                return # Stop processing

        # 4. Передаем полезные данные в хэндлер
        data['user_level'] = user_level
        data['limit'] = limit
        # data['db'] is not passed from here; handlers should use bot['db']
        # data['user_service'] can be passed if needed: data['user_service'] = self.user_service

        return await handler(event, data)
