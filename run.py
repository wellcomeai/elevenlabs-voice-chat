#!/usr/bin/env python3
"""
Скрипт для запуска ElevenLabs Conversational AI Assistant
Проверяет конфигурацию и запускает сервер
"""

import os
import sys
import logging
import asyncio
import uvicorn
from pathlib import Path

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def check_environment():
    """Проверка переменных окружения и файлов"""
    print("🔍 Проверка конфигурации ElevenLabs AI Assistant...")
    
    issues = []
    warnings = []
    
    # Проверка API ключа
    elevenlabs_key = os.getenv("ELEVENLABS_API_KEY")
    if not elevenlabs_key:
        issues.append("❌ ELEVENLABS_API_KEY не установлен")
        print("💡 Получите API ключ на: https://elevenlabs.io/")
        print("💡 Установите: export ELEVENLABS_API_KEY=your_api_key")
    else:
        print("✅ ElevenLabs API ключ найден")
        
        # Проверяем длину ключа (примерная валидация)
        if len(elevenlabs_key) < 20:
            warnings.append("⚠️  API ключ кажется слишком коротким")
    
    # Проверка Agent ID (необязательный)
    agent_id = os.getenv("ELEVENLABS_AGENT_ID")
    if agent_id:
        print(f"✅ Agent ID настроен: {agent_id[:8]}...")
    else:
        warnings.append("⚠️  ELEVENLABS_AGENT_ID не установлен (будет использован публичный агент)")
    
    # Проверка Python версии
    if sys.version_info < (3, 8):
        issues.append("❌ Требуется Python 3.8 или выше")
    else:
        print(f"✅ Python версия: {sys.version.split()[0]}")
    
    # Проверка файлов
    required_files = ["app.py", "requirements.txt"]
    for file in required_files:
        if not Path(file).exists():
            issues.append(f"❌ Файл {file} не найден")
        else:
            print(f"✅ {file} найден")
    
    # Проверка index.html
    if not Path("index.html").exists():
        warnings.append("⚠️  index.html не найден (будет использован fallback)")
    else:
        print("✅ index.html найден")
    
    return issues, warnings

def print_setup_instructions():
    """Выводит инструкции по настройке"""
    print("\n" + "="*60)
    print("📋 ИНСТРУКЦИИ ПО НАСТРОЙКЕ")
    print("="*60)
    
    print("\n1️⃣ Получите ElevenLabs API ключ:")
    print("   • Зарегистрируйтесь на https://elevenlabs.io/")
    print("   • Перейдите в Profile Settings")
    print("   • Скопируйте API Key")
    
    print("\n2️⃣ Установите переменные окружения:")
    print("   Linux/Mac:")
    print("   export ELEVENLABS_API_KEY=your_api_key_here")
    print("   export ELEVENLABS_AGENT_ID=your_agent_id  # опционально")
    print("\n   Windows:")
    print("   set ELEVENLABS_API_KEY=your_api_key_here")
    print("   set ELEVENLABS_AGENT_ID=your_agent_id     # опционально")
    
    print("\n3️⃣ Создайте .env файл (альтернатива):")
    print("   ELEVENLABS_API_KEY=your_api_key_here")
    print("   ELEVENLABS_AGENT_ID=your_agent_id")
    
    print("\n4️⃣ Для создания собственного агента:")
    print("   • Войдите в ElevenLabs dashboard")
    print("   • Создайте Conversational AI Agent")
    print("   • Скопируйте Agent ID")
    
    print("\n5️⃣ Установите зависимости:")
    print("   pip install -r requirements.txt")

def test_imports():
    """Проверка импорта зависимостей"""
    print("\n🧪 Проверка зависимостей...")
    
    try:
        import fastapi
        print("✅ FastAPI")
    except ImportError:
        print("❌ FastAPI не установлен")
        return False
        
    try:
        import websockets
        print("✅ WebSockets")
    except ImportError:
        print("❌ WebSockets не установлен")
        return False
        
    try:
        import uvicorn
        print("✅ Uvicorn")
    except ImportError:
        print("❌ Uvicorn не установлен")
        return False
    
    return True

def create_env_file_template():
    """Создает шаблон .env файла"""
    env_template = """# ElevenLabs Conversational AI Configuration
# Скопируйте этот файл в .env и заполните своими значениями

# ОБЯЗАТЕЛЬНО: Ваш API ключ от ElevenLabs
ELEVENLABS_API_KEY=your_elevenlabs_api_key_here

# ОПЦИОНАЛЬНО: ID вашего агента (если не указан, будет использован публичный)
ELEVENLABS_AGENT_ID=your_agent_id_here

# Настройки сервера
PORT=8000
LOG_LEVEL=info
"""
    
    with open(".env.template", "w", encoding="utf-8") as f:
        f.write(env_template)
    
    print("✅ Создан файл .env.template")

def main():
    """Основная функция запуска"""
    print("🚀 ElevenLabs Conversational AI Assistant")
    print("=" * 50)
    
    # Проверка окружения
    issues, warnings = check_environment()
    
    # Выводим предупреждения
    if warnings:
        print("\n⚠️  Предупреждения:")
        for warning in warnings:
            print(f"   {warning}")
    
    # Если есть критические проблемы
    if issues:
        print("\n❌ Критические проблемы:")
        for issue in issues:
            print(f"   {issue}")
        
        print_setup_instructions()
        create_env_file_template()
        
        response = input("\n❓ Продолжить запуск несмотря на проблемы? (y/N): ")
        if response.lower() != 'y':
            print("👋 Исправьте проблемы и запустите снова")
            return sys.exit(1)
    
    # Проверка зависимостей
    if not test_imports():
        print("\n❌ Не все зависимости установлены")
        print("💡 Выполните: pip install -r requirements.txt")
        return sys.exit(1)
    
    # Загружаем .env если есть
    try:
        from dotenv import load_dotenv
        if Path(".env").exists():
            load_dotenv()
            print("✅ Загружен .env файл")
    except ImportError:
        pass  # python-dotenv не обязательная зависимость
    
    print("\n📋 Конфигурация запуска:")
    print(f"   • Порт: {os.getenv('PORT', 8000)}")
    print(f"   • API ключ: {'✅ Настроен' if os.getenv('ELEVENLABS_API_KEY') else '❌ Не настроен'}")
    print(f"   • Agent ID: {'✅ Настроен' if os.getenv('ELEVENLABS_AGENT_ID') else '⚠️  Публичный агент'}")
    
    print("\n🔗 После запуска откройте:")
    port = os.getenv("PORT", 8000)
    print(f"   • http://localhost:{port}")
    print(f"   • http://127.0.0.1:{port}")
    
    print("\n🎯 Возможности:")
    print("   • Реальное время разговор с AI")
    print("   • Распознавание речи")
    print("   • Синтез речи")
    print("   • Voice Activity Detection")
    print("   • Обработка перебиваний")
    
    print("\n" + "=" * 50)
    print("🎤 Запуск сервера...")
    
    try:
        port = int(os.getenv("PORT", 8000))
        
        # Импортируем приложение
        from app import app
        
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=port,
            log_level="info",
            reload=False  # Отключаем reload для продакшена
        )
        
    except KeyboardInterrupt:
        print("\n👋 Сервер остановлен пользователем")
    except Exception as e:
        print(f"\n❌ Ошибка запуска: {e}")
        print("\n💡 Возможные решения:")
        print("   1. Проверьте что порт свободен")
        print("   2. Установите зависимости: pip install -r requirements.txt")
        print("   3. Проверьте права доступа")
        print("   4. Запустите от имени администратора")
        sys.exit(1)

if __name__ == "__main__":
    main()
