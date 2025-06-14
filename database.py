import aiosqlite
from datetime import datetime, timedelta

class Database:
    def __init__(self, db_path):
        self.db_path = db_path

    async def _execute(self, query, params=None):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(query, params or ())
            await db.commit()
            return cursor

    async def _fetchone(self, query, params=None):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(query, params or ()) as cursor:
                return await cursor.fetchone()

    async def _fetchall(self, query, params=None):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(query, params or ()) as cursor:
                return await cursor.fetchall()

    async def init_db(self):
        await self._execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                subscription_level INTEGER NOT NULL DEFAULT 0,
                subscription_end TIMESTAMP,
                is_blocked INTEGER NOT NULL DEFAULT 0,
                last_selected_model TEXT,
                system_prompt TEXT,
                temperature REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await self._execute('''
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                model TEXT,
                request_date DATE,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        await self._execute('''
            CREATE TABLE IF NOT EXISTS broadcasts (
                broadcast_id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_text TEXT,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await self._execute('''
            CREATE TABLE IF NOT EXISTS sent_broadcast_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                broadcast_id INTEGER,
                user_id INTEGER,
                message_id INTEGER,
                FOREIGN KEY (broadcast_id) REFERENCES broadcasts (broadcast_id)
            )
        ''')
        
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('PRAGMA table_info(users)')
            columns = [row[1] for row in await cursor.fetchall()]
            if 'last_selected_model' not in columns:
                await db.execute('ALTER TABLE users ADD COLUMN last_selected_model TEXT')
            if 'system_prompt' not in columns:
                await db.execute('ALTER TABLE users ADD COLUMN system_prompt TEXT')
            if 'temperature' not in columns:
                await db.execute('ALTER TABLE users ADD COLUMN temperature REAL')
            if 'created_at' not in columns:
                await db.execute('ALTER TABLE users ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
            await db.commit()

    async def add_user(self, user_id: int, username: str) -> bool:
        user = await self._fetchone('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
        if user:
            await self._execute('UPDATE users SET username = ? WHERE user_id = ? AND username IS NOT ?', (username, user_id, username))
            return False
        else:
            await self._execute(
                'INSERT INTO users (user_id, username, created_at) VALUES (?, ?, ?)',
                (user_id, username, datetime.now())
            )
            return True

    async def get_registration_counts(self) -> dict:
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_start = today_start - timedelta(days=1)
        seven_days_ago = today_start - timedelta(days=7)
        thirty_days_ago = today_start - timedelta(days=30)

        query = '''
            SELECT
                COUNT(CASE WHEN created_at >= ? THEN 1 END),
                COUNT(CASE WHEN created_at >= ? AND created_at < ? THEN 1 END),
                COUNT(CASE WHEN created_at >= ? THEN 1 END),
                COUNT(CASE WHEN created_at >= ? THEN 1 END)
            FROM users
        '''
        params = (today_start, yesterday_start, today_start, seven_days_ago, thirty_days_ago)
        counts_tuple = await self._fetchone(query, params)
        
        return {
            'today': counts_tuple[0],
            'yesterday': counts_tuple[1],
            'last_7_days': counts_tuple[2],
            'last_30_days': counts_tuple[3]
        }

    async def get_user_settings(self, user_id: int):
        query = 'SELECT system_prompt, temperature FROM users WHERE user_id = ?'
        return await self._fetchone(query, (user_id,))

    async def update_user_settings(self, user_id: int, prompt: str = None, temp: float = None):
        if prompt is not None:
            await self._execute('UPDATE users SET system_prompt = ? WHERE user_id = ?', (prompt, user_id))
        if temp is not None:
            await self._execute('UPDATE users SET temperature = ? WHERE user_id = ?', (temp, user_id))

    async def add_broadcast(self, message_text: str) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('INSERT INTO broadcasts (message_text) VALUES (?)', (message_text,))
            await db.commit()
            return cursor.lastrowid

    async def add_sent_broadcast_message(self, broadcast_id: int, user_id: int, message_id: int):
        await self._execute(
            'INSERT INTO sent_broadcast_messages (broadcast_id, user_id, message_id) VALUES (?, ?, ?)',
            (broadcast_id, user_id, message_id)
        )

    async def get_sent_messages_for_broadcast(self, broadcast_id: int):
        return await self._fetchall(
            'SELECT user_id, message_id FROM sent_broadcast_messages WHERE broadcast_id = ?',
            (broadcast_id,)
        )

    async def delete_broadcast(self, broadcast_id: int):
        await self._execute('DELETE FROM sent_broadcast_messages WHERE broadcast_id = ?', (broadcast_id,))
        await self._execute('DELETE FROM broadcasts WHERE broadcast_id = ?', (broadcast_id,))

    async def get_all_users_paginated(self, page: int, page_size: int = 1):
        offset = (page - 1) * page_size
        query = f"SELECT * FROM users ORDER BY created_at DESC LIMIT ? OFFSET ?"
        return await self._fetchall(query, (page_size, offset))

    async def update_last_selected_model(self, user_id: int, model_name: str):
        await self._execute('UPDATE users SET last_selected_model = ? WHERE user_id = ?', (model_name, user_id))

    async def get_last_selected_model(self, user_id: int):
        result = await self._fetchone('SELECT last_selected_model FROM users WHERE user_id = ?', (user_id,))
        return result[0] if result and result[0] else None

    async def get_user_id_by_username(self, username):
        return await self._fetchone('SELECT user_id FROM users WHERE username = ?', (username,))

    async def get_user_info(self, user_id):
        return await self._fetchone('SELECT * FROM users WHERE user_id = ?', (user_id,))

    async def update_subscription(self, user_id, level):
        end_date = datetime.now() + timedelta(days=30) if level > 0 else None
        await self._execute(
            'UPDATE users SET subscription_level = ?, subscription_end = ? WHERE user_id = ?',
            (level, end_date, user_id)
        )

    async def block_user(self, user_id, block=True):
        await self._execute('UPDATE users SET is_blocked = ? WHERE user_id = ?', (1 if block else 0, user_id))

    async def is_user_blocked(self, user_id):
        result = await self._fetchone('SELECT is_blocked FROM users WHERE user_id = ?', (user_id,))
        return result and result[0] == 1

    async def get_user_requests_today(self, user_id):
        today = datetime.now().date()
        result = await self._fetchone(
            'SELECT COUNT(*) FROM requests WHERE user_id = ? AND request_date = ?',
            (user_id, today)
        )
        return result[0] if result else 0

    async def add_request(self, user_id, model):
        today = datetime.now().date()
        await self._execute(
            'INSERT INTO requests (user_id, model, request_date) VALUES (?, ?, ?)',
            (user_id, model, today)
        )

    async def check_subscription(self, user_id):
        result = await self._fetchone(
            'SELECT subscription_level, subscription_end FROM users WHERE user_id = ?',
            (user_id,)
        )
        if not result: return 0
        level, end_date_str = result
        if level > 0 and end_date_str:
            end_date = datetime.fromisoformat(end_date_str)
            if end_date < datetime.now():
                # Не обновляем здесь, просто возвращаем 0. Обновление - отдельная задача.
                return 0
        return level

    async def cleanup_expired_subscriptions(self) -> int:
        """Деактивирует истекшие подписки и возвращает количество затронутых пользователей."""
        cursor = await self._execute("UPDATE users SET subscription_level = 0, subscription_end = NULL WHERE subscription_end < ?", (datetime.now(),))
        return cursor.rowcount

    async def get_subscription_end(self, user_id):
        result = await self._fetchone('SELECT subscription_end FROM users WHERE user_id = ?', (user_id,))
        if result and result[0]: return datetime.fromisoformat(result[0])
        return None

    async def get_user_count(self):
        result = await self._fetchone('SELECT COUNT(*) FROM users')
        return result[0] if result else 0

    async def get_subscription_stats(self):
        query = 'SELECT subscription_level, COUNT(*) FROM users GROUP BY subscription_level'
        rows = await self._fetchall(query)
        stats = {0: 0, 1: 0, 2: 0}
        stats.update(dict(rows))
        return stats
        
    async def get_all_user_ids(self):
        rows = await self._fetchall('SELECT user_id FROM users WHERE is_blocked = 0')
        return [row[0] for row in rows]

    async def reset_all_subscriptions(self, admin_ids: set) -> int:
        """Сбрасывает все подписки до Free, кроме админских."""
        placeholders = ', '.join('?' for _ in admin_ids)
        query = f'UPDATE users SET subscription_level = 0, subscription_end = NULL WHERE user_id NOT IN ({placeholders})'
        
        cursor = await self._execute(query, tuple(admin_ids))
        return cursor.rowcount