# states.py
from aiogram.fsm.state import State, StatesGroup

class AdminActions(StatesGroup):
    waiting_for_grant_user = State()
    waiting_for_block_user = State()
    waiting_for_unblock_user = State()
    waiting_for_broadcast_message = State()
    waiting_for_broadcast_confirmation = State()
    waiting_for_search_user = State()
    waiting_for_revoke_user = State() # <<< НОВОЕ СОСТОЯНИЕ

class ImageGeneration(StatesGroup):
    waiting_for_prompt = State()

class UserSettings(StatesGroup):
    waiting_for_prompt = State()
    waiting_for_temperature = State()

class Chatting(StatesGroup):
    in_chat = State()