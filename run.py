#!/usr/bin/env python3
"""
Улучшенный скрипт для запуска ElevenLabs Voice Assistant
с диагностикой и проверкой системы
"""

import uvicorn
import sys
import os
import asyncio
import aiohttp
import logging
from pathlib import Path

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def check_environment():
    """Проверка окружения и конфигурации"""
    print("🔍 Проверка системы...")
    
    issues = []
    
    # Проверка Python версии
    if sys.version_info < (3, 8):
        issues.append("❌ Требуется Python 3.8 или выше")
    else:
        print(f"✅ Python версия: {sys.version}")
    
    # Проверка файлов
    required_files = [
        'app.py',
        'static/index.html',
        'requirements.txt'
    ]
    
    for file_path in required_files:
        if not Path(file_path).exists():
            issues.append(f"❌ Отсутствует файл: {file_path}")
        else:
            print(f"✅ Файл найден: {file_path}")
    
    # Проверка переменных окружения
    env_keys = ['ELEVENLABS_API_KEY', 'OPENAI_API_KEY']
    for key in env_keys:
        if not os.getenv(key):
            print(f"⚠️  Переменная окружения {key} не задана (будет использовано значение по умолчанию)")
    
    # Проверка портов
    try:
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('127.0.0.1', 8000))
        if result == 0:
            issues.append("❌ Порт 8000 уже занят")
        else:
            print("✅ Порт 8000 свободен")
        sock.close()
    except Exception as e:
        print(f"⚠️  Не удалось проверить порт: {e}")
    
    return issues

async def test_api_connections():
    """Тестирование соединений с API"""
    print("\n🌐 Тестирование API соединений...")
    
    # Тест ElevenLabs
    try:
        elevenlabs_key = os.getenv("ELEVENLABS_API_KEY", "sk_ad652dd64291b883f60472d7719ba49e82b6a43bbe4f3506")
        headers = {'xi-api-key': elevenlabs_key}
        
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.get('https://api.elevenlabs.io/v1/voices', headers=headers) as response:
                if response.status == 200:
                    voices = await response.json()
                    print(f"✅ ElevenLabs API работает. Доступно голосов: {len(voices.get('voices', []))}")
                else:
                    print(f"❌ ElevenLabs API ошибка: {response.status}")
    except Exception as e:
        print(f"❌ Ошибка подключения к ElevenLabs: {e}")
    
    # Тест OpenAI
    try:
        from openai import OpenAI
        openai_key = os.getenv("OPENAI_API_KEY", "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")
        client = OpenAI(api_key=openai_key, timeout=10)
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Test"}],
            max_tokens=5
        )
        print("✅ OpenAI API работает")
    except Exception as e:
        print(f"❌ Ошибка подключения к OpenAI: {e}")

def print_troubleshooting():
    """Выводит советы по устранению проблем"""
    print("\n🔧 Советы по устранению проблем:")
    print("1. Проблемы с распознаванием речи:")
    print("   - Говорите четко и достаточно громко")
    print("   - Запись должна быть не менее 1 секунды")
    print("   - Проверьте разрешения браузера на микрофон")
    print("   - Попробуйте другой браузер (Chrome/Firefox)")
    print("   - Используйте HTTPS для лучшей работы WebRTC")
    
    print("\n2. Проблемы с API:")
    print("   - Проверьте API ключи в переменных окружения")
    print("   - Убедитесь что у вас есть кредиты на ElevenLabs")
    print("   - Проверьте лимиты запросов")
    
    print("\n3. Проблемы с подключением:")
    print("   - Проверьте интернет соединение")
    print("   - Отключите VPN если используете")
    print("   - Проверьте настройки файрволла")
    
    print("\n4. Улучшение качества:")
    print("   - Используйте внешний микрофон для лучшего качества")
    print("   - Минимизируйте фоновый шум")
    print("   - Говорите на расстоянии 15-30 см от микрофона")

def main():
    """Основная функция запуска с диагностикой"""
    print("🚀 Запуск ElevenLabs Voice Assistant (Улучшенная версия)")
    print("=" * 60)
    
    # Проверка окружения
    issues = check_environment()
    
    if issues:
        print("\n❌ Обнаружены проблемы:")
        for issue in issues:
            print(f"   {issue}")
        print("\nИсправьте проблемы перед запуском!")
        return sys.exit(1)
    
    # Тестирование API
    try:
        asyncio.run(test_api_connections())
    except Exception as e:
        print(f"⚠️  Ошибка при тестировании API: {e}")
    
    print("\n📋 Конфигурация:")
    print("   - Порт: 8000")
    print("   - Хост: 0.0.0.0 (доступен извне)")
    print("   - Голос: Josh (ElevenLabs)")
    print("   - LLM: GPT-4o-mini")
    print("   - TTS: ElevenLabs Flash v2.5")
    print("   - Улучшенная обработка аудио")
    print("   - Детальное логирование")
    
    print("\n🔗 Откройте в браузере:")
    print("   - http://localhost:8000")
    print("   - http://127.0.0.1:8000")
    if sys.platform == "win32":
        print("   - http://[IP_компьютера]:8000")
    
    print("\n💡 Горячие клавиши:")
    print("   - Пробел: Начать/остановить запись")
    print("   - Ctrl+C: Остановить сервер")
    
    print("\n🎯 Для лучшего качества:")
    print("   - Включите Debug режим в интерфейсе")
    print("   - Настройте подавление шума")
    print("   - Говорите четко и не спешите")
    
    print_troubleshooting()
    
    print("\n" + "=" * 60)
    print("🎤 Сервер запускается...")
    
    try:
        uvicorn.run(
            "app:app",
            host="0.0.0.0", 
            port=8000,
            log_level="info",
            reload=False,
            access_log=True
        )
    except KeyboardInterrupt:
        print("\n👋 Сервер остановлен!")
    except Exception as e:
        print(f"\n❌ Ошибка запуска: {e}")
        print("\nПопробуйте:")
        print("1. Перезапустить с sudo (Linux/Mac)")
        print("2. Запустить от имени администратора (Windows)")
        print("3. Изменить порт в коде")
        print("4. Проверить что установлены все зависимости")
        sys.exit(1)

if __name__ == "__main__":
    main()
