#!/usr/bin/env python3
"""
Скрипт запуска ElevenLabs Conversational AI с диагностикой
Проверяет окружение и запускает основное приложение
"""

import sys
import asyncio
import argparse
from pathlib import Path

# Добавляем текущую директорию в путь
sys.path.insert(0, str(Path(__file__).parent))

from config import Config
from utils import (
    setup_logging, print_banner, check_dependencies, 
    validate_environment, print_system_info
)
import main

def parse_arguments():
    """Парсинг аргументов командной строки"""
    parser = argparse.ArgumentParser(
        description="ElevenLabs Conversational AI - Python CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  python run.py                    # Обычный запуск
  python run.py --debug            # Режим отладки
  python run.py --check            # Только проверка окружения
  python run.py --info             # Информация о системе
  python run.py --setup            # Создание .env шаблона
        """
    )
    
    parser.add_argument(
        "--debug", 
        action="store_true", 
        help="Включить режим отладки"
    )
    
    parser.add_argument(
        "--check", 
        action="store_true", 
        help="Только проверка окружения (без запуска)"
    )
    
    parser.add_argument(
        "--info", 
        action="store_true", 
        help="Показать информацию о системе"
    )
    
    parser.add_argument(
        "--setup", 
        action="store_true", 
        help="Создать .env шаблон"
    )
    
    parser.add_argument(
        "--log-level", 
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Уровень логирования"
    )
    
    parser.add_argument(
        "--log-file", 
        type=str,
        help="Файл для сохранения логов"
    )
    
    return parser.parse_args()

def check_python_version():
    """Проверка версии Python"""
    if sys.version_info < (3, 8):
        print("❌ Ошибка: Требуется Python 3.8 или выше")
        print(f"   Текущая версия: {sys.version}")
        print("   Обновите Python: https://www.python.org/downloads/")
        return False
    
    print(f"✅ Python {sys.version.split()[0]}")
    return True

def setup_environment(args):
    """Настройка окружения"""
    
    # Определяем уровень логирования
    if args.debug:
        log_level = "DEBUG"
    else:
        log_level = args.log_level
    
    # Настраиваем логирование
    setup_logging(log_level=log_level, log_file=args.log_file)
    
    return True

def create_env_template():
    """Создание .env шаблона"""
    try:
        config = Config()
        
        if Path(".env").exists():
            response = input("📄 Файл .env уже существует. Перезаписать? (y/N): ")
            if response.lower() != 'y':
                print("❌ Отменено")
                return False
        
        # Создаем .env файл
        env_content = config.create_env_template()
        
        with open(".env", "w") as f:
            f.write(env_content)
        
        print("✅ Файл .env создан")
        print("💡 Отредактируйте .env файл и установите ELEVENLABS_API_KEY")
        print("   Получите ключ на: https://elevenlabs.io/")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка создания .env: {e}")
        return False

async def run_diagnostics():
    """Запуск полной диагностики"""
    print("🔍 Полная диагностика системы:")
    print("=" * 50)
    
    # Проверка Python
    if not check_python_version():
        return False
    
    # Проверка зависимостей  
    if not check_dependencies():
        return False
    
    # Проверка окружения
    if not validate_environment():
        return False
    
    # Проверка конфигурации
    config = Config()
    if not config.validate():
        print("\n❌ Конфигурация некорректна")
        print("💡 Создайте .env файл: python run.py --setup")
        return False
    
    config.print_config()
    
    # Проверка подключения к ElevenLabs
    print("\n🔗 Проверка подключения к ElevenLabs...")
    
    try:
        from websocket_client import ElevenLabsWebSocketClient
        
        client = ElevenLabsWebSocketClient(
            api_key=config.ELEVENLABS_API_KEY,
            agent_id=config.ELEVENLABS_AGENT_ID
        )
        
        result = await client.connect()
        
        if result:
            print("✅ Подключение к ElevenLabs успешно")
            stats = client.get_statistics()
            print(f"   Conversation ID: {stats['conversation_id']}")
            await client.disconnect()
        else:
            print("❌ Ошибка подключения к ElevenLabs")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка тестирования ElevenLabs: {e}")
        return False
    
    print("\n🎉 Все проверки пройдены! Система готова к работе.")
    return True

async def main_async():
    """Асинхронная главная функция"""
    
    # Парсинг аргументов
    args = parse_arguments()
    
    # Баннер
    if not args.check and not args.setup:
        print_banner()
    
    # Настройка окружения
    setup_environment(args)
    
    # Команды без запуска приложения
    if args.setup:
        return 0 if create_env_template() else 1
    
    if args.info:
        print_system_info()
        return 0
    
    if args.check:
        result = await run_diagnostics()
        return 0 if result else 1
    
    # Быстрая проверка перед запуском
    print("🔍 Предварительная проверка...")
    
    if not check_python_version():
        return 1
    
    if not check_dependencies():
        print("💡 Установите зависимости: pip install -r requirements.txt")
        return 1
    
    # Проверка конфигурации
    config = Config()
    if not config.validate():
        print("\n❌ Конфигурация некорректна")
        print("💡 Создайте .env файл: python run.py --setup")
        print("💡 Или установите переменную: export ELEVENLABS_API_KEY=your_key")
        return 1
    
    print("✅ Проверки пройдены")
    
    # Запуск основного приложения
    try:
        print("\n🚀 Запуск голосового ассистента...")
        return await main.main()
        
    except KeyboardInterrupt:
        print("\n👋 Программа прервана пользователем")
        return 0
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        return 1

def main():
    """Точка входа"""
    try:
        return asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\n👋 До свидания!")
        return 0
    except Exception as e:
        print(f"\n❌ Неожиданная ошибка: {e}")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
