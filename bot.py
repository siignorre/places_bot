import asyncio
import logging
import sys
from os import getenv
from dotenv import load_dotenv
from datetime import datetime

from aiogram import Bot, Dispatcher, Router, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
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

# Загрузка переменных окружения
load_dotenv()
TOKEN = getenv("BOT_TOKEN")

# Настройка логирования
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

# Инициализация
dp = Dispatcher()
router = Router()
db = Database()

# Состояния для добавления места
class AddPlaceStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_type = State()
    waiting_for_price = State()
    waiting_for_address = State()
    waiting_for_description = State()
    waiting_for_location = State()

# Временное хранилище данных о месте
user_place_data = {}

# Функция форматирования даты
def format_date(date_str):
    """Форматирует дату в формат ДД.ММ.ГГГГ"""
    try:
        # Парсим дату из строки (формат SQLite: YYYY-MM-DD HH:MM:SS)
        dt = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
        return dt.strftime('%d.%m.%Y')
    except:
        return date_str

# Главное меню
def get_main_menu():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить место"), KeyboardButton(text="🎉 Добавить мероприятие")],
            [KeyboardButton(text="📋 Мои места"), KeyboardButton(text="🔍 Поиск")],
            [KeyboardButton(text="📊 Статистика")],
        ],
        resize_keyboard=True
    )
    return keyboard

# Кнопка отмены
def get_cancel_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
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
    """Получение названия места"""
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено", reply_markup=get_main_menu())
        return
    
    # Название с большой буквы
    user_place_data[message.from_user.id]['name'] = message.text.capitalize()
    await state.set_state(AddPlaceStates.waiting_for_type)
    await message.answer(
        "🏷 Выберите тип места:",
        reply_markup=get_place_type_keyboard()
    )

@router.message(AddPlaceStates.waiting_for_type)
async def process_place_type(message: Message, state: FSMContext):
    """Получение типа места"""
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено", reply_markup=get_main_menu())
        return
    
    # Сохраняем тип места
    user_place_data[message.from_user.id]['place_type'] = message.text
    
    # Проверяем, нужна ли ценовая категория (для ресторанов, кафе, баров)
    if message.text in ["🍺 Бар", "☕️ Кафе", "🍽 Ресторан"]:
        await state.set_state(AddPlaceStates.waiting_for_price)
        await message.answer(
            "💰 Выберите ценовую категорию:",
            reply_markup=get_price_category_keyboard()
        )
    else:
        # Для остальных типов сразу переходим к адресу
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

@router.message(AddPlaceStates.waiting_for_price)
async def process_price_category(message: Message, state: FSMContext):
    """Получение ценовой категории"""
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено", reply_markup=get_main_menu())
        return
    
    # Сохраняем ценовую категорию
    user_place_data[message.from_user.id]['price_category'] = message.text
    
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
        "📝 Добавьте описание или заметку\n\n"
        "Например: <i>Лучший кофе в городе, Wi-Fi есть</i>",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="⏭ Пропустить")],
                [KeyboardButton(text="❌ Отмена")]
            ],
            resize_keyboard=True
        ),
        parse_mode=ParseMode.HTML
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
    
    await state.set_state(AddPlaceStates.waiting_for_location)
    await message.answer(
        "📍 Отправьте геолокацию места\n\n"
        "Нажмите 📎 → Геопозиция в Telegram\n"
        "Или нажмите 'Завершить' без геолокации",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="✅ Завершить без геолокации")],
                [KeyboardButton(text="❌ Отмена")]
            ],
            resize_keyboard=True
        )
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
        address=data.get('address'),
        description=data.get('description'),
        latitude=data.get('latitude'),
        longitude=data.get('longitude')
    )
    
    response = f"✅ Место сохранено!\n\n"
    response += f"📍 <b>{data.get('name')}</b>\n"
    if data.get('place_type'):
        response += f"🏷 {data.get('place_type')}"
        if data.get('price_category'):
            response += f" {data.get('price_category')}"
        response += "\n"
    if data.get('address'):
        response += f"📮 {data.get('address')}\n"
    if data.get('description'):
        response += f"📝 {data.get('description')}\n"
    if data.get('latitude') and data.get('longitude'):
        response += f"🗺 Координаты сохранены"
    
    await message.answer(response, parse_mode=ParseMode.HTML, reply_markup=get_main_menu())
    
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

@router.callback_query(F.data.startswith("filter_"))
async def filter_places(callback: CallbackQuery):
    """Фильтрация мест по категории"""
    filter_type = callback.data.replace("filter_", "")
    
    # Используем фильтрацию на уровне БД (быстрее)
    if filter_type == "all":
        places = await db.get_user_places(callback.from_user.id)
    else:
        places = await db.get_user_places(callback.from_user.id, place_type=filter_type)
    
    if not places:
        await callback.answer("В этой категории пока нет мест", show_alert=True)
        return
    
    await callback.answer()
    
    # Отображаем места
    category_name = filter_type if filter_type == "all" else filter_type
    header = f"📋 <b>Все места ({len(places)})</b>" if filter_type == "all" else f"<b>{category_name} ({len(places)})</b>"
    
    await callback.message.answer(header, parse_mode=ParseMode.HTML)
    
    for place in places:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🗺 Показать на карте", callback_data=f"show_map_{place['id']}")],
            [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete_{place['id']}")]
        ])
        
        text = f"📍 <b>{place['name']}</b>\n"
        if place.get('place_type'):
            text += f"🏷 {place['place_type']}"
            if place.get('price_category'):
                text += f" {place['price_category']}"
            text += "\n"
        if place['address']:
            text += f"📮 {place['address']}\n"
        if place['description']:
            text += f"📝 {place['description']}\n"
        text += f"\n🕐 Добавлено: {format_date(place['created_at'])}"
        
        # Если есть координаты, отправляем локацию
        if place['latitude'] and place['longitude']:
            await callback.message.answer_location(
                latitude=place['latitude'],
                longitude=place['longitude']
            )
        
        await callback.message.answer(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )

@router.callback_query(F.data.startswith("show_map_"))
async def show_place_on_map(callback: CallbackQuery):
    """Показать место на карте"""
    place_id = int(callback.data.split("_")[2])
    place = await db.get_place(place_id, callback.from_user.id)
    
    if not place:
        await callback.answer("Место не найдено", show_alert=True)
        return
    
    if place['latitude'] and place['longitude']:
        await callback.message.answer_location(
            latitude=place['latitude'],
            longitude=place['longitude']
        )
        await callback.answer("📍 Геолокация отправлена")
    else:
        await callback.answer("У этого места нет сохраненной геолокации", show_alert=True)

@router.callback_query(F.data.startswith("delete_"))
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
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🗺 Показать на карте", callback_data=f"show_map_{place['id']}")],
            [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete_{place['id']}")]
        ])
        
        text = f"📍 <b>{place['name']}</b>\n"
        if place.get('place_type'):
            text += f"🏷 {place['place_type']}"
            if place.get('price_category'):
                text += f" {place['price_category']}"
            text += "\n"
        if place['address']:
            text += f"📮 {place['address']}\n"
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

# ===== СТАТИСТИКА =====

@router.message(F.text == "📊 Статистика")
async def show_stats(message: Message):
    """Показать статистику пользователя"""
    count = await db.count_user_places(message.from_user.id)
    
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
        reply_markup=get_main_menu()
    )

async def main():
    """Запуск бота"""
    # Инициализация базы данных
    await db.init_db()
    
    # Инициализация бота
    bot = Bot(TOKEN)
    
    # Подключение роутера
    dp.include_router(router)
    
    logger.info("Бот запущен!")
    
    # Запуск polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен")

