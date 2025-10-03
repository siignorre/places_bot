# 🚀 Развертывание на Railway

## Шаг 1: Создание GitHub репозитория

1. Откройте https://github.com/new
2. Назовите репозиторий: `places_bot`
3. Сделайте его **Private** (приватным)
4. **НЕ добавляйте** README, .gitignore или лицензию
5. Нажмите "Create repository"

## Шаг 2: Загрузка кода на GitHub

Скопируйте эти команды в терминал (в папке проекта):

```bash
cd /Users/danik/Desktop/places_bot
git init
git add .
git commit -m "Initial commit: Places Bot"
git branch -M main
git remote add origin https://github.com/ВАШ_USERNAME/places_bot.git
git push -u origin main
```

⚠️ **Замените** `ВАШ_USERNAME` на ваше имя пользователя GitHub!

## Шаг 3: Развертывание на Railway

1. Откройте https://railway.app
2. Нажмите "Start a New Project"
3. Войдите через GitHub
4. Выберите "Deploy from GitHub repo"
5. Выберите репозиторий `places_bot`
6. Railway автоматически обнаружит Python проект

## Шаг 4: Добавление переменной окружения

1. В Railway откройте вкладку **Variables**
2. Нажмите "New Variable"
3. Добавьте:
   - **Name:** `BOT_TOKEN`
   - **Value:** `8345142181:AAG-I1FTxZSt-BoHPRzKHgq8CUhAdgtS1iE`
4. Нажмите "Add"

## Шаг 5: Готово! 🎉

Бот автоматически развернется и запустится. Проверьте в Telegram - он должен работать 24/7!

### Просмотр логов:

В Railway перейдите на вкладку **Deployments** → кликните на последний деплой → смотрите логи

### Обновление бота:

Просто сделайте `git push` - Railway автоматически обновит бота:

```bash
git add .
git commit -m "Обновление"
git push
```

---

## 💡 Полезные ссылки

- Railway Dashboard: https://railway.app/dashboard
- Логи бота: в Railway → Deployments
- GitHub репозиторий: https://github.com/ВАШ_USERNAME/places_bot

