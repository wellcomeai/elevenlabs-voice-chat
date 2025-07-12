"""
Вспомогательные функции для ElevenLabs Conversational AI
"""

import logging
import sys
import platform
from pathlib import Path
from typing import Optional
import colorlog

def setup_logging(log_level: str = "INFO", log_file: Optional[str] = None):
    """Настройка логирования"""
    
    # Определяем уровень логирования
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Форматтер для консоли
    console_formatter = colorlog.ColoredFormatter(
        "%(log_color)s%(asctime)s | %(name)-12s | %(levelname)-8s | %(message)s",
        datefmt="%H:%M:%S",
        log_colors={
            'DEBUG': 'cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'red,bg_white',
        }
    )
    
    # Форматтер для файла
    file_formatter = logging.Formatter(
        "%(asctime)s | %(name)-12s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Настраиваем root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    
    # Удаляем существующие обработчики
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Консольный обработчик
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    # Файловый обработчик (если нужен)
    if log_file:
        try:
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(numeric_level)
            file_handler.setFormatter(file_formatter)
            root_logger.addHandler(file_handler)
            
            logging.info(f"📝 Логи сохраняются в: {log_file}")
        except Exception as e:
            logging.warning(f"⚠️ Не удалось создать файл логов: {e}")
    
    # Настраиваем уровни для библиотек
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)

def print_banner():
    """Вывод баннера приложения"""
    banner = """
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║             🎤 ElevenLabs Conversational AI v3.0 🤖             ║
║                                                                  ║
║                   Python CLI Voice Assistant                    ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
"""
    print(banner)
    
    # Системная информация
    print(f"🖥️  Система: {platform.system()} {platform.release()}")
    print(f"🐍 Python: {platform.python_version()}")
    print(f"📁 Папка: {Path.cwd()}")
    print()

def print_help():
    """Вывод справки"""
    help_text = """
📋 Команды голосового ассистента:

🎤 Управление записью:
   ENTER       - Начать/остановить запись
   'r' + ENTER - Переключить запись
   ПРОБЕЛ      - Быстрое переключение (в некоторых терминалах)

📊 Информация:
   'h' + ENTER - Показать эту справку
   's' + ENTER - Показать статистику
   'i' + ENTER - Информация о системе

🔧 Управление:
   'q' + ENTER - Выход из приложения
   Ctrl+C      - Экстренный выход

💡 Советы:
   • Говорите четко и не слишком быстро
   • Используйте наушники для лучшего качества
   • Дождитесь завершения ответа AI
   • При проблемах проверьте подключение к интернету

🎵 Аудио:
   • Частота дискретизации: 16 kHz
   • Формат: PCM 16-bit моно
   • Автоматическое воспроизведение ответов
"""
    print(help_text)

def print_system_info():
    """Вывод информации о системе"""
    try:
        import pyaudio
        
        print("\n💻 Информация о системе:")
        print(f"   🖥️  ОС: {platform.platform()}")
        print(f"   🐍 Python: {platform.python_version()}")
        print(f"   📁 Папка: {Path.cwd()}")
        
        # PyAudio информация
        pa = pyaudio.PyAudio()
        print(f"\n🎵 Аудио система:")
        print(f"   🔊 PyAudio версия: {pyaudio.get_portaudio_version_text()}")
        print(f"   🎤 Устройств ввода: {pa.get_default_input_device_info()['name']}")
        print(f"   🔊 Устройств вывода: {pa.get_default_output_device_info()['name']}")
        pa.terminate()
        
    except Exception as e:
        print(f"\n❌ Ошибка получения информации о системе: {e}")

def check_dependencies():
    """Проверка зависимостей"""
    dependencies = {
        "aiohttp": "HTTP клиент",
        "websockets": "WebSocket клиент", 
        "pyaudio": "Аудио обработка",
        "numpy": "Численные вычисления",
        "colorlog": "Цветное логирование"
    }
    
    missing = []
    
    for package, description in dependencies.items():
        try:
            __import__(package)
            print(f"✅ {package:12} - {description}")
        except ImportError:
            print(f"❌ {package:12} - {description} (НЕ УСТАНОВЛЕН)")
            missing.append(package)
    
    if missing:
        print(f"\n❌ Не установлены пакеты: {', '.join(missing)}")
        print("💡 Установите их командой:")
        print(f"   pip install {' '.join(missing)}")
        return False
    
    print("\n✅ Все зависимости установлены")
    return True

def format_duration(seconds: float) -> str:
    """Форматирование длительности"""
    if seconds < 60:
        return f"{seconds:.1f}с"
    elif seconds < 3600:
        minutes = seconds // 60
        secs = seconds % 60
        return f"{int(minutes)}м {secs:.0f}с"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{int(hours)}ч {int(minutes)}м"

def format_bytes(bytes_count: int) -> str:
    """Форматирование размера в байтах"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_count < 1024.0:
            return f"{bytes_count:.1f} {unit}"
        bytes_count /= 1024.0
    return f"{bytes_count:.1f} TB"

def create_directories():
    """Создание необходимых директорий"""
    directories = [
        Path("logs"),
        Path("temp"),
        Path("config")
    ]
    
    for directory in directories:
        try:
            directory.mkdir(exist_ok=True)
            logging.debug(f"📁 Директория создана: {directory}")
        except Exception as e:
            logging.warning(f"⚠️ Не удалось создать {directory}: {e}")

def validate_environment():
    """Валидация окружения"""
    print("🔍 Проверка окружения...")
    
    # Проверка Python версии
    if sys.version_info < (3, 8):
        print("❌ Требуется Python 3.8 или выше")
        return False
    else:
        print(f"✅ Python {platform.python_version()}")
    
    # Проверка зависимостей
    if not check_dependencies():
        return False
    
    # Создание директорий
    create_directories()
    
    print("✅ Окружение готово")
    return True

def get_terminal_size():
    """Получение размера терминала"""
    try:
        import shutil
        columns, rows = shutil.get_terminal_size()
        return columns, rows
    except:
        return 80, 24  # Значения по умолчанию

def clear_screen():
    """Очистка экрана"""
    import os
    os.system('cls' if os.name == 'nt' else 'clear')

def print_progress_bar(current: int, total: int, prefix: str = "", suffix: str = "", length: int = 30):
    """Вывод прогресс-бара"""
    percent = (current / total) * 100
    filled_length = int(length * current // total)
    bar = '█' * filled_length + '-' * (length - filled_length)
    
    print(f'\r{prefix} |{bar}| {percent:.1f}% {suffix}', end='', flush=True)
    
    if current == total:
        print()  # Новая строка в конце
