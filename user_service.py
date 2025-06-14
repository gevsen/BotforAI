# Assuming config and database.Database are available
import config
from database import Database # Assuming Database class is in database.py

class UserService:
    def __init__(self, db: Database):
        self.db = db

    async def get_user_level(self, user_id: int) -> int:
        if user_id in config.ADMIN_IDS:
            return 3  # Admin level (Assuming 3 is the highest, adjust if config.ADMIN_ACCESS_LEVEL is used elsewhere)

        # Check subscription status
        subscription_status = await self.db.check_subscription(user_id) # Returns a status object or similar
        if subscription_status:
            # Example: if status is 'active' or 'trialing' for a paid tier
            # This logic depends heavily on what db.check_subscription returns
            # and how subscription levels are defined.
            # For instance, if it returns a level number directly:
            if isinstance(subscription_status, int) and subscription_status > 0:
                return subscription_status # e.g., 1 for Standard, 2 for Premium (non-admin)
            # Or if it returns a status string/object:
            if hasattr(subscription_status, 'status'): # Example if it's an object
                if subscription_status.status in ("active", "trialing"):
                     # We need to map this status to a level, e.g. by checking subscription type
                     # This part is complex without knowing the exact return of check_subscription
                     # For now, let's assume a premium active sub is level 2
                    if hasattr(subscription_status, 'level') and subscription_status.level == 2: # Fictional attribute
                        return 2 # Premium
                    # If it's a basic paid subscription, maybe level 1
                    if hasattr(subscription_status, 'level') and subscription_status.level == 1: # Fictional attribute
                        return 1 # Standard
                    # Fallback if status is active/trialing but level is not clear
                    # This might indicate a new subscription type not mapped yet
                    # or that the db.check_subscription should directly return the numeric level.
                    # For simplicity, assume level 2 for any active paid sub if not admin.
                    return 2


        # If no active paid subscription, check if user exists for basic level
        user_exists = await self.db.check_user_exists(user_id)
        if user_exists:
            return 1 # Basic/Free tier for existing users without active paid subscription

        # If user does not exist and is not admin, they have no access or level 0
        return 0

    async def get_user_limit(self, user_id: int) -> int | float:
        if user_id in config.ADMIN_IDS:
            return float('inf')  # Admins have no limit

        user_level = await self.get_user_level(user_id)

        return config.LIMITS.get(user_level, 0) # Default to 0 if level has no defined limit

    async def get_user_settings(self, user_id: int) -> tuple | None:
        return await self.db.get_user_settings(user_id)

    async def update_user_settings(self, user_id: int, prompt: str = None, temp: float = None):
        await self.db.update_user_settings(user_id, prompt, temp)

    async def is_user_blocked(self, user_id: int) -> bool:
        """Checks if the user is blocked."""
        return await self.db.is_user_blocked(user_id)

    async def get_user_requests_today(self, user_id: int) -> int:
        """Gets the number of requests made by the user today."""
        return await self.db.get_user_requests_today(user_id)
