#!/usr/bin/env python3
"""
Скрипт запуска ElevenLabs Voice Chat
Проверяет конфигурацию и запускает сервер
"""

import os
import sys
import logging
from pathlib import Path

def check_environment():
    """Проверка окружения"""
    print("🔍 Проверка конфигурации...")
    
    issues = []
    warnings = []
    
    # Проверка Python версии
    if sys.version_info < (3, 8):
        issues.append("❌ Требуется Python 3.8 или выше")
    else:
        print(f"✅ Python {sys.version.split()[0]}")
    
    # Проверка API ключа
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key or api_key == "your_api_key_here":
        issues.append("❌ ELEVENLABS_API_KEY не установлен")
    else:
        print("✅ ElevenLabs API ключ найден")
        if len(api_key) < 20:
            warnings.append("⚠️ API ключ кажется слишком коротким")
    
    # Проверка Agent ID
    agent_id = os.getenv("ELEVENLABS_AGENT_ID")
    if agent_id:
        print(f"✅ Agent ID: {agent_id[:12]}...")
    else:
        warnings.append("⚠️ ELEVENLABS_AGENT_ID не установлен (будет использован по умолчанию)")
    
    # Проверка файлов
    required_files = ["app.py", "requirements.txt", "index.html"]
    for file in required_files:
        if Path(file).exists():
            print(f"✅ {file}")
        else:
            issues.append(f"❌ Файл {file} не найден")
    
    return issues, warnings

def check_dependencies():
    """Проверка зависимостей"""
    print("\n🧪 Проверка зависимостей...")
    
    missing = []
    
    try:
        import fastapi
        print("✅ FastAPI")
    except ImportError:
        missing.append("fastapi")
    
    try:
        import uvicorn
        print("✅ Uvicorn")
    except ImportError:
        missing.append("uvicorn")
    
    try:
        import websockets
        print("✅ WebSockets")
    except ImportError:
        missing.append("websockets")
    
    try:
        import aiohttp
        print("✅ Aiohttp")
    except ImportError:
        missing.append("aiohttp")
    
    return missing

def print_setup_instructions():
    """Инструкции по настройке"""
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
    print("\n   Windows:")
    print("   set ELEVENLABS_API_KEY=your_api_key_here")
    
    print("\n3️⃣ Или создайте .env файл:")
    print("   ELEVENLABS_API_KEY=your_api_key_here")
    print("   ELEVENLABS_AGENT_ID=your_agent_id")
    
    print("\n4️⃣ Установите зависимости:")
    print("   pip install -r requirements.txt")

def create_env_template():
    """Создание шаблона .env"""
    if not Path(".env.example").exists():
        env_content = """# ElevenLabs Voice Chat Configuration
ELEVENLABS_API_KEY=your_api_key_here
ELEVENLABS_AGENT_ID=agent_01jzwcew2ferttga9m1zcn3js1
PORT=8000
LOG_LEVEL=info
"""
        with open(".env.example", "w") as f:
            f.write(env_content)
        print("✅ Создан .env.example")

def main():
    """Основная функция"""
    print("🚀 ElevenLabs Voice Chat - Запуск")
    print("=" * 50)
    
    # Загружаем .env если есть
    try:
        from dotenv import load_dotenv
        if Path(".env").exists():
            load_dotenv()
            print("✅ Загружен .env файл")
    except ImportError:
        pass
    
    # Проверка окружения
    issues, warnings = check_environment()
    
    # Проверка зависимостей
    missing_deps = check_dependencies()
    
    # Создаем шаблон .env
    create_env_template()
    
    # Выводим предупреждения
    if warnings:
        print("\n⚠️ Предупреждения:")
        for warning in warnings:
            print(f"   {warning}")
    
    # Проверяем критические проблемы
    if issues or missing_deps:
        print("\n❌ Критические проблемы:")
        for issue in issues:
            print(f"   {issue}")
        
        if missing_deps:
            print(f"   ❌ Не установлены: {', '.join(missing_deps)}")
            print("   💡 Выполните: pip install -r requirements.txt")
        
        print_setup_instructions()
        
        response = input("\n❓ Продолжить запуск? (y/N): ")
        if response.lower() != 'y':
            print("👋 Исправьте проблемы и запустите снова")
            return sys.exit(1)
    
    # Показываем конфигурацию
    print("\n📋 Конфигурация:")
    port = os.getenv("PORT", 8000)
    print(f"   • Порт: {port}")
    print(f"   • API ключ: {'✅ Настроен' if os.getenv('ELEVENLABS_API_KEY') else '❌ Не настроен'}")
    print(f"   • Agent ID: {os.getenv('ELEVENLABS_AGENT_ID', 'По умолчанию')}")
    
    print(f"\n🔗 После запуска откройте:")
    print(f"   • http://localhost:{port}")
    print(f"   • http://127.0.0.1:{port}")
    
    print("\n🎯 Возможности:")
    print("   • Голосовой разговор с AI")
    print("   • Распознавание речи в реальном времени")
    print("   • Синтез речи")
    print("   • Voice Activity Detection")
    print("   • Обработка перебиваний")
    
    print("\n" + "=" * 50)
    print("🎤 Запуск сервера...")
    
    try:
        # Импортируем и запускаем приложение
        from app import main as run_app
        run_app()
        
    except KeyboardInterrupt:
        print("\n👋 Сервер остановлен")
    except Exception as e:
        print(f"\n❌ Ошибка запуска: {e}")
        print("\n💡 Возможные решения:")
        print("   1. Проверьте API ключ")
        print("   2. Убедитесь что порт свободен")
        print("   3. Установите зависимости: pip install -r requirements.txt")
        sys.exit(1)

if __name__ == "__main__":
    main()
