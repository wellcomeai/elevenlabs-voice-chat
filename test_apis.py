#!/usr/bin/env python3
"""
Скрипт для тестирования API соединений
Запустите перед основным приложением для проверки ключей
"""

import os
import asyncio
import aiohttp
import tempfile
import logging
from openai import OpenAI

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_elevenlabs_api():
    """Тестирование ElevenLabs API"""
    api_key = os.getenv("ELEVENLABS_API_KEY")
    
    if not api_key or api_key == "your_elevenlabs_key":
        print("❌ ElevenLabs API ключ не установлен")
        print("💡 Установите: export ELEVENLABS_API_KEY=your_key")
        return False
    
    try:
        print("🔍 Тестируем ElevenLabs API...")
        
        # Тест 1: Получение списка голосов
        url = "https://api.elevenlabs.io/v1/voices"
        headers = {'xi-api-key': api_key}
        
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    voices = await response.json()
                    print(f"✅ ElevenLabs API работает. Доступно голосов: {len(voices.get('voices', []))}")
                elif response.status == 401:
                    print("❌ ElevenLabs API: неверный ключ")
                    return False
                else:
                    print(f"❌ ElevenLabs API ошибка: {response.status}")
                    return False
        
        # Тест 2: Создание тестового TTS
        print("🔍 Тестируем TTS...")
        tts_url = "https://api.elevenlabs.io/v1/text-to-speech/JBFqnCBsd6RMkjVDRZzb"
        
        payload = {
            "text": "Тест",
            "model_id": "eleven_flash_v2_5",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.8
            }
        }
        
        headers['Content-Type'] = 'application/json'
        
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
            async with session.post(tts_url, json=payload, headers=headers) as response:
                if response.status == 200:
                    print("✅ TTS работает")
                elif response.status == 401:
                    print("❌ TTS: превышены лимиты или проблемы с оплатой")
                    return False
                else:
                    error_text = await response.text()
                    print(f"❌ TTS ошибка {response.status}: {error_text}")
                    return False
        
        # Тест 3: Создание тестового STT файла
        print("🔍 Тестируем STT...")
        
        # Создаем минимальный WAV файл (тишина)
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
            # Простейший WAV заголовок + 1 секунда тишины
            wav_header = b'RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00'
            temp_file.write(wav_header + b'\x00' * 8000)  # 1 сек тишины при 8kHz
            temp_file_path = temp_file.name
        
        try:
            stt_url = "https://api.elevenlabs.io/v1/speech-to-text"
            headers = {'xi-api-key': api_key}  # Убираем Content-Type для FormData
            
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                with open(temp_file_path, 'rb') as audio_file:
                    audio_content = audio_file.read()
                
                data = aiohttp.FormData()
                data.add_field('audio', audio_content, filename='test.wav', content_type='audio/wav')
                data.add_field('model_id', 'eleven_multilingual_sts_v2')
                
                async with session.post(stt_url, data=data, headers=headers) as response:
                    if response.status == 200:
                        result = await response.json()
                        print("✅ STT работает")
                    elif response.status == 400:
                        print("⚠️  STT: тестовый файл не подходит (это нормально)")
                    elif response.status == 401:
                        print("❌ STT: превышены лимиты или проблемы с аккаунтом")
                        return False
                    else:
                        error_text = await response.text()
                        print(f"❌ STT ошибка {response.status}: {error_text}")
        
        finally:
            try:
                os.unlink(temp_file_path)
            except:
                pass
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка тестирования ElevenLabs: {e}")
        return False

def test_openai_api():
    """Тестирование OpenAI API"""
    api_key = os.getenv("OPENAI_API_KEY")
    
    if not api_key or api_key == "your_openai_key":
        print("❌ OpenAI API ключ не установлен")
        print("💡 Установите: export OPENAI_API_KEY=your_key")
        return False
    
    try:
        print("🔍 Тестируем OpenAI API...")
        
        client = OpenAI(api_key=api_key, timeout=10)
        
        # Тест 1: Получение списка моделей
        models = client.models.list()
        print("✅ OpenAI API: соединение установлено")
        
        # Тест 2: Простой запрос к GPT
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Скажи 'тест'"}],
            max_tokens=5,
            timeout=10
        )
        
        print("✅ OpenAI GPT работает")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка OpenAI API: {e}")
        return False

async def main():
    """Основная функция тестирования"""
    print("🧪 Тестирование API соединений")
    print("=" * 40)
    
    # Проверка переменных окружения
    print("📋 Проверка переменных окружения:")
    
    elevenlabs_key = os.getenv("ELEVENLABS_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")
    
    print(f"   ELEVENLABS_API_KEY: {'✅ Установлен' if elevenlabs_key and elevenlabs_key != 'your_elevenlabs_key' else '❌ Не установлен'}")
    print(f"   OPENAI_API_KEY: {'✅ Установлен' if openai_key and openai_key != 'your_openai_key' else '❌ Не установлен'}")
    
    print("\n🔍 Тестирование API...")
    
    # Тестируем ElevenLabs
    elevenlabs_ok = await test_elevenlabs_api()
    
    print()
    
    # Тестируем OpenAI
    openai_ok = test_openai_api()
    
    print("\n" + "=" * 40)
    print("📊 Результаты тестирования:")
    print(f"   ElevenLabs API: {'✅ OK' if elevenlabs_ok else '❌ ОШИБКА'}")
    print(f"   OpenAI API: {'✅ OK' if openai_ok else '❌ ОШИБКА'}")
    
    if elevenlabs_ok and openai_ok:
        print("\n🎉 Все API работают! Можно запускать основное приложение.")
        return True
    else:
        print("\n⚠️  Есть проблемы с API. Исправьте их перед запуском приложения.")
        print("\n💡 Получить ключи:")
        print("   - ElevenLabs: https://elevenlabs.io/")
        print("   - OpenAI: https://platform.openai.com/")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
