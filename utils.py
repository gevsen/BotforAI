# handlers/utils.py
import aiohttp
from aiogram.fsm.context import FSMContext

import config
from database import Database

async def get_user_level(db: Database, user_id: int) -> int:
    """Возвращает уровень подписки пользователя (админы всегда Premium)."""
    if user_id in config.ADMIN_IDS:
        return 2
    return await db.check_subscription(user_id)

async def get_user_limit(db: Database, user_id: int) -> int | float:
    """Возвращает дневной лимит запросов для пользователя."""
    if user_id in config.ADMIN_IDS:
        return float('inf')
    level = await get_user_level(db, user_id)
    return config.LIMITS.get(level, 0)

async def prepare_api_payload(db: Database, user_id: int, user_text: str, model: str, state: FSMContext) -> dict:
    """Готовит данные для запроса к API, включая историю и настройки."""
    settings = await db.get_user_settings(user_id)
    system_prompt = (settings[0] or config.DEFAULT_SYSTEM_PROMPT) if settings else config.DEFAULT_SYSTEM_PROMPT
    temperature = (settings[1] or config.DEFAULT_TEMPERATURE) if settings else config.DEFAULT_TEMPERATURE

    user_data = await state.get_data()
    history = user_data.get('chat_history', [])
    
    if not history:
        history.append({"role": "system", "content": system_prompt})
    
    history.append({'role': 'user', 'content': user_text})
    
    return {
        'model': model,
        'messages': history,
        'temperature': temperature
    }

async def execute_chat_request(session: aiohttp.ClientSession, payload: dict) -> tuple[str | None, str | None]:
    """Выполняет запрос к API чата и возвращает (ответ, ошибка)."""
    headers = {'Authorization': f'Bearer {config.API_KEY}', 'Content-Type': 'application/json'}
    try:
        async with session.post(f'{config.API_URL}/chat/completions', headers=headers, json=payload, timeout=120) as response:
            if response.status == 200:
                result = await response.json()
                return result['choices'][0]['message']['content'], None
            else:
                error_details = await response.text()
                return None, f'Ошибка API {response.status}: {error_details}'
    except Exception as e:
        return None, str(e)