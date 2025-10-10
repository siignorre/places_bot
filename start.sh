#!/bin/bash

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Пути
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCKFILE="$SCRIPT_DIR/.bot.lock"
BOT_SCRIPT="$SCRIPT_DIR/bot.py"
VENV_DIR="$SCRIPT_DIR/venv"
REQUIREMENTS="$SCRIPT_DIR/requirements.txt"
ENV_FILE="$SCRIPT_DIR/.env"

# Функция вывода с цветом
print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_header() {
    echo -e "${PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}🤖  Telegram Bot Manager${NC}"
    echo -e "${PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# Проверка статуса бота
check_status() {
    if [ -f "$LOCKFILE" ]; then
        PID=$(cat "$LOCKFILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            return 0  # Работает
        else
            return 1  # Lockfile есть, но процесс мёртв
        fi
    fi
    return 2  # Не запущен
}

# Показать статус
show_status() {
    print_header
    check_status
    STATUS=$?
    
    if [ $STATUS -eq 0 ]; then
        PID=$(cat "$LOCKFILE")
        print_success "Бот запущен (PID: $PID)"
        echo ""
        print_info "Логи: tail -f $SCRIPT_DIR/bot.log"
        print_info "Остановить: ./start.sh stop"
    elif [ $STATUS -eq 1 ]; then
        print_warning "Найден старый lockfile, но процесс не работает"
        print_info "Очистка: rm -f $LOCKFILE"
    else
        print_error "Бот не запущен"
        print_info "Запустить: ./start.sh start"
    fi
}

# Остановка бота
stop_bot() {
    print_header
    check_status
    STATUS=$?
    
    if [ $STATUS -eq 0 ]; then
        PID=$(cat "$LOCKFILE")
        print_info "Остановка бота (PID: $PID)..."
        
        kill "$PID" 2>/dev/null
        sleep 2
        
        if ps -p "$PID" > /dev/null 2>&1; then
            print_warning "Принудительная остановка..."
            kill -9 "$PID" 2>/dev/null
        fi
        
        rm -f "$LOCKFILE"
        print_success "Бот остановлен"
    elif [ $STATUS -eq 1 ]; then
        print_warning "Очистка старого lockfile..."
        rm -f "$LOCKFILE"
        print_success "Готово"
    else
        print_warning "Бот уже остановлен"
    fi
}

# Запуск бота
start_bot() {
    print_header
    
    # Проверка, что бот не запущен
    check_status
    if [ $? -eq 0 ]; then
        PID=$(cat "$LOCKFILE")
        print_error "Бот уже запущен (PID: $PID)"
        print_info "Остановите: ./start.sh stop"
        exit 1
    fi
    
    # Очистка старого lockfile если он есть
    if [ -f "$LOCKFILE" ]; then
        print_warning "Удаление старого lockfile..."
        rm -f "$LOCKFILE"
    fi
    
    # Проверка Python
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 не найден"
        print_info "Установите: brew install python3 (macOS)"
        exit 1
    fi
    
    # Проверка bot.py
    if [ ! -f "$BOT_SCRIPT" ]; then
        print_error "Файл bot.py не найден"
        exit 1
    fi
    
    # Проверка .env
    if [ ! -f "$ENV_FILE" ]; then
        print_warning "Файл .env не найден"
        print_info "Создайте .env с BOT_TOKEN=ваш_токен"
    fi
    
    # Создание виртуального окружения
    if [ ! -d "$VENV_DIR" ]; then
        print_info "Создание виртуального окружения..."
        python3 -m venv "$VENV_DIR"
        print_success "Виртуальное окружение создано"
    fi
    
    # Активация venv
    source "$VENV_DIR/bin/activate"
    
    # Проверка и установка зависимостей
    if [ ! -f "$REQUIREMENTS" ]; then
        print_error "Файл requirements.txt не найден"
        exit 1
    fi
    
    # Проверяем хеш requirements.txt для автообновления
    REQUIREMENTS_HASH_FILE="$VENV_DIR/.requirements_hash"
    CURRENT_HASH=$(md5 -q "$REQUIREMENTS" 2>/dev/null || md5sum "$REQUIREMENTS" 2>/dev/null | cut -d' ' -f1)
    
    NEED_INSTALL=false
    
    # Проверяем, нужно ли устанавливать зависимости
    if [ ! -f "$REQUIREMENTS_HASH_FILE" ]; then
        NEED_INSTALL=true
        print_info "Первая установка зависимостей..."
    elif [ "$(cat "$REQUIREMENTS_HASH_FILE")" != "$CURRENT_HASH" ]; then
        NEED_INSTALL=true
        print_warning "Обнаружены изменения в requirements.txt"
        print_info "Обновление зависимостей..."
    elif ! python3 -c "import aiogram" &> /dev/null; then
        NEED_INSTALL=true
        print_warning "Зависимости повреждены"
        print_info "Переустановка зависимостей..."
    fi
    
    # Установка/обновление зависимостей
    if [ "$NEED_INSTALL" = true ]; then
        pip install -q -r "$REQUIREMENTS"
        if [ $? -eq 0 ]; then
            echo "$CURRENT_HASH" > "$REQUIREMENTS_HASH_FILE"
            print_success "Зависимости установлены"
        else
            print_error "Ошибка установки зависимостей"
            exit 1
        fi
    else
        print_success "Зависимости актуальны"
    fi
    
    # Запуск бота
    echo ""
    print_success "Запуск бота..."
    print_info "Логи: tail -f $SCRIPT_DIR/bot.log"
    print_info "Остановить: Ctrl+C или ./start.sh stop"
    echo ""
    
    python3 "$BOT_SCRIPT"
}

# Перезапуск бота
restart_bot() {
    print_header
    print_info "Перезапуск бота..."
    echo ""
    
    stop_bot
    sleep 1
    start_bot
}

# Обновление зависимостей
update_dependencies() {
    print_header
    
    if [ ! -d "$VENV_DIR" ]; then
        print_error "Виртуальное окружение не найдено"
        print_info "Сначала запустите: ./start.sh start"
        exit 1
    fi
    
    if [ ! -f "$REQUIREMENTS" ]; then
        print_error "Файл requirements.txt не найден"
        exit 1
    fi
    
    print_info "Принудительное обновление зависимостей..."
    source "$VENV_DIR/bin/activate"
    
    pip install -q --upgrade -r "$REQUIREMENTS"
    
    if [ $? -eq 0 ]; then
        # Обновляем хеш
        REQUIREMENTS_HASH_FILE="$VENV_DIR/.requirements_hash"
        CURRENT_HASH=$(md5 -q "$REQUIREMENTS" 2>/dev/null || md5sum "$REQUIREMENTS" 2>/dev/null | cut -d' ' -f1)
        echo "$CURRENT_HASH" > "$REQUIREMENTS_HASH_FILE"
        
        print_success "Зависимости обновлены"
        echo ""
        print_info "Перезапустите бота: ./start.sh restart"
    else
        print_error "Ошибка обновления зависимостей"
        exit 1
    fi
}

# Помощь
show_help() {
    print_header
    echo ""
    echo "Использование: ./start.sh [команда]"
    echo ""
    echo "Команды:"
    echo "  start    - Запустить бота"
    echo "  stop     - Остановить бота"
    echo "  restart  - Перезапустить бота"
    echo "  status   - Показать статус бота"
    echo "  update   - Обновить зависимости (requirements.txt)"
    echo "  help     - Показать эту справку"
    echo ""
    echo "Без аргументов запускает бота (аналог 'start')"
    echo ""
    echo "Примеры:"
    echo "  ./start.sh              # Запустить"
    echo "  ./start.sh status       # Проверить статус"
    echo "  ./start.sh update       # Обновить зависимости"
    echo ""
}

# Основная логика
cd "$SCRIPT_DIR"

case "${1:-start}" in
    start)
        start_bot
        ;;
    stop)
        stop_bot
        ;;
    restart)
        restart_bot
        ;;
    status)
        show_status
        ;;
    update)
        update_dependencies
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        print_error "Неизвестная команда: $1"
        echo ""
        show_help
        exit 1
        ;;
esac
