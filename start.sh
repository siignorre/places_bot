#!/bin/bash

echo "🤖 Запуск Telegram бота..."
echo ""

# Проверка установки Python
if ! command -v python3 &> /dev/null
then
    echo "❌ Python 3 не найден. Установите Python 3.8 или выше"
    exit 1
fi

# Создание виртуального окружения если не существует
if [ ! -d "venv" ]; then
    echo "📦 Создание виртуального окружения..."
    python3 -m venv venv
fi

# Активация виртуального окружения
source venv/bin/activate

# Проверка и установка зависимостей
if ! python3 -c "import aiogram" &> /dev/null
then
    echo "📦 Установка зависимостей..."
    pip install -r requirements.txt
    echo ""
fi

# Запуск бота
echo "✅ Запуск бота..."
echo "Для остановки нажмите Ctrl+C"
echo ""
python3 bot.py

