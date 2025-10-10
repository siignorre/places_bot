import aiosqlite
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path='places.db'):
        self.db_path = db_path
        self._connection: Optional[aiosqlite.Connection] = None
    
    async def connect(self):
        """Открыть постоянное соединение с БД"""
        if self._connection is None:
            self._connection = await aiosqlite.connect(self.db_path)
            self._connection.row_factory = aiosqlite.Row
        return self._connection
    
    async def close(self):
        """Закрыть соединение с БД"""
        if self._connection:
            await self._connection.close()
            self._connection = None
    
    async def init_db(self):
        """Инициализация базы данных"""
        db = await self.connect()
        try:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS places (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    place_type TEXT,
                    price_category TEXT,
                    status TEXT DEFAULT 'visited',
                    review TEXT,
                    address TEXT,
                    description TEXT,
                    latitude REAL,
                    longitude REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            # Добавляем новые колонки если таблица уже существует (миграция)
            try:
                await db.execute('ALTER TABLE places ADD COLUMN status TEXT DEFAULT "visited"')
            except:
                pass  # Колонка уже существует
            
            try:
                await db.execute('ALTER TABLE places ADD COLUMN review TEXT')
            except:
                pass  # Колонка уже существует
            
            try:
                await db.execute('ALTER TABLE places ADD COLUMN social_link TEXT')
            except:
                pass  # Колонка уже существует
            
            try:
                await db.execute('ALTER TABLE places ADD COLUMN cuisine TEXT')
            except:
                pass  # Колонка уже существует
            
            try:
                await db.execute('ALTER TABLE places ADD COLUMN working_hours TEXT')
            except:
                pass  # Колонка уже существует
            
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
            await db.execute('''
                CREATE INDEX IF NOT EXISTS idx_status ON places(status)
            ''')
            
            # Таблица для чаевых (смен)
            await db.execute('''
                CREATE TABLE IF NOT EXISTS tips (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    tips_date TEXT NOT NULL,
                    card_amount REAL DEFAULT 0,
                    netmonet_amount REAL DEFAULT 0,
                    cash_amount REAL DEFAULT 0,
                    total_amount REAL NOT NULL,
                    hours_worked REAL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Добавляем новую колонку если таблица уже существует (миграция)
            try:
                await db.execute('ALTER TABLE tips ADD COLUMN hours_worked REAL DEFAULT 0')
            except:
                pass  # Колонка уже существует
            
            # Индексы для таблицы чаевых
            await db.execute('''
                CREATE INDEX IF NOT EXISTS idx_tips_user_id ON tips(user_id)
            ''')
            await db.execute('''
                CREATE INDEX IF NOT EXISTS idx_tips_date ON tips(tips_date DESC)
            ''')
            
            # Таблица для продаж Авито
            await db.execute('''
                CREATE TABLE IF NOT EXISTS avito_sales (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    item_name TEXT NOT NULL,
                    amount REAL NOT NULL,
                    sale_date TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Индексы для таблицы Авито
            await db.execute('''
                CREATE INDEX IF NOT EXISTS idx_avito_user_id ON avito_sales(user_id)
            ''')
            await db.execute('''
                CREATE INDEX IF NOT EXISTS idx_avito_date ON avito_sales(sale_date DESC)
            ''')
            
            # Таблица для трат
            await db.execute('''
                CREATE TABLE IF NOT EXISTS expenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    category TEXT NOT NULL,
                    name TEXT NOT NULL,
                    amount REAL NOT NULL,
                    expense_date TEXT NOT NULL,
                    note TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Индексы для таблицы трат
            await db.execute('''
                CREATE INDEX IF NOT EXISTS idx_expenses_user_id ON expenses(user_id)
            ''')
            await db.execute('''
                CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(expense_date DESC)
            ''')
            await db.execute('''
                CREATE INDEX IF NOT EXISTS idx_expenses_category ON expenses(category)
            ''')
            
            # Таблица для обязательных расходов
            await db.execute('''
                CREATE TABLE IF NOT EXISTS recurring_expenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    amount REAL NOT NULL,
                    payment_date TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Индексы для таблицы обязательных расходов
            await db.execute('''
                CREATE INDEX IF NOT EXISTS idx_recurring_expenses_user_id ON recurring_expenses(user_id)
            ''')
            await db.execute('''
                CREATE INDEX IF NOT EXISTS idx_recurring_expenses_date ON recurring_expenses(payment_date)
            ''')
            
            # Таблица для фильмов
            await db.execute('''
                CREATE TABLE IF NOT EXISTS movies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    genre TEXT,
                    year INTEGER,
                    overview TEXT,
                    status TEXT NOT NULL,
                    rating INTEGER,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Миграция: добавляем поле overview если его нет
            try:
                await db.execute('ALTER TABLE movies ADD COLUMN overview TEXT')
            except:
                pass  # Поле уже существует
            
            await db.execute('''
                CREATE INDEX IF NOT EXISTS idx_movies_user_id ON movies(user_id)
            ''')
            
            # Таблица для сериалов
            await db.execute('''
                CREATE TABLE IF NOT EXISTS series (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    genre TEXT,
                    year INTEGER,
                    overview TEXT,
                    seasons INTEGER,
                    episodes INTEGER,
                    status TEXT NOT NULL,
                    rating INTEGER,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Миграция: добавляем новые поля для series если их нет
            try:
                await db.execute('ALTER TABLE series ADD COLUMN overview TEXT')
            except:
                pass  # Поле уже существует
            try:
                await db.execute('ALTER TABLE series ADD COLUMN seasons INTEGER')
            except:
                pass  # Поле уже существует
            try:
                await db.execute('ALTER TABLE series ADD COLUMN episodes INTEGER')
            except:
                pass  # Поле уже существует
            
            await db.execute('''
                CREATE INDEX IF NOT EXISTS idx_series_user_id ON series(user_id)
            ''')
            
            # Таблица для подкастов
            await db.execute('''
                CREATE TABLE IF NOT EXISTS podcasts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    author TEXT,
                    status TEXT NOT NULL,
                    rating INTEGER,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            await db.execute('''
                CREATE INDEX IF NOT EXISTS idx_podcasts_user_id ON podcasts(user_id)
            ''')
            
            # Таблица заметок
            await db.execute('''
                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    category TEXT NOT NULL,
                    text TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            await db.execute('''
                CREATE INDEX IF NOT EXISTS idx_notes_user_id ON notes(user_id)
            ''')
            
            await db.execute('''
                CREATE INDEX IF NOT EXISTS idx_notes_category ON notes(category)
            ''')
            
            # Таблица вишлиста
            await db.execute('''
                CREATE TABLE IF NOT EXISTS wishlist (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    size_category TEXT NOT NULL,
                    type_category TEXT NOT NULL,
                    price REAL,
                    priority TEXT,
                    photo_url TEXT,
                    link TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            await db.execute('''
                CREATE INDEX IF NOT EXISTS idx_wishlist_user_id ON wishlist(user_id)
            ''')
            
            await db.execute('''
                CREATE INDEX IF NOT EXISTS idx_wishlist_priority ON wishlist(priority)
            ''')
            
            await db.commit()
            logger.info("База данных инициализирована")
        except Exception as e:
            logger.error(f"Ошибка при инициализации БД: {e}")
            raise
    
    async def add_place(self, user_id: int, name: str, place_type: str = None,
                       price_category: str = None, status: str = 'visited', 
                       review: str = None, address: str = None, 
                       description: str = None, latitude: float = None, 
                       longitude: float = None, social_link: str = None, cuisine: str = None,
                       working_hours: str = None):
        """Добавить новое место"""
        try:
            db = await self.connect()
            cursor = await db.execute('''
                INSERT INTO places (user_id, name, place_type, price_category, status, review, address, description, latitude, longitude, social_link, cuisine, working_hours)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, name, place_type, price_category, status, review, address, description, latitude, longitude, social_link, cuisine, working_hours))
            await db.commit()
            return cursor.lastrowid
        except Exception as e:
            logger.error(f"Ошибка при добавлении места: {e}")
            return None
    
    async def get_user_places(self, user_id: int, place_type: str = None, status: str = None, limit: int = None, offset: int = 0):
        """Получить места пользователя с пагинацией"""
        try:
            db = await self.connect()
            # Строим запрос с учетом фильтров
            conditions = ["user_id = ?"]
            params = [user_id]
            
            if place_type:
                conditions.append("place_type = ?")
                params.append(place_type)
            
            if status:
                conditions.append("status = ?")
                params.append(status)
            
            query = f"SELECT * FROM places WHERE {' AND '.join(conditions)} ORDER BY created_at DESC"
            
            if limit:
                query += ' LIMIT ? OFFSET ?'
                params = params + [limit, offset]
            
            async with db.execute(query, tuple(params)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка при получении мест: {e}")
            return []
    
    async def get_place(self, place_id: int, user_id: int):
        """Получить конкретное место"""
        try:
            db = await self.connect()
            async with db.execute(
                'SELECT * FROM places WHERE id = ? AND user_id = ?',
                (place_id, user_id)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Ошибка при получении места: {e}")
            return None
    
    async def update_place(self, place_id: int, user_id: int, **kwargs):
        """Обновить место"""
        try:
            db = await self.connect()
            # Формируем SET часть запроса только для переданных полей
            set_parts = []
            values = []
            for key, value in kwargs.items():
                if value is not None:
                    set_parts.append(f"{key} = ?")
                    values.append(value)
            
            if not set_parts:
                return False
            
            values.extend([place_id, user_id])
            query = f"UPDATE places SET {', '.join(set_parts)} WHERE id = ? AND user_id = ?"
            await db.execute(query, values)
            await db.commit()
            return True
        except Exception as e:
            logger.error(f"Ошибка при обновлении места: {e}")
            return False
    
    async def delete_place(self, place_id: int, user_id: int):
        """Удалить место"""
        try:
            db = await self.connect()
            await db.execute(
                'DELETE FROM places WHERE id = ? AND user_id = ?',
                (place_id, user_id)
            )
            await db.commit()
        except Exception as e:
            logger.error(f"Ошибка при удалении места: {e}")
    
    async def search_places(self, user_id: int, query: str):
        """Поиск мест по названию, адресу, описанию или типу"""
        try:
            db = await self.connect()
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
    
    async def count_user_places(self, user_id: int, place_type: str = None, status: str = None):
        """Подсчитать количество мест пользователя"""
        try:
            db = await self.connect()
            # Строим запрос с учетом фильтров
            conditions = ["user_id = ?"]
            params = [user_id]
            
            if place_type:
                conditions.append("place_type = ?")
                params.append(place_type)
            
            if status:
                conditions.append("status = ?")
                params.append(status)
            
            query = f"SELECT COUNT(*) as count FROM places WHERE {' AND '.join(conditions)}"
            
            async with db.execute(query, tuple(params)) as cursor:
                row = await cursor.fetchone()
                return row['count'] if row else 0
        except Exception as e:
            logger.error(f"Ошибка при подсчете мест: {e}")
            return 0
    
    # ===== ФУНКЦИИ ДЛЯ ЧАЕВЫХ =====
    
    async def add_tips(self, user_id: int, tips_date: str, card_amount: float = 0,
                      netmonet_amount: float = 0, cash_amount: float = 0, total_amount: float = 0,
                      hours_worked: float = 0):
        """Добавить запись о чаевых (смене)"""
        try:
            db = await self.connect()
            cursor = await db.execute('''
                INSERT INTO tips (user_id, tips_date, card_amount, netmonet_amount, cash_amount, total_amount, hours_worked)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, tips_date, card_amount, netmonet_amount, cash_amount, total_amount, hours_worked))
            await db.commit()
            return cursor.lastrowid
        except Exception as e:
            logger.error(f"Ошибка при добавлении чаевых: {e}")
            return None
    
    async def get_user_tips(self, user_id: int, limit: int = None, offset: int = 0):
        """Получить все чаевые пользователя"""
        try:
            db = await self.connect()
            query = 'SELECT * FROM tips WHERE user_id = ? ORDER BY tips_date DESC, created_at DESC'
            if limit:
                query += f' LIMIT {limit} OFFSET {offset}'
            
            async with db.execute(query, (user_id,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка при получении чаевых: {e}")
            return []
    
    async def count_user_tips(self, user_id: int):
        """Подсчитать количество записей о чаевых"""
        try:
            db = await self.connect()
            async with db.execute('SELECT COUNT(*) as count FROM tips WHERE user_id = ?', (user_id,)) as cursor:
                row = await cursor.fetchone()
                return row['count'] if row else 0
        except Exception as e:
            logger.error(f"Ошибка при подсчете чаевых: {e}")
            return 0
    
    async def get_tips_stats(self, user_id: int):
        """Получить статистику по чаевым"""
        try:
            db = await self.connect()
            async with db.execute('''
                SELECT 
                    COUNT(*) as shifts_count,
                    SUM(card_amount) as total_card,
                    SUM(netmonet_amount) as total_netmonet,
                    SUM(cash_amount) as total_cash,
                    SUM(total_amount) as total_tips,
                    AVG(total_amount) as avg_tips
                FROM tips WHERE user_id = ?
            ''', (user_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Ошибка при получении статистики чаевых: {e}")
            return None
    
    async def delete_tips(self, tips_id: int, user_id: int):
        """Удалить запись о чаевых"""
        try:
            db = await self.connect()
            await db.execute(
                'DELETE FROM tips WHERE id = ? AND user_id = ?',
                (tips_id, user_id)
            )
            await db.commit()
        except Exception as e:
            logger.error(f"Ошибка при удалении чаевых: {e}")
    
    async def get_tips_months(self, user_id: int):
        """Получить список месяцев с чаевыми"""
        try:
            db = await self.connect()
            # Извлекаем уникальные месяцы из дат (формат DD.MM.YYYY)
            async with db.execute('''
                SELECT DISTINCT substr(tips_date, 4, 7) as month_year
                FROM tips 
                WHERE user_id = ?
                ORDER BY substr(tips_date, 7, 4) DESC, substr(tips_date, 4, 2) DESC
            ''', (user_id,)) as cursor:
                rows = await cursor.fetchall()
                return [row['month_year'] for row in rows]
        except Exception as e:
            logger.error(f"Ошибка при получении месяцев: {e}")
            return []
    
    async def get_tips_stats_by_month(self, user_id: int, month_year: str):
        """Получить статистику по чаевым (сменам) за месяц (формат MM.YYYY)"""
        try:
            db = await self.connect()
            # Ищем записи где дата содержит месяц и год
            async with db.execute('''
                SELECT 
                    COUNT(*) as shifts_count,
                    SUM(card_amount) as total_card,
                    SUM(netmonet_amount) as total_netmonet,
                    SUM(cash_amount) as total_cash,
                    SUM(total_amount) as total_tips,
                    SUM(hours_worked) as total_hours,
                    AVG(total_amount) as avg_tips
                FROM tips 
                WHERE user_id = ? AND substr(tips_date, 4, 7) = ?
            ''', (user_id, month_year)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Ошибка при получении статистики за месяц: {e}")
            return None
    
    async def get_tips_stats_by_period(self, user_id: int, start_date: str, end_date: str):
        """Получить статистику по чаевым за период (формат DD.MM.YYYY)"""
        try:
            db = await self.connect()
            async with db.execute('''
                SELECT 
                    COUNT(*) as shifts_count,
                    SUM(card_amount) as total_card,
                    SUM(netmonet_amount) as total_netmonet,
                    SUM(cash_amount) as total_cash,
                    SUM(total_amount) as total_tips,
                    SUM(hours_worked) as total_hours,
                    AVG(total_amount) as avg_tips
                FROM tips 
                WHERE user_id = ? AND tips_date >= ? AND tips_date <= ?
            ''', (user_id, start_date, end_date)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Ошибка при получении статистики за период: {e}")
            return None
    
    async def get_all_users(self):
        """Получить список всех пользователей с записями о чаевых"""
        try:
            db = await self.connect()
            async with db.execute('SELECT DISTINCT user_id FROM tips') as cursor:
                rows = await cursor.fetchall()
                return [row['user_id'] for row in rows]
        except Exception as e:
            logger.error(f"Ошибка при получении пользователей: {e}")
            return []
    
    # ===== ФУНКЦИИ ДЛЯ АВИТО =====
    
    async def add_avito_sale(self, user_id: int, item_name: str, amount: float, sale_date: str):
        """Добавить продажу на Авито"""
        try:
            db = await self.connect()
            cursor = await db.execute('''
                INSERT INTO avito_sales (user_id, item_name, amount, sale_date)
                VALUES (?, ?, ?, ?)
            ''', (user_id, item_name, amount, sale_date))
            await db.commit()
            return cursor.lastrowid
        except Exception as e:
            logger.error(f"Ошибка при добавлении продажи Авито: {e}")
            return None
    
    async def get_user_avito_sales(self, user_id: int, limit: int = None, offset: int = 0):
        """Получить все продажи пользователя"""
        try:
            db = await self.connect()
            query = 'SELECT * FROM avito_sales WHERE user_id = ? ORDER BY sale_date DESC, created_at DESC'
            if limit:
                query += f' LIMIT {limit} OFFSET {offset}'
            
            async with db.execute(query, (user_id,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка при получении продаж Авито: {e}")
            return []
    
    async def count_user_avito_sales(self, user_id: int):
        """Подсчитать количество продаж"""
        try:
            db = await self.connect()
            async with db.execute('SELECT COUNT(*) as count FROM avito_sales WHERE user_id = ?', (user_id,)) as cursor:
                row = await cursor.fetchone()
                return row['count'] if row else 0
        except Exception as e:
            logger.error(f"Ошибка при подсчете продаж Авито: {e}")
            return 0
    
    async def get_avito_stats(self, user_id: int):
        """Получить общую статистику по Авито"""
        try:
            db = await self.connect()
            async with db.execute('''
                SELECT 
                    COUNT(*) as sales_count,
                    SUM(amount) as total_amount,
                    AVG(amount) as avg_amount
                FROM avito_sales WHERE user_id = ?
            ''', (user_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Ошибка при получении статистики Авито: {e}")
            return None
    
    async def delete_avito_sale(self, sale_id: int, user_id: int):
        """Удалить продажу"""
        try:
            db = await self.connect()
            await db.execute(
                'DELETE FROM avito_sales WHERE id = ? AND user_id = ?',
                (sale_id, user_id)
            )
            await db.commit()
        except Exception as e:
            logger.error(f"Ошибка при удалении продажи Авито: {e}")
    
    # ===== ФУНКЦИИ ДЛЯ РАСХОДОВ =====
    
    async def add_expense(self, user_id: int, category: str, name: str, amount: float, expense_date: str, note: str = None):
        """Добавить трату"""
        try:
            db = await self.connect()
            cursor = await db.execute('''
                INSERT INTO expenses (user_id, category, name, amount, expense_date, note)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, category, name, amount, expense_date, note))
            await db.commit()
            return cursor.lastrowid
        except Exception as e:
            logger.error(f"Ошибка при добавлении траты: {e}")
            return None
    
    async def get_user_expenses(self, user_id: int, limit: int = None, offset: int = 0):
        """Получить траты пользователя"""
        try:
            db = await self.connect()
            query = 'SELECT * FROM expenses WHERE user_id = ? ORDER BY expense_date DESC, created_at DESC'
            if limit:
                query += f' LIMIT {limit} OFFSET {offset}'
            
            async with db.execute(query, (user_id,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка при получении трат: {e}")
            return []
    
    async def get_expenses_by_category(self, user_id: int, month_year: str):
        """Получить траты по категориям за месяц"""
        try:
            db = await self.connect()
            async with db.execute('''
                SELECT category, SUM(amount) as total
                FROM expenses
                WHERE user_id = ? AND substr(expense_date, 4, 7) = ?
                GROUP BY category
            ''', (user_id, month_year)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка при получении трат по категориям: {e}")
            return []
    
    async def add_recurring_expense(self, user_id: int, name: str, amount: float, payment_date: str):
        """Добавить обязательный расход"""
        try:
            db = await self.connect()
            cursor = await db.execute('''
                INSERT INTO recurring_expenses (user_id, name, amount, payment_date)
                VALUES (?, ?, ?, ?)
            ''', (user_id, name, amount, payment_date))
            await db.commit()
            return cursor.lastrowid
        except Exception as e:
            logger.error(f"Ошибка при добавлении обязательного расхода: {e}")
            return None
    
    async def get_user_recurring_expenses(self, user_id: int):
        """Получить обязательные расходы пользователя"""
        try:
            db = await self.connect()
            async with db.execute('''
                SELECT * FROM recurring_expenses 
                WHERE user_id = ? 
                ORDER BY payment_date
            ''', (user_id,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка при получении обязательных расходов: {e}")
            return []
    
    # ===== ФУНКЦИИ ДЛЯ МЕДИА =====
    
    async def add_movie(self, user_id: int, title: str, genre: str, year: int, overview: str, status: str, rating: int = None, notes: str = None):
        """Добавить фильм"""
        try:
            db = await self.connect()
            cursor = await db.execute('''
                INSERT INTO movies (user_id, title, genre, year, overview, status, rating, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, title, genre, year, overview, status, rating, notes))
            await db.commit()
            return cursor.lastrowid
        except Exception as e:
            logger.error(f"Ошибка при добавлении фильма: {e}")
            return None
    
    async def get_user_movies(self, user_id: int):
        """Получить фильмы пользователя"""
        try:
            db = await self.connect()
            async with db.execute('''
                SELECT * FROM movies 
                WHERE user_id = ? 
                ORDER BY created_at DESC
            ''', (user_id,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка при получении фильмов: {e}")
            return []
    
    async def get_movie_stats(self, user_id: int):
        """Получить статистику фильмов"""
        try:
            db = await self.connect()
            async with db.execute('''
                SELECT 
                    COUNT(*) as total_count,
                    COUNT(CASE WHEN status = '✅ Просмотрел' THEN 1 END) as watched_count,
                    ROUND(AVG(CASE WHEN rating IS NOT NULL THEN rating END), 1) as avg_rating
                FROM movies
                WHERE user_id = ?
            ''', (user_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Ошибка при получении статистики фильмов: {e}")
            return None
    
    async def add_series(self, user_id: int, title: str, genre: str, year: int, overview: str, seasons: int, episodes: int, status: str, rating: int = None, notes: str = None):
        """Добавить сериал"""
        try:
            db = await self.connect()
            cursor = await db.execute('''
                INSERT INTO series (user_id, title, genre, year, overview, seasons, episodes, status, rating, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, title, genre, year, overview, seasons, episodes, status, rating, notes))
            await db.commit()
            return cursor.lastrowid
        except Exception as e:
            logger.error(f"Ошибка при добавлении сериала: {e}")
            return None
    
    async def get_user_series(self, user_id: int):
        """Получить сериалы пользователя"""
        try:
            db = await self.connect()
            async with db.execute('''
                SELECT * FROM series 
                WHERE user_id = ? 
                ORDER BY created_at DESC
            ''', (user_id,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка при получении сериалов: {e}")
            return []
    
    async def get_series_stats(self, user_id: int):
        """Получить статистику сериалов"""
        try:
            db = await self.connect()
            async with db.execute('''
                SELECT 
                    COUNT(*) as total_count,
                    COUNT(CASE WHEN status = '⏳ Смотрю' THEN 1 END) as watching_count,
                    COUNT(CASE WHEN status = '✅ Просмотрел' THEN 1 END) as watched_count,
                    ROUND(AVG(CASE WHEN rating IS NOT NULL THEN rating END), 1) as avg_rating
                FROM series
                WHERE user_id = ?
            ''', (user_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Ошибка при получении статистики сериалов: {e}")
            return None
    
    async def add_podcast(self, user_id: int, title: str, author: str, status: str, rating: int = None, notes: str = None):
        """Добавить подкаст"""
        try:
            db = await self.connect()
            cursor = await db.execute('''
                INSERT INTO podcasts (user_id, title, author, status, rating, notes)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, title, author, status, rating, notes))
            await db.commit()
            return cursor.lastrowid
        except Exception as e:
            logger.error(f"Ошибка при добавлении подкаста: {e}")
            return None
    
    async def get_user_podcasts(self, user_id: int):
        """Получить подкасты пользователя"""
        try:
            db = await self.connect()
            async with db.execute('''
                SELECT * FROM podcasts 
                WHERE user_id = ? 
                ORDER BY created_at DESC
            ''', (user_id,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка при получении подкастов: {e}")
            return []
    
    async def get_podcast_stats(self, user_id: int):
        """Получить статистику подкастов"""
        try:
            db = await self.connect()
            async with db.execute('''
                SELECT 
                    COUNT(*) as total_count,
                    COUNT(CASE WHEN status = '✅ Просмотрел' THEN 1 END) as listened_count,
                    ROUND(AVG(CASE WHEN rating IS NOT NULL THEN rating END), 1) as avg_rating
                FROM podcasts
                WHERE user_id = ?
            ''', (user_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Ошибка при получении статистики подкастов: {e}")
            return None
    
    async def update_movie_status(self, movie_id: int, user_id: int, new_status: str):
        """Обновить статус фильма"""
        try:
            db = await self.connect()
            await db.execute('UPDATE movies SET status = ? WHERE id = ? AND user_id = ?', (new_status, movie_id, user_id))
            await db.commit()
            return True
        except Exception as e:
            logger.error(f"Ошибка при обновлении статуса фильма: {e}")
            return False
    
    async def update_series_status(self, series_id: int, user_id: int, new_status: str):
        """Обновить статус сериала"""
        try:
            db = await self.connect()
            await db.execute('UPDATE series SET status = ? WHERE id = ? AND user_id = ?', (new_status, series_id, user_id))
            await db.commit()
            return True
        except Exception as e:
            logger.error(f"Ошибка при обновлении статуса сериала: {e}")
            return False
    
    async def delete_movie(self, movie_id: int, user_id: int):
        """Удалить фильм"""
        try:
            db = await self.connect()
            await db.execute('DELETE FROM movies WHERE id = ? AND user_id = ?', (movie_id, user_id))
            await db.commit()
            return True
        except Exception as e:
            logger.error(f"Ошибка при удалении фильма: {e}")
            return False
    
    async def delete_series(self, series_id: int, user_id: int):
        """Удалить сериал"""
        try:
            db = await self.connect()
            await db.execute('DELETE FROM series WHERE id = ? AND user_id = ?', (series_id, user_id))
            await db.commit()
            return True
        except Exception as e:
            logger.error(f"Ошибка при удалении сериала: {e}")
            return False
    
    async def delete_podcast(self, podcast_id: int, user_id: int):
        """Удалить подкаст"""
        try:
            db = await self.connect()
            await db.execute('DELETE FROM podcasts WHERE id = ? AND user_id = ?', (podcast_id, user_id))
            await db.commit()
            return True
        except Exception as e:
            logger.error(f"Ошибка при удалении подкаста: {e}")
            return False
    
    # ==================== ЗАМЕТКИ ====================
    
    async def add_note(self, user_id: int, category: str, text: str):
        """Добавить заметку"""
        try:
            db = await self.connect()
            cursor = await db.execute(
                'INSERT INTO notes (user_id, category, text) VALUES (?, ?, ?)',
                (user_id, category, text)
            )
            await db.commit()
            return cursor.lastrowid
        except Exception as e:
            logger.error(f"Ошибка при добавлении заметки: {e}")
            return None
    
    async def get_user_notes(self, user_id: int, limit: int = None, offset: int = 0, category: str = None):
        """Получить заметки пользователя"""
        try:
            db = await self.connect()
            query = 'SELECT * FROM notes WHERE user_id = ?'
            params = [user_id]
            
            if category:
                query += ' AND category = ?'
                params.append(category)
            
            query += ' ORDER BY created_at DESC'
            
            if limit:
                query += ' LIMIT ? OFFSET ?'
                params.extend([limit, offset])
            
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка при получении заметок: {e}")
            return []
    
    async def count_user_notes(self, user_id: int, category: str = None):
        """Подсчитать количество заметок"""
        try:
            db = await self.connect()
            query = 'SELECT COUNT(*) as count FROM notes WHERE user_id = ?'
            params = [user_id]
            
            if category:
                query += ' AND category = ?'
                params.append(category)
            
            async with db.execute(query, params) as cursor:
                row = await cursor.fetchone()
                return row['count'] if row else 0
        except Exception as e:
            logger.error(f"Ошибка при подсчёте заметок: {e}")
            return 0
    
    async def search_notes(self, user_id: int, search_text: str):
        """Поиск заметок по тексту"""
        try:
            db = await self.connect()
            async with db.execute(
                'SELECT * FROM notes WHERE user_id = ? AND text LIKE ? ORDER BY created_at DESC',
                (user_id, f'%{search_text}%')
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка при поиске заметок: {e}")
            return []
    
    async def update_note(self, note_id: int, user_id: int, new_text: str):
        """Обновить текст заметки"""
        try:
            db = await self.connect()
            await db.execute(
                'UPDATE notes SET text = ? WHERE id = ? AND user_id = ?',
                (new_text, note_id, user_id)
            )
            await db.commit()
            return True
        except Exception as e:
            logger.error(f"Ошибка при обновлении заметки: {e}")
            return False
    
    async def delete_note(self, note_id: int, user_id: int):
        """Удалить заметку"""
        try:
            db = await self.connect()
            await db.execute('DELETE FROM notes WHERE id = ? AND user_id = ?', (note_id, user_id))
            await db.commit()
            return True
        except Exception as e:
            logger.error(f"Ошибка при удалении заметки: {e}")
            return False
    
    # ==================== ВИШЛИСТ ====================
    
    async def add_wishlist_item(self, user_id: int, name: str, size_category: str, 
                               type_category: str, price: float = None, priority: str = None,
                               photo_url: str = None, link: str = None):
        """Добавить элемент в вишлист"""
        try:
            db = await self.connect()
            cursor = await db.execute('''
                INSERT INTO wishlist (user_id, name, size_category, type_category, price, priority, photo_url, link)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, name, size_category, type_category, price, priority, photo_url, link))
            await db.commit()
            return cursor.lastrowid
        except Exception as e:
            logger.error(f"Ошибка при добавлении в вишлист: {e}")
            return None
    
    async def get_user_wishlist(self, user_id: int, size_category: str = None, priority: str = None):
        """Получить вишлист пользователя"""
        try:
            db = await self.connect()
            
            query = 'SELECT * FROM wishlist WHERE user_id = ?'
            params = [user_id]
            
            if size_category:
                query += ' AND size_category = ?'
                params.append(size_category)
            
            if priority:
                query += ' AND priority = ?'
                params.append(priority)
            
            query += ' ORDER BY created_at DESC'
            
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка при получении вишлиста: {e}")
            return []
    
    async def delete_wishlist_item(self, item_id: int, user_id: int):
        """Удалить элемент из вишлиста"""
        try:
            db = await self.connect()
            await db.execute('DELETE FROM wishlist WHERE id = ? AND user_id = ?', (item_id, user_id))
            await db.commit()
            return True
        except Exception as e:
            logger.error(f"Ошибка при удалении из вишлиста: {e}")
            return False
    
    async def count_user_wishlist(self, user_id: int, size_category: str = None):
        """Подсчитать количество элементов в вишлисте"""
        try:
            db = await self.connect()
            
            query = 'SELECT COUNT(*) as count FROM wishlist WHERE user_id = ?'
            params = [user_id]
            
            if size_category:
                query += ' AND size_category = ?'
                params.append(size_category)
            
            async with db.execute(query, params) as cursor:
                row = await cursor.fetchone()
                return row['count'] if row else 0
        except Exception as e:
            logger.error(f"Ошибка при подсчёте вишлиста: {e}")
            return 0

