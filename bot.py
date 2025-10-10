import asyncio
import logging
import sys
import os
import signal
import atexit
import warnings
import urllib.parse
from os import getenv
from dotenv import load_dotenv
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any

# Подавляем предупреждение urllib3 про OpenSSL
warnings.filterwarnings('ignore', message='urllib3 v2 only supports OpenSSL')

from aiogram import Bot, Dispatcher, Router, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.types import (
    Message, 
    CallbackQuery, 
    InlineKeyboardMarkup, 
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import Database
from google_sheets import GoogleSheetsSync
from constants import (
    GENRE_MAP, GENRE_REVERSE_MAP, GENRE_BUTTONS,
    PLACE_TYPES, PRICE_CATEGORIES, EXPENSE_CATEGORIES,
    CUISINE_TYPES, CUISINE_BUTTONS,
    MOVIE_STATUS_WATCHED, MOVIE_STATUS_UNWATCHED,
    SERIES_STATUS_UNWATCHED, SERIES_STATUS_WATCHING, SERIES_STATUS_WATCHED,
    PLACES_PER_PAGE, TIPS_PER_PAGE, NOTE_CATEGORIES, NOTE_CATEGORY_BUTTONS, NOTES_PER_PAGE,
    EMOJI_CANCEL, EMOJI_SKIP, EMOJI_BACK, EMOJI_DELETE,
    WISHLIST_SIZE_CATEGORIES, WISHLIST_TYPE_CATEGORIES, WISHLIST_PRIORITIES
)
from utils import (
    SimpleCache, format_date, format_movie_text, format_series_text, capitalize_first,
    calculate_tips_distribution, calculate_avito_distribution, 
    get_motivation_message, format_distribution,
    calculate_wage_distribution, format_wage_distribution,
    search_place_yandex, get_place_details_yandex
)

# Загрузка переменных окружения
load_dotenv()
TOKEN = getenv("BOT_TOKEN")

# Настройка логирования (в файл и консоль)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Уменьшаем логирование aiogram для производительности
logging.getLogger('aiogram.event').setLevel(logging.WARNING)  # Меньше INFO сообщений

# Файл блокировки
LOCKFILE = Path('.bot.lock')

# Кэш для данных
# Инициализация
dp = Dispatcher()
router = Router()
db = Database()
cache = SimpleCache(ttl_seconds=600)  # Кэш на 10 минут (увеличено для быстродействия)
google_sheets = GoogleSheetsSync()  # Google Sheets синхронизация

# Состояния для добавления места
class AddPlaceStates(StatesGroup):
    waiting_for_name = State()
    choosing_from_search = State()  # Новое состояние для выбора из результатов поиска
    choosing_fill_method = State()  # Выбор: автоматически или вручную
    waiting_for_type = State()
    waiting_for_cuisine = State()
    waiting_for_price = State()
    waiting_for_status = State()
    waiting_for_review = State()
    waiting_for_address = State()
    waiting_for_description = State()
    waiting_for_social = State()
    waiting_for_location = State()

# FSM состояния для редактирования места
class EditPlaceStates(StatesGroup):
    selecting_field = State()
    editing_name = State()
    editing_type = State()
    editing_cuisine = State()
    editing_price = State()
    editing_status = State()
    editing_review = State()
    editing_address = State()
    editing_description = State()
    editing_social = State()
    editing_location = State()
    editing_working_hours = State()

# FSM состояния для добавления чаевых
class AddTipsStates(StatesGroup):
    waiting_for_hours = State()  # Новое состояние для ввода часов
    waiting_for_card = State()
    waiting_for_netmonet = State()
    waiting_for_cash = State()
    waiting_for_date = State()

# FSM состояния для добавления продажи на Авито
class AddAvitoStates(StatesGroup):
    waiting_for_item_name = State()
    waiting_for_amount = State()
    waiting_for_date = State()

# FSM состояния для добавления траты
class AddExpenseStates(StatesGroup):
    waiting_for_category = State()
    waiting_for_name = State()
    waiting_for_amount = State()
    waiting_for_date_choice = State()
    waiting_for_date = State()
    waiting_for_note_choice = State()
    waiting_for_note = State()

# FSM состояния для добавления обязательного расхода
class AddRecurringExpenseStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_amount = State()
    waiting_for_date = State()

# FSM состояния для добавления фильма
class AddMovieStates(StatesGroup):
    waiting_for_title = State()
    waiting_for_genre = State()
    waiting_for_year = State()
    waiting_for_status = State()
    waiting_for_rating = State()
    waiting_for_notes = State()

# FSM состояния для просмотра фильмов
class ViewMoviesStates(StatesGroup):
    waiting_for_genre = State()
    waiting_for_random_genre = State()

# FSM состояния для просмотра сериалов
class ViewSeriesStates(StatesGroup):
    waiting_for_genre = State()

# FSM состояния для добавления сериала
class AddSeriesStates(StatesGroup):
    waiting_for_title = State()
    waiting_for_genre = State()
    waiting_for_year = State()
    waiting_for_seasons = State()
    waiting_for_episodes = State()
    waiting_for_status = State()
    waiting_for_rating = State()
    waiting_for_notes = State()

# FSM состояния для добавления подкаста
class AddPodcastStates(StatesGroup):
    waiting_for_title = State()
    waiting_for_author = State()
    waiting_for_status = State()
    waiting_for_rating = State()
    waiting_for_notes = State()

# FSM состояния для быстрой заметки
class QuickNoteStates(StatesGroup):
    waiting_for_category = State()
    waiting_for_text = State()
    waiting_for_edit = State()

# FSM состояния для поиска заметок
class SearchNotesStates(StatesGroup):
    waiting_for_query = State()

# FSM состояния для добавления в вишлист
class AddWishlistStates(StatesGroup):
    waiting_for_size_category = State()
    waiting_for_type_category = State()
    waiting_for_name = State()
    waiting_for_price = State()
    waiting_for_priority = State()
    waiting_for_photo = State()
    waiting_for_link = State()

# Временное хранилище данных о месте
user_place_data = {}

# Временное хранилище данных о чаевых
user_tips_data = {}

# Временное хранилище данных о продажах Авито
user_avito_data = {}

# Временное хранилище данных о тратах
user_expense_data = {}

# Временное хранилище данных об обязательных расходах
user_recurring_expense_data = {}

# Временное хранилище данных о медиа
user_movie_data = {}
user_series_data = {}
user_podcast_data = {}
user_note_data = {}
user_wishlist_data = {}

# Функция форматирования даты
# Главное меню
def get_main_menu():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👤 Личное")],
            [KeyboardButton(text="📚 Изучение"), KeyboardButton(text="💰 Финансы")],
            [KeyboardButton(text="📝 Быстрая заметка"), KeyboardButton(text="🎥 Видеография")],
        ],
        resize_keyboard=True
    )
    return keyboard

# Подменю "Личное"
def get_personal_submenu():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Места"), KeyboardButton(text="✈️ Путешествие")],
            [KeyboardButton(text="📔 Дневник"), KeyboardButton(text="💪 Тренировки")],
            [KeyboardButton(text="⭐ Вишлист")],
            [KeyboardButton(text="◀️ Назад")],
        ],
        resize_keyboard=True
    )
    return keyboard

# Подменю "Места"
def get_places_submenu():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить место"), KeyboardButton(text="🎉 Добавить мероприятие")],
            [KeyboardButton(text="📋 Мои места"), KeyboardButton(text="🔍 Поиск")],
            [KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="◀️ К личному")],
        ],
        resize_keyboard=True
    )
    return keyboard

# Подменю "Изучение"
def get_learning_submenu():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎬 Медиа")],
            [KeyboardButton(text="📖 Книги")],
            [KeyboardButton(text="💡 Новые темы")],
            [KeyboardButton(text="◀️ Назад")],
        ],
        resize_keyboard=True
    )
    return keyboard

# Подменю "Видеография"
def get_videography_submenu():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💡 Идеи")],
            [KeyboardButton(text="⭐ Вишлист")],
            [KeyboardButton(text="📸 Кадр")],
            [KeyboardButton(text="◀️ Назад")],
        ],
        resize_keyboard=True
    )
    return keyboard

# Меню Медиа
def get_media_submenu():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎬 Фильмы")],
            [KeyboardButton(text="📺 Сериалы")],
            [KeyboardButton(text="🎙 Подкасты")],
            [KeyboardButton(text="◀️ К изучению")],
        ],
        resize_keyboard=True
    )
    return keyboard

# Меню Фильмов
def get_movies_submenu():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить фильм")],
            [KeyboardButton(text="✅ Просмотренные"), KeyboardButton(text="👁 Не смотрел")],
            [KeyboardButton(text="🎲 Случайный фильм")],
            [KeyboardButton(text="◀️ К медиа")],
        ],
        resize_keyboard=True
    )
    return keyboard

# Клавиатура выбора жанра
def get_genre_keyboard():
    keyboard_layout = [[KeyboardButton(text=genre) for genre in row] for row in GENRE_BUTTONS]
    keyboard_layout.append([KeyboardButton(text=EMOJI_BACK)])
    keyboard = ReplyKeyboardMarkup(
        keyboard=keyboard_layout,
        resize_keyboard=True
    )
    return keyboard

# Меню Сериалов
def get_series_submenu():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить сериал")],
            [KeyboardButton(text="✅ Просмотренные"), KeyboardButton(text="👀 Смотрю")],
            [KeyboardButton(text="👁 Не смотрел")],
            [KeyboardButton(text="◀️ К медиа")],
        ],
        resize_keyboard=True
    )
    return keyboard

# Меню Подкастов
def get_podcasts_submenu():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить подкаст")],
            [KeyboardButton(text="📋 Мои подкасты")],
            [KeyboardButton(text="📊 Статистика подкастов")],
            [KeyboardButton(text="◀️ К медиа")],
        ],
        resize_keyboard=True
    )
    return keyboard

# Меню заметок
def get_notes_submenu():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Новая заметка")],
            [KeyboardButton(text="📋 Мои заметки")],
            [KeyboardButton(text="🔍 Поиск заметок")],
            [KeyboardButton(text="◀️ Назад")],
        ],
        resize_keyboard=True
    )
    return keyboard

def get_note_category_keyboard():
    """Клавиатура для выбора категории заметки"""
    keyboard_layout = [[KeyboardButton(text=cat) for cat in row] for row in NOTE_CATEGORY_BUTTONS]
    keyboard_layout.append([KeyboardButton(text=EMOJI_BACK)])
    keyboard = ReplyKeyboardMarkup(
        keyboard=keyboard_layout,
        resize_keyboard=True
    )
    return keyboard

# Меню вишлиста
def get_wishlist_submenu():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить желание")],
            [KeyboardButton(text="📋 Мой вишлист")],
            [KeyboardButton(text="◀️ К личному")],
        ],
        resize_keyboard=True
    )
    return keyboard

# Клавиатура выбора размера покупки
def get_wishlist_size_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=cat)] for cat in WISHLIST_SIZE_CATEGORIES
        ] + [[KeyboardButton(text=EMOJI_CANCEL)]],
        resize_keyboard=True
    )
    return keyboard

# Клавиатура выбора типа покупки
def get_wishlist_type_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=WISHLIST_TYPE_CATEGORIES[0]), KeyboardButton(text=WISHLIST_TYPE_CATEGORIES[1])],
            [KeyboardButton(text=WISHLIST_TYPE_CATEGORIES[2]), KeyboardButton(text=WISHLIST_TYPE_CATEGORIES[3])],
            [KeyboardButton(text=EMOJI_CANCEL)]
        ],
        resize_keyboard=True
    )
    return keyboard

# Клавиатура выбора приоритета
def get_wishlist_priority_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=cat)] for cat in WISHLIST_PRIORITIES
        ] + [[KeyboardButton(text=EMOJI_CANCEL)]],
        resize_keyboard=True
    )
    return keyboard

# Клавиатура статуса для фильмов/подкастов
def get_movie_status_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👁 Не смотрел")],
            [KeyboardButton(text="✅ Просмотрел")],
            [KeyboardButton(text="❌ Отмена")]
        ],
        resize_keyboard=True
    )
    return keyboard

# Клавиатура статуса для сериалов
def get_series_status_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👁 Не смотрел")],
            [KeyboardButton(text="⏳ Смотрю")],
            [KeyboardButton(text="✅ Просмотрел")],
            [KeyboardButton(text="❌ Отмена")]
        ],
        resize_keyboard=True
    )
    return keyboard

# Клавиатура рейтинга (1-5 звёзд)
def get_rating_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⭐"), KeyboardButton(text="⭐⭐"), KeyboardButton(text="⭐⭐⭐")],
            [KeyboardButton(text="⭐⭐⭐⭐"), KeyboardButton(text="⭐⭐⭐⭐⭐")],
            [KeyboardButton(text="⏭ Пропустить"), KeyboardButton(text="❌ Отмена")]
        ],
        resize_keyboard=True
    )
    return keyboard

# Подменю "Путешествие"
def get_travel_submenu():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🗺 Планы поездок")],
            [KeyboardButton(text="✈️ Посещенные страны")],
            [KeyboardButton(text="📝 Список желаний")],
            [KeyboardButton(text="◀️ К личному")],
        ],
        resize_keyboard=True
    )
    return keyboard

# Подменю "Финансы"
def get_finance_submenu():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💼 Смена")],
            [KeyboardButton(text="🛒 Авито")],
            [KeyboardButton(text="💸 Расходы")],
            [KeyboardButton(text="📊 Отчеты")],
            [KeyboardButton(text="◀️ Назад")],
        ],
        resize_keyboard=True
    )
    return keyboard

# Меню Авито
def get_avito_submenu():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Новая продажа")],
            [KeyboardButton(text="📋 Мои продажи")],
            [KeyboardButton(text="📈 Статистика Авито")],
            [KeyboardButton(text="◀️ Назад")],
        ],
        resize_keyboard=True
    )
    return keyboard

# Меню Расходов
def get_expenses_submenu():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Новая трата")],
            [KeyboardButton(text="📋 Обязательные расходы")],
            [KeyboardButton(text="📋 История трат")],
            [KeyboardButton(text="◀️ К финансам")],
        ],
        resize_keyboard=True
    )
    return keyboard

# Меню Обязательных расходов
def get_recurring_expenses_submenu():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить")],
            [KeyboardButton(text="📋 Мои платежи")],
            [KeyboardButton(text="◀️ К расходам")],
        ],
        resize_keyboard=True
    )
    return keyboard

# Клавиатура категорий трат
def get_expense_category_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🍔 Еда"), KeyboardButton(text="🎉 Развлечения")],
            [KeyboardButton(text="👕 Одежда"), KeyboardButton(text="🚗 Транспорт")],
            [KeyboardButton(text="❌ Отмена")]
        ],
        resize_keyboard=True
    )
    return keyboard

# Клавиатура выбора даты
def get_date_choice_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📅 Сегодня")],
            [KeyboardButton(text="📆 Ввести дату")],
            [KeyboardButton(text="❌ Отмена")]
        ],
        resize_keyboard=True
    )
    return keyboard

# Клавиатура для заметки
def get_note_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✍️ Добавить заметку")],
            [KeyboardButton(text="⏭ Пропустить")],
            [KeyboardButton(text="❌ Отмена")]
        ],
        resize_keyboard=True
    )
    return keyboard

# Меню чаевых
def get_tips_submenu():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Новая смена")],
            [KeyboardButton(text="📋 Мои смены")],
            [KeyboardButton(text="📈 Статистика смен")],
            [KeyboardButton(text="◀️ Назад")],
        ],
        resize_keyboard=True
    )
    return keyboard

# Клавиатура с кнопкой "Пропустить"
def get_skip_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⏭ Пропустить")],
            [KeyboardButton(text="❌ Отмена")]
        ],
        resize_keyboard=True
    )
    return keyboard

# Кнопка отмены
def get_cancel_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=EMOJI_CANCEL)]],
        resize_keyboard=True
    )
    return keyboard

# Клавиатура выбора типа места
def get_place_type_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🍺 Бар"), KeyboardButton(text="☕️ Кафе")],
            [KeyboardButton(text="🍽 Ресторан"), KeyboardButton(text="🏛 Музей")],
            [KeyboardButton(text="🌳 Парк"), KeyboardButton(text="📍 Локация")],
            [KeyboardButton(text="❌ Отмена")]
        ],
        resize_keyboard=True
    )
    return keyboard

# Клавиатура выбора ценовой категории
def get_price_category_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💲"), KeyboardButton(text="💲💲"), KeyboardButton(text="💲💲💲")],
            [KeyboardButton(text="❌ Отмена")]
        ],
        resize_keyboard=True
    )
    return keyboard

# Клавиатура выбора кухни ресторана
def get_cuisine_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            *[[KeyboardButton(text=cuisine) for cuisine in row] for row in CUISINE_BUTTONS],
            [KeyboardButton(text="❌ Отмена")]
        ],
        resize_keyboard=True
    )
    return keyboard

# Клавиатура выбора статуса места
def get_status_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Посещено"), KeyboardButton(text="📅 Планирую посетить")],
            [KeyboardButton(text="❌ Отмена")]
        ],
        resize_keyboard=True
    )
    return keyboard

@router.message(CommandStart())
async def command_start_handler(message: Message):
    """Обработчик команды /start"""
    await message.answer(
        f"Салют! Куда пойдем? 🗺",
        reply_markup=get_main_menu()
    )

@router.message(Command("help"))
async def command_help_handler(message: Message):
    """Обработчик команды /help"""
    await message.answer(
        "📖 <b>Доступные команды:</b>\n\n"
        "➕ <b>Добавить место</b> - сохранить новое место\n"
        "📋 <b>Мои места</b> - список всех сохраненных мест\n"
        "🔍 <b>Поиск</b> - найти место по названию\n"
        "📊 <b>Статистика</b> - сколько мест сохранено\n\n"
        "При добавлении места можно указать:\n"
        "• Название (обязательно)\n"
        "• Адрес\n"
        "• Описание\n"
        "• Геолокацию (отправьте точку на карте)",
        parse_mode=ParseMode.HTML
    )

# ===== НАВИГАЦИЯ =====

@router.message(F.text == "👤 Личное")
async def show_personal_menu(message: Message):
    """Показать меню 'Личное'"""
    await message.answer(
        "👤 <b>Личное</b>\n\nВаша личная информация:",
        reply_markup=get_personal_submenu(),
        parse_mode=ParseMode.HTML
    )

@router.message(F.text == "📍 Места")
async def show_places_menu(message: Message):
    """Показать подменю 'Места'"""
    await message.answer(
        "📍 <b>Места</b>\n\nВыберите действие:",
        reply_markup=get_places_submenu(),
        parse_mode=ParseMode.HTML
    )

@router.message(F.text == "📚 Изучение")
async def show_learning_menu(message: Message):
    """Показать подменю 'Изучение'"""
    await message.answer(
        "📚 <b>Изучение</b>\n\nВыберите категорию:",
        reply_markup=get_learning_submenu(),
        parse_mode=ParseMode.HTML
    )

@router.message(F.text == "🎬 Медиа")
async def show_media_menu(message: Message):
    """Показать меню медиа"""
    await message.answer(
        "🎬 <b>Медиа</b>\n\nВыберите тип контента:",
        reply_markup=get_media_submenu(),
        parse_mode=ParseMode.HTML
    )

@router.message(F.text == "🎬 Фильмы")
async def show_movies_menu(message: Message):
    """Показать меню фильмов"""
    await message.answer(
        "🎬 <b>Фильмы</b>",
        reply_markup=get_movies_submenu(),
        parse_mode=ParseMode.HTML
    )

@router.message(F.text == "📺 Сериалы")
async def show_series_menu(message: Message):
    """Показать меню сериалов"""
    await message.answer(
        "📺 <b>Сериалы</b>",
        reply_markup=get_series_submenu(),
        parse_mode=ParseMode.HTML
    )

@router.message(F.text == "🎙 Подкасты")
async def show_podcasts_menu(message: Message):
    """Показать меню подкастов - в разработке"""
    await message.answer(
        "🎙 <b>Подкасты</b>\n\n🚧 Функция в разработке",
        reply_markup=get_media_submenu(),
        parse_mode=ParseMode.HTML
    )

@router.message(F.text == "✈️ Путешествие")
async def show_travel_menu(message: Message):
    """Показать подменю 'Путешествие'"""
    await message.answer(
        "✈️ <b>Путешествие</b>\n\nПланируйте и отслеживайте свои поездки:",
        reply_markup=get_travel_submenu(),
        parse_mode=ParseMode.HTML
    )

@router.message(F.text == "💰 Финансы")
async def show_finance_menu(message: Message):
    """Показать подменю 'Финансы'"""
    await message.answer(
        "💰 <b>Финансы</b>\n\nУправляйте своим бюджетом:",
        reply_markup=get_finance_submenu(),
        parse_mode=ParseMode.HTML
    )

@router.message(F.text == "◀️ Назад")
async def back_to_main_menu(message: Message, state: FSMContext):
    """Вернуться в главное меню"""
    await state.clear()  # Очищаем состояние на всякий случай
    await message.answer(
        "Главное меню",
        reply_markup=get_main_menu()
    )

@router.message(F.text == "◀️ К финансам")
async def back_to_finance_menu(message: Message, state: FSMContext):
    """Вернуться в меню финансов"""
    await state.clear()
    await message.answer(
        "💰 <b>Финансы</b>",
        reply_markup=get_finance_submenu(),
        parse_mode=ParseMode.HTML
    )

@router.message(F.text == "◀️ К расходам")
async def back_to_expenses_menu(message: Message, state: FSMContext):
    """Вернуться в меню расходов"""
    await state.clear()
    await message.answer(
        "💸 <b>Расходы</b>",
        reply_markup=get_expenses_submenu(),
        parse_mode=ParseMode.HTML
    )

@router.message(F.text == "◀️ К изучению")
async def back_to_learning_menu(message: Message, state: FSMContext):
    """Вернуться в меню изучения"""
    await state.clear()
    await message.answer(
        "📚 <b>Изучение</b>",
        reply_markup=get_learning_submenu(),
        parse_mode=ParseMode.HTML
    )

@router.message(F.text == "◀️ К медиа")
async def back_to_media_menu(message: Message, state: FSMContext):
    """Вернуться в меню медиа"""
    await state.clear()
    await message.answer(
        "🎬 <b>Медиа</b>",
        reply_markup=get_media_submenu(),
        parse_mode=ParseMode.HTML
    )

@router.message(F.text == "◀️ К личному")
async def back_to_personal_menu(message: Message, state: FSMContext):
    """Вернуться в меню личного"""
    await state.clear()
    await message.answer(
        "👤 <b>Личное</b>",
        reply_markup=get_personal_submenu(),
        parse_mode=ParseMode.HTML
    )

# ===== НОВЫЕ РАЗДЕЛЫ (заглушки) =====

@router.message(F.text == "📝 Быстрая заметка")
async def quick_note_handler(message: Message):
    """Быстрая заметка - главное меню"""
    await message.answer(
        "📝 <b>Быстрая заметка</b>",
        reply_markup=get_notes_submenu(),
        parse_mode=ParseMode.HTML
    )

# ==================== ОБРАБОТЧИКИ ЗАМЕТОК ====================

@router.message(F.text == "➕ Новая заметка")
async def add_note_start(message: Message, state: FSMContext):
    """Начало добавления заметки"""
    user_note_data[message.from_user.id] = {}
    await state.set_state(QuickNoteStates.waiting_for_category)
    await message.answer(
        "📝 Выберите категорию заметки:",
        reply_markup=get_note_category_keyboard()
    )

@router.message(QuickNoteStates.waiting_for_category)
async def process_note_category(message: Message, state: FSMContext):
    """Обработка выбора категории заметки"""
    if message.text == EMOJI_BACK:
        await state.clear()
        del user_note_data[message.from_user.id]
        await message.answer("Отменено", reply_markup=get_notes_submenu())
        return
    
    category = NOTE_CATEGORIES.get(message.text)
    if not category:
        await message.answer("❌ Выберите категорию из списка", reply_markup=get_note_category_keyboard())
        return
    
    user_note_data[message.from_user.id]['category'] = category
    await state.set_state(QuickNoteStates.waiting_for_text)
    await message.answer(
        f"{message.text}\n\nВведите текст заметки:",
        reply_markup=get_cancel_keyboard()
    )

@router.message(QuickNoteStates.waiting_for_text)
async def process_note_text(message: Message, state: FSMContext):
    """Обработка текста заметки"""
    if message.text == EMOJI_CANCEL:
        await state.clear()
        del user_note_data[message.from_user.id]
        await message.answer("Отменено", reply_markup=get_notes_submenu())
        return
    
    user_id = message.from_user.id
    user_name = message.from_user.full_name
    category = user_note_data[user_id]['category']
    text = message.text
    
    # Сохраняем в БД
    note_id = await db.add_note(user_id, category, text)
    
    if note_id:
        # Синхронизация с Google Sheets
        note_data = {
            'id': note_id,
            'category': category,
            'text': text
        }
        await asyncio.to_thread(google_sheets.add_note, user_id, user_name, note_data)
        
        await message.answer(
            f"✅ Заметка сохранена!\n\n"
            f"📁 Категория: {category}\n"
            f"📝 {text}",
            reply_markup=get_notes_submenu()
        )
    else:
        await message.answer(
            "❌ Ошибка при сохранении заметки",
            reply_markup=get_notes_submenu()
        )
    
    await state.clear()
    del user_note_data[user_id]

@router.message(F.text == "📋 Мои заметки")
async def show_my_notes(message: Message):
    """Показать список заметок"""
    user_id = message.from_user.id
    notes = await db.get_user_notes(user_id, limit=NOTES_PER_PAGE)
    total_count = await db.count_user_notes(user_id)
    
    if not notes:
        await message.answer(
            "📋 У вас пока нет заметок.",
            reply_markup=get_notes_submenu()
        )
        return
    
    # Показываем каждую заметку с кнопками
    for note in notes:
        note_date = format_date(note['created_at'])
        text = f"📝 <b>{note['category']}</b> ({note_date})\n\n{note['text']}"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit_note_{note['id']}"),
                InlineKeyboardButton(text=EMOJI_DELETE, callback_data=f"delete_note_{note['id']}")
            ]
        ])
        
        await message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    
    # Сообщение о количестве
    if total_count > NOTES_PER_PAGE:
        await message.answer(
            f"📊 Показано {len(notes)} из {total_count} заметок",
            reply_markup=get_notes_submenu()
        )
    else:
        await message.answer(
            f"📊 Всего заметок: {total_count}",
            reply_markup=get_notes_submenu()
        )

@router.callback_query(F.data.startswith("edit_note_"))
async def edit_note_callback(callback: CallbackQuery, state: FSMContext):
    """Редактировать заметку"""
    note_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    
    await state.update_data(note_id=note_id)
    await state.set_state(QuickNoteStates.waiting_for_edit)
    
    await callback.message.answer(
        "✏️ Введите новый текст заметки:",
        reply_markup=get_cancel_keyboard()
    )
    await callback.answer()

@router.message(QuickNoteStates.waiting_for_edit)
async def process_note_edit(message: Message, state: FSMContext):
    """Обработка редактирования заметки"""
    if message.text == EMOJI_CANCEL:
        await state.clear()
        await message.answer("Отменено", reply_markup=get_notes_submenu())
        return
    
    data = await state.get_data()
    note_id = data.get('note_id')
    user_id = message.from_user.id
    new_text = message.text
    
    success = await db.update_note(note_id, user_id, new_text)
    
    if success:
        await message.answer(
            f"✅ Заметка обновлена!\n\n📝 {new_text}",
            reply_markup=get_notes_submenu()
        )
    else:
        await message.answer(
            "❌ Ошибка при обновлении заметки",
            reply_markup=get_notes_submenu()
        )
    
    await state.clear()

@router.callback_query(F.data.startswith("delete_note_"))
async def delete_note_callback(callback: CallbackQuery):
    """Удалить заметку"""
    note_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    
    success = await db.delete_note(note_id, user_id)
    
    if success:
        # Удаляем из Google Sheets
        await asyncio.to_thread(google_sheets.delete_note, note_id)
        
        await callback.message.edit_text("✅ Заметка удалена")
        await callback.answer("Удалено", show_alert=False)
    else:
        await callback.answer("❌ Ошибка при удалении", show_alert=True)

@router.message(F.text == "🔍 Поиск заметок")
async def search_notes_start(message: Message, state: FSMContext):
    """Начало поиска заметок"""
    await state.set_state(SearchNotesStates.waiting_for_query)
    await message.answer(
        "🔍 Введите текст для поиска:",
        reply_markup=get_cancel_keyboard()
    )

@router.message(SearchNotesStates.waiting_for_query)
async def process_search_notes(message: Message, state: FSMContext):
    """Обработка поиска заметок"""
    if message.text == EMOJI_CANCEL:
        await state.clear()
        await message.answer("Отменено", reply_markup=get_notes_submenu())
        return
    
    user_id = message.from_user.id
    search_text = message.text
    
    notes = await db.search_notes(user_id, search_text)
    
    if not notes:
        await message.answer(
            f"🔍 По запросу «{search_text}» ничего не найдено",
            reply_markup=get_notes_submenu()
        )
        await state.clear()
        return
    
    # Показываем найденные заметки
    for note in notes:
        note_date = format_date(note['created_at'])
        text = f"📝 <b>{note['category']}</b> ({note_date})\n\n{note['text']}"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit_note_{note['id']}"),
                InlineKeyboardButton(text=EMOJI_DELETE, callback_data=f"delete_note_{note['id']}")
            ]
        ])
        
        await message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    
    await message.answer(
        f"🔍 Найдено заметок: {len(notes)}",
        reply_markup=get_notes_submenu()
    )
    await state.clear()

@router.message(F.text == "🎥 Видеография")
async def videography_handler(message: Message):
    """Видеография"""
    await message.answer(
        "🎥 <b>Видеография</b>",
        reply_markup=get_videography_submenu(),
        parse_mode=ParseMode.HTML
    )

@router.message(F.text == "💡 Идеи")
async def videography_ideas_handler(message: Message):
    """Идеи для видеографии"""
    await message.answer(
        "💡 <b>Идеи для съёмок</b>\n\n"
        "Функция в разработке...",
        reply_markup=get_videography_submenu(),
        parse_mode=ParseMode.HTML
    )

# Вишлист для видеографии - заглушка удалена (используется основной вишлист)

@router.message(F.text == "📸 Кадр")
async def videography_frame_handler(message: Message):
    """Кадр"""
    await message.answer(
        "📸 <b>Кадр</b>\n\n"
        "Функция в разработке...",
        reply_markup=get_videography_submenu(),
        parse_mode=ParseMode.HTML
    )

@router.message(F.text == "📔 Дневник")
async def diary_handler(message: Message):
    """Дневник"""
    await message.answer(
        "📔 <b>Дневник</b>\n\n"
        "Функция в разработке...",
        reply_markup=get_personal_submenu(),
        parse_mode=ParseMode.HTML
    )

@router.message(F.text == "💪 Тренировки")
async def workouts_handler(message: Message):
    """Тренировки"""
    await message.answer(
        "💪 <b>Тренировки</b>\n\n"
        "Функция в разработке...",
        reply_markup=get_personal_submenu(),
        parse_mode=ParseMode.HTML
    )

# Вишлист - обработчик ниже (строка ~3568)

# ===== ДОБАВЛЕНИЕ МЕСТА =====

@router.message(F.text == "➕ Добавить место")
async def add_place_start(message: Message, state: FSMContext):
    """Начало добавления места"""
    user_place_data[message.from_user.id] = {}
    await state.set_state(AddPlaceStates.waiting_for_name)
    await message.answer(
        "📍 Как называется это место?",
        reply_markup=get_cancel_keyboard()
    )

@router.message(AddPlaceStates.waiting_for_name)
async def process_place_name(message: Message, state: FSMContext):
    """Получение названия места и поиск в Яндекс.Картах"""
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено", reply_markup=get_main_menu())
        return
    
    query = message.text
    
    # Ищем место в Яндекс.Картах
    await message.answer("🔍 Ищу место в Яндекс.Картах...")
    places = await search_place_yandex(query, limit=7)
    
    if not places:
        # Если не нашли - сохраняем название и продолжаем обычный flow
        user_place_data[message.from_user.id]['name'] = message.text.capitalize()
        user_place_data[message.from_user.id]['yandex_data'] = None
        await state.set_state(AddPlaceStates.waiting_for_type)
        await message.answer(
            "❌ Место не найдено в Яндекс.Картах.\n\n"
            "🏷 Выберите тип места вручную:",
            reply_markup=get_place_type_keyboard()
        )
        return
    
    # Сохраняем результаты поиска
    user_place_data[message.from_user.id]['search_results'] = places
    user_place_data[message.from_user.id]['search_query'] = query
    
    # Создаем кнопки для выбора
    keyboard_buttons = []
    for i, place in enumerate(places, 1):
        display_name = place.get('name', 'Без названия')
        address = place.get('description', '')
        button_text = f"{i}. {display_name}"
        if address:
            button_text += f"\n   {address}"
        keyboard_buttons.append([KeyboardButton(text=button_text)])
    
    keyboard_buttons.append([KeyboardButton(text="❌ Не нашёл, введу вручную")])
    keyboard_buttons.append([KeyboardButton(text="❌ Отмена")])
    
    keyboard = ReplyKeyboardMarkup(keyboard=keyboard_buttons, resize_keyboard=True)
    
    await state.set_state(AddPlaceStates.choosing_from_search)
    await message.answer(
        f"✅ Найдено мест: {len(places)}\n\n"
        "Выберите нужное место из списка:",
        reply_markup=keyboard
    )

@router.message(AddPlaceStates.choosing_from_search)
async def process_place_selection(message: Message, state: FSMContext):
    """Обработка выбора места из результатов поиска"""
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено", reply_markup=get_main_menu())
        return
    
    if message.text == "❌ Не нашёл, введу вручную":
        # Переходим к ручному вводу
        query = user_place_data[message.from_user.id].get('search_query', 'Место')
        user_place_data[message.from_user.id]['name'] = query.capitalize()
        user_place_data[message.from_user.id]['yandex_data'] = None
        await state.set_state(AddPlaceStates.waiting_for_type)
        await message.answer(
            "📝 Хорошо, заполним вручную.\n\n"
            "🏷 Выберите тип места:",
            reply_markup=get_place_type_keyboard()
        )
        return
    
    # Определяем номер выбранного места
    try:
        # Пытаемся извлечь номер из начала текста кнопки
        place_num = int(message.text.split('.')[0]) - 1
        search_results = user_place_data[message.from_user.id].get('search_results', [])
        
        if 0 <= place_num < len(search_results):
            selected_place = search_results[place_num]
            
            # Сохраняем выбранное место
            user_place_data[message.from_user.id]['selected_yandex_place'] = selected_place
            user_place_data[message.from_user.id]['name'] = selected_place.get('name', 'Место')
            
            # Спрашиваем: автоматически или вручную
            keyboard = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="🤖 Заполнить автоматически")],
                    [KeyboardButton(text="✍️ Заполнить вручную")],
                    [KeyboardButton(text="❌ Отмена")]
                ],
                resize_keyboard=True
            )
            
            await state.set_state(AddPlaceStates.choosing_fill_method)
            await message.answer(
                f"✅ Выбрано: <b>{selected_place.get('name')}</b>\n"
                f"📍 {selected_place.get('description', '')}\n\n"
                "Как хотите заполнить информацию о месте?",
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard
            )
        else:
            await message.answer("❌ Неверный выбор. Пожалуйста, выберите место из списка.")
    except (ValueError, IndexError):
        await message.answer("❌ Неверный формат. Пожалуйста, выберите место из списка.")

@router.message(AddPlaceStates.choosing_fill_method)
async def process_fill_method(message: Message, state: FSMContext):
    """Обработка выбора способа заполнения: автоматически или вручную"""
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено", reply_markup=get_main_menu())
        return
    
    selected_place = user_place_data[message.from_user.id].get('selected_yandex_place')
    
    if message.text == "🤖 Заполнить автоматически":
        # Получаем детали места из Yandex API
        await message.answer("⏳ Получаю подробную информацию...")
        
        latitude = selected_place.get('latitude')
        longitude = selected_place.get('longitude')
        
        details = await get_place_details_yandex(latitude, longitude)
        
        # Заполняем данные автоматически
        user_place_data[message.from_user.id]['name'] = selected_place.get('name', 'Место')
        user_place_data[message.from_user.id]['address'] = details.get('address') or selected_place.get('address')
        user_place_data[message.from_user.id]['latitude'] = latitude
        user_place_data[message.from_user.id]['longitude'] = longitude
        user_place_data[message.from_user.id]['cuisine'] = details.get('cuisine')
        user_place_data[message.from_user.id]['working_hours'] = details.get('working_hours')
        
        # Пропускаем некоторые шаги и сразу спрашиваем тип места
        await state.set_state(AddPlaceStates.waiting_for_type)
        await message.answer(
            f"✅ Данные получены!\n\n"
            f"📍 <b>Название:</b> {user_place_data[message.from_user.id]['name']}\n"
            f"🗺 <b>Адрес:</b> {user_place_data[message.from_user.id].get('address', 'не указан')}\n"
            f"🍽 <b>Кухня:</b> {user_place_data[message.from_user.id].get('cuisine', 'не определена')}\n"
            f"🕐 <b>Режим работы:</b> {user_place_data[message.from_user.id].get('working_hours', 'не указан')}\n\n"
            "🏷 Теперь выберите тип места:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_place_type_keyboard()
        )
    
    elif message.text == "✍️ Заполнить вручную":
        # Сохраняем только основные данные и переходим к ручному заполнению
        user_place_data[message.from_user.id]['latitude'] = selected_place.get('latitude')
        user_place_data[message.from_user.id]['longitude'] = selected_place.get('longitude')
        
        await state.set_state(AddPlaceStates.waiting_for_type)
        await message.answer(
            "📝 Хорошо, заполним вручную.\n\n"
            "🏷 Выберите тип места:",
            reply_markup=get_place_type_keyboard()
        )
    else:
        await message.answer("❌ Пожалуйста, выберите один из вариантов.")

@router.message(AddPlaceStates.waiting_for_type)
async def process_place_type(message: Message, state: FSMContext):
    """Получение типа места"""
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено", reply_markup=get_main_menu())
        return
    
    # Сохраняем тип места
    user_place_data[message.from_user.id]['place_type'] = message.text
    
    # Если это ресторан, спрашиваем про кухню
    if message.text == "🍽 Ресторан":
        await state.set_state(AddPlaceStates.waiting_for_cuisine)
        await message.answer(
            "🍽 Какая кухня в этом ресторане?",
            reply_markup=get_cuisine_keyboard()
        )
    # Проверяем, нужна ли ценовая категория (для кафе, баров)
    elif message.text in ["🍺 Бар", "☕️ Кафе"]:
        await state.set_state(AddPlaceStates.waiting_for_price)
        await message.answer(
            "💰 Выберите ценовую категорию:",
            reply_markup=get_price_category_keyboard()
        )
    else:
        # Для остальных типов сразу переходим к выбору статуса
        await state.set_state(AddPlaceStates.waiting_for_status)
        await message.answer(
            "📊 Выберите статус места:",
            reply_markup=get_status_keyboard()
        )

@router.message(AddPlaceStates.waiting_for_cuisine)
async def process_cuisine(message: Message, state: FSMContext):
    """Получение типа кухни ресторана"""
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено", reply_markup=get_main_menu())
        return
    
    # Сохраняем тип кухни
    if message.text in CUISINE_TYPES:
        user_place_data[message.from_user.id]['cuisine'] = CUISINE_TYPES[message.text]
    
    # После выбора кухни переходим к ценовой категории
    await state.set_state(AddPlaceStates.waiting_for_price)
    await message.answer(
        "💰 Выберите ценовую категорию:",
        reply_markup=get_price_category_keyboard()
    )

@router.message(AddPlaceStates.waiting_for_price)
async def process_price_category(message: Message, state: FSMContext):
    """Получение ценовой категории"""
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено", reply_markup=get_main_menu())
        return
    
    # Сохраняем ценовую категорию
    user_place_data[message.from_user.id]['price_category'] = message.text
    
    # Переходим к выбору статуса
    await state.set_state(AddPlaceStates.waiting_for_status)
    await message.answer(
        "📊 Выберите статус места:",
        reply_markup=get_status_keyboard()
    )

@router.message(AddPlaceStates.waiting_for_status)
async def process_status(message: Message, state: FSMContext):
    """Получение статуса места"""
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено", reply_markup=get_main_menu())
        return
    
    # Сохраняем статус
    if message.text == "✅ Посещено":
        user_place_data[message.from_user.id]['status'] = 'visited'
        
        # Если посещено - предлагаем написать рецензию
        await state.set_state(AddPlaceStates.waiting_for_review)
        await message.answer(
            "⭐️ Напишите мини-рецензию о месте\n\n"
            "Что понравилось? Ваши впечатления?",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="⏭ Пропустить")],
                    [KeyboardButton(text="❌ Отмена")]
                ],
                resize_keyboard=True
            )
        )
    elif message.text == "📅 Планирую посетить":
        user_place_data[message.from_user.id]['status'] = 'planned'
        
        # Пропускаем рецензию, переходим к адресу
        await state.set_state(AddPlaceStates.waiting_for_address)
        await message.answer(
            "📮 Введите адрес места\n\n"
            "Или нажмите 'Пропустить', если адрес неизвестен",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="⏭ Пропустить")],
                    [KeyboardButton(text="❌ Отмена")]
                ],
                resize_keyboard=True
            )
        )

@router.message(AddPlaceStates.waiting_for_review)
async def process_review(message: Message, state: FSMContext):
    """Получение рецензии"""
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено", reply_markup=get_main_menu())
        return
    
    # Сохраняем рецензию (если не пропустили)
    if message.text != "⏭ Пропустить":
        user_place_data[message.from_user.id]['review'] = message.text
    
    # Переходим к адресу
    await state.set_state(AddPlaceStates.waiting_for_address)
    await message.answer(
        "📮 Введите адрес места\n\n"
        "Или нажмите 'Пропустить', если адрес неизвестен",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="⏭ Пропустить")],
                [KeyboardButton(text="❌ Отмена")]
            ],
            resize_keyboard=True
        )
    )

@router.message(AddPlaceStates.waiting_for_address)
async def process_place_address(message: Message, state: FSMContext):
    """Получение адреса места"""
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено", reply_markup=get_main_menu())
        return
    
    if message.text != "⏭ Пропустить":
        user_place_data[message.from_user.id]['address'] = message.text
    
    await state.set_state(AddPlaceStates.waiting_for_description)
    await message.answer(
        "📝 Добавьте описание или заметку",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="⏭ Пропустить")],
                [KeyboardButton(text="❌ Отмена")]
            ],
            resize_keyboard=True
        )
    )

@router.message(AddPlaceStates.waiting_for_description)
async def process_place_description(message: Message, state: FSMContext):
    """Получение описания места"""
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено", reply_markup=get_main_menu())
        return
    
    if message.text != "⏭ Пропустить":
        user_place_data[message.from_user.id]['description'] = message.text
    
    await state.set_state(AddPlaceStates.waiting_for_social)
    await message.answer(
        "📱 Введите Instagram или Telegram через @\n\n"
        "Например: <code>@username</code>\n\n"
        "Или нажмите 'Пропустить'",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="⏭ Пропустить")],
                [KeyboardButton(text="❌ Отмена")]
            ],
            resize_keyboard=True
        ),
        parse_mode=ParseMode.HTML
    )

@router.message(AddPlaceStates.waiting_for_social)
async def process_place_social(message: Message, state: FSMContext):
    """Получение социальной сети"""
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено", reply_markup=get_main_menu())
        return
    
    if message.text != "⏭ Пропустить":
        social_link = message.text.strip()
        if not social_link.startswith('@'):
            social_link = '@' + social_link
        user_place_data[message.from_user.id]['social_link'] = social_link
    
    await state.set_state(AddPlaceStates.waiting_for_location)
    await message.answer(
        "📍 Отправьте геолокацию места\n\n"
        "🗺 <b>Способы:</b>\n"
        "• Нажмите 📎 → Геопозиция (в Telegram)\n"
        "• Напишите координаты (например: <code>55.7558, 37.6173</code>)\n"
        "• Нажмите 'Завершить' без геолокации",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="✅ Завершить без геолокации")],
                [KeyboardButton(text="❌ Отмена")]
            ],
            resize_keyboard=True
        ),
        parse_mode=ParseMode.HTML
    )

@router.message(AddPlaceStates.waiting_for_location, F.location)
async def process_location(message: Message, state: FSMContext):
    """Получение геолокации"""
    user_place_data[message.from_user.id]['latitude'] = message.location.latitude
    user_place_data[message.from_user.id]['longitude'] = message.location.longitude
    await save_place(message, state)

@router.message(AddPlaceStates.waiting_for_location, F.text == "✅ Завершить без геолокации")
async def process_skip_location(message: Message, state: FSMContext):
    """Пропуск геолокации"""
    await save_place(message, state)

@router.message(AddPlaceStates.waiting_for_location, F.text)
async def process_text_coordinates(message: Message, state: FSMContext):
    """Обработка текстовых координат"""
    if message.text == "❌ Отмена":
        return  # Будет обработано следующим хэндлером
    
    # Пытаемся распарсить координаты из текста
    # Поддерживаем форматы: "55.7558, 37.6173" или "55.7558,37.6173" или "55.7558 37.6173"
    text = message.text.strip().replace(',', ' ')
    parts = text.split()
    
    if len(parts) == 2:
        try:
            lat = float(parts[0])
            lon = float(parts[1])
            
            # Проверяем валидность координат
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                user_place_data[message.from_user.id]['latitude'] = lat
                user_place_data[message.from_user.id]['longitude'] = lon
                await save_place(message, state)
            else:
                await message.answer(
                    "❌ Координаты вне допустимого диапазона\n\n"
                    "Широта: от -90 до 90\n"
                    "Долгота: от -180 до 180\n\n"
                    "Попробуйте еще раз или нажмите 'Завершить'"
                )
        except ValueError:
            await message.answer(
                "❌ Не удалось распознать координаты\n\n"
                "Формат: <code>широта, долгота</code>\n"
                "Пример: <code>55.7558, 37.6173</code>\n\n"
                "Попробуйте еще раз или нажмите 'Завершить'",
                parse_mode=ParseMode.HTML
            )
    else:
        await message.answer(
            "❌ Неверный формат координат\n\n"
            "Формат: <code>широта, долгота</code>\n"
            "Пример: <code>55.7558, 37.6173</code>\n\n"
            "Попробуйте еще раз или нажмите 'Завершить'",
            parse_mode=ParseMode.HTML
        )

@router.message(AddPlaceStates.waiting_for_location, F.text == "❌ Отмена")
async def process_cancel_location(message: Message, state: FSMContext):
    """Отмена добавления"""
    await state.clear()
    user_place_data.pop(message.from_user.id, None)
    await message.answer("Отменено", reply_markup=get_main_menu())

async def save_place(message: Message, state: FSMContext):
    """Сохранение места в базу данных"""
    data = user_place_data.get(message.from_user.id, {})
    
    place_id = await db.add_place(
        user_id=message.from_user.id,
        name=data.get('name'),
        place_type=data.get('place_type'),
        price_category=data.get('price_category'),
        status=data.get('status', 'visited'),
        review=data.get('review'),
        address=data.get('address'),
        description=data.get('description'),
        latitude=data.get('latitude'),
        longitude=data.get('longitude'),
        social_link=data.get('social_link'),
        cuisine=data.get('cuisine'),
        working_hours=data.get('working_hours')
    )
    
    # Очищаем кэш для этого пользователя (статистика изменилась)
    cache.clear(pattern=f"_{message.from_user.id}")
    
    # Синхронизируем с Google Sheets (асинхронно, не блокируя бота)
    place_data_with_id = {**data, 'id': place_id}
    asyncio.create_task(asyncio.to_thread(
        google_sheets.add_place,
        user_id=message.from_user.id,
        user_name=message.from_user.full_name,
        place_data=place_data_with_id
    ))
    
    response = f"✅ Место сохранено!\n\n"
    response += f"📍 <b>{data.get('name')}</b>\n"
    
    # Показываем статус (сразу после названия)
    if data.get('status') == 'visited':
        response += f"✅ Посещено\n"
    elif data.get('status') == 'planned':
        response += f"📅 Планирую посетить\n"
    
    if data.get('place_type'):
        response += f"🏷 {data.get('place_type')}"
        if data.get('price_category'):
            response += f" {data.get('price_category')}"
        # Добавляем кухню для ресторанов
        if data.get('cuisine'):
            response += f" • {data.get('cuisine')}"
        response += "\n"
    
    # Показываем рецензию
    if data.get('review'):
        response += f"⭐️ <i>{data.get('review')}</i>\n"
    
    if data.get('address'):
        response += f"📮 {data.get('address')}\n"
    if data.get('working_hours'):
        response += f"🕐 {data.get('working_hours')}\n"
    if data.get('description'):
        response += f"📝 {data.get('description')}\n"
    if data.get('latitude') and data.get('longitude'):
        response += f"🗺 Координаты сохранены"
    
    await message.answer(response, parse_mode=ParseMode.HTML, reply_markup=get_places_submenu())
    
    # Очистка данных
    user_place_data.pop(message.from_user.id, None)
    await state.clear()

# ===== ПРОСМОТР МЕСТ =====

@router.message(F.text == "📋 Мои места")
async def show_places(message: Message):
    """Показать меню выбора категории мест"""
    places = await db.get_user_places(message.from_user.id)
    
    if not places:
        await message.answer(
            "У вас пока нет сохраненных мест.\n"
            "Нажмите '➕ Добавить место' для начала!",
            reply_markup=get_main_menu()
        )
        return
    
    # Создаем клавиатуру с категориями
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Посещенные", callback_data="filter_status_visited"),
            InlineKeyboardButton(text="📅 Запланированные", callback_data="filter_status_planned")
        ],
        [
            InlineKeyboardButton(text="🍺 Бары", callback_data="filter_🍺 Бар"),
            InlineKeyboardButton(text="☕️ Кафе", callback_data="filter_☕️ Кафе")
        ],
        [
            InlineKeyboardButton(text="🍽 Рестораны", callback_data="filter_🍽 Ресторан"),
            InlineKeyboardButton(text="🏛 Музеи", callback_data="filter_🏛 Музей")
        ],
        [
            InlineKeyboardButton(text="🌳 Парки", callback_data="filter_🌳 Парк"),
            InlineKeyboardButton(text="📍 Локации", callback_data="filter_📍 Локация")
        ],
        [
            InlineKeyboardButton(text="📋 Все места", callback_data="filter_all")
        ]
    ])
    
    await message.answer(
        f"📋 <b>У вас {len(places)} мест</b>\n\n"
        f"Выберите категорию для просмотра:",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )

async def show_places_page(message_or_callback, user_id: int, filter_type: str = "all", status_filter: str = None, offset: int = 0):
    """Показать страницу мест с пагинацией"""
    # Используем фильтрацию на уровне БД (быстрее)
    if filter_type == "all" and not status_filter:
        places = await db.get_user_places(user_id, limit=PLACES_PER_PAGE, offset=offset)
        total_count = await db.count_user_places(user_id)
    elif status_filter:
        places = await db.get_user_places(user_id, place_type=(filter_type if filter_type != "all" else None), status=status_filter, limit=PLACES_PER_PAGE, offset=offset)
        total_count = await db.count_user_places(user_id, place_type=(filter_type if filter_type != "all" else None), status=status_filter)
    else:
        places = await db.get_user_places(user_id, place_type=filter_type, limit=PLACES_PER_PAGE, offset=offset)
        total_count = await db.count_user_places(user_id, place_type=filter_type)
    
    if not places:
        return False, 0
    
    # Отображаем места
    category_name = filter_type if filter_type == "all" else filter_type
    
    for place in places:
        buttons = []
        
        # Кнопка "Посетил" - только для запланированных мест
        if place.get('status') == 'planned':
            buttons.append([InlineKeyboardButton(text="✅ Посетил", callback_data=f"mark_visited_{place['id']}")])
        
        # Кнопка "Показать на карте" - если есть координаты или адрес
        if place.get('latitude') and place.get('longitude'):
            # Если есть координаты - открываем точное место
            yandex_maps_url = f"https://yandex.ru/maps/?pt={place['longitude']},{place['latitude']}&z=16&l=map"
            buttons.append([InlineKeyboardButton(text="🗺 Яндекс.Карты", url=yandex_maps_url)])
        elif place.get('address'):
            # Если только адрес - поиск по адресу
            address_encoded = urllib.parse.quote(place['address'])
            yandex_maps_url = f"https://yandex.ru/maps/?text={address_encoded}"
            buttons.append([InlineKeyboardButton(text="🗺 Яндекс.Карты (поиск)", url=yandex_maps_url)])
        
        # Добавляем кнопку социальной сети, если она указана
        if place.get('social_link'):
            social_link = place['social_link']
            if social_link.startswith('@'):
                # Определяем, Instagram или Telegram (упрощённо)
                if 'tg://' in social_link or 't.me' in social_link:
                    url = f"https://t.me/{social_link[1:]}"
                    text_btn = "📱 Telegram"
                else:
                    url = f"https://instagram.com/{social_link[1:]}"
                    text_btn = "📷 Instagram"
                buttons.append([InlineKeyboardButton(text=text_btn, url=url)])
        
        buttons.append([InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit_{place['id']}")])
        buttons.append([InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete_{place['id']}")])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        text = f"📍 <b>{place['name']}</b>\n"
        if place.get('place_type'):
            text += f"🏷 {place['place_type']}"
            if place.get('price_category'):
                text += f" {place['price_category']}"
            # Добавляем кухню для ресторанов
            if place.get('cuisine'):
                text += f" • {place['cuisine']}"
            text += "\n"
        
        # Показываем статус
        if place.get('status') == 'visited':
            text += f"✅ Посещено\n"
        elif place.get('status') == 'planned':
            text += f"📅 Планирую посетить\n"
        
        # Показываем рецензию
        if place.get('review'):
            text += f"⭐️ <i>{place['review']}</i>\n"
        
        if place['address']:
            text += f"📮 {place['address']}\n"
        if place.get('working_hours'):
            text += f"🕐 Режим работы: {place['working_hours']}\n"
        if place['description']:
            text += f"📝 {place['description']}\n"
        text += f"\n📅 Добавлено: {format_date(place['created_at'])}"
        
        # Определяем целевое сообщение один раз
        target = message_or_callback.message if hasattr(message_or_callback, 'message') else message_or_callback
        
        # Отправляем текст с кнопками
        await target.answer(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )
    
    # Показываем кнопку "Показать еще" если есть еще места
    has_more = (offset + PLACES_PER_PAGE) < total_count
    if has_more:
        target = message_or_callback.message if hasattr(message_or_callback, 'message') else message_or_callback
        more_button = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=f"📄 Показать еще ({total_count - offset - PLACES_PER_PAGE} осталось)",
                callback_data=f"more_{filter_type}_{offset + PLACES_PER_PAGE}"
            )]
        ])
        await target.answer("👇", reply_markup=more_button)
    
    return True, total_count

@router.callback_query(F.data.startswith("filter_"))
async def filter_places(callback: CallbackQuery):
    """Фильтрация мест по категории или статусу"""
    filter_data = callback.data.replace("filter_", "")
    
    await callback.answer()
    
    # Проверяем, это фильтр по статусу или по типу
    if filter_data.startswith("status_"):
        status_filter = filter_data.replace("status_", "")
        filter_type = "all"
        if status_filter == "visited":
            header = "✅ <b>Посещенные места</b>"
        else:
            header = "📅 <b>Запланированные места</b>"
    else:
        status_filter = None
        filter_type = filter_data
        header = f"📋 <b>Все места</b>" if filter_type == "all" else f"<b>{filter_type}</b>"
    
    await callback.message.answer(header, parse_mode=ParseMode.HTML)
    
    success, total = await show_places_page(callback, callback.from_user.id, filter_type, status_filter, 0)
    
    if not success:
        await callback.message.answer("В этой категории пока нет мест")

@router.callback_query(F.data.startswith("more_"))
async def load_more_places(callback: CallbackQuery):
    """Загрузить еще места"""
    parts = callback.data.split("_")
    filter_type = parts[1]
    offset = int(parts[2])
    
    await callback.answer()
    await callback.message.delete()  # Удаляем кнопку "Показать еще"
    
    success, total = await show_places_page(callback, callback.from_user.id, filter_type, offset)
    
    if not success:
        await callback.message.answer("Больше мест нет")

@router.callback_query(F.data.startswith("mark_visited_"))
async def mark_place_visited(callback: CallbackQuery):
    """Пометить место как посещенное"""
    place_id = int(callback.data.split("_")[2])
    place = await db.get_place(place_id, callback.from_user.id)
    
    if not place:
        await callback.answer("Место не найдено", show_alert=True)
        return
    
    # Обновляем статус на "visited"
    await db.update_place(place_id, callback.from_user.id, status='visited')
    
    # Очищаем кэш
    cache.clear(pattern=f"_{callback.from_user.id}")
    
    await callback.answer("✅ Место помечено как посещенное!")
    await callback.message.answer(
        f"✅ <b>{place['name']}</b> перемещено в посещенные места!",
        parse_mode=ParseMode.HTML
    )

def get_edit_place_keyboard():
    """Клавиатура для редактирования места"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Название"), KeyboardButton(text="🏷 Тип")],
            [KeyboardButton(text="💰 Цена"), KeyboardButton(text="🍽 Кухня")],
            [KeyboardButton(text="📊 Статус"), KeyboardButton(text="⭐️ Рецензия")],
            [KeyboardButton(text="📮 Адрес"), KeyboardButton(text="🕐 Режим работы")],
            [KeyboardButton(text="📝 Описание"), KeyboardButton(text="📱 Соцсеть")],
            [KeyboardButton(text="🗺 Локация")],
            [KeyboardButton(text="✅ Готово")]
        ],
        resize_keyboard=True
    )

@router.callback_query(F.data.startswith("edit_"))
async def edit_place_start(callback: CallbackQuery, state: FSMContext):
    """Начать редактирование места"""
    place_id = int(callback.data.split("_")[1])
    place = await db.get_place(place_id, callback.from_user.id)
    
    if not place:
        await callback.answer("Место не найдено", show_alert=True)
        return
    
    # Сохраняем ID и название редактируемого места
    await state.update_data(editing_place_id=place_id, editing_place_name=place['name'])
    await state.set_state(EditPlaceStates.selecting_field)
    
    await callback.message.answer(
        f"✏️ Редактирование места: <b>{place['name']}</b>\n\n"
        f"Выберите, что хотите изменить:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_edit_place_keyboard()
    )
    await callback.answer()

@router.callback_query(F.data.regexp(r"^delete_\d+$"))
async def delete_place_confirm(callback: CallbackQuery):
    """Подтверждение удаления места"""
    place_id = int(callback.data.split("_")[1])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"confirm_delete_{place_id}"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_delete")
        ]
    ])
    
    await callback.message.edit_text(
        "⚠️ Вы уверены, что хотите удалить это место?",
        reply_markup=keyboard
    )

@router.callback_query(F.data.startswith("confirm_delete_"))
async def delete_place(callback: CallbackQuery):
    """Удаление места"""
    place_id = int(callback.data.split("_")[2])
    await db.delete_place(place_id, callback.from_user.id)
    
    # Удаляем из Google Sheets (асинхронно, не блокируя)
    asyncio.create_task(asyncio.to_thread(
        google_sheets.delete_place,
        place_id
    ))
    
    # Очищаем кэш
    cache.clear(pattern=f"_{callback.from_user.id}")
    
    await callback.message.edit_text("🗑 Место удалено")
    await callback.answer("Удалено успешно")

@router.callback_query(F.data == "cancel_delete")
async def cancel_delete(callback: CallbackQuery):
    """Отмена удаления"""
    await callback.message.delete()
    await callback.answer("Отменено")

# ===== ПОИСК =====

# Состояния для поиска
class SearchStates(StatesGroup):
    waiting_for_query = State()

@router.message(F.text == "🔍 Поиск")
async def search_start(message: Message, state: FSMContext):
    """Начало поиска"""
    await state.set_state(SearchStates.waiting_for_query)
    await message.answer(
        "🔍 Введите название места для поиска:",
        reply_markup=get_cancel_keyboard()
    )

@router.message(SearchStates.waiting_for_query)
async def search_places(message: Message, state: FSMContext):
    """Поиск мест"""
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено", reply_markup=get_main_menu())
        return
    
    query = message.text
    places = await db.search_places(message.from_user.id, query)
    
    await state.clear()
    
    if not places:
        await message.answer(
            f"😔 Места по запросу '<i>{query}</i>' не найдены",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_menu()
        )
        return
    
    await message.answer(
        f"🔍 Найдено мест: <b>{len(places)}</b>",
        parse_mode=ParseMode.HTML
    )
    
    for place in places:
        buttons = []
        
        # Кнопка "Посетил" - только для запланированных мест
        if place.get('status') == 'planned':
            buttons.append([InlineKeyboardButton(text="✅ Посетил", callback_data=f"mark_visited_{place['id']}")])
        
        # Кнопка "Показать на карте" - если есть координаты или адрес
        if place.get('latitude') and place.get('longitude'):
            # Если есть координаты - открываем точное место
            yandex_maps_url = f"https://yandex.ru/maps/?pt={place['longitude']},{place['latitude']}&z=16&l=map"
            buttons.append([InlineKeyboardButton(text="🗺 Яндекс.Карты", url=yandex_maps_url)])
        elif place.get('address'):
            # Если только адрес - поиск по адресу
            address_encoded = urllib.parse.quote(place['address'])
            yandex_maps_url = f"https://yandex.ru/maps/?text={address_encoded}"
            buttons.append([InlineKeyboardButton(text="🗺 Яндекс.Карты (поиск)", url=yandex_maps_url)])
        
        buttons.append([InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit_{place['id']}")])
        buttons.append([InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete_{place['id']}")])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        text = f"📍 <b>{place['name']}</b>\n"
        if place.get('place_type'):
            text += f"🏷 {place['place_type']}"
            if place.get('price_category'):
                text += f" {place['price_category']}"
            # Добавляем кухню для ресторанов
            if place.get('cuisine'):
                text += f" • {place['cuisine']}"
            text += "\n"
        if place['address']:
            text += f"📮 {place['address']}\n"
        if place.get('working_hours'):
            text += f"🕐 Режим работы: {place['working_hours']}\n"
        if place['description']:
            text += f"📝 {place['description']}"
        
        if place['latitude'] and place['longitude']:
            await message.answer_location(
                latitude=place['latitude'],
                longitude=place['longitude']
            )
        
        await message.answer(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )

# ===== РЕДАКТИРОВАНИЕ МЕСТА =====

@router.message(EditPlaceStates.selecting_field)
async def edit_place_select_field(message: Message, state: FSMContext):
    """Выбор поля для редактирования"""
    if message.text == "✅ Готово":
        await state.clear()
        await message.answer("✅ Редактирование завершено!", reply_markup=get_main_menu())
        return
    
    field_map = {
        "📝 Название": ("name", EditPlaceStates.editing_name, "Введите новое название места:"),
        "🏷 Тип": ("place_type", EditPlaceStates.editing_type, "Выберите новый тип места:"),
        "💰 Цена": ("price_category", EditPlaceStates.editing_price, "Выберите новую ценовую категорию:"),
        "🍽 Кухня": ("cuisine", EditPlaceStates.editing_cuisine, "Выберите новый тип кухни:"),
        "📊 Статус": ("status", EditPlaceStates.editing_status, "Выберите новый статус:"),
        "⭐️ Рецензия": ("review", EditPlaceStates.editing_review, "Введите новую рецензию:"),
        "📮 Адрес": ("address", EditPlaceStates.editing_address, "Введите новый адрес:"),
        "🕐 Режим работы": ("working_hours", EditPlaceStates.editing_working_hours, "Введите режим работы (например, 09:00 - 22:00):"),
        "📝 Описание": ("description", EditPlaceStates.editing_description, "Введите новое описание:"),
        "📱 Соцсеть": ("social_link", EditPlaceStates.editing_social, "Введите новую ссылку (или @ username):"),
        "🗺 Локация": ("location", EditPlaceStates.editing_location, "Отправьте новую геолокацию:")
    }
    
    if message.text not in field_map:
        await message.answer("Неверный выбор. Попробуйте снова.")
        return
    
    field, new_state, prompt = field_map[message.text]
    await state.update_data(editing_field=field)
    await state.set_state(new_state)
    
    # Показываем соответствующую клавиатуру
    if field == "place_type":
        keyboard = get_place_type_keyboard()
    elif field == "price_category":
        keyboard = get_price_category_keyboard()
    elif field == "cuisine":
        keyboard = get_cuisine_keyboard()
    elif field == "status":
        keyboard = get_status_keyboard()
    else:
        keyboard = get_cancel_keyboard()
    
    await message.answer(prompt, reply_markup=keyboard)

@router.message(EditPlaceStates.editing_name)
async def edit_place_name(message: Message, state: FSMContext):
    """Редактирование названия места"""
    if message.text == "❌ Отмена":
        await state.set_state(EditPlaceStates.selecting_field)
        data = await state.get_data()
        place_name = data.get('editing_place_name', 'место')
        await message.answer(
            f"Отменено.\n\n✏️ Редактирование места: <b>{place_name}</b>\n\nВыберите, что хотите изменить:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_edit_place_keyboard()
        )
        return
    
    data = await state.get_data()
    place_id = data.get('editing_place_id')
    await db.update_place(place_id, message.from_user.id, name=message.text)
    cache.clear(pattern=f"_{message.from_user.id}")
    
    # Обновляем название в state
    await state.update_data(editing_place_name=message.text)
    await state.set_state(EditPlaceStates.selecting_field)
    
    await message.answer(
        f"✅ Название обновлено на: <b>{message.text}</b>\n\n"
        f"✏️ Редактирование места: <b>{message.text}</b>\n\nВыберите, что ещё хотите изменить:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_edit_place_keyboard()
    )

@router.message(EditPlaceStates.editing_type)
async def edit_place_type(message: Message, state: FSMContext):
    """Редактирование типа места"""
    data = await state.get_data()
    place_name = data.get('editing_place_name', 'место')
    
    if message.text == "❌ Отмена":
        await state.set_state(EditPlaceStates.selecting_field)
        await message.answer(
            f"Отменено.\n\n✏️ Редактирование места: <b>{place_name}</b>\n\nВыберите, что хотите изменить:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_edit_place_keyboard()
        )
        return
    
    place_id = data.get('editing_place_id')
    await db.update_place(place_id, message.from_user.id, place_type=message.text)
    cache.clear(pattern=f"_{message.from_user.id}")
    await state.set_state(EditPlaceStates.selecting_field)
    
    await message.answer(
        f"✅ Тип места обновлен на: {message.text}\n\n"
        f"✏️ Редактирование места: <b>{place_name}</b>\n\nВыберите, что ещё хотите изменить:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_edit_place_keyboard()
    )

@router.message(EditPlaceStates.editing_cuisine)
async def edit_place_cuisine(message: Message, state: FSMContext):
    """Редактирование кухни ресторана"""
    data = await state.get_data()
    place_name = data.get('editing_place_name', 'место')
    
    if message.text == "❌ Отмена":
        await state.set_state(EditPlaceStates.selecting_field)
        await message.answer(
            f"Отменено.\n\n✏️ Редактирование места: <b>{place_name}</b>\n\nВыберите, что хотите изменить:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_edit_place_keyboard()
        )
        return
    
    place_id = data.get('editing_place_id')
    cuisine = CUISINE_TYPES.get(message.text, message.text)
    await db.update_place(place_id, message.from_user.id, cuisine=cuisine)
    cache.clear(pattern=f"_{message.from_user.id}")
    await state.set_state(EditPlaceStates.selecting_field)
    
    await message.answer(
        f"✅ Кухня обновлена на: {cuisine}\n\n"
        f"✏️ Редактирование места: <b>{place_name}</b>\n\nВыберите, что ещё хотите изменить:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_edit_place_keyboard()
    )

@router.message(EditPlaceStates.editing_price)
async def edit_place_price(message: Message, state: FSMContext):
    """Редактирование ценовой категории"""
    data = await state.get_data()
    place_name = data.get('editing_place_name', 'место')
    
    if message.text == "❌ Отмена":
        await state.set_state(EditPlaceStates.selecting_field)
        await message.answer(
            f"Отменено.\n\n✏️ Редактирование места: <b>{place_name}</b>\n\nВыберите, что хотите изменить:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_edit_place_keyboard()
        )
        return
    
    place_id = data.get('editing_place_id')
    await db.update_place(place_id, message.from_user.id, price_category=message.text)
    cache.clear(pattern=f"_{message.from_user.id}")
    await state.set_state(EditPlaceStates.selecting_field)
    
    await message.answer(
        f"✅ Ценовая категория обновлена на: {message.text}\n\n"
        f"✏️ Редактирование места: <b>{place_name}</b>\n\nВыберите, что ещё хотите изменить:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_edit_place_keyboard()
    )

@router.message(EditPlaceStates.editing_status)
async def edit_place_status(message: Message, state: FSMContext):
    """Редактирование статуса места"""
    data = await state.get_data()
    place_name = data.get('editing_place_name', 'место')
    
    if message.text == "❌ Отмена":
        await state.set_state(EditPlaceStates.selecting_field)
        await message.answer(
            f"Отменено.\n\n✏️ Редактирование места: <b>{place_name}</b>\n\nВыберите, что хотите изменить:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_edit_place_keyboard()
        )
        return
    
    place_id = data.get('editing_place_id')
    status = 'visited' if message.text == "✅ Посещено" else 'planned'
    await db.update_place(place_id, message.from_user.id, status=status)
    cache.clear(pattern=f"_{message.from_user.id}")
    await state.set_state(EditPlaceStates.selecting_field)
    
    await message.answer(
        f"✅ Статус обновлен на: {message.text}\n\n"
        f"✏️ Редактирование места: <b>{place_name}</b>\n\nВыберите, что ещё хотите изменить:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_edit_place_keyboard()
    )

@router.message(EditPlaceStates.editing_review)
async def edit_place_review(message: Message, state: FSMContext):
    """Редактирование рецензии"""
    data = await state.get_data()
    place_name = data.get('editing_place_name', 'место')
    
    if message.text == "❌ Отмена":
        await state.set_state(EditPlaceStates.selecting_field)
        await message.answer(
            f"Отменено.\n\n✏️ Редактирование места: <b>{place_name}</b>\n\nВыберите, что хотите изменить:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_edit_place_keyboard()
        )
        return
    
    place_id = data.get('editing_place_id')
    await db.update_place(place_id, message.from_user.id, review=message.text)
    cache.clear(pattern=f"_{message.from_user.id}")
    await state.set_state(EditPlaceStates.selecting_field)
    
    await message.answer(
        f"✅ Рецензия обновлена\n\n"
        f"✏️ Редактирование места: <b>{place_name}</b>\n\nВыберите, что ещё хотите изменить:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_edit_place_keyboard()
    )

@router.message(EditPlaceStates.editing_address)
async def edit_place_address(message: Message, state: FSMContext):
    """Редактирование адреса"""
    data = await state.get_data()
    place_name = data.get('editing_place_name', 'место')
    
    if message.text == "❌ Отмена":
        await state.set_state(EditPlaceStates.selecting_field)
        await message.answer(
            f"Отменено.\n\n✏️ Редактирование места: <b>{place_name}</b>\n\nВыберите, что хотите изменить:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_edit_place_keyboard()
        )
        return
    
    place_id = data.get('editing_place_id')
    await db.update_place(place_id, message.from_user.id, address=message.text)
    cache.clear(pattern=f"_{message.from_user.id}")
    await state.set_state(EditPlaceStates.selecting_field)
    
    await message.answer(
        f"✅ Адрес обновлен\n\n"
        f"✏️ Редактирование места: <b>{place_name}</b>\n\nВыберите, что ещё хотите изменить:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_edit_place_keyboard()
    )

@router.message(EditPlaceStates.editing_working_hours)
async def edit_place_working_hours(message: Message, state: FSMContext):
    """Редактирование режима работы"""
    data = await state.get_data()
    place_name = data.get('editing_place_name', 'место')
    
    if message.text == "❌ Отмена":
        await state.set_state(EditPlaceStates.selecting_field)
        await message.answer(
            f"Отменено.\n\n✏️ Редактирование места: <b>{place_name}</b>\n\nВыберите, что хотите изменить:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_edit_place_keyboard()
        )
        return
    
    place_id = data.get('editing_place_id')
    await db.update_place(place_id, message.from_user.id, working_hours=message.text)
    cache.clear(pattern=f"_{message.from_user.id}")
    await state.set_state(EditPlaceStates.selecting_field)
    
    await message.answer(
        f"✅ Режим работы обновлен\n\n"
        f"✏️ Редактирование места: <b>{place_name}</b>\n\nВыберите, что ещё хотите изменить:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_edit_place_keyboard()
    )

@router.message(EditPlaceStates.editing_description)
async def edit_place_description(message: Message, state: FSMContext):
    """Редактирование описания"""
    data = await state.get_data()
    place_name = data.get('editing_place_name', 'место')
    
    if message.text == "❌ Отмена":
        await state.set_state(EditPlaceStates.selecting_field)
        await message.answer(
            f"Отменено.\n\n✏️ Редактирование места: <b>{place_name}</b>\n\nВыберите, что хотите изменить:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_edit_place_keyboard()
        )
        return
    
    place_id = data.get('editing_place_id')
    await db.update_place(place_id, message.from_user.id, description=message.text)
    cache.clear(pattern=f"_{message.from_user.id}")
    await state.set_state(EditPlaceStates.selecting_field)
    
    await message.answer(
        f"✅ Описание обновлено\n\n"
        f"✏️ Редактирование места: <b>{place_name}</b>\n\nВыберите, что ещё хотите изменить:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_edit_place_keyboard()
    )

@router.message(EditPlaceStates.editing_social)
async def edit_place_social(message: Message, state: FSMContext):
    """Редактирование соцсети"""
    data = await state.get_data()
    place_name = data.get('editing_place_name', 'место')
    
    if message.text == "❌ Отмена":
        await state.set_state(EditPlaceStates.selecting_field)
        await message.answer(
            f"Отменено.\n\n✏️ Редактирование места: <b>{place_name}</b>\n\nВыберите, что хотите изменить:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_edit_place_keyboard()
        )
        return
    
    place_id = data.get('editing_place_id')
    await db.update_place(place_id, message.from_user.id, social_link=message.text)
    cache.clear(pattern=f"_{message.from_user.id}")
    await state.set_state(EditPlaceStates.selecting_field)
    
    await message.answer(
        f"✅ Соцсеть обновлена\n\n"
        f"✏️ Редактирование места: <b>{place_name}</b>\n\nВыберите, что ещё хотите изменить:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_edit_place_keyboard()
    )

@router.message(EditPlaceStates.editing_location)
async def edit_place_location(message: Message, state: FSMContext):
    """Редактирование локации"""
    data = await state.get_data()
    place_name = data.get('editing_place_name', 'место')
    
    if message.text == "❌ Отмена":
        await state.set_state(EditPlaceStates.selecting_field)
        await message.answer(
            f"Отменено.\n\n✏️ Редактирование места: <b>{place_name}</b>\n\nВыберите, что хотите изменить:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_edit_place_keyboard()
        )
        return
    
    latitude = None
    longitude = None
    
    if message.location:
        # Геолокация из Telegram
        latitude = message.location.latitude
        longitude = message.location.longitude
    elif message.text:
        # Парсим текстовый ввод координат
        try:
            # Пробуем разделить по запятой или пробелу
            coords = message.text.replace(',', ' ').split()
            if len(coords) == 2:
                latitude = float(coords[0].strip())
                longitude = float(coords[1].strip())
                # Проверка валидности координат
                if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                    raise ValueError("Координаты вне допустимого диапазона")
            else:
                raise ValueError("Неверный формат")
        except (ValueError, IndexError):
            await message.answer(
                "❌ Неверный формат координат!\n\n"
                "Отправьте геолокацию через Telegram или введите координаты в формате:\n"
                "55.7558, 37.6173\n"
                "или\n"
                "55.7558 37.6173"
            )
            return
    
    if latitude and longitude:
        place_id = data.get('editing_place_id')
        await db.update_place(
            place_id, message.from_user.id,
            latitude=latitude,
            longitude=longitude
        )
        cache.clear(pattern=f"_{message.from_user.id}")
        await state.set_state(EditPlaceStates.selecting_field)
        
        await message.answer(
            f"✅ Локация обновлена ({latitude}, {longitude})\n\n"
            f"✏️ Редактирование места: <b>{place_name}</b>\n\nВыберите, что ещё хотите изменить:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_edit_place_keyboard()
        )
    else:
        await message.answer(
            "Пожалуйста, отправьте геолокацию или введите координаты в формате:\n"
            "55.7558, 37.6173"
        )

# ===== СТАТИСТИКА =====

@router.message(F.text == "📊 Статистика")
async def show_stats(message: Message):
    """Показать статистику пользователя с кэшированием"""
    cache_key = f"stats_{message.from_user.id}"
    
    # Пробуем получить из кэша
    cached_count = cache.get(cache_key)
    if cached_count is not None:
        count = cached_count
    else:
        count = await db.count_user_places(message.from_user.id)
        cache.set(cache_key, count)
    
    await message.answer(
        f"📊 <b>Ваша статистика:</b>\n\n"
        f"📍 Сохранено мест: <b>{count}</b>\n"
        f"👤 Пользователь: {message.from_user.full_name}",
        parse_mode=ParseMode.HTML
    )

# ===== МЕРОПРИЯТИЯ =====

@router.message(F.text == "🎉 Добавить мероприятие")
async def add_event(message: Message):
    """Добавление мероприятия"""
    await message.answer(
        "🎉 <b>Функция в разработке!</b>\n\n"
        "Скоро вы сможете добавлять мероприятия с датой и временем.",
        parse_mode=ParseMode.HTML,
        reply_markup=get_places_submenu()
    )

# ===== ИЗУЧЕНИЕ =====

@router.message(F.text == "🎬 Фильмы")
async def show_movies(message: Message):
    """Раздел фильмов"""
    await message.answer(
        "🎬 <b>Фильмы</b>\n\n"
        "Здесь вы сможете:\n"
        "• Сохранять фильмы к просмотру\n"
        "• Отмечать просмотренные\n"
        "• Добавлять заметки и оценки\n\n"
        "<i>Функция в разработке...</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_learning_submenu()
    )

@router.message(F.text == "📖 Книги")
async def show_books(message: Message):
    """Раздел книг"""
    await message.answer(
        "📖 <b>Книги</b>\n\n"
        "Здесь вы сможете:\n"
        "• Вести список книг для чтения\n"
        "• Отмечать прочитанные\n"
        "• Сохранять цитаты и мысли\n\n"
        "<i>Функция в разработке...</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_learning_submenu()
    )

@router.message(F.text == "💡 Новые темы")
async def show_topics(message: Message):
    """Раздел новых тем"""
    await message.answer(
        "💡 <b>Новые темы</b>\n\n"
        "Здесь вы сможете:\n"
        "• Сохранять интересные темы для изучения\n"
        "• Отслеживать прогресс обучения\n"
        "• Добавлять заметки и ресурсы\n\n"
        "<i>Функция в разработке...</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_learning_submenu()
    )

# ===== ПУТЕШЕСТВИЕ =====

@router.message(F.text == "🗺 Планы поездок")
async def show_travel_plans(message: Message):
    """Планы поездок"""
    await message.answer(
        "🗺 <b>Планы поездок</b>\n\n"
        "Здесь вы сможете:\n"
        "• Создавать планы будущих поездок\n"
        "• Добавлять места которые хотите посетить\n"
        "• Планировать маршруты\n\n"
        "<i>Функция в разработке...</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_travel_submenu()
    )

@router.message(F.text == "✈️ Посещенные страны")
async def show_visited_countries(message: Message):
    """Посещенные страны"""
    await message.answer(
        "✈️ <b>Посещенные страны</b>\n\n"
        "Здесь вы сможете:\n"
        "• Отмечать страны которые посетили\n"
        "• Добавлять фото и воспоминания\n"
        "• Видеть карту своих путешествий\n\n"
        "<i>Функция в разработке...</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_travel_submenu()
    )

@router.message(F.text == "📝 Список желаний")
async def show_travel_wishlist(message: Message):
    """Список желаний для путешествий"""
    await message.answer(
        "📝 <b>Список желаний</b>\n\n"
        "Здесь вы сможете:\n"
        "• Сохранять места мечты\n"
        "• Отслеживать прогресс\n"
        "• Планировать бюджет поездок\n\n"
        "<i>Функция в разработке...</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_travel_submenu()
    )

# ===== ФИНАНСЫ =====

@router.message(F.text == "💸 Расходы")
async def show_expenses_menu(message: Message):
    """Показать меню расходов"""
    await message.answer(
        "💸 <b>Расходы</b>\n\nУправляйте своими тратами:",
        reply_markup=get_expenses_submenu(),
        parse_mode=ParseMode.HTML
    )

# ===== ТРАТЫ =====

@router.message(F.text == "➕ Новая трата")
async def add_expense_start(message: Message, state: FSMContext):
    """Начало добавления траты"""
    user_expense_data[message.from_user.id] = {}
    await state.set_state(AddExpenseStates.waiting_for_category)
    await message.answer(
        "🏷 Выберите категорию траты:",
        reply_markup=get_expense_category_keyboard()
    )

@router.message(AddExpenseStates.waiting_for_category)
async def process_expense_category(message: Message, state: FSMContext):
    """Получение категории траты"""
    if message.text == "❌ Отмена":
        await state.clear()
        del user_expense_data[message.from_user.id]
        await message.answer("Отменено", reply_markup=get_finance_submenu())
        return
    
    user_expense_data[message.from_user.id]['category'] = message.text
    await state.set_state(AddExpenseStates.waiting_for_name)
    await message.answer(
        "📝 Введите название траты:",
        reply_markup=get_cancel_keyboard()
    )

@router.message(AddExpenseStates.waiting_for_name)
async def process_expense_name(message: Message, state: FSMContext):
    """Получение названия траты"""
    if message.text == "❌ Отмена":
        await state.clear()
        del user_expense_data[message.from_user.id]
        await message.answer("Отменено", reply_markup=get_finance_submenu())
        return
    
    user_expense_data[message.from_user.id]['name'] = message.text.capitalize()
    await state.set_state(AddExpenseStates.waiting_for_amount)
    await message.answer(
        "💰 Введите сумму:",
        reply_markup=get_cancel_keyboard()
    )

@router.message(AddExpenseStates.waiting_for_amount)
async def process_expense_amount(message: Message, state: FSMContext):
    """Получение суммы траты"""
    if message.text == "❌ Отмена":
        await state.clear()
        del user_expense_data[message.from_user.id]
        await message.answer("Отменено", reply_markup=get_finance_submenu())
        return
    
    try:
        amount = float(message.text.replace(',', '.'))
        if amount < 0:
            await message.answer("❌ Сумма не может быть отрицательной. Попробуйте ещё раз:")
            return
        user_expense_data[message.from_user.id]['amount'] = amount
    except ValueError:
        await message.answer("❌ Неверный формат. Введите число:")
        return
    
    await state.set_state(AddExpenseStates.waiting_for_date_choice)
    await message.answer(
        "📅 Выберите дату траты:",
        reply_markup=get_date_choice_keyboard()
    )

@router.message(AddExpenseStates.waiting_for_date_choice)
async def process_expense_date_choice(message: Message, state: FSMContext):
    """Обработка выбора даты"""
    if message.text == "❌ Отмена":
        await state.clear()
        del user_expense_data[message.from_user.id]
        await message.answer("Отменено", reply_markup=get_finance_submenu())
        return
    
    if message.text == "📅 Сегодня":
        user_expense_data[message.from_user.id]['expense_date'] = datetime.now().strftime('%d.%m.%Y')
        await state.set_state(AddExpenseStates.waiting_for_note_choice)
        await message.answer(
            "📝 Хотите добавить заметку?",
            reply_markup=get_note_keyboard()
        )
    elif message.text == "📆 Ввести дату":
        await state.set_state(AddExpenseStates.waiting_for_date)
        await message.answer(
            "📅 Введите дату:\n\n"
            "Формат: ДД.ММ.ГГГГ (например: 06.10.2025)\n"
            "Или просто ДД.ММ (год подставится автоматически)",
            reply_markup=get_cancel_keyboard()
        )
    else:
        await message.answer("❌ Неверный выбор. Используйте кнопки:")

@router.message(AddExpenseStates.waiting_for_date)
async def process_expense_date(message: Message, state: FSMContext):
    """Получение даты вручную"""
    if message.text == "❌ Отмена":
        await state.clear()
        del user_expense_data[message.from_user.id]
        await message.answer("Отменено", reply_markup=get_finance_submenu())
        return
    
    try:
        date_parts = message.text.strip().split('.')
        if len(date_parts) == 2:
            day, month = date_parts
            year = datetime.now().year
        elif len(date_parts) == 3:
            day, month, year = date_parts
        else:
            raise ValueError("Неверный формат")
        
        expense_date = datetime(int(year), int(month), int(day))
        user_expense_data[message.from_user.id]['expense_date'] = expense_date.strftime('%d.%m.%Y')
        
    except (ValueError, IndexError):
        await message.answer(
            "❌ Неверный формат даты. Попробуйте ещё раз.\n"
            "Например: 06.10.2025 или 06.10"
        )
        return
    
    await state.set_state(AddExpenseStates.waiting_for_note_choice)
    await message.answer(
        "📝 Хотите добавить заметку?",
        reply_markup=get_note_keyboard()
    )

@router.message(AddExpenseStates.waiting_for_note_choice)
async def process_expense_note_choice(message: Message, state: FSMContext):
    """Обработка выбора заметки"""
    if message.text == "❌ Отмена":
        await state.clear()
        del user_expense_data[message.from_user.id]
        await message.answer("Отменено", reply_markup=get_finance_submenu())
        return
    
    if message.text == "⏭ Пропустить":
        user_expense_data[message.from_user.id]['note'] = None
        await save_expense(message, state)
    elif message.text == "✍️ Добавить заметку":
        await state.set_state(AddExpenseStates.waiting_for_note)
        await message.answer(
            "📝 Введите заметку:",
            reply_markup=get_cancel_keyboard()
        )
    else:
        await message.answer("❌ Неверный выбор. Используйте кнопки:")

@router.message(AddExpenseStates.waiting_for_note)
async def process_expense_note(message: Message, state: FSMContext):
    """Получение заметки"""
    if message.text == "❌ Отмена":
        await state.clear()
        del user_expense_data[message.from_user.id]
        await message.answer("Отменено", reply_markup=get_finance_submenu())
        return
    
    user_expense_data[message.from_user.id]['note'] = message.text
    await save_expense(message, state)

async def save_expense(message: Message, state: FSMContext):
    """Сохранение траты"""
    category = user_expense_data[message.from_user.id]['category']
    name = user_expense_data[message.from_user.id]['name']
    amount = user_expense_data[message.from_user.id]['amount']
    expense_date = user_expense_data[message.from_user.id]['expense_date']
    note = user_expense_data[message.from_user.id].get('note')
    
    # Сохраняем в БД
    expense_id = await db.add_expense(
        user_id=message.from_user.id,
        category=category,
        name=name,
        amount=amount,
        expense_date=expense_date,
        note=note
    )
    
    # Синхронизация с Google Sheets
    if google_sheets.enabled:
        await asyncio.to_thread(
            google_sheets.add_expense,
            message.from_user.id,
            message.from_user.full_name,
            {
                'id': expense_id,
                'category': category,
                'name': name,
                'amount': amount,
                'expense_date': expense_date,
                'note': note or ''
            }
        )
    
    # Формируем итоговое сообщение
    result_message = f"✅ Трата добавлена!\n\n"
    result_message += f"{category} {name}\n"
    result_message += f"💰 {amount:,.0f} ₽\n"
    result_message += f"📅 {expense_date}"
    if note:
        result_message += f"\n📝 {note}"
    
    await state.clear()
    del user_expense_data[message.from_user.id]
    await message.answer(result_message, reply_markup=get_expenses_submenu())

# ===== ОБЯЗАТЕЛЬНЫЕ РАСХОДЫ =====

@router.message(F.text == "📋 Обязательные расходы")
async def show_recurring_expenses_menu(message: Message):
    """Показать меню обязательных расходов"""
    await message.answer(
        "📋 <b>Обязательные расходы</b>\n\nУправляйте регулярными платежами:",
        reply_markup=get_recurring_expenses_submenu(),
        parse_mode=ParseMode.HTML
    )

@router.message(F.text == "➕ Добавить")
async def add_recurring_expense_start(message: Message, state: FSMContext):
    """Начало добавления обязательного расхода"""
    user_recurring_expense_data[message.from_user.id] = {}
    await state.set_state(AddRecurringExpenseStates.waiting_for_name)
    await message.answer(
        "📝 Введите название платежа\n(например: Подписка Spotify, Кредит):",
        reply_markup=get_cancel_keyboard()
    )

@router.message(AddRecurringExpenseStates.waiting_for_name)
async def process_recurring_expense_name(message: Message, state: FSMContext):
    """Получение названия обязательного расхода"""
    if message.text == "❌ Отмена":
        await state.clear()
        del user_recurring_expense_data[message.from_user.id]
        await message.answer("Отменено", reply_markup=get_finance_submenu())
        return
    
    user_recurring_expense_data[message.from_user.id]['name'] = message.text.capitalize()
    await state.set_state(AddRecurringExpenseStates.waiting_for_amount)
    await message.answer(
        "💰 Введите сумму платежа:",
        reply_markup=get_cancel_keyboard()
    )

@router.message(AddRecurringExpenseStates.waiting_for_amount)
async def process_recurring_expense_amount(message: Message, state: FSMContext):
    """Получение суммы обязательного расхода"""
    if message.text == "❌ Отмена":
        await state.clear()
        del user_recurring_expense_data[message.from_user.id]
        await message.answer("Отменено", reply_markup=get_finance_submenu())
        return
    
    try:
        amount = float(message.text.replace(',', '.'))
        if amount < 0:
            await message.answer("❌ Сумма не может быть отрицательной. Попробуйте ещё раз:")
            return
        user_recurring_expense_data[message.from_user.id]['amount'] = amount
    except ValueError:
        await message.answer("❌ Неверный формат. Введите число:")
        return
    
    await state.set_state(AddRecurringExpenseStates.waiting_for_date)
    await message.answer(
        "📅 Введите дату оплаты:\n\n"
        "Формат: ДД.ММ.ГГГГ (например: 05.10.2025)\n"
        "Или просто ДД.ММ (год подставится автоматически)",
        reply_markup=get_cancel_keyboard()
    )

@router.message(AddRecurringExpenseStates.waiting_for_date)
async def process_recurring_expense_date(message: Message, state: FSMContext):
    """Получение даты обязательного расхода и сохранение"""
    if message.text == "❌ Отмена":
        await state.clear()
        del user_recurring_expense_data[message.from_user.id]
        await message.answer("Отменено", reply_markup=get_finance_submenu())
        return
    
    try:
        date_parts = message.text.strip().split('.')
        if len(date_parts) == 2:
            day, month = date_parts
            year = datetime.now().year
        elif len(date_parts) == 3:
            day, month, year = date_parts
        else:
            raise ValueError("Неверный формат")
        
        payment_date = datetime(int(year), int(month), int(day))
        user_recurring_expense_data[message.from_user.id]['payment_date'] = payment_date.strftime('%d.%m.%Y')
        
    except (ValueError, IndexError):
        await message.answer(
            "❌ Неверный формат даты. Попробуйте ещё раз.\n"
            "Например: 05.10.2025 или 05.10"
        )
        return
    
    # Сохраняем в БД
    name = user_recurring_expense_data[message.from_user.id]['name']
    amount = user_recurring_expense_data[message.from_user.id]['amount']
    
    recurring_id = await db.add_recurring_expense(
        user_id=message.from_user.id,
        name=name,
        amount=amount,
        payment_date=user_recurring_expense_data[message.from_user.id]['payment_date']
    )
    
    # Синхронизация с Google Sheets
    if google_sheets.enabled:
        await asyncio.to_thread(
            google_sheets.add_recurring_expense,
            message.from_user.id,
            message.from_user.full_name,
            {
                'id': recurring_id,
                'name': name,
                'amount': amount,
                'payment_date': user_recurring_expense_data[message.from_user.id]['payment_date']
            }
        )
    
    # Формируем итоговое сообщение
    result_message = (
        f"✅ Обязательный расход добавлен!\n\n"
        f"📝 {name}\n"
        f"💰 {amount:,.0f} ₽\n"
        f"📅 {payment_date.strftime('%d.%m')}"
    )
    
    await state.clear()
    del user_recurring_expense_data[message.from_user.id]
    await message.answer(result_message, reply_markup=get_recurring_expenses_submenu())

@router.message(F.text == "📋 Мои платежи")
async def show_recurring_expenses_list(message: Message):
    """Показать список обязательных расходов"""
    user_id = message.from_user.id
    
    expenses = await db.get_user_recurring_expenses(user_id)
    
    if not expenses:
        await message.answer(
            "📋 У вас пока нет обязательных расходов.\n\n"
            "Добавьте первый через «➕ Добавить»",
            reply_markup=get_recurring_expenses_submenu()
        )
        return
    
    # Формируем список
    text = "📋 <b>Обязательные расходы:</b>\n\n"
    total = 0
    for expense in expenses:
        text += f"<b>{expense['payment_date']}</b> — {expense['name']} — {expense['amount']:,.0f} ₽\n"
        total += expense['amount']
    
    text += f"\n💰 <b>Итого:</b> {total:,.0f} ₽/месяц"
    
    await message.answer(text, reply_markup=get_recurring_expenses_submenu(), parse_mode=ParseMode.HTML)

@router.message(F.text == "📋 История трат")
async def show_expenses_history(message: Message):
    """Показать историю трат"""
    user_id = message.from_user.id
    
    expenses = await db.get_user_expenses(user_id, limit=15)
    
    if not expenses:
        await message.answer(
            "📋 У вас пока нет трат.\n\n"
            "Добавьте первую через «➕ Новая трата»",
            reply_markup=get_expenses_submenu()
        )
        return
    
    # Формируем список
    text = "📋 <b>История трат:</b>\n\n"
    for expense in expenses:
        category_emoji = expense['category'].split()[0]  # Берём эмодзи из категории
        text += f"<b>{expense['expense_date']}</b> — {category_emoji} {expense['name']} — {expense['amount']:,.0f} ₽\n"
    
    await message.answer(text, reply_markup=get_expenses_submenu(), parse_mode=ParseMode.HTML)

@router.message(F.text == "🛒 Авито")
async def show_avito_menu(message: Message):
    """Показать меню Авито"""
    await message.answer(
        "🛒 <b>Авито</b>\n\nУправляйте своими продажами:",
        reply_markup=get_avito_submenu(),
        parse_mode=ParseMode.HTML
    )

@router.message(F.text == "➕ Новая продажа")
async def add_avito_start(message: Message, state: FSMContext):
    """Начало добавления продажи"""
    user_avito_data[message.from_user.id] = {}
    await state.set_state(AddAvitoStates.waiting_for_item_name)
    await message.answer(
        "📦 Введите название вещи которую продали:",
        reply_markup=get_cancel_keyboard()
    )

@router.message(AddAvitoStates.waiting_for_item_name)
async def process_avito_item_name(message: Message, state: FSMContext):
    """Получение названия вещи"""
    if message.text == "❌ Отмена":
        await state.clear()
        del user_avito_data[message.from_user.id]
        await message.answer("Отменено", reply_markup=get_finance_submenu())
        return
    
    # Название с большой буквы
    user_avito_data[message.from_user.id]['item_name'] = message.text.capitalize()
    await state.set_state(AddAvitoStates.waiting_for_amount)
    await message.answer(
        "💰 Введите сумму продажи:",
        reply_markup=get_cancel_keyboard()
    )

@router.message(AddAvitoStates.waiting_for_amount)
async def process_avito_amount(message: Message, state: FSMContext):
    """Получение суммы продажи"""
    if message.text == "❌ Отмена":
        await state.clear()
        del user_avito_data[message.from_user.id]
        await message.answer("Отменено", reply_markup=get_finance_submenu())
        return
    
    try:
        amount = float(message.text.replace(',', '.'))
        if amount < 0:
            await message.answer("❌ Сумма не может быть отрицательной. Попробуйте ещё раз:")
            return
        user_avito_data[message.from_user.id]['amount'] = amount
    except ValueError:
        await message.answer("❌ Неверный формат. Введите число:")
        return
    
    await state.set_state(AddAvitoStates.waiting_for_date)
    await message.answer(
        "📅 Введите дату продажи:\n\n"
        "Формат: ДД.ММ.ГГГГ (например: 06.10.2025)\n"
        "Или просто ДД.ММ (год подставится автоматически)",
        reply_markup=get_cancel_keyboard()
    )

@router.message(AddAvitoStates.waiting_for_date)
async def process_avito_date(message: Message, state: FSMContext):
    """Получение даты продажи и сохранение"""
    if message.text == "❌ Отмена":
        await state.clear()
        del user_avito_data[message.from_user.id]
        await message.answer("Отменено", reply_markup=get_finance_submenu())
        return
    
    # Парсим дату
    try:
        date_parts = message.text.strip().split('.')
        if len(date_parts) == 2:
            day, month = date_parts
            year = datetime.now().year
        elif len(date_parts) == 3:
            day, month, year = date_parts
        else:
            raise ValueError("Неверный формат")
        
        # Валидация
        sale_date = datetime(int(year), int(month), int(day))
        user_avito_data[message.from_user.id]['sale_date'] = sale_date.strftime('%d.%m.%Y')
        
    except (ValueError, IndexError):
        await message.answer(
            "❌ Неверный формат даты. Попробуйте ещё раз.\n"
            "Например: 06.10.2025 или 06.10"
        )
        return
    
    # Сохраняем в БД
    item_name = user_avito_data[message.from_user.id]['item_name']
    amount = user_avito_data[message.from_user.id]['amount']
    
    avito_id = await db.add_avito_sale(
        user_id=message.from_user.id,
        item_name=item_name,
        amount=amount,
        sale_date=user_avito_data[message.from_user.id]['sale_date']
    )
    
    # Синхронизация с Google Sheets
    if google_sheets.enabled:
        await asyncio.to_thread(
            google_sheets.add_avito_sale,
            message.from_user.id,
            message.from_user.full_name,
            {
                'id': avito_id,
                'item_name': item_name,
                'amount': amount,
                'sale_date': user_avito_data[message.from_user.id]['sale_date']
            }
        )
    
    # Формируем итоговое сообщение
    date_short = sale_date.strftime('%d.%m')
    result_message = (
        f"✅ <b>Успешно продано!</b>\n\n"
        f"📦 {item_name}\n"
        f"💰 {amount:,.0f} ₽\n"
        f"📅 {date_short}"
    )
    
    # Рассчитываем и показываем распределение
    distribution = calculate_avito_distribution(amount)
    result_message += f"\n\n{format_distribution(distribution)}"
    
    await state.clear()
    del user_avito_data[message.from_user.id]
    await message.answer(result_message, reply_markup=get_avito_submenu(), parse_mode=ParseMode.HTML)

@router.message(F.text == "📋 Мои продажи")
async def show_avito_sales(message: Message):
    """Показать список продаж Авито"""
    user_id = message.from_user.id
    
    sales = await db.get_user_avito_sales(user_id)
    
    if not sales:
        await message.answer(
            "📋 У вас пока нет продаж.\n\n"
            "Добавьте первую продажу через «➕ Новая продажа»",
            reply_markup=get_avito_submenu()
        )
        return
    
    # Формируем список
    text = "📋 <b>Мои продажи:</b>\n\n"
    for sale in sales[:10]:  # Показываем только последние 10
        text += f"<b>{sale['sale_date']}</b> — {sale['item_name']} — {sale['amount']:,.0f} ₽\n"
    
    if len(sales) > 10:
        text += f"\n<i>... и ещё {len(sales) - 10} продаж</i>"
    
    await message.answer(text, reply_markup=get_avito_submenu(), parse_mode=ParseMode.HTML)

@router.message(F.text == "📈 Статистика Авито")
async def show_avito_statistics(message: Message):
    """Показать статистику Авито"""
    user_id = message.from_user.id
    
    stats = await db.get_avito_stats(user_id)
    
    if not stats or stats['sales_count'] == 0:
        await message.answer(
            "📈 У вас пока нет продаж.\n\n"
            "Добавьте первую продажу через «➕ Новая продажа»",
            reply_markup=get_avito_submenu()
        )
        return
    
    # Формируем сообщение со статистикой
    text = (
        f"📊 <b>Статистика Авито</b>\n\n"
        f"📦 Продано вещей: {stats['sales_count']}\n"
        f"💰 Общая сумма: {stats['total_amount']:,.0f} ₽\n"
        f"📈 Средняя цена: {stats['avg_amount']:,.0f} ₽"
    )
    
    await message.answer(text, reply_markup=get_avito_submenu(), parse_mode=ParseMode.HTML)

# ===== МЕДИА: ФИЛЬМЫ =====

@router.message(F.text == "➕ Добавить фильм")
async def add_movie_start(message: Message, state: FSMContext):
    """Начало добавления фильма"""
    user_movie_data[message.from_user.id] = {}
    await state.set_state(AddMovieStates.waiting_for_title)
    await message.answer(
        "🎬 Введите название фильма:",
        reply_markup=get_cancel_keyboard()
    )

@router.message(AddMovieStates.waiting_for_title)
async def process_movie_title(message: Message, state: FSMContext):
    """Получение названия фильма"""
    if message.text == "❌ Отмена":
        await state.clear()
        del user_movie_data[message.from_user.id]
        await message.answer("Отменено", reply_markup=get_movies_submenu())
        return
    
    user_movie_data[message.from_user.id]['title'] = message.text.capitalize()
    await state.set_state(AddMovieStates.waiting_for_genre)
    await message.answer(
        "🎭 Выберите жанр фильма:",
        reply_markup=get_genre_keyboard()
    )

@router.message(AddMovieStates.waiting_for_genre)
async def process_movie_genre(message: Message, state: FSMContext):
    """Получение жанра фильма"""
    if message.text == "❌ Отмена" or message.text == "◀️ Назад":
        await state.clear()
        del user_movie_data[message.from_user.id]
        await message.answer("Отменено", reply_markup=get_movies_submenu())
        return
    
    genre = GENRE_MAP.get(message.text, message.text)
    user_movie_data[message.from_user.id]['genre'] = genre
    await state.set_state(AddMovieStates.waiting_for_year)
    await message.answer(
        "📅 Введите год выпуска:",
        reply_markup=get_cancel_keyboard()
    )

@router.message(AddMovieStates.waiting_for_year)
async def process_movie_year(message: Message, state: FSMContext):
    """Получение года выпуска"""
    if message.text == "❌ Отмена":
        await state.clear()
        del user_movie_data[message.from_user.id]
        await message.answer("Отменено", reply_markup=get_movies_submenu())
        return
    
    try:
        year = int(message.text)
        if year < 1800 or year > 2100:
            await message.answer("❌ Неверный год. Введите год от 1800 до 2100:")
            return
        user_movie_data[message.from_user.id]['year'] = year
    except ValueError:
        await message.answer("❌ Введите корректный год (например, 2020):")
        return
    
    await state.set_state(AddMovieStates.waiting_for_status)
    await message.answer(
        "📊 Выберите статус:",
        reply_markup=get_movie_status_keyboard()
    )


@router.message(AddMovieStates.waiting_for_status)
async def process_movie_status(message: Message, state: FSMContext):
    """Получение статуса"""
    if message.text == "❌ Отмена":
        await state.clear()
        del user_movie_data[message.from_user.id]
        await message.answer("Отменено", reply_markup=get_movies_submenu())
        return
    
    if message.text not in ["👁 Не смотрел", "✅ Просмотрел"]:
        await message.answer("❌ Неверный выбор. Используйте кнопки:")
        return
    
    user_movie_data[message.from_user.id]['status'] = message.text
    await state.set_state(AddMovieStates.waiting_for_rating)
    await message.answer(
        "⭐ Оцените фильм (1-5 звёзд) или пропустите:",
        reply_markup=get_rating_keyboard()
    )

@router.message(AddMovieStates.waiting_for_rating)
async def process_movie_rating(message: Message, state: FSMContext):
    """Получение рейтинга"""
    if message.text == "❌ Отмена":
        await state.clear()
        del user_movie_data[message.from_user.id]
        await message.answer("Отменено", reply_markup=get_movies_submenu())
        return
    
    if message.text == "⏭ Пропустить":
        user_movie_data[message.from_user.id]['rating'] = None
    else:
        rating_map = {"⭐": 1, "⭐⭐": 2, "⭐⭐⭐": 3, "⭐⭐⭐⭐": 4, "⭐⭐⭐⭐⭐": 5}
        if message.text not in rating_map:
            await message.answer("❌ Неверный выбор. Используйте кнопки:")
            return
        user_movie_data[message.from_user.id]['rating'] = rating_map[message.text]
    
    await state.set_state(AddMovieStates.waiting_for_notes)
    await message.answer(
        "📝 Добавьте заметку или пропустите:",
        reply_markup=get_skip_keyboard()
    )

@router.message(AddMovieStates.waiting_for_notes)
async def process_movie_notes(message: Message, state: FSMContext):
    """Получение заметок и сохранение"""
    if message.text == "❌ Отмена":
        await state.clear()
        del user_movie_data[message.from_user.id]
        await message.answer("Отменено", reply_markup=get_movies_submenu())
        return
    
    if message.text == "⏭ Пропустить":
        user_movie_data[message.from_user.id]['notes'] = None
    else:
        user_movie_data[message.from_user.id]['notes'] = message.text
    
    # Сохраняем в БД
    movie_id = await db.add_movie(
        user_id=message.from_user.id,
        title=user_movie_data[message.from_user.id]['title'],
        genre=user_movie_data[message.from_user.id]['genre'],
        year=user_movie_data[message.from_user.id]['year'],
        overview='',
        status=user_movie_data[message.from_user.id]['status'],
        rating=user_movie_data[message.from_user.id].get('rating'),
        notes=user_movie_data[message.from_user.id].get('notes')
    )
    
    # Синхронизация с Google Sheets
    await asyncio.to_thread(
        google_sheets.add_media,
        message.from_user.id,
        message.from_user.username or message.from_user.first_name,
        {
            'id': movie_id,
            'type': 'Фильм',
            'title': user_movie_data[message.from_user.id]['title'],
            'genre': user_movie_data[message.from_user.id]['genre'],
            'year': user_movie_data[message.from_user.id]['year'],
            'overview': '',
            'status': user_movie_data[message.from_user.id]['status'],
            'rating': user_movie_data[message.from_user.id].get('rating'),
            'notes': user_movie_data[message.from_user.id].get('notes', '')
        }
    )
    
    # Формируем итоговое сообщение
    result = f"✅ Фильм добавлен!\n\n"
    result += f"🎬 {user_movie_data[message.from_user.id]['title']}\n"
    result += f"🎭 {user_movie_data[message.from_user.id]['genre']}\n"
    result += f"📅 {user_movie_data[message.from_user.id]['year']}\n"
    result += f"📊 {user_movie_data[message.from_user.id]['status']}"
    
    if user_movie_data[message.from_user.id].get('rating'):
        result += f"\n⭐ {'⭐' * user_movie_data[message.from_user.id]['rating']}"
    
    await state.clear()
    del user_movie_data[message.from_user.id]
    await message.answer(result, reply_markup=get_movies_submenu())

@router.message(F.text == "✅ Просмотренные")
async def show_watched_movies_menu(message: Message, state: FSMContext):
    """Меню просмотренных фильмов - выбор жанра"""
    await state.update_data(movie_status="✅ Просмотрел")
    await state.set_state(ViewMoviesStates.waiting_for_genre)
    await message.answer(
        "✅ <b>Просмотренные фильмы</b>\n\nВыберите жанр:",
        reply_markup=get_genre_keyboard(),
        parse_mode=ParseMode.HTML
    )

@router.message(F.text == "👁 Не смотрел")
async def show_unwatched_movies_menu(message: Message, state: FSMContext):
    """Меню непросмотренных фильмов - выбор жанра"""
    await state.update_data(movie_status="👁 Не смотрел")
    await state.set_state(ViewMoviesStates.waiting_for_genre)
    await message.answer(
        "👁 <b>Не смотрел</b>\n\nВыберите жанр:",
        reply_markup=get_genre_keyboard(),
        parse_mode=ParseMode.HTML
    )

@router.message(ViewMoviesStates.waiting_for_genre)
async def show_movies_by_genre(message: Message, state: FSMContext):
    """Показать фильмы по жанру и статусу"""
    if message.text == "◀️ Назад":
        await state.clear()
        await message.answer("Вернулись в меню", reply_markup=get_movies_submenu())
        return
    
    genre = GENRE_MAP.get(message.text)
    if not genre:
        await message.answer("❌ Выберите жанр из списка", reply_markup=get_genre_keyboard())
        return
    
    data = await state.get_data()
    status = data.get('movie_status')
    user_id = message.from_user.id
    
    # Получаем фильмы с нужным жанром и статусом
    all_movies = await db.get_user_movies(user_id)
    filtered_movies = [m for m in all_movies if m['genre'] == genre and m['status'] == status]
    
    if not filtered_movies:
        await message.answer(
            f"📋 У вас нет фильмов в жанре <b>{genre}</b> со статусом <b>{status}</b>",
            reply_markup=get_movies_submenu(),
            parse_mode=ParseMode.HTML
        )
        await state.clear()
        return
    
    # Показываем каждый фильм
    for movie in filtered_movies:
        text = format_movie_text(movie)
        
        # Кнопки зависят от статуса
        buttons = []
        if status == "👁 Не смотрел":
            buttons.append([InlineKeyboardButton(text="✅ Просмотрел", callback_data=f"mark_watched_{movie['id']}")])
        buttons.append([InlineKeyboardButton(text=EMOJI_DELETE, callback_data=f"delete_movie_{movie['id']}")])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    
    await message.answer(
        f"📊 Всего фильмов: {len(filtered_movies)}",
        reply_markup=get_movies_submenu()
    )
    await state.clear()

@router.callback_query(F.data.startswith("mark_watched_"))
async def mark_movie_watched_callback(callback: CallbackQuery):
    """Отметить фильм как просмотренный"""
    movie_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    
    success = await db.update_movie_status(movie_id, user_id, "✅ Просмотрел")
    
    if success:
        await callback.message.edit_text(
            callback.message.text + "\n\n✅ <b>Отмечено как просмотренное</b>",
            parse_mode=ParseMode.HTML
        )
        await callback.answer("Фильм перемещён в 'Просмотренные'", show_alert=False)
    else:
        await callback.answer("❌ Ошибка при обновлении", show_alert=True)

@router.callback_query(F.data.startswith("delete_movie_"))
async def delete_movie_callback(callback: CallbackQuery):
    """Удалить фильм"""
    movie_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    
    success = await db.delete_movie(movie_id, user_id)
    
    if success:
        await callback.message.edit_text("✅ Фильм удалён")
        await callback.answer("Удалено", show_alert=False)
    else:
        await callback.answer("❌ Ошибка при удалении", show_alert=True)

@router.message(F.text == "🎲 Случайный фильм")
async def random_movie_menu(message: Message, state: FSMContext):
    """Меню случайного фильма - выбор жанра"""
    await state.set_state(ViewMoviesStates.waiting_for_random_genre)
    await message.answer(
        "🎲 <b>Случайный фильм</b>\n\nВыберите жанр:",
        reply_markup=get_genre_keyboard(),
        parse_mode=ParseMode.HTML
    )

@router.message(ViewMoviesStates.waiting_for_random_genre)
async def show_random_movie(message: Message, state: FSMContext):
    """Показать случайный фильм из выбранного жанра"""
    if message.text == "◀️ Назад":
        await state.clear()
        await message.answer("Вернулись в меню", reply_markup=get_movies_submenu())
        return
    
    genre = GENRE_MAP.get(message.text)
    if not genre:
        await message.answer("❌ Выберите жанр из списка", reply_markup=get_genre_keyboard())
        return
    
    user_id = message.from_user.id
    
    # Получаем все фильмы этого жанра
    all_movies = await db.get_user_movies(user_id)
    genre_movies = [m for m in all_movies if m['genre'] == genre]
    
    if not genre_movies:
        await message.answer(
            f"📋 У вас нет фильмов в жанре <b>{genre}</b>",
            reply_markup=get_movies_submenu(),
            parse_mode=ParseMode.HTML
        )
        await state.clear()
        return
    
    # Выбираем случайный фильм
    import random
    movie = random.choice(genre_movies)
    
    text = f"🎲 <b>Случайный фильм из жанра {genre}</b>\n\n"
    text += format_movie_text(movie)
    
    await message.answer(text, reply_markup=get_movies_submenu(), parse_mode=ParseMode.HTML)
    await state.clear()

# ======================= ОБРАБОТЧИКИ ДЛЯ СЕРИАЛОВ =======================

@router.message(F.text == "➕ Добавить сериал")
async def add_series_start(message: Message, state: FSMContext):
    """Начало добавления сериала"""
    user_series_data[message.from_user.id] = {}
    await state.set_state(AddSeriesStates.waiting_for_title)
    await message.answer(
        "📺 Введите название сериала:",
        reply_markup=get_cancel_keyboard()
    )

@router.message(AddSeriesStates.waiting_for_title)
async def process_series_title(message: Message, state: FSMContext):
    """Получение названия сериала"""
    if message.text == "❌ Отмена":
        await state.clear()
        del user_series_data[message.from_user.id]
        await message.answer("Отменено", reply_markup=get_series_submenu())
        return
    
    user_series_data[message.from_user.id]['title'] = message.text.capitalize()
    await state.set_state(AddSeriesStates.waiting_for_genre)
    await message.answer(
        "🎭 Введите жанр сериала:",
        reply_markup=get_cancel_keyboard()
    )

@router.message(AddSeriesStates.waiting_for_genre)
async def process_series_genre(message: Message, state: FSMContext):
    """Получение жанра сериала"""
    if message.text == "❌ Отмена":
        await state.clear()
        del user_series_data[message.from_user.id]
        await message.answer("Отменено", reply_markup=get_series_submenu())
        return
    
    user_series_data[message.from_user.id]['genre'] = message.text.capitalize()
    await state.set_state(AddSeriesStates.waiting_for_year)
    await message.answer(
        "📅 Введите год выпуска:",
        reply_markup=get_cancel_keyboard()
    )

@router.message(AddSeriesStates.waiting_for_year)
async def process_series_year(message: Message, state: FSMContext):
    """Получение года выпуска сериала"""
    if message.text == "❌ Отмена":
        await state.clear()
        del user_series_data[message.from_user.id]
        await message.answer("Отменено", reply_markup=get_series_submenu())
        return
    
    try:
        year = int(message.text)
        if year < 1800 or year > 2100:
            await message.answer("❌ Неверный год. Введите год от 1800 до 2100:")
            return
        user_series_data[message.from_user.id]['year'] = year
    except ValueError:
        await message.answer("❌ Введите корректный год (например, 2020):")
        return
    
    await state.set_state(AddSeriesStates.waiting_for_seasons)
    await message.answer(
        "📊 Введите количество сезонов:",
        reply_markup=get_cancel_keyboard()
    )

@router.message(AddSeriesStates.waiting_for_seasons)
async def process_series_seasons(message: Message, state: FSMContext):
    """Получение количества сезонов"""
    if message.text == "❌ Отмена":
        await state.clear()
        del user_series_data[message.from_user.id]
        await message.answer("Отменено", reply_markup=get_series_submenu())
        return
    
    try:
        seasons = int(message.text)
        if seasons < 1:
            await message.answer("❌ Количество сезонов должно быть больше 0:")
            return
        user_series_data[message.from_user.id]['seasons'] = seasons
    except ValueError:
        await message.answer("❌ Введите число (например, 3):")
        return
    
    await state.set_state(AddSeriesStates.waiting_for_episodes)
    await message.answer(
        "📺 Введите общее количество серий:",
        reply_markup=get_cancel_keyboard()
    )

@router.message(AddSeriesStates.waiting_for_episodes)
async def process_series_episodes(message: Message, state: FSMContext):
    """Получение количества серий"""
    if message.text == "❌ Отмена":
        await state.clear()
        del user_series_data[message.from_user.id]
        await message.answer("Отменено", reply_markup=get_series_submenu())
        return
    
    try:
        episodes = int(message.text)
        if episodes < 1:
            await message.answer("❌ Количество серий должно быть больше 0:")
            return
        user_series_data[message.from_user.id]['episodes'] = episodes
    except ValueError:
        await message.answer("❌ Введите число (например, 24):")
        return
    
    await state.set_state(AddSeriesStates.waiting_for_status)
    await message.answer(
        "📊 Выберите статус:",
        reply_markup=get_series_status_keyboard()
    )

@router.message(AddSeriesStates.waiting_for_status)
async def process_series_status(message: Message, state: FSMContext):
    """Получение статуса сериала"""
    if message.text == "❌ Отмена":
        await state.clear()
        del user_series_data[message.from_user.id]
        await message.answer("Отменено", reply_markup=get_series_submenu())
        return
    
    if message.text not in ["📺 Не смотрел", "👀 Смотрю", "✅ Просмотрел"]:
        await message.answer("❌ Выберите статус из предложенных вариантов:")
        return
    
    user_series_data[message.from_user.id]['status'] = message.text
    await state.set_state(AddSeriesStates.waiting_for_rating)
    await message.answer(
        "⭐ Оцените сериал (1-5 звёзд):",
        reply_markup=get_rating_keyboard()
    )

@router.message(AddSeriesStates.waiting_for_rating)
async def process_series_rating(message: Message, state: FSMContext):
    """Получение рейтинга сериала"""
    if message.text == "❌ Отмена":
        await state.clear()
        del user_series_data[message.from_user.id]
        await message.answer("Отменено", reply_markup=get_series_submenu())
        return
    
    if message.text == "⏭ Пропустить":
        user_series_data[message.from_user.id]['rating'] = None
    else:
        try:
            rating = int(message.text.count('⭐'))
            if rating < 1 or rating > 5:
                await message.answer("❌ Рейтинг должен быть от 1 до 5 звёзд:")
                return
            user_series_data[message.from_user.id]['rating'] = rating
        except:
            await message.answer("❌ Неверный формат. Выберите рейтинг из кнопок:")
            return
    
    await state.set_state(AddSeriesStates.waiting_for_notes)
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⏭ Пропустить")],
            [KeyboardButton(text="❌ Отмена")],
        ],
        resize_keyboard=True
    )
    await message.answer("📝 Добавьте заметки (или нажмите Пропустить):", reply_markup=keyboard)

@router.message(AddSeriesStates.waiting_for_notes)
async def process_series_notes(message: Message, state: FSMContext):
    """Получение заметок и сохранение сериала"""
    if message.text == "❌ Отмена":
        await state.clear()
        del user_series_data[message.from_user.id]
        await message.answer("Отменено", reply_markup=get_series_submenu())
        return
    
    if message.text == "⏭ Пропустить":
        user_series_data[message.from_user.id]['notes'] = None
    else:
        user_series_data[message.from_user.id]['notes'] = message.text
    
    # Сохраняем в БД
    series_id = await db.add_series(
        user_id=message.from_user.id,
        title=user_series_data[message.from_user.id]['title'],
        genre=user_series_data[message.from_user.id]['genre'],
        year=user_series_data[message.from_user.id]['year'],
        overview='',
        seasons=user_series_data[message.from_user.id].get('seasons', 0),
        episodes=user_series_data[message.from_user.id].get('episodes', 0),
        status=user_series_data[message.from_user.id]['status'],
        rating=user_series_data[message.from_user.id].get('rating'),
        notes=user_series_data[message.from_user.id].get('notes')
    )
    
    # Синхронизация с Google Sheets
    await asyncio.to_thread(
        google_sheets.add_media,
        message.from_user.id,
        message.from_user.username or message.from_user.first_name,
        {
            'id': series_id,
            'type': 'Сериал',
            'title': user_series_data[message.from_user.id]['title'],
            'genre': user_series_data[message.from_user.id]['genre'],
            'year': user_series_data[message.from_user.id]['year'],
            'overview': '',
            'seasons': user_series_data[message.from_user.id].get('seasons', 0),
            'episodes': user_series_data[message.from_user.id].get('episodes', 0),
            'status': user_series_data[message.from_user.id]['status'],
            'rating': user_series_data[message.from_user.id].get('rating'),
            'notes': user_series_data[message.from_user.id].get('notes', '')
        }
    )
    
    # Формируем итоговое сообщение
    result = f"✅ Сериал добавлен!\n\n"
    result += f"📺 {user_series_data[message.from_user.id]['title']}\n"
    result += f"🎭 {user_series_data[message.from_user.id]['genre']}\n"
    result += f"📅 {user_series_data[message.from_user.id]['year']}\n"
    result += f"📊 Сезонов: {user_series_data[message.from_user.id].get('seasons', 0)}, "
    result += f"Серий: {user_series_data[message.from_user.id].get('episodes', 0)}\n"
    result += f"📺 {user_series_data[message.from_user.id]['status']}"
    
    if user_series_data[message.from_user.id].get('rating'):
        result += f"\n⭐ {'⭐' * user_series_data[message.from_user.id]['rating']}"
    
    await state.clear()
    del user_series_data[message.from_user.id]
    await message.answer(result, reply_markup=get_series_submenu())

# Обработчики для просмотренных сериалов
@router.message(F.text == "✅ Просмотренные")
async def show_watched_series_menu(message: Message, state: FSMContext):
    """Показать просмотренные сериалы с выбором жанра"""
    await state.update_data(series_status=SERIES_STATUS_WATCHED)
    await state.set_state(ViewSeriesStates.waiting_for_genre)
    await message.answer(
        "✅ Выберите жанр для просмотренных сериалов:",
        reply_markup=get_genre_keyboard()
    )

@router.message(F.text == "👀 Смотрю")
async def show_watching_series_menu(message: Message, state: FSMContext):
    """Показать сериалы, которые смотрю, с выбором жанра"""
    await state.update_data(series_status=SERIES_STATUS_WATCHING)
    await state.set_state(ViewSeriesStates.waiting_for_genre)
    await message.answer(
        "👀 Выберите жанр для сериалов, которые смотрите:",
        reply_markup=get_genre_keyboard()
    )

@router.message(F.text == "👁 Не смотрел")
async def show_unwatched_series_menu(message: Message, state: FSMContext):
    """Показать непросмотренные сериалы с выбором жанра"""
    await state.update_data(series_status=SERIES_STATUS_UNWATCHED)
    await state.set_state(ViewSeriesStates.waiting_for_genre)
    await message.answer(
        "👁 Выберите жанр для непросмотренных сериалов:",
        reply_markup=get_genre_keyboard()
    )

@router.message(ViewSeriesStates.waiting_for_genre)
async def show_series_by_genre(message: Message, state: FSMContext):
    """Показать сериалы по выбранному жанру и статусу"""
    if message.text == EMOJI_BACK:
        await state.clear()
        await message.answer("Вернулись в меню", reply_markup=get_series_submenu())
        return
    
    genre = GENRE_MAP.get(message.text)
    if not genre:
        await message.answer("❌ Выберите жанр из списка", reply_markup=get_genre_keyboard())
        return
    
    data = await state.get_data()
    status = data.get('series_status')
    user_id = message.from_user.id
    
    # Получаем сериалы с нужным жанром и статусом
    all_series = await db.get_user_series(user_id)
    filtered_series = [s for s in all_series if s['genre'] == genre and s['status'] == status]
    
    if not filtered_series:
        await message.answer(
            f"📋 У вас нет сериалов в жанре <b>{genre}</b> со статусом <b>{status}</b>",
            reply_markup=get_series_submenu(),
            parse_mode=ParseMode.HTML
        )
        await state.clear()
        return
    
    # Показываем каждый сериал
    for series in filtered_series:
        text = format_series_text(series)
        
        # Кнопки зависят от статуса
        buttons = []
        if status == SERIES_STATUS_UNWATCHED:
            buttons.append([InlineKeyboardButton(text="✅ Просмотрел", callback_data=f"mark_series_watched_{series['id']}")])
        buttons.append([InlineKeyboardButton(text=EMOJI_DELETE, callback_data=f"delete_series_{series['id']}")])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    
    await message.answer(
        f"📊 Всего сериалов: {len(filtered_series)}",
        reply_markup=get_series_submenu()
    )
    await state.clear()

# Обработчик для пометки сериала как просмотренного
@router.callback_query(F.data.startswith("mark_series_watched_"))
async def mark_series_watched_callback(callback: CallbackQuery):
    """Отметить сериал как просмотренный"""
    series_id = int(callback.data.split("_")[3])
    user_id = callback.from_user.id
    
    success = await db.update_series_status(series_id, user_id, SERIES_STATUS_WATCHED)
    
    if success:
        await callback.message.edit_text("✅ Сериал отмечен как просмотренный")
        await callback.answer("Статус обновлён", show_alert=False)
    else:
        await callback.answer("❌ Ошибка при обновлении", show_alert=True)

@router.callback_query(F.data.startswith("delete_series_"))
async def delete_series_callback(callback: CallbackQuery):
    """Удалить сериал"""
    series_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    
    success = await db.delete_series(series_id, user_id)
    
    if success:
        await callback.message.edit_text("✅ Сериал удалён")
        await callback.answer("Удалено", show_alert=False)
    else:
        await callback.answer("❌ Ошибка при удалении", show_alert=True)

# Меню отчётов
def get_reports_submenu():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Общий отчёт")],
            [KeyboardButton(text="📈 По категориям")],
            [KeyboardButton(text="📉 Сравнение месяцев")],
            [KeyboardButton(text="◀️ К финансам")],
        ],
        resize_keyboard=True
    )
    return keyboard

@router.message(F.text == "📊 Отчеты")
async def show_finance_reports_menu(message: Message):
    """Меню финансовых отчётов"""
    await message.answer(
        "📊 <b>Отчеты</b>\n\nВыберите тип отчёта:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_reports_submenu()
    )

@router.message(F.text == "📊 Общий отчёт")
async def show_general_report(message: Message):
    """Показать общий финансовый отчёт за текущий месяц"""
    user_id = message.from_user.id
    current_month = datetime.now().strftime('%m.%Y')
    
    # Получаем данные
    tips_stats = await db.get_tips_stats_by_month(user_id, current_month)
    avito_stats = await db.get_avito_stats(user_id)
    
    # Получаем все расходы за месяц
    all_expenses = await db.get_user_expenses(user_id)
    month_expenses = [e for e in all_expenses if e['expense_date'].endswith(current_month)]
    total_expenses = sum(e['amount'] for e in month_expenses)
    
    # Получаем обязательные расходы
    recurring = await db.get_user_recurring_expenses(user_id)
    total_recurring = sum(r['amount'] for r in recurring)
    
    # Формируем отчёт
    text = f"📊 <b>Общий отчёт за {datetime.now().strftime('%B %Y')}</b>\n\n"
    
    # Доходы
    text += "💰 <b>Доходы:</b>\n"
    tips_total = tips_stats['total_amount'] if tips_stats else 0
    avito_total = avito_stats['total_amount'] if avito_stats else 0
    total_income = tips_total + avito_total
    
    if tips_total > 0:
        text += f"  └ Смены: {tips_total:,.0f} ₽\n"
    if avito_total > 0:
        text += f"  └ Авито: {avito_total:,.0f} ₽\n"
    text += f"  <b>Итого: {total_income:,.0f} ₽</b>\n\n"
    
    # Расходы
    text += "💸 <b>Расходы:</b>\n"
    if total_recurring > 0:
        text += f"  └ Обязательные: {total_recurring:,.0f} ₽\n"
    if total_expenses > 0:
        text += f"  └ Траты: {total_expenses:,.0f} ₽\n"
    total_expense = total_recurring + total_expenses
    text += f"  <b>Итого: {total_expense:,.0f} ₽</b>\n\n"
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_reports_submenu())

@router.message(F.text == "📈 По категориям")
async def show_category_report(message: Message):
    """Показать отчёт по категориям трат"""
    user_id = message.from_user.id
    current_month = datetime.now().strftime('%m.%Y')
    
    # Получаем траты по категориям
    categories = await db.get_expenses_by_category(user_id, current_month)
    
    if not categories:
        await message.answer(
            "📈 У вас пока нет трат в этом месяце.",
            reply_markup=get_reports_submenu()
        )
        return
    
    # Сортируем по сумме
    categories.sort(key=lambda x: x['total'], reverse=True)
    total = sum(c['total'] for c in categories)
    
    # Формируем отчёт
    text = f"📈 <b>Траты по категориям за {datetime.now().strftime('%B')}</b>\n\n"
    
    for cat in categories:
        percentage = (cat['total'] / total * 100) if total > 0 else 0
        text += f"{cat['category']}: {cat['total']:,.0f} ₽ ({percentage:.1f}%)\n"
    
    text += f"\n💰 <b>Всего: {total:,.0f} ₽</b>"
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_reports_submenu())

@router.message(F.text == "📉 Сравнение месяцев")
async def show_comparison_report(message: Message):
    """Сравнить текущий месяц с предыдущим"""
    user_id = message.from_user.id
    
    current_month = datetime.now().strftime('%m.%Y')
    prev_date = datetime.now().replace(day=1) - timedelta(days=1)
    prev_month = prev_date.strftime('%m.%Y')
    
    # Получаем данные для текущего месяца
    current_expenses = await db.get_user_expenses(user_id)
    current_month_expenses = [e for e in current_expenses if e['expense_date'].endswith(current_month)]
    current_total = sum(e['amount'] for e in current_month_expenses)
    
    # Получаем данные для предыдущего месяца
    prev_month_expenses = [e for e in current_expenses if e['expense_date'].endswith(prev_month)]
    prev_total = sum(e['amount'] for e in prev_month_expenses)
    
    # Формируем отчёт
    text = "📉 <b>Сравнение месяцев</b>\n\n"
    
    text += f"<b>{prev_date.strftime('%B')}:</b> {prev_total:,.0f} ₽\n"
    text += f"<b>{datetime.now().strftime('%B')}:</b> {current_total:,.0f} ₽\n\n"
    
    if current_total > prev_total:
        diff = current_total - prev_total
        text += f"📈 Расходы выросли на {diff:,.0f} ₽"
    elif current_total < prev_total:
        diff = prev_total - current_total
        text += f"📉 Расходы снизились на {diff:,.0f} ₽"
    else:
        text += "➡️ Расходы остались на том же уровне"
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_reports_submenu())

# ===== ЧАЕВЫЕ =====

@router.message(F.text == "💼 Смена")
async def show_tips_menu(message: Message):
    """Показать меню смен"""
    await message.answer(
        "💼 <b>Смена</b>\n\nУправляйте информацией о своих сменах:",
        reply_markup=get_tips_submenu(),
        parse_mode=ParseMode.HTML
    )

@router.message(F.text == "➕ Новая смена")
async def add_tips_start(message: Message, state: FSMContext):
    """Начало добавления смены"""
    user_tips_data[message.from_user.id] = {}
    await state.set_state(AddTipsStates.waiting_for_hours)
    await message.answer(
        "⏰ Введите количество отработанных часов:\n\n"
        "Напишите число (например, 8 или 5.5).",
        reply_markup=get_cancel_keyboard()
    )

@router.message(AddTipsStates.waiting_for_hours)
async def process_tips_hours(message: Message, state: FSMContext):
    """Получение количества часов"""
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено", reply_markup=get_main_menu())
        return
    
    try:
        hours = float(message.text.replace(',', '.'))
        if hours <= 0:
            await message.answer("❌ Количество часов должно быть больше 0. Попробуйте снова:")
            return
        
        user_tips_data[message.from_user.id]['hours_worked'] = hours
        await state.set_state(AddTipsStates.waiting_for_card)
        await message.answer(
            f"✅ Часов отработано: {hours}\n\n"
            "💳 Теперь введите сумму чаевых на дебетовые карты:\n\n"
            "Напишите число или нажмите «Пропустить» если ничего не было.",
            reply_markup=get_skip_keyboard()
        )
    except ValueError:
        await message.answer(
            "❌ Пожалуйста, введите корректное число часов (например, 8 или 5.5):"
        )

@router.message(AddTipsStates.waiting_for_card)
async def process_tips_card(message: Message, state: FSMContext):
    """Получение суммы на карты"""
    if message.text == "❌ Отмена":
        await state.clear()
        del user_tips_data[message.from_user.id]
        await message.answer("Отменено", reply_markup=get_finance_submenu())
        return
    
    if message.text == "⏭ Пропустить":
        user_tips_data[message.from_user.id]['card'] = 0
    else:
        try:
            amount = float(message.text.replace(',', '.'))
            if amount < 0:
                await message.answer("❌ Сумма не может быть отрицательной. Попробуйте ещё раз:")
                return
            user_tips_data[message.from_user.id]['card'] = amount
        except ValueError:
            await message.answer("❌ Неверный формат. Введите число или нажмите «Пропустить»:")
            return
    
    await state.set_state(AddTipsStates.waiting_for_netmonet)
    await message.answer(
        "📱 Введите сумму чаевых на Нет.Монет:\n\n"
        "Напишите число или нажмите «Пропустить» если ничего не было.",
        reply_markup=get_skip_keyboard()
    )

@router.message(AddTipsStates.waiting_for_netmonet)
async def process_tips_netmonet(message: Message, state: FSMContext):
    """Получение суммы на Нет.Монет"""
    if message.text == "❌ Отмена":
        await state.clear()
        del user_tips_data[message.from_user.id]
        await message.answer("Отменено", reply_markup=get_finance_submenu())
        return
    
    if message.text == "⏭ Пропустить":
        user_tips_data[message.from_user.id]['netmonet'] = 0
    else:
        try:
            amount = float(message.text.replace(',', '.'))
            if amount < 0:
                await message.answer("❌ Сумма не может быть отрицательной. Попробуйте ещё раз:")
                return
            user_tips_data[message.from_user.id]['netmonet'] = amount
        except ValueError:
            await message.answer("❌ Неверный формат. Введите число или нажмите «Пропустить»:")
            return
    
    await state.set_state(AddTipsStates.waiting_for_cash)
    await message.answer(
        "💵 Введите сумму наличных чаевых:\n\n"
        "Напишите число или нажмите «Пропустить» если ничего не было.",
        reply_markup=get_skip_keyboard()
    )

@router.message(AddTipsStates.waiting_for_cash)
async def process_tips_cash(message: Message, state: FSMContext):
    """Получение суммы наличных"""
    if message.text == "❌ Отмена":
        await state.clear()
        del user_tips_data[message.from_user.id]
        await message.answer("Отменено", reply_markup=get_finance_submenu())
        return
    
    if message.text == "⏭ Пропустить":
        user_tips_data[message.from_user.id]['cash'] = 0
    else:
        try:
            amount = float(message.text.replace(',', '.'))
            if amount < 0:
                await message.answer("❌ Сумма не может быть отрицательной. Попробуйте ещё раз:")
                return
            user_tips_data[message.from_user.id]['cash'] = amount
        except ValueError:
            await message.answer("❌ Неверный формат. Введите число или нажмите «Пропустить»:")
            return
    
    await state.set_state(AddTipsStates.waiting_for_date)
    await message.answer(
        "📅 Введите дату когда были эти чаевые:\n\n"
        "Формат: ДД.ММ.ГГГГ (например: 06.10.2025)\n"
        "Или просто ДД.ММ (год подставится автоматически)",
        reply_markup=get_cancel_keyboard()
    )

@router.message(AddTipsStates.waiting_for_date)
async def process_tips_date(message: Message, state: FSMContext):
    """Получение даты чаевых и сохранение"""
    if message.text == "❌ Отмена":
        await state.clear()
        del user_tips_data[message.from_user.id]
        await message.answer("Отменено", reply_markup=get_finance_submenu())
        return
    
    # Парсим дату
    try:
        date_parts = message.text.strip().split('.')
        if len(date_parts) == 2:
            # Только день и месяц - добавляем текущий год
            day, month = date_parts
            year = datetime.now().year
        elif len(date_parts) == 3:
            day, month, year = date_parts
        else:
            raise ValueError("Неверный формат")
        
        # Валидация
        tips_date = datetime(int(year), int(month), int(day))
        user_tips_data[message.from_user.id]['date'] = tips_date.strftime('%d.%m.%Y')
        
    except (ValueError, IndexError):
        await message.answer(
            "❌ Неверный формат даты. Попробуйте ещё раз.\n"
            "Например: 06.10.2025 или 06.10"
        )
        return
    
    # Вычисляем ставку и чаевые
    hours_worked = user_tips_data[message.from_user.id].get('hours_worked', 0)
    wage = hours_worked * 180  # Ставка: 180₽/час
    
    card = user_tips_data[message.from_user.id]['card']
    netmonet = user_tips_data[message.from_user.id]['netmonet']
    cash = user_tips_data[message.from_user.id]['cash']
    tips_total = card + netmonet + cash  # Чаевые
    
    total = wage + tips_total  # Итого = ставка + чаевые
    
    user_tips_data[message.from_user.id]['wage'] = wage
    user_tips_data[message.from_user.id]['tips_total'] = tips_total
    user_tips_data[message.from_user.id]['total'] = total
    
    # Сохраняем в БД
    tips_id = await db.add_tips(
        user_id=message.from_user.id,
        tips_date=user_tips_data[message.from_user.id]['date'],
        card_amount=card,
        netmonet_amount=netmonet,
        cash_amount=cash,
        total_amount=total,
        hours_worked=hours_worked
    )
    
    # Синхронизация с Google Sheets
    if google_sheets.enabled:
        await asyncio.to_thread(
            google_sheets.add_tips,
            message.from_user.id,
            message.from_user.full_name,
            {
                'id': tips_id,
                'date': user_tips_data[message.from_user.id]['date'],
                'card': card,
                'netmonet': netmonet,
                'cash': cash,
                'total': total
            }
        )
    
    # Формируем итоговое сообщение
    date_short = tips_date.strftime('%d.%m')
    result_message = (
        f"✅ Смена за {date_short} добавлена!\n\n"
        f"⏰ Часов отработано: {hours_worked}\n"
        f"💼 Ставка (180₽/ч): {wage:,.0f} ₽\n"
        f"💰 Чаевые: {tips_total:,.0f} ₽\n"
        f"💵 <b>ИТОГО: {total:,.0f} ₽</b>\n\n"
        f"<i>Чаевые по источникам:</i>\n"
        f"💳 Карты: {card:,.0f} ₽\n"
        f"📱 Нет.Монет: {netmonet:,.0f} ₽\n"
        f"💵 Наличные: {cash:,.0f} ₽"
    )
    
    # Добавляем мотивационное сообщение
    motivation = get_motivation_message(tips_total)
    if motivation:
        result_message += f"\n\n{motivation}"
    
    # Рассчитываем и показываем распределение только для чаевых
    distribution = calculate_tips_distribution(tips_total)
    result_message += f"\n\n{format_distribution(distribution)}"
    
    await state.clear()
    del user_tips_data[message.from_user.id]
    await message.answer(result_message, reply_markup=get_tips_submenu(), parse_mode=ParseMode.HTML)

@router.message(F.text == "📋 Мои смены")
async def show_my_tips(message: Message):
    """Показать список смен с пагинацией"""
    await show_tips_page(message, offset=0)

async def show_tips_page(message: Message, offset: int = 0):
    """Показать страницу со сменами"""
    user_id = message.from_user.id
    
    # Получаем смены с пагинацией
    tips_list = await db.get_user_tips(user_id, limit=TIPS_PER_PAGE, offset=offset)
    total_count = await db.count_user_tips(user_id)
    
    if not tips_list:
        await message.answer(
            "📋 У вас пока нет записей о сменах.\n\n"
            "Добавьте первую смену через «➕ Новая смена»",
            reply_markup=get_tips_submenu()
        )
        return
    
    # Формируем список
    text = "📋 <b>Мои смены:</b>\n\n"
    for tip in tips_list:
        hours = tip.get('hours_worked', 0)
        text += f"<b>{tip['tips_date']}</b>\n"
        text += f"  ⏰ {hours}ч • 💰 {tip['total_amount']:,.0f} ₽\n"
    
    # Создаем клавиатуру с кнопкой "Показать еще"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    
    has_more = (offset + TIPS_PER_PAGE) < total_count
    if has_more:
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(
                text=f"📄 Показать еще ({total_count - offset - TIPS_PER_PAGE} осталось)",
                callback_data=f"tips_more_{offset + TIPS_PER_PAGE}"
            )
        ])
    
    await message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)

@router.callback_query(F.data.startswith("tips_more_"))
async def load_more_tips(callback: CallbackQuery):
    """Загрузить еще чаевые"""
    offset = int(callback.data.split("_")[2])
    await show_tips_page(callback.message, offset)
    await callback.answer()

@router.message(F.text == "📈 Статистика смен")
async def show_tips_statistics(message: Message):
    """Показать выбор месяца для статистики смен"""
    user_id = message.from_user.id
    
    # Получаем список месяцев со сменами
    months = await db.get_tips_months(user_id)
    
    if not months:
        await message.answer(
            "📈 У вас пока нет записей о сменах.\n\n"
            "Добавьте первую смену через «➕ Новая смена»",
            reply_markup=get_tips_submenu()
        )
        return
    
    # Словарь для названий месяцев
    month_names = {
        '01': 'Январь', '02': 'Февраль', '03': 'Март', '04': 'Апрель',
        '05': 'Май', '06': 'Июнь', '07': 'Июль', '08': 'Август',
        '09': 'Сентябрь', '10': 'Октябрь', '11': 'Ноябрь', '12': 'Декабрь'
    }
    
    # Создаем клавиатуру с месяцами
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    
    for month_year in months:
        month, year = month_year.split('.')
        month_name = month_names.get(month, month)
        button_text = f"{month_name} {year}"
        
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"tipstats_{month_year}"
            )
        ])
    
    await message.answer(
        "📈 <b>Выберите месяц для просмотра статистики:</b>",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML
    )

@router.callback_query(F.data.startswith("tipstats_"))
async def show_month_statistics(callback: CallbackQuery):
    """Показать статистику за выбранный месяц"""
    month_year = callback.data.split("_")[1]
    user_id = callback.from_user.id
    
    # Получаем статистику
    stats = await db.get_tips_stats_by_month(user_id, month_year)
    
    if not stats or stats['shifts_count'] == 0:
        await callback.answer("Нет данных за этот месяц", show_alert=True)
        return
    
    # Словарь для названий месяцев
    month_names = {
        '01': 'Январь', '02': 'Февраль', '03': 'Март', '04': 'Апрель',
        '05': 'Май', '06': 'Июнь', '07': 'Июль', '08': 'Август',
        '09': 'Сентябрь', '10': 'Октябрь', '11': 'Ноябрь', '12': 'Декабрь'
    }
    
    month, year = month_year.split('.')
    month_name = month_names.get(month, month)
    
    # Формируем сообщение со статистикой
    total_hours = stats.get('total_hours', 0) or 0
    text = (
        f"📊 <b>{month_name} {year}</b>\n\n"
        f"🔢 Смен отработано: {stats['shifts_count']}\n"
        f"⏰ Часов отработано: {total_hours}\n"
        f"💰 Итого заработано: {stats['total_tips']:,.0f} ₽\n\n"
        f"💳 Карты: {stats['total_card']:,.0f} ₽\n"
        f"📱 Нет.Монет: {stats['total_netmonet']:,.0f} ₽\n"
        f"💵 Наличные: {stats['total_cash']:,.0f} ₽\n\n"
        f"📈 Среднее за смену: {stats['avg_tips']:,.0f} ₽"
    )
    
    # Добавляем суммарное распределение за месяц (только для чаевых, без ставки)
    tips_only = (stats.get('total_card', 0) or 0) + (stats.get('total_netmonet', 0) or 0) + (stats.get('total_cash', 0) or 0)
    if tips_only > 0:
        distribution = calculate_tips_distribution(tips_only)
        text += f"\n\n{format_distribution(distribution)}"
    
    await callback.message.answer(text, parse_mode=ParseMode.HTML)
    await callback.answer()

# ===== ВИШЛИСТ =====

@router.message(F.text == "⭐ Вишлист")
async def show_wishlist_menu(message: Message):
    """Показать меню вишлиста"""
    await message.answer(
        "🎁 <b>Вишлист</b>\n\nУправляйте списком желаний:",
        reply_markup=get_wishlist_submenu(),
        parse_mode=ParseMode.HTML
    )

@router.message(F.text == "◀️ К личному")
async def back_to_personal(message: Message, state: FSMContext):
    """Вернуться к личному меню"""
    await state.clear()
    await message.answer(
        "👤 <b>Личное</b>",
        reply_markup=get_personal_submenu(),
        parse_mode=ParseMode.HTML
    )

@router.message(F.text == "➕ Добавить желание")
async def add_wishlist_start(message: Message, state: FSMContext):
    """Начать добавление в вишлист"""
    user_wishlist_data[message.from_user.id] = {}
    await state.set_state(AddWishlistStates.waiting_for_size_category)
    await message.answer(
        "📦 <b>Выберите размер покупки:</b>",
        reply_markup=get_wishlist_size_keyboard(),
        parse_mode=ParseMode.HTML
    )

@router.message(AddWishlistStates.waiting_for_size_category)
async def process_wishlist_size(message: Message, state: FSMContext):
    """Обработка выбора размера"""
    if message.text == EMOJI_CANCEL:
        await state.clear()
        del user_wishlist_data[message.from_user.id]
        await message.answer("Отменено", reply_markup=get_wishlist_submenu())
        return
    
    if message.text not in WISHLIST_SIZE_CATEGORIES:
        await message.answer("❌ Выберите категорию из списка:")
        return
    
    user_wishlist_data[message.from_user.id]['size_category'] = message.text
    await state.set_state(AddWishlistStates.waiting_for_type_category)
    await message.answer(
        "🏷 <b>Выберите тип покупки:</b>",
        reply_markup=get_wishlist_type_keyboard(),
        parse_mode=ParseMode.HTML
    )

@router.message(AddWishlistStates.waiting_for_type_category)
async def process_wishlist_type(message: Message, state: FSMContext):
    """Обработка выбора типа"""
    if message.text == EMOJI_CANCEL:
        await state.clear()
        del user_wishlist_data[message.from_user.id]
        await message.answer("Отменено", reply_markup=get_wishlist_submenu())
        return
    
    if message.text not in WISHLIST_TYPE_CATEGORIES:
        await message.answer("❌ Выберите тип из списка:")
        return
    
    user_wishlist_data[message.from_user.id]['type_category'] = message.text
    await state.set_state(AddWishlistStates.waiting_for_name)
    await message.answer(
        "📝 <b>Введите название желания:</b>\n\n"
        "Например: iPhone 15 Pro или Новые кроссовки",
        reply_markup=get_cancel_keyboard(),
        parse_mode=ParseMode.HTML
    )

@router.message(AddWishlistStates.waiting_for_name)
async def process_wishlist_name(message: Message, state: FSMContext):
    """Обработка названия"""
    if message.text == EMOJI_CANCEL:
        await state.clear()
        del user_wishlist_data[message.from_user.id]
        await message.answer("Отменено", reply_markup=get_wishlist_submenu())
        return
    
    user_wishlist_data[message.from_user.id]['name'] = message.text
    await state.set_state(AddWishlistStates.waiting_for_price)
    await message.answer(
        "💰 <b>Введите цену (в рублях):</b>\n\n"
        "Или нажмите «Пропустить» если не знаете",
        reply_markup=get_skip_keyboard(),
        parse_mode=ParseMode.HTML
    )

@router.message(AddWishlistStates.waiting_for_price)
async def process_wishlist_price(message: Message, state: FSMContext):
    """Обработка цены"""
    if message.text == EMOJI_CANCEL:
        await state.clear()
        del user_wishlist_data[message.from_user.id]
        await message.answer("Отменено", reply_markup=get_wishlist_submenu())
        return
    
    if message.text == EMOJI_SKIP:
        user_wishlist_data[message.from_user.id]['price'] = None
    else:
        try:
            price = float(message.text.replace(',', '.').replace(' ', ''))
            user_wishlist_data[message.from_user.id]['price'] = price
        except ValueError:
            await message.answer("❌ Введите число или нажмите «Пропустить»:")
            return
    
    await state.set_state(AddWishlistStates.waiting_for_priority)
    await message.answer(
        "⭐️ <b>Выберите приоритет:</b>",
        reply_markup=get_wishlist_priority_keyboard(),
        parse_mode=ParseMode.HTML
    )

@router.message(AddWishlistStates.waiting_for_priority)
async def process_wishlist_priority(message: Message, state: FSMContext):
    """Обработка приоритета"""
    if message.text == EMOJI_CANCEL:
        await state.clear()
        del user_wishlist_data[message.from_user.id]
        await message.answer("Отменено", reply_markup=get_wishlist_submenu())
        return
    
    if message.text not in WISHLIST_PRIORITIES:
        await message.answer("❌ Выберите приоритет из списка:")
        return
    
    user_wishlist_data[message.from_user.id]['priority'] = message.text
    await state.set_state(AddWishlistStates.waiting_for_photo)
    await message.answer(
        "📸 <b>Отправьте фото товара</b>\n\n"
        "Или нажмите «Пропустить»",
        reply_markup=get_skip_keyboard(),
        parse_mode=ParseMode.HTML
    )

@router.message(AddWishlistStates.waiting_for_photo)
async def process_wishlist_photo(message: Message, state: FSMContext):
    """Обработка фото"""
    if message.text == EMOJI_CANCEL:
        await state.clear()
        del user_wishlist_data[message.from_user.id]
        await message.answer("Отменено", reply_markup=get_wishlist_submenu())
        return
    
    if message.text == EMOJI_SKIP:
        user_wishlist_data[message.from_user.id]['photo_url'] = None
    elif message.photo:
        # Сохраняем file_id фото
        user_wishlist_data[message.from_user.id]['photo_url'] = message.photo[-1].file_id
    else:
        await message.answer("❌ Отправьте фото или нажмите «Пропустить»:")
        return
    
    await state.set_state(AddWishlistStates.waiting_for_link)
    await message.answer(
        "🔗 <b>Отправьте ссылку на товар</b>\n\n"
        "Или нажмите «Пропустить»",
        reply_markup=get_skip_keyboard(),
        parse_mode=ParseMode.HTML
    )

@router.message(AddWishlistStates.waiting_for_link)
async def process_wishlist_link(message: Message, state: FSMContext):
    """Обработка ссылки и сохранение"""
    if message.text == EMOJI_CANCEL:
        await state.clear()
        del user_wishlist_data[message.from_user.id]
        await message.answer("Отменено", reply_markup=get_wishlist_submenu())
        return
    
    if message.text == EMOJI_SKIP:
        user_wishlist_data[message.from_user.id]['link'] = None
    else:
        user_wishlist_data[message.from_user.id]['link'] = message.text
    
    # Сохраняем в БД
    data = user_wishlist_data[message.from_user.id]
    item_id = await db.add_wishlist_item(
        user_id=message.from_user.id,
        name=data['name'],
        size_category=data['size_category'],
        type_category=data['type_category'],
        price=data.get('price'),
        priority=data.get('priority'),
        photo_url=data.get('photo_url'),
        link=data.get('link')
    )
    
    # Формируем сообщение
    result_text = f"✅ <b>Желание добавлено!</b>\n\n"
    result_text += f"📦 {data['name']}\n"
    result_text += f"🏷 {data['type_category']}\n"
    result_text += f"📏 {data['size_category']}\n"
    
    if data.get('price'):
        result_text += f"💰 {data['price']:,.0f} ₽\n"
    
    if data.get('priority'):
        result_text += f"⭐️ {data['priority']}\n"
    
    await state.clear()
    del user_wishlist_data[message.from_user.id]
    
    await message.answer(result_text, reply_markup=get_wishlist_submenu(), parse_mode=ParseMode.HTML)

@router.message(F.text == "📋 Мой вишлист")
async def show_my_wishlist(message: Message):
    """Показать вишлист"""
    user_id = message.from_user.id
    
    items = await db.get_user_wishlist(user_id)
    
    if not items:
        await message.answer(
            "📋 Ваш вишлист пуст.\n\n"
            "Добавьте первое желание через «➕ Добавить желание»",
            reply_markup=get_wishlist_submenu()
        )
        return
    
    # Группируем по приоритетам
    by_priority = {}
    for item in items:
        priority = item.get('priority', '💭 Когда-нибудь')
        if priority not in by_priority:
            by_priority[priority] = []
        by_priority[priority].append(item)
    
    text = "🎁 <b>Ваш вишлист:</b>\n\n"
    
    for priority in WISHLIST_PRIORITIES:
        if priority in by_priority:
            text += f"\n<b>{priority}</b>\n"
            for item in by_priority[priority]:
                text += f"• {item['name']}"
                if item.get('price'):
                    text += f" — {item['price']:,.0f} ₽"
                text += f" ({item['type_category']})\n"
    
    text += f"\n📊 Всего желаний: {len(items)}"
    
    await message.answer(text, reply_markup=get_wishlist_submenu(), parse_mode=ParseMode.HTML)

def create_lockfile():
    """Создать файл блокировки"""
    if LOCKFILE.exists():
        logger.error("⚠️ Бот уже запущен! Найден файл блокировки.")
        logger.error("Если бот не запущен, удалите файл .bot.lock")
        sys.exit(1)
    
    LOCKFILE.write_text(str(os.getpid()))
    logger.info(f"✅ Lockfile создан (PID: {os.getpid()})")

def remove_lockfile():
    """Удалить файл блокировки"""
    if LOCKFILE.exists():
        LOCKFILE.unlink()
        logger.info("🗑 Lockfile удален")

async def send_period_reminder(bot: Bot, user_id: int, start_date: str, end_date: str, period_name: str):
    """Отправить напоминание о периоде"""
    try:
        stats = await db.get_tips_stats_by_period(user_id, start_date, end_date)
        
        if not stats or stats['shifts_count'] == 0:
            return
        
        # Считаем только ставку (hours * 180)
        total_hours = stats.get('total_hours', 0) or 0
        wage = total_hours * 180
        
        # Формируем сообщение
        text = (
            f"💼 <b>Напоминание о зарплате</b>\n\n"
            f"📅 Период: {period_name}\n"
            f"({start_date} - {end_date})\n\n"
            f"📊 <b>Статистика:</b>\n"
            f"• Смен: {stats['shifts_count']}\n"
            f"• Часов: {total_hours}\n"
            f"• 💼 Ставка: {wage:,.0f} ₽\n\n"
        )
        
        # Добавляем распределение ставки
        if wage > 0:
            distribution = calculate_wage_distribution(wage)
            text += format_wage_distribution(distribution)
        
        await bot.send_message(user_id, text, parse_mode=ParseMode.HTML)
        logger.info(f"✅ Напоминание отправлено пользователю {user_id} за период {period_name}")
        
    except Exception as e:
        logger.error(f"Ошибка при отправке напоминания: {e}")


async def check_and_send_reminders(bot: Bot):
    """Проверка и отправка напоминаний"""
    while True:
        try:
            now = datetime.now()
            
            # Проверяем время: 10:00 утра
            if now.hour == 10 and now.minute == 0:
                day = now.day
                
                # 5-го числа: период 15-31 предыдущего месяца
                if day == 5:
                    if now.month == 1:
                        prev_month = 12
                        prev_year = now.year - 1
                    else:
                        prev_month = now.month - 1
                        prev_year = now.year
                    
                    # Последний день предыдущего месяца
                    if prev_month in [1, 3, 5, 7, 8, 10, 12]:
                        last_day = 31
                    elif prev_month in [4, 6, 9, 11]:
                        last_day = 30
                    else:
                        last_day = 29 if prev_year % 4 == 0 and (prev_year % 100 != 0 or prev_year % 400 == 0) else 28
                    
                    start_date = f"15.{prev_month:02d}.{prev_year}"
                    end_date = f"{last_day}.{prev_month:02d}.{prev_year}"
                    period_name = f"15-{last_day} {['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'][prev_month-1]}"
                    
                    users = await db.get_all_users()
                    for user_id in users:
                        await send_period_reminder(bot, user_id, start_date, end_date, period_name)
                
                # 25-го числа: период 1-15 текущего месяца
                elif day == 25:
                    start_date = f"01.{now.month:02d}.{now.year}"
                    end_date = f"15.{now.month:02d}.{now.year}"
                    period_name = f"1-15 {['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'][now.month-1]}"
                    
                    users = await db.get_all_users()
                    for user_id in users:
                        await send_period_reminder(bot, user_id, start_date, end_date, period_name)
                
                await asyncio.sleep(60)  # Спим минуту после отправки
            else:
                await asyncio.sleep(60)  # Проверяем каждую минуту
                
        except Exception as e:
            logger.error(f"Ошибка в системе напоминаний: {e}")
            await asyncio.sleep(60)


async def shutdown(signal_name=None):
    """Корректное завершение работы"""
    if signal_name:
        logger.info(f"⚠️ Получен сигнал {signal_name}, завершение...")
    else:
        logger.info("⚠️ Завершение работы...")
    
    # Закрываем соединение с БД
    await db.close()
    logger.info("✅ БД закрыта")
    
    # Удаляем lockfile
    remove_lockfile()

async def main():
    """Запуск бота"""
    # Создаем lockfile
    create_lockfile()
    
    # Регистрируем очистку при выходе
    atexit.register(remove_lockfile)
    
    # Инициализация базы данных
    await db.init_db()
    
    # Быстрое подключение к Google Sheets
    if google_sheets.connect():
        logger.info(f"📊 Google Sheets: {google_sheets.get_spreadsheet_url()}")
        # Запускаем инициализацию листов в фоне
        asyncio.create_task(asyncio.to_thread(google_sheets.lazy_init_sheets))
    
    # Инициализация бота
    bot = Bot(TOKEN)
    
    # Подключение роутера
    dp.include_router(router)
    
    logger.info("🚀 Бот запущен и готов к работе!")
    logger.info("⚡️ Кэширование включено (TTL: 10 минут)")
    logger.info("📄 Пагинация: {} мест на странице".format(PLACES_PER_PAGE))
    logger.info("🚄 Фоновая синхронизация с Google Sheets")
    logger.info("🔔 Система напоминаний активирована (5-е и 25-е числа в 10:00)")
    
    # Запускаем систему напоминаний в фоне
    asyncio.create_task(check_and_send_reminders(bot))
    
    try:
        # Запуск polling с таймаутом
        await dp.start_polling(bot, timeout=60, request_timeout=30)
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        raise
    finally:
        await shutdown()

if __name__ == "__main__":
    try:
        # Обработка сигналов для graceful shutdown
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Регистрируем обработчики сигналов
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(
                sig,
                lambda s=sig: asyncio.create_task(shutdown(signal.Signals(s).name))
            )
        
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        logger.info("⌨️ Получен Ctrl+C")
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка: {e}", exc_info=True)
    finally:
        logger.info("👋 Бот остановлен")

