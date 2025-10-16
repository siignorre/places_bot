#!/bin/bash

# Скрипт для деплоя на Railway

echo "🚀 Начинаем деплой..."

# Проверяем статус Git
git status

# Добавляем все изменения
git add .

# Создаем коммит
git commit -m "feat: добавлена система идей с категориями и синхронизацией"

# Пушим в main
git push origin main

echo "✅ Деплой завершен!"

