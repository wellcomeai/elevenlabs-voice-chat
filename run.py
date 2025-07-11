#!/usr/bin/env python3
"""
Простой скрипт для запуска минимальной версии Voice Assistant
"""

import uvicorn
import sys
import os
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def check_environment():
    """Проверка переменных окружения"""
    print("🔍 Проверка конфигурации...")
    
    issues = []
    
    # Проверка API ключей
    elevenlabs_key = os.getenv("ELEVENLABS_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")
    
    if not elevenlabs_key or elevenlabs_key == "your_elevenlabs_key":
        issues.append("❌ ELEVENLABS_API_KEY не установлен")
        print("⚠️  Установите переменную окружения: export ELEVENLABS_API_KEY=your_key")
    else:
        print("✅ ElevenLabs API ключ найден")
    
    if not openai_key or openai_key == "your_openai_key":
        issues.append("❌ OPENAI_API_KEY не установлен")
        print("⚠️  Установите переменную окружения: export OPENAI_API_KEY=your_key")
    else:
        print("✅ OpenAI API ключ найден")
    
    # Проверка Python версии
    if sys.version_info < (3, 8):
        issues.append("❌ Требуется Python 3.8 или выше")
    else:
        print(f"✅ Python версия: {sys.version}")
    
    return issues

def main():
    """Основная функция запуска"""
    print("🚀 Запуск Voice Assistant - Минимальная версия")
    print("=" * 50)
    
    # Проверка окружения
    issues = check_environment()
    
    if issues:
        print("\n❌ Обнаружены проблемы:")
        for issue in issues:
            print(f"   {issue}")
        print("\n💡 Для работы нужны API ключи:")
        print("   1. ElevenLabs API Key: https://elevenlabs.io/")
        print("   2. OpenAI API Key: https://platform.openai.com/")
        print("\n📝 Установка переменных окружения:")
        print("   export ELEVENLABS_API_KEY=your_elevenlabs_key")
        print("   export OPENAI_API_KEY=your_openai_key")
        print("\n⚠️  БЕЗ КЛЮЧЕЙ приложение будет работать с ошибками!")
        
        response = input("\nПродолжить запуск? (y/N): ")
        if response.lower() != 'y':
            return sys.exit(1)
    
    print("\n📋 Конфигурация:")
    print("   - Порт: 8000")
    print("   - Хост: 0.0.0.0")
    print("   - Режим: Production")
    
    print("\n🔗 После запуска откройте:")
    print("   - http://localhost:8000")
    print("   - http://127.0.0.1:8000")
    
    print("\n🎯 Использование:")
    print("   1. Нажмите на синюю кнопку с микрофоном")
    print("   2. Говорите четко и громко")
    print("   3. Нажмите еще раз для остановки записи")
    print("   4. Ждите ответа ассистента")
    
    print("\n" + "=" * 50)
    print("🎤 Сервер запускается...")
    
    try:
        uvicorn.run(
            "app:app",
            host="0.0.0.0", 
            port=8000,
            log_level="info",
            reload=False
        )
    except KeyboardInterrupt:
        print("\n👋 Сервер остановлен!")
    except Exception as e:
        print(f"\n❌ Ошибка запуска: {e}")
        print("\nПопробуйте:")
        print("1. Установить зависимости: pip install -r requirements.txt")
        print("2. Проверить что порт 8000 свободен")
        print("3. Запустить от имени администратора")
        sys.exit(1)

if __name__ == "__main__":
    main()
