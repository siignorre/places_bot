"""
Утилиты для бота
"""
from datetime import datetime
from typing import Dict, Any, Optional, List
import time
import aiohttp
import os
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

class SimpleCache:
    """Простой кэш для хранения данных с TTL"""
    def __init__(self, ttl_seconds: int = 300):
        self.cache: Dict[str, tuple[Any, float]] = {}
        self.ttl = ttl_seconds
    
    def get(self, key: str) -> Optional[Any]:
        """Получить значение из кэша"""
        if key in self.cache:
            value, timestamp = self.cache[key]
            if time.time() - timestamp < self.ttl:
                return value
            else:
                del self.cache[key]
        return None
    
    def set(self, key: str, value: Any):
        """Сохранить значение в кэш"""
        self.cache[key] = (value, time.time())
    
    def clear(self, pattern: str = None):
        """Очистить кэш (или записи по паттерну)"""
        if pattern:
            keys_to_delete = [k for k in self.cache.keys() if pattern in k]
            for key in keys_to_delete:
                del self.cache[key]
        else:
            self.cache.clear()

def format_date(date_str: str) -> str:
    """Форматировать дату в DD.MM.YYYY"""
    try:
        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return dt.strftime('%d.%m.%Y')
    except:
        return date_str

def format_movie_text(movie: dict, include_genre: bool = True) -> str:
    """Форматировать текст фильма для отображения"""
    rating_stars = "⭐" * movie['rating'] if movie.get('rating') else ""
    text = f"🎬 <b>{movie['title']}</b> ({movie['year']})\n"
    
    if include_genre:
        text += f"🎭 {movie['genre']}\n"
    
    text += f"📊 {movie['status']}"
    
    if rating_stars:
        text += f"\n{rating_stars}"
    
    if movie.get('notes'):
        text += f"\n📝 {movie['notes']}"
    
    return text

def format_series_text(series: dict, include_genre: bool = True) -> str:
    """Форматировать текст сериала для отображения"""
    rating_stars = "⭐" * series['rating'] if series.get('rating') else ""
    text = f"📺 <b>{series['title']}</b> ({series['year']})\n"
    
    if include_genre:
        text += f"🎭 {series['genre']}\n"
    
    text += f"📊 Сезонов: {series.get('seasons', 0)}, Серий: {series.get('episodes', 0)}\n"
    text += f"📺 {series['status']}"
    
    if rating_stars:
        text += f"\n{rating_stars}"
    
    if series.get('notes'):
        text += f"\n📝 {series['notes']}"
    
    return text

def capitalize_first(text: str) -> str:
    """Первая буква заглавная"""
    return text[0].upper() + text[1:] if text else text

def calculate_tips_distribution(total_amount: float) -> dict:
    """
    Рассчитать распределение чаевых по категориям
    
    Фиксированные суммы:
    - 1000 ₽ Яндекс.Пэй
    - 1000 ₽ Сбербанк
    - 1000 ₽ Обучение
    - 300 ₽ Акции
    - 300 ₽ Бизнес
    Итого: 3600 ₽
    
    Свыше 3600 распределяется:
    - 50% Жизнь
    - 30% Одежда
    - 20% Накопления/Техника
    """
    distribution = {
        'Сбербанк': 0,
        'Яндекс Пэй': 0,
        'Бизнес': 0,
        'Обучение': 0,
        'Акции': 0,
        'Жизнь': 0,
        'Одежда': 0,
        'Накопления/Техника': 0
    }
    
    if total_amount <= 0:
        return distribution
    
    if total_amount < 3600:
        # Если меньше 3600, пропорционально распределяем фиксированные суммы
        ratio = total_amount / 3600
        distribution['Яндекс Пэй'] = 1000 * ratio
        distribution['Сбербанк'] = 1000 * ratio
        distribution['Обучение'] = 1000 * ratio
        distribution['Акции'] = 300 * ratio
        distribution['Бизнес'] = 300 * ratio
    else:
        # Фиксированные суммы
        distribution['Яндекс Пэй'] = 1000
        distribution['Сбербанк'] = 1000
        distribution['Обучение'] = 1000
        distribution['Акции'] = 300
        distribution['Бизнес'] = 300
        
        # Остаток по процентам
        remainder = total_amount - 3600
        if remainder > 0:
            distribution['Жизнь'] = remainder * 0.50
            distribution['Одежда'] = remainder * 0.30
            distribution['Накопления/Техника'] = remainder * 0.20
    
    return distribution

def calculate_avito_distribution(amount: float) -> dict:
    """
    Рассчитать распределение для продажи на Авито
    
    30% Сбербанк, 10% Яндекс Пэй, 20% Обучение, 40% Хотелки
    """
    return {
        'Сбербанк': amount * 0.30,
        'Яндекс Пэй': amount * 0.10,
        'Обучение': amount * 0.20,
        'Хотелки': amount * 0.40
    }

def get_motivation_message(amount: float) -> str:
    """
    Получить мотивационное сообщение в зависимости от суммы чаевых
    """
    if amount < 2000:
        return ""  # Без сообщения для малых сумм
    elif amount < 4000:
        return "💪 Неплохо! Продолжай в том же духе!"
    elif amount < 6000:
        return "🔥 Отличная смена! Так держать!"
    elif amount < 8000:
        return "🌟 Вау! Ты крутой!"
    elif amount < 12000:
        return "🚀 Невероятно! Ты машина!"
    else:
        return "👑⭐ Легенда! Ты просто космос!"

def format_distribution(distribution: dict) -> str:
    """
    Форматировать распределение для отображения
    """
    text = "💰 <b>Распределение:</b>\n\n"
    
    emoji_map = {
        'Сбербанк': '💳',
        'Яндекс Пэй': '💰',
        'Бизнес': '💼',
        'Жизнь': '🏠',
        'Обучение': '📚',
        'Акции': '📈',
        'Одежда': '👔',
        'Накопления/Техника': '💻'
    }
    
    for category, amount in distribution.items():
        if amount > 0:
            emoji = emoji_map.get(category, '💵')
            text += f"{emoji} <b>{category}:</b> {amount:,.0f} ₽\n"
    
    return text


def calculate_wage_distribution(wage_amount: float) -> dict:
    """
    Рассчитать распределение ставки (не чаевых!)
    
    30% Сбербанк, 20% Обучение, 40% Жизнь, 10% Хотелки
    """
    return {
        'Сбербанк': wage_amount * 0.30,
        'Обучение': wage_amount * 0.20,
        'Жизнь': wage_amount * 0.40,
        'Хотелки': wage_amount * 0.10
    }


def format_wage_distribution(distribution: dict) -> str:
    """
    Форматировать распределение ставки для отображения
    """
    text = "💼 <b>Распределение ставки:</b>\n\n"
    
    emoji_map = {
        'Сбербанк': '💳',
        'Обучение': '📚',
        'Жизнь': '🏠',
        'Хотелки': '🎁'
    }
    
    for category, amount in distribution.items():
        if amount > 0:
            emoji = emoji_map.get(category, '💵')
            text += f"{emoji} <b>{category}:</b> {amount:,.0f} ₽\n"
    
    return text


# ============= YANDEX MAPS API =============

async def search_place_yandex(query: str, limit: int = 7) -> List[Dict[str, Any]]:
    """
    Поиск места в Яндекс.Картах по названию, адресу или координатам
    
    Args:
        query: Название места, адрес или координаты
        limit: Максимальное количество результатов
        
    Returns:
        Список найденных мест с информацией
    """
    api_key = os.getenv('YANDEX_API_KEY', '56546efa-170e-47c4-8793-af1f3b2f1fc1')
    
    if not api_key:
        return []
    
    # Используем Geocoder API для поиска
    url = "https://geocode-maps.yandex.ru/1.x/"
    
    params = {
        'apikey': api_key,
        'geocode': query,
        'format': 'json',
        'results': limit,
        'kind': 'house'  # Искать здания/места
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=10) as response:
                if response.status != 200:
                    return []
                
                data = await response.json()
                
                places = []
                members = data.get('response', {}).get('GeoObjectCollection', {}).get('featureMember', [])
                
                for member in members:
                    geo_object = member.get('GeoObject', {})
                    
                    # Координаты
                    pos = geo_object.get('Point', {}).get('pos', '').split()
                    if len(pos) == 2:
                        longitude, latitude = float(pos[0]), float(pos[1])
                    else:
                        continue
                    
                    # Название и адрес
                    name = geo_object.get('name', '')
                    description = geo_object.get('description', '')
                    full_address = geo_object.get('metaDataProperty', {}).get('GeocoderMetaData', {}).get('text', '')
                    
                    # Категория места
                    kind = geo_object.get('metaDataProperty', {}).get('GeocoderMetaData', {}).get('kind', '')
                    
                    places.append({
                        'name': name,
                        'description': description,
                        'address': full_address,
                        'latitude': latitude,
                        'longitude': longitude,
                        'kind': kind,
                        'display_text': f"{name}\n{description}" if description else name
                    })
                
                return places
                
    except Exception as e:
        print(f"Ошибка при поиске места в Яндекс.Картах: {e}")
        return []


async def get_place_details_yandex(latitude: float, longitude: float) -> Dict[str, Any]:
    """
    Получить подробную информацию о месте по координатам
    
    Args:
        latitude: Широта
        longitude: Долгота
        
    Returns:
        Словарь с информацией о месте
    """
    api_key = os.getenv('YANDEX_API_KEY', '56546efa-170e-47c4-8793-af1f3b2f1fc1')
    
    if not api_key:
        return {}
    
    # Используем Organizations API для получения деталей
    url = "https://search-maps.yandex.ru/v1/"
    
    params = {
        'apikey': api_key,
        'text': f"{latitude},{longitude}",
        'lang': 'ru_RU',
        'type': 'biz',
        'results': 1
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=10) as response:
                if response.status != 200:
                    return {}
                
                data = await response.json()
                
                features = data.get('features', [])
                if not features:
                    return {}
                
                properties = features[0].get('properties', {})
                company_meta = properties.get('CompanyMetaData', {})
                
                # Получаем информацию
                result = {
                    'name': properties.get('name', ''),
                    'address': properties.get('description', ''),
                    'categories': company_meta.get('Categories', []),
                    'phones': company_meta.get('Phones', []),
                    'hours': company_meta.get('Hours', {}),
                    'url': company_meta.get('url', '')
                }
                
                # Форматируем часы работы
                hours_data = result.get('hours', {})
                if hours_data:
                    availabilities = hours_data.get('Availabilities', [])
                    if availabilities:
                        # Берем первый доступный интервал
                        first_availability = availabilities[0]
                        intervals = first_availability.get('Intervals', [])
                        if intervals:
                            # Берем первый интервал времени
                            interval = intervals[0]
                            from_time = interval.get('from', '')
                            to_time = interval.get('to', '')
                            if from_time and to_time:
                                result['working_hours'] = f"{from_time} - {to_time}"
                
                # Определяем тип кухни для ресторанов
                categories = result.get('categories', [])
                cuisine = None
                for cat in categories:
                    cat_name = cat.get('name', '').lower()
                    if 'японск' in cat_name or 'суши' in cat_name:
                        cuisine = 'Японская'
                    elif 'китайск' in cat_name:
                        cuisine = 'Китайская'
                    elif 'итальянск' in cat_name or 'пицц' in cat_name:
                        cuisine = 'Итальянская'
                    elif 'французск' in cat_name:
                        cuisine = 'Французская'
                    elif 'испанск' in cat_name:
                        cuisine = 'Испанская'
                    elif 'греческ' in cat_name:
                        cuisine = 'Греческая'
                    elif 'американск' in cat_name or 'бургер' in cat_name:
                        cuisine = 'Американская'
                    
                    if cuisine:
                        break
                
                result['cuisine'] = cuisine
                
                return result
                
    except Exception as e:
        print(f"Ошибка при получении деталей места: {e}")
        return {}

