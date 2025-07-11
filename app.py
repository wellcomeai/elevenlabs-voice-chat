"""
Улучшенная версия обработки аудио для лучшего распознавания речи
"""

import asyncio
import json
import logging
import aiohttp
import websockets
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
import base64
import io
import tempfile
import os

# Настройка более детального логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# API ключи (рекомендуется вынести в переменные окружения)
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "sk_ad652dd64291b883f60472d7719ba49e82b6a43bbe4f3506")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "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")

class VoiceAssistantHandler:
    """Улучшенный обработчик голосового ассистента"""
    
    def __init__(self):
        self.conversation_history = []
    
    async def speech_to_text(self, audio_data):
        """Улучшенное преобразование речи в текст"""
        try:
            logger.info(f"Получены аудио данные размером: {len(audio_data)} байт")
            
            # Проверяем минимальный размер аудио
            if len(audio_data) < 1000:  # Менее 1KB
                logger.warning("Аудио слишком короткое")
                return "Запись слишком короткая. Попробуйте говорить дольше."
            
            # Создаем временный файл для аудио
            with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as temp_file:
                temp_file.write(audio_data)
                temp_file_path = temp_file.name
            
            try:
                url = "https://api.elevenlabs.io/v1/speech-to-text"
                
                # Множественные попытки с разными параметрами
                stt_configs = [
                    {'model_id': 'eleven_english_sts_v2'},
                    {'model_id': 'eleven_multilingual_sts_v2'},
                    {'model_id': 'eleven_turbo_v2_5'}
                ]
                
                for config in stt_configs:
                    try:
                        logger.info(f"Пробуем STT с моделью: {config['model_id']}")
                        
                        # Подготавливаем данные
                        data = aiohttp.FormData()
                        
                        # Читаем файл для отправки
                        with open(temp_file_path, 'rb') as f:
                            data.add_field(
                                'audio', 
                                f.read(), 
                                filename='audio.webm', 
                                content_type='audio/webm'
                            )
                        
                        # Добавляем параметры модели
                        for key, value in config.items():
                            data.add_field(key, value)
                        
                        headers = {
                            'xi-api-key': ELEVENLABS_API_KEY
                        }
                        
                        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                            async with session.post(url, data=data, headers=headers) as response:
                                logger.info(f"STT ответ: {response.status}")
                                
                                if response.status == 200:
                                    result = await response.json()
                                    transcript = result.get('text', '').strip()
                                    
                                    if transcript and len(transcript) > 1:
                                        logger.info(f"STT успешно: {transcript}")
                                        return transcript
                                    else:
                                        logger.warning(f"Пустая транскрипция с моделью {config['model_id']}")
                                else:
                                    error_text = await response.text()
                                    logger.error(f"STT ошибка {response.status} с моделью {config['model_id']}: {error_text}")
                    
                    except Exception as model_error:
                        logger.error(f"Ошибка с моделью {config['model_id']}: {model_error}")
                        continue
                
                # Если все модели не сработали
                return "Не удалось распознать речь. Попробуйте говорить четче и громче."
                
            finally:
                # Удаляем временный файл
                try:
                    os.unlink(temp_file_path)
                except:
                    pass
                        
        except Exception as e:
            logger.error(f"STT общая ошибка: {e}")
            return "Ошибка распознавания речи. Проверьте микрофон."
    
    async def generate_response(self, user_text):
        """Генерация ответа с улучшенной обработкой ошибок"""
        try:
            if not openai_client:
                return "Извините, сервис временно недоступен."
            
            logger.info(f"Генерируем ответ для: {user_text}")
            
            # Добавляем сообщение пользователя
            self.conversation_history.append({
                "role": "user",
                "content": user_text
            })
            
            # Ограничиваем историю
            if len(self.conversation_history) > 10:
                self.conversation_history = self.conversation_history[-10:]
            
            # Подготавливаем сообщения
            messages = [
                {"role": "system", "content": ASSISTANT_CONFIG["system_prompt"]}
            ] + self.conversation_history
            
            # Запрос к OpenAI с timeout
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                max_tokens=150,
                temperature=0.7,
                timeout=15
            )
            
            assistant_response = response.choices[0].message.content
            
            # Добавляем ответ в историю
            self.conversation_history.append({
                "role": "assistant", 
                "content": assistant_response
            })
            
            logger.info(f"LLM ответ: {assistant_response}")
            return assistant_response
            
        except Exception as e:
            logger.error(f"LLM ошибка: {e}")
            return "Извините, произошла ошибка. Попробуйте еще раз."
    
    async def text_to_speech_stream(self, text, websocket):
        """Улучшенный TTS с обработкой ошибок"""
        try:
            logger.info(f"Начинаем TTS для текста: {text[:50]}...")
            
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{ASSISTANT_CONFIG['voice_id']}/stream"
            
            headers = {
                'xi-api-key': ELEVENLABS_API_KEY,
                'Content-Type': 'application/json'
            }
            
            payload = {
                "text": text,
                "model_id": ASSISTANT_CONFIG["model_id"],
                "voice_settings": ASSISTANT_CONFIG["voice_settings"],
                "optimize_streaming_latency": 2,  # Более консервативная настройка
                "output_format": "mp3_44100_128"  # Явно указываем формат
            }
            
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as session:
                async with session.post(url, json=payload, headers=headers) as response:
                    if response.status == 200:
                        # Сигнализируем начало
                        await websocket.send_json({
                            "type": "tts_start",
                            "text": text
                        })
                        
                        chunk_count = 0
                        # Читаем поток по чанкам
                        async for chunk in response.content.iter_chunked(2048):  # Увеличили размер чанка
                            if chunk:
                                chunk_count += 1
                                audio_b64 = base64.b64encode(chunk).decode('utf-8')
                                await websocket.send_json({
                                    "type": "audio_chunk",
                                    "audio": audio_b64,
                                    "chunk_id": chunk_count
                                })
                        
                        await websocket.send_json({
                            "type": "tts_end",
                            "total_chunks": chunk_count
                        })
                        
                        logger.info(f"TTS завершен. Отправлено {chunk_count} чанков")
                    else:
                        error_text = await response.text()
                        logger.error(f"TTS ошибка {response.status}: {error_text}")
                        await websocket.send_json({
                            "type": "error",
                            "message": "Ошибка синтеза речи"
                        })
                        
        except Exception as e:
            logger.error(f"TTS исключение: {e}")
            await websocket.send_json({
                "type": "error",
                "message": "Ошибка при озвучивании"
            })

# Инициализация OpenAI
try:
    openai_client = OpenAI(
        api_key=OPENAI_API_KEY,
        timeout=30.0,
        max_retries=2
    )
    logger.info("OpenAI клиент инициализирован")
except Exception as e:
    logger.error(f"Ошибка инициализации OpenAI: {e}")
    openai_client = None

# Конфигурация ассистента
ASSISTANT_CONFIG = {
    "name": "Алиса",
    "voice_id": "JBFqnCBsd6RMkjVDRZzb",  # Josh voice
    "model_id": "eleven_flash_v2_5",
    "system_prompt": """Ты - дружелюбный голосовой ассистент по имени Алиса. 

Твоя личность:
- Говори естественно и живо, как хороший друг
- Будь полезной и информативной  
- Отвечай кратко (1-2 предложения максимум)
- Проявляй эмоции и энтузиазм
- Будь позитивной и поддерживающей

Стиль общения:
- Используй простые слова
- Говори по существу
- При сложных вопросах предлагай разбить на части
- Не бойся переспрашивать если что-то неясно

Помни: твои ответы будут озвучены, поэтому говори так, чтобы было приятно слушать!""",
    "voice_settings": {
        "stability": 0.5,
        "similarity_boost": 0.8,
        "style": 0.2,
        "use_speaker_boost": True
    }
}
