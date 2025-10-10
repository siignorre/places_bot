import gspread
import logging
from google.oauth2.service_account import Credentials
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

class GoogleSheetsSync:
    """Синхронизация с Google Sheets"""
    
    def __init__(self, credentials_file: str = 'credentials.json', spreadsheet_name: str = 'Places Bot Data'):
        self.credentials_file = Path(credentials_file)
        self.spreadsheet_name = spreadsheet_name
        self.client = None
        self.spreadsheet = None
        self.enabled = False
        
    def connect(self):
        """Быстрое подключение к Google Sheets (без проверки листов)"""
        try:
            if not self.credentials_file.exists():
                logger.warning("⚠️ Файл credentials.json не найден. Google Sheets синхронизация отключена.")
                return False
            
            # Настройка авторизации
            scope = [
                'https://spreadsheets.google.com/feeds',
                'https://www.googleapis.com/auth/drive'
            ]
            
            creds = Credentials.from_service_account_file(
                str(self.credentials_file),
                scopes=scope
            )
            
            self.client = gspread.authorize(creds)
            
            # Быстрое подключение - только открываем таблицу
            try:
                self.spreadsheet = self.client.open(self.spreadsheet_name)
                logger.info(f"⚡ Быстрое подключение к таблице: {self.spreadsheet_name}")
            except gspread.SpreadsheetNotFound:
                self.spreadsheet = self.client.create(self.spreadsheet_name)
                logger.info(f"📊 Создана новая таблица: {self.spreadsheet_name}")
            
            self.enabled = True
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к Google Sheets: {e}")
            self.enabled = False
            return False
    
    def lazy_init_sheets(self):
        """Ленивая инициализация листов в фоне (проверка и создание)"""
        if not self.enabled:
            return
        
        try:
            sheets_to_check = {
                "Места": self._init_places_sheet,
                "Чаевые": self._init_tips_sheet,
                "Авито": self._init_avito_sheet,
                "Траты": self._init_expenses_sheet,
                "Обязательные расходы": self._init_recurring_expenses_sheet,
                "Медиа": self._init_media_sheet,
                "Заметки": self._init_notes_sheet
            }
            
            for sheet_name, init_func in sheets_to_check.items():
                try:
                    self.spreadsheet.worksheet(sheet_name)
                    logger.info(f"✅ Лист '{sheet_name}' найден")
                except gspread.WorksheetNotFound:
                    logger.info(f"📝 Лист '{sheet_name}' не найден, создаём...")
                    init_func()
            
            logger.info("🎉 Все листы Google Sheets готовы!")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при инициализации листов: {e}")
    
    def _init_sheets(self):
        """Инициализация всех листов таблицы"""
        self._init_places_sheet()
        self._init_tips_sheet()
        self._init_avito_sheet()
        self._init_expenses_sheet()
        self._init_recurring_expenses_sheet()
        self._init_media_sheet()
    
    def _init_places_sheet(self):
        """Инициализация листа 'Места'"""
        try:
            # Лист для мест
            places_sheet = self.spreadsheet.add_worksheet(title="Места", rows=1000, cols=10)
            places_sheet.append_row([
                'ID', 'Название', 'Тип', 'Цена', 'Статус', 'Рецензия',
                'Адрес', 'Описание', 'Соц.сеть', 'Дата добавления'
            ])
            
            # Форматирование заголовков
            places_sheet.format('A1:J1', {
                'textFormat': {'bold': True},
                'backgroundColor': {'red': 0.8, 'green': 0.8, 'blue': 0.8}
            })
            
            # Скрываем столбец ID (столбец A)
            try:
                self.spreadsheet.batch_update({
                    'requests': [{
                        'updateDimensionProperties': {
                            'range': {
                                'sheetId': places_sheet.id,
                                'dimension': 'COLUMNS',
                                'startIndex': 0,  # Столбец A (ID)
                                'endIndex': 1
                            },
                            'properties': {
                                'hiddenByUser': True
                            },
                            'fields': 'hiddenByUser'
                        }
                    }]
                })
                logger.info("🔒 Столбец ID (Места) скрыт")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось скрыть столбец ID: {e}")
            
            logger.info("✅ Лист 'Места' инициализирован")
        except Exception as e:
            logger.error(f"❌ Ошибка при инициализации листа 'Места': {e}")
    
    def _init_tips_sheet(self):
        """Инициализация листа 'Чаевые'"""
        try:
            # Лист для чаевых
            tips_sheet = self.spreadsheet.add_worksheet(title="Чаевые", rows=1000, cols=7)
            tips_sheet.append_row([
                'ID', 'Дата', 'Карты', 'Нет.Монет', 'Наличные', 'Итого', 'Дата добавления'
            ])
            
            # Форматирование заголовков
            tips_sheet.format('A1:G1', {
                'textFormat': {'bold': True},
                'backgroundColor': {'red': 0.8, 'green': 0.8, 'blue': 0.8}
            })
            
            # Добавляем строку с формулами внизу (строка 1000)
            # Формулы будут считать суммы по столбцам C, D, E, F (Карты, Нет.Монет, Наличные, Итого)
            # И количество смен (COUNT) в столбце B
            tips_sheet.update('A1000', [['ИТОГО:']])
            tips_sheet.update('B1000', [['=COUNTA(B2:B999)']])  # Количество смен
            tips_sheet.update('C1000', [['=SUM(C2:C999)']])  # Сумма карт
            tips_sheet.update('D1000', [['=SUM(D2:D999)']])  # Сумма Нет.Монет
            tips_sheet.update('E1000', [['=SUM(E2:E999)']])  # Сумма наличных
            tips_sheet.update('F1000', [['=SUM(F2:F999)']])  # Итого
            
            # Форматирование строки с формулами (жирный шрифт, желтый фон)
            tips_sheet.format('A1000:G1000', {
                'textFormat': {'bold': True},
                'backgroundColor': {'red': 1.0, 'green': 0.95, 'blue': 0.8}
            })
            
            # Скрываем столбец ID (столбец A)
            try:
                self.spreadsheet.batch_update({
                    'requests': [{
                        'updateDimensionProperties': {
                            'range': {
                                'sheetId': tips_sheet.id,
                                'dimension': 'COLUMNS',
                                'startIndex': 0,  # Столбец A (ID)
                                'endIndex': 1
                            },
                            'properties': {
                                'hiddenByUser': True
                            },
                            'fields': 'hiddenByUser'
                        }
                    }]
                })
                logger.info("🔒 Столбец ID (Чаевые) скрыт")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось скрыть столбец ID: {e}")
            
            logger.info("✅ Лист 'Чаевые' инициализирован с формулами")
        except Exception as e:
            logger.error(f"❌ Ошибка при инициализации листа 'Чаевые': {e}")
    
    def _init_avito_sheet(self):
        """Инициализация листа 'Авито'"""
        try:
            # Лист для Авито
            avito_sheet = self.spreadsheet.add_worksheet(title="Авито", rows=1000, cols=5)
            avito_sheet.append_row([
                'ID', 'Название вещи', 'Сумма продажи', 'Дата продажи', 'Дата добавления'
            ])
            
            # Форматирование заголовков
            avito_sheet.format('A1:E1', {
                'textFormat': {'bold': True},
                'backgroundColor': {'red': 0.8, 'green': 0.8, 'blue': 0.8}
            })
            
            # Добавляем строку с формулами внизу (строка 1000)
            avito_sheet.update('A1000', [['ИТОГО:']])
            avito_sheet.update('B1000', [['=COUNTA(B2:B999)']])  # Количество вещей
            avito_sheet.update('C1000', [['=SUM(C2:C999)']])  # Общая сумма
            
            # Форматирование строки с формулами
            avito_sheet.format('A1000:E1000', {
                'textFormat': {'bold': True},
                'backgroundColor': {'red': 1.0, 'green': 0.95, 'blue': 0.8}
            })
            
            # Скрываем столбец ID (столбец A)
            try:
                self.spreadsheet.batch_update({
                    'requests': [{
                        'updateDimensionProperties': {
                            'range': {
                                'sheetId': avito_sheet.id,
                                'dimension': 'COLUMNS',
                                'startIndex': 0,  # Столбец A (ID)
                                'endIndex': 1
                            },
                            'properties': {
                                'hiddenByUser': True
                            },
                            'fields': 'hiddenByUser'
                        }
                    }]
                })
                logger.info("🔒 Столбец ID (Авито) скрыт")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось скрыть столбец ID: {e}")
            
            logger.info("✅ Лист 'Авито' инициализирован с формулами")
        except Exception as e:
            logger.error(f"❌ Ошибка при инициализации листа 'Авито': {e}")
    
    def add_place(self, user_id: int, user_name: str, place_data: dict):
        """Добавить место в таблицу"""
        if not self.enabled:
            return False
        
        try:
            sheet = self.spreadsheet.worksheet("Места")
            
            # Преобразуем статус в читаемый формат
            status = place_data.get('status', 'visited')
            status_text = '✅ Посещено' if status == 'visited' else '📅 Планирую'
            
            row = [
                place_data.get('id', ''),
                place_data.get('name', ''),
                place_data.get('place_type', ''),
                place_data.get('price_category', ''),
                status_text,
                place_data.get('review', ''),
                place_data.get('address', ''),
                place_data.get('description', ''),
                place_data.get('social_link', ''),
                datetime.now().strftime('%d.%m.%Y %H:%M')
            ]
            
            sheet.append_row(row)
            logger.info(f"📊 Место добавлено в Google Sheets: {place_data.get('name')}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка при добавлении в Google Sheets: {e}")
            return False
    
    def delete_place(self, place_id: int):
        """Удалить место из таблицы"""
        if not self.enabled:
            return False
        
        try:
            sheet = self.spreadsheet.worksheet("Места")
            
            # Найти строку с нужным ID
            cell = sheet.find(str(place_id), in_column=1)
            if cell:
                sheet.delete_rows(cell.row)
                logger.info(f"📊 Место удалено из Google Sheets: ID {place_id}")
                return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка при удалении из Google Sheets: {e}")
            return False
    
    def add_tips(self, user_id: int, user_name: str, tips_data: dict):
        """Добавить чаевые в таблицу"""
        if not self.enabled:
            return False
        
        try:
            sheet = self.spreadsheet.worksheet("Чаевые")
            
            row = [
                tips_data.get('id', ''),
                tips_data.get('date', ''),
                tips_data.get('card', 0),
                tips_data.get('netmonet', 0),
                tips_data.get('cash', 0),
                tips_data.get('total', 0),
                datetime.now().strftime('%d.%m.%Y %H:%M')
            ]
            
            # Вставляем в строку 2 (после заголовков), чтобы новые записи были сверху
            sheet.insert_row(row, 2)
            logger.info(f"📊 Чаевые добавлены в Google Sheets: {tips_data.get('date')}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка при добавлении чаевых в Google Sheets: {e}")
            return False
    
    def delete_tips(self, tips_id: int):
        """Удалить чаевые из таблицы"""
        if not self.enabled:
            return False
        
        try:
            sheet = self.spreadsheet.worksheet("Чаевые")
            
            # Найти строку с нужным ID
            cell = sheet.find(str(tips_id), in_column=1)
            if cell:
                sheet.delete_rows(cell.row)
                logger.info(f"📊 Чаевые удалены из Google Sheets: ID {tips_id}")
                return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка при удалении чаевых из Google Sheets: {e}")
            return False
    
    def add_avito_sale(self, user_id: int, user_name: str, sale_data: dict):
        """Добавить продажу Авито в таблицу"""
        if not self.enabled:
            return False
        
        try:
            sheet = self.spreadsheet.worksheet("Авито")
            
            row = [
                sale_data.get('id', ''),
                sale_data.get('item_name', ''),
                sale_data.get('amount', 0),
                sale_data.get('sale_date', ''),
                datetime.now().strftime('%d.%m.%Y %H:%M')
            ]
            
            # Вставляем в строку 2 (после заголовков)
            sheet.insert_row(row, 2)
            logger.info(f"📊 Продажа Авито добавлена в Google Sheets: {sale_data.get('item_name')}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка при добавлении продажи Авито в Google Sheets: {e}")
            return False
    
    def delete_avito_sale(self, sale_id: int):
        """Удалить продажу Авито из таблицы"""
        if not self.enabled:
            return False
        
        try:
            sheet = self.spreadsheet.worksheet("Авито")
            
            # Найти строку с нужным ID
            cell = sheet.find(str(sale_id), in_column=1)
            if cell:
                sheet.delete_rows(cell.row)
                logger.info(f"📊 Продажа Авито удалена из Google Sheets: ID {sale_id}")
                return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка при удалении продажи Авито из Google Sheets: {e}")
            return False
    
    def _init_expenses_sheet(self):
        """Инициализация листа 'Траты'"""
        try:
            # Лист для трат
            expenses_sheet = self.spreadsheet.add_worksheet(title="Траты", rows=1000, cols=7)
            expenses_sheet.append_row([
                'ID', 'Дата', 'Категория', 'Название', 'Сумма', 'Заметка', 'Дата добавления'
            ])
            
            # Форматирование заголовков
            expenses_sheet.format('A1:G1', {
                'textFormat': {'bold': True},
                'backgroundColor': {'red': 0.8, 'green': 0.8, 'blue': 0.8}
            })
            
            # Скрываем столбец ID
            try:
                self.spreadsheet.batch_update({
                    'requests': [{
                        'updateDimensionProperties': {
                            'range': {
                                'sheetId': expenses_sheet.id,
                                'dimension': 'COLUMNS',
                                'startIndex': 0,
                                'endIndex': 1
                            },
                            'properties': {
                                'hiddenByUser': True
                            },
                            'fields': 'hiddenByUser'
                        }
                    }]
                })
                logger.info("🔒 Столбец ID (Траты) скрыт")
            except Exception as e:
                logger.error(f"Не удалось скрыть столбец ID: {e}")
            
            # Добавляем формулы для подсчета (строка 1000)
            expenses_sheet.update('B1000', [['Итого:']])
            expenses_sheet.update('E1000', [['=SUM(E2:E999)']])  # Сумма трат
            expenses_sheet.update('A999', [['Количество трат:']])
            expenses_sheet.update('B999', [['=COUNTA(B2:B998)']])  # Количество трат
            
            logger.info("✅ Лист 'Траты' инициализирован с формулами")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при инициализации листа 'Траты': {e}")
    
    def _init_recurring_expenses_sheet(self):
        """Инициализация листа 'Обязательные расходы'"""
        try:
            # Лист для обязательных расходов
            recurring_sheet = self.spreadsheet.add_worksheet(title="Обязательные расходы", rows=1000, cols=5)
            recurring_sheet.append_row([
                'ID', 'Название', 'Сумма', 'Дата оплаты', 'Дата добавления'
            ])
            
            # Форматирование заголовков
            recurring_sheet.format('A1:E1', {
                'textFormat': {'bold': True},
                'backgroundColor': {'red': 0.8, 'green': 0.8, 'blue': 0.8}
            })
            
            # Скрываем столбец ID
            try:
                self.spreadsheet.batch_update({
                    'requests': [{
                        'updateDimensionProperties': {
                            'range': {
                                'sheetId': recurring_sheet.id,
                                'dimension': 'COLUMNS',
                                'startIndex': 0,
                                'endIndex': 1
                            },
                            'properties': {
                                'hiddenByUser': True
                            },
                            'fields': 'hiddenByUser'
                        }
                    }]
                })
                logger.info("🔒 Столбец ID (Обязательные расходы) скрыт")
            except Exception as e:
                logger.error(f"Не удалось скрыть столбец ID: {e}")
            
            # Добавляем формулы для подсчета (строка 1000)
            recurring_sheet.update('B1000', [['Итого:']])
            recurring_sheet.update('C1000', [['=SUM(C2:C999)']])  # Сумма обязательных расходов
            recurring_sheet.update('A999', [['Количество платежей:']])
            recurring_sheet.update('B999', [['=COUNTA(B2:B998)']])  # Количество платежей
            
            logger.info("✅ Лист 'Обязательные расходы' инициализирован с формулами")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при инициализации листа 'Обязательные расходы': {e}")
    
    def _init_media_sheet(self):
        """Инициализация единого листа 'Медиа' для фильмов, сериалов и подкастов"""
        try:
            # Единая таблица для всех типов медиа
            media_sheet = self.spreadsheet.add_worksheet(title="Медиа", rows=1000, cols=12)
            media_sheet.append_row([
                'ID', 'Тип', 'Название', 'Жанр', 'Год', 'Сюжет', 
                'Сезоны', 'Серии', 'Статус', 'Рейтинг', 'Заметки', 'Дата добавления'
            ])
            
            # Форматирование заголовков
            media_sheet.format('A1:L1', {
                'textFormat': {'bold': True},
                'backgroundColor': {'red': 0.8, 'green': 0.8, 'blue': 0.8}
            })
            
            # Скрываем столбец ID
            try:
                self.spreadsheet.batch_update({
                    'requests': [{
                        'updateDimensionProperties': {
                            'range': {
                                'sheetId': media_sheet.id,
                                'dimension': 'COLUMNS',
                                'startIndex': 0,
                                'endIndex': 1
                            },
                            'properties': {
                                'hiddenByUser': True
                            },
                            'fields': 'hiddenByUser'
                        }
                    }]
                })
                logger.info("🔒 Столбец ID (Медиа) скрыт")
            except Exception as e:
                logger.error(f"Не удалось скрыть столбец ID: {e}")
            
            # Добавляем формулы для подсчета (строка 1000)
            media_sheet.update('B1000', [['Всего:']])
            media_sheet.update('C1000', [['=COUNTA(B2:B999)']])  # Общее количество
            media_sheet.update('A999', [['Фильмов:']])
            media_sheet.update('B999', [['=COUNTIF(B2:B998,"Фильм")']])  # Количество фильмов
            media_sheet.update('A998', [['Сериалов:']])
            media_sheet.update('B998', [['=COUNTIF(B2:B998,"Сериал")']])  # Количество сериалов
            media_sheet.update('A997', [['Подкастов:']])
            media_sheet.update('B997', [['=COUNTIF(B2:B998,"Подкаст")']])  # Количество подкастов
            
            logger.info("✅ Лист 'Медиа' инициализирован с формулами")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при инициализации листа 'Медиа': {e}")
    
    def add_media(self, user_id: int, user_name: str, media_data: dict):
        """Добавить медиа (фильм/сериал/подкаст) в таблицу"""
        if not self.enabled:
            return False
        
        try:
            sheet = self.spreadsheet.worksheet("Медиа")
            
            row = [
                media_data.get('id', ''),
                media_data.get('type', ''),  # Фильм/Сериал/Подкаст
                media_data.get('title', ''),
                media_data.get('genre', ''),
                media_data.get('year', ''),
                media_data.get('overview', ''),
                media_data.get('seasons', '') if media_data.get('seasons') else '',
                media_data.get('episodes', '') if media_data.get('episodes') else '',
                media_data.get('status', ''),
                '⭐' * media_data.get('rating', 0) if media_data.get('rating') else '',
                media_data.get('notes', ''),
                datetime.now().strftime('%d.%m.%Y %H:%M')
            ]
            
            # Вставляем в строку 2 (после заголовков)
            sheet.insert_row(row, 2)
            logger.info(f"📊 Медиа добавлено в Google Sheets: {media_data.get('title')}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка при добавлении медиа в Google Sheets: {e}")
            return False
    
    def add_expense(self, user_id: int, user_name: str, expense_data: dict):
        """Добавить трату в таблицу"""
        if not self.enabled:
            return False
        
        try:
            sheet = self.spreadsheet.worksheet("Траты")
            
            row = [
                expense_data.get('id', ''),
                expense_data.get('expense_date', ''),
                expense_data.get('category', ''),
                expense_data.get('name', ''),
                expense_data.get('amount', 0),
                expense_data.get('note', ''),
                datetime.now().strftime('%d.%m.%Y %H:%M')
            ]
            
            # Вставляем в строку 2 (после заголовков)
            sheet.insert_row(row, 2)
            logger.info(f"📊 Трата добавлена в Google Sheets: {expense_data.get('name')}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка при добавлении траты в Google Sheets: {e}")
            return False
    
    def add_recurring_expense(self, user_id: int, user_name: str, expense_data: dict):
        """Добавить обязательный расход в таблицу"""
        if not self.enabled:
            return False
        
        try:
            sheet = self.spreadsheet.worksheet("Обязательные расходы")
            
            row = [
                expense_data.get('id', ''),
                expense_data.get('name', ''),
                expense_data.get('amount', 0),
                expense_data.get('payment_date', ''),
                datetime.now().strftime('%d.%m.%Y %H:%M')
            ]
            
            # Вставляем в строку 2 (после заголовков)
            sheet.insert_row(row, 2)
            logger.info(f"📊 Обязательный расход добавлен в Google Sheets: {expense_data.get('name')}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка при добавлении обязательного расхода в Google Sheets: {e}")
            return False
    
    def _init_notes_sheet(self):
        """Инициализация листа 'Заметки'"""
        try:
            notes_sheet = self.spreadsheet.add_worksheet(title="Заметки", rows=1000, cols=4)
            notes_sheet.append_row(['ID', 'Дата', 'Категория', 'Текст'])
            
            # Форматирование заголовков
            notes_sheet.format('A1:D1', {
                'textFormat': {'bold': True},
                'backgroundColor': {'red': 0.8, 'green': 0.8, 'blue': 0.8}
            })
            
            # Скрываем столбец ID
            try:
                self.spreadsheet.batch_update({
                    'requests': [{
                        'updateDimensionProperties': {
                            'range': {
                                'sheetId': notes_sheet.id,
                                'dimension': 'COLUMNS',
                                'startIndex': 0,
                                'endIndex': 1
                            },
                            'properties': {
                                'hiddenByUser': True
                            },
                            'fields': 'hiddenByUser'
                        }
                    }]
                })
                logger.info("🔒 Столбец ID (Заметки) скрыт")
            except Exception as e:
                logger.error(f"Не удалось скрыть столбец ID: {e}")
            
            # Добавляем формулы для подсчета (строка 1000)
            notes_sheet.update('C1000', [['Всего заметок:']])
            notes_sheet.update('D1000', [['=COUNTA(C2:C999)']])  # Общее количество
            
            logger.info("✅ Лист 'Заметки' инициализирован с формулами")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при инициализации листа 'Заметки': {e}")
    
    def add_note(self, user_id: int, user_name: str, note_data: dict):
        """Добавить заметку в таблицу"""
        if not self.enabled:
            return False
        
        try:
            sheet = self.spreadsheet.worksheet("Заметки")
            
            row = [
                note_data.get('id', ''),
                datetime.now().strftime('%d.%m.%Y %H:%M'),
                note_data.get('category', ''),
                note_data.get('text', '')
            ]
            
            # Вставляем в строку 2 (после заголовков)
            sheet.insert_row(row, 2)
            logger.info(f"📊 Заметка добавлена в Google Sheets")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка при добавлении заметки в Google Sheets: {e}")
            return False
    
    def delete_note(self, note_id: int):
        """Удалить заметку из таблицы"""
        if not self.enabled:
            return False
        
        try:
            sheet = self.spreadsheet.worksheet("Заметки")
            cell = sheet.find(str(note_id))
            if cell:
                sheet.delete_rows(cell.row)
                logger.info(f"🗑 Заметка удалена из Google Sheets")
                return True
            return False
            
        except Exception as e:
            logger.error(f"❌ Ошибка при удалении заметки из Google Sheets: {e}")
            return False
    
    def get_spreadsheet_url(self) -> str:
        """Получить ссылку на таблицу"""
        if self.spreadsheet:
            return self.spreadsheet.url
        return None

