import aiosqlite
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path='places.db'):
        self.db_path = db_path
    
    async def init_db(self):
        """Инициализация базы данных"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS places (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    place_type TEXT,
                    price_category TEXT,
                    address TEXT,
                    description TEXT,
                    latitude REAL,
                    longitude REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            # Создаем индексы для ускорения запросов
            await db.execute('''
                CREATE INDEX IF NOT EXISTS idx_user_id ON places(user_id)
            ''')
            await db.execute('''
                CREATE INDEX IF NOT EXISTS idx_place_type ON places(place_type)
            ''')
            await db.execute('''
                CREATE INDEX IF NOT EXISTS idx_created_at ON places(created_at DESC)
            ''')
            await db.commit()
        logger.info("База данных инициализирована")
    
    async def add_place(self, user_id: int, name: str, place_type: str = None,
                       price_category: str = None, address: str = None, 
                       description: str = None, latitude: float = None, 
                       longitude: float = None):
        """Добавить новое место"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute('''
                    INSERT INTO places (user_id, name, place_type, price_category, address, description, latitude, longitude)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (user_id, name, place_type, price_category, address, description, latitude, longitude))
                await db.commit()
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"Ошибка при добавлении места: {e}")
            return None
    
    async def get_user_places(self, user_id: int, place_type: str = None):
        """Получить все места пользователя, опционально с фильтром по типу"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                if place_type:
                    query = 'SELECT * FROM places WHERE user_id = ? AND place_type = ? ORDER BY created_at DESC'
                    params = (user_id, place_type)
                else:
                    query = 'SELECT * FROM places WHERE user_id = ? ORDER BY created_at DESC'
                    params = (user_id,)
                
                async with db.execute(query, params) as cursor:
                    rows = await cursor.fetchall()
                    return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка при получении мест: {e}")
            return []
    
    async def get_place(self, place_id: int, user_id: int):
        """Получить конкретное место"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                'SELECT * FROM places WHERE id = ? AND user_id = ?',
                (place_id, user_id)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None
    
    async def delete_place(self, place_id: int, user_id: int):
        """Удалить место"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                'DELETE FROM places WHERE id = ? AND user_id = ?',
                (place_id, user_id)
            )
            await db.commit()
    
    async def search_places(self, user_id: int, query: str):
        """Поиск мест по названию, адресу, описанию или типу"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute('''
                    SELECT * FROM places 
                    WHERE user_id = ? AND (name LIKE ? OR address LIKE ? OR description LIKE ? OR place_type LIKE ?)
                    ORDER BY created_at DESC
                ''', (user_id, f'%{query}%', f'%{query}%', f'%{query}%', f'%{query}%')) as cursor:
                    rows = await cursor.fetchall()
                    return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка при поиске мест: {e}")
            return []
    
    async def count_user_places(self, user_id: int):
        """Подсчитать количество мест пользователя"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                'SELECT COUNT(*) FROM places WHERE user_id = ?',
                (user_id,)
            ) as cursor:
                result = await cursor.fetchone()
                return result[0] if result else 0

