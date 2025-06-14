import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')

try:
    ADMIN_IDS_STR = os.getenv('ADMIN_IDS')
    if not ADMIN_IDS_STR:
        raise ValueError("Переменная ADMIN_IDS не найдена в .env файле.")
    ADMIN_IDS = {int(admin_id) for admin_id in ADMIN_IDS_STR.split(',')}
except (ValueError, TypeError) as e:
    print(f"Ошибка: ADMIN_IDS имеет неверный формат в .env файле. Убедитесь, что ID перечислены через запятую. {e}")
    exit()

PAYMENT_USERNAME = "xakenn"
SUPPORT_USERNAME = "gevsen"

API_KEY = os.getenv('API_KEY')
API_URL = os.getenv('API_URL')

IMAGE_API_URL = "https://nustjourney.mirandasite.online/v1"
IMAGE_MODEL = "gpt-image-1"

GROUP_TRIGGER = ".mini"
DEFAULT_GROUP_MODEL = "gpt-4.1"

DEFAULT_SYSTEM_PROMPT = "You are a helpful AI assistant."
DEFAULT_TEMPERATURE = 0.7

DATABASE_PATH = os.getenv('DATABASE', 'bot_database.db')

SUB_LEVEL_MAP = {
    0: 'free',
    1: 'standard',
    2: 'premium'
}

ALL_MODELS = {
    '🤖 OpenAI': ['gpt-4.5-preview', 'gpt-4.1', 'o1-pro', 'o4-mini', 'chatgpt-4o-latest'],
    '🔥 DeepSeek': ['deepseek-chat-v3-0324', 'deepseek-r1-0528'],
    '🦙 Meta': ['llama-3.1-nemotron-ultra-253b-v1'],
    '🎯 Alibaba': ['qwen3-235b-a22b'],
    '💎 Google': ['gemini-2.5-pro-exp-03-25'],
    '🧠 Microsoft': ['phi-4-reasoning-plus'],
    '🚀 xAI': ['grok-3', 'grok-3-mini'],
    '🏛️ Anthropic': ['claude-3.7-sonnet']
}

FREE_MODELS_SET = {'deepseek-chat-v3-0324', 'gpt-4.1', 'chatgpt-4o-latest'}

STANDARD_ADDITIONAL_MODELS_SET = {
    'llama-3.1-nemotron-ultra-253b-v1', 'qwen3-235b-a22b', 
    'gemini-2.5-pro-exp-03-25', 'phi-4-reasoning-plus', 'grok-3-mini'
}

PREMIUM_ADDITIONAL_MODELS_SET = {
    'gpt-4.5-preview', 'o1-pro', 'o4-mini', 
    'deepseek-r1-0528', 'grok-3', 'claude-3.7-sonnet'
}

STANDARD_MODELS_SET = FREE_MODELS_SET | STANDARD_ADDITIONAL_MODELS_SET
PREMIUM_MODELS_SET = STANDARD_MODELS_SET | PREMIUM_ADDITIONAL_MODELS_SET

SUBSCRIPTION_MODELS = {
    "free": {
        "level": 0,
        "name": "Free",
        "price": 0,
        "models": list(FREE_MODELS_SET),
        "description": "<b>Базовый доступ для знакомства с ботом.</b>\nВключает несколько быстрых и популярных моделей для простых задач."
    },
    "standard": {
        "level": 1,
        "name": "Standard",
        "price": 150,
        "models": list(STANDARD_MODELS_SET),
        "description": "<b>Отличный набор для ежедневных задач.</b>\nДоступ к расширенному списку умных и креативных моделей от ведущих разработчиков."
    },
    "premium": {
        "level": 2,
        "name": "Premium",
        "price": 350,
        "models": list(PREMIUM_MODELS_SET),
        "description": "<b>Полный арсенал для профессионалов.</b>\nАбсолютно все доступные модели, включая самые мощные, эксклюзивные и экспериментальные."
    }
}

LIMITS = {
    0: 3,
    1: 40,
    2: 100,
}

CHAT_HISTORY_MAX_LEN = 10