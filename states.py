from aiogram.fsm.state import State, StatesGroup

class AdminActions(StatesGroup):
    waiting_for_grant_user = State()
    waiting_for_block_user = State()
    waiting_for_unblock_user = State()
    waiting_for_broadcast_message = State()