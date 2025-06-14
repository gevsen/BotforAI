from aiogram import Router, F

from .chat import chat_router
from .image import image_router
from .settings import settings_router
from .subscription import subscription_router
from .misc import misc_router

# Main user router for private chats
user_private_router = Router(name="user_private") # Added a router name for clarity

# Apply global filters to this main router
# These filters will apply to all messages and callback queries handled by routers included below.
user_private_router.message.filter(F.chat.type == 'private')
user_private_router.callback_query.filter(F.chat.type == 'private') # Ensuring callbacks also from private chat context

user_private_router.include_routers(
    chat_router,
    image_router,
    settings_router,
    subscription_router,
    misc_router
)
