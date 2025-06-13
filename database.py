import aiosqlite
from datetime import datetime, timedelta

class Database:
    def __init__(self, db_path):
        self.db_path = db_path

    async def _execute(self, query, params=None):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(query, params or ())
            await db.commit()

    async def _fetchone(self, query, params=None):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(query, params or ()) as cursor:
                return await cursor.fetchone()

    async def _fetchall(self, query, params=None):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(query, params or ()) as cursor:
                return await cursor.fetchall()

    async def _add_is_blocked_column_if_not_exists(self):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('PRAGMA table_info(users)')
            columns = [row[1] for row in await cursor.fetchall()]
            if 'is_blocked' not in columns:
                await db.execute('ALTER TABLE users ADD COLUMN is_blocked INTEGER DEFAULT 0')
                await db.commit()

    async def create_tables(self):
        await self._execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                subscription_level INTEGER DEFAULT 0,
                subscription_end TIMESTAMP,
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

    async def init_db(self):
        await self.create_tables()
        await self._add_is_blocked_column_if_not_exists()

    async def add_user(self, user_id, username):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                'INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)',
                (user_id, username)
            )
            await db.execute(
                'UPDATE users SET username = ? WHERE user_id = ? AND username IS NOT ?',
                (username, user_id, username)
            )
            await db.commit()

    async def get_user(self, user_id):
        return await self._fetchone('SELECT * FROM users WHERE user_id = ?', (user_id,))

    async def get_user_by_username(self, username):
        return await self._fetchone('SELECT * FROM users WHERE username = ?', (username,))

    async def update_subscription(self, user_id, level):
        end_date = datetime.now() if level == 0 else datetime.now() + timedelta(days=30)
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
        if result:
            level, end_date_str = result
            if end_date_str:
                end_date = datetime.fromisoformat(end_date_str)
                if end_date < datetime.now():
                    await self.update_subscription(user_id, 0)
                    return 0
            return level
        return 0

    async def get_subscription_end(self, user_id):
        result = await self._fetchone('SELECT subscription_end FROM users WHERE user_id = ?', (user_id,))
        if result and result[0]:
            return datetime.fromisoformat(result[0])
        return None

    async def get_all_users(self):
        return await self._fetchall('SELECT user_id, username, subscription_level, is_blocked FROM users')

    async def get_user_count(self):
        result = await self._fetchone('SELECT COUNT(*) FROM users')
        return result[0] if result else 0

    async def get_subscription_stats(self):
        stats = {}
        for level in [0, 1, 2]:
            result = await self._fetchone(
                'SELECT COUNT(*) FROM users WHERE subscription_level = ?',
                (level,)
            )
            stats[level] = result[0] if result else 0
        return stats
        
    async def get_all_user_ids(self):
        rows = await self._fetchall('SELECT user_id FROM users')
        return [row[0] for row in rows]