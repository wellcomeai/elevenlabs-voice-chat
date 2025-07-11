"""
ElevenLabs Voice Assistant MVP - Простой WebSocket сервер
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

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# API ключи (встроенные для MVP)
ELEVENLABS_API_KEY = "sk_ad652dd64291b883f60472d7719ba49e82b6a43bbe4f3506"
OPENAI_API_KEY = "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"

# Конфигурация ассистента (встроенная)
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

# Инициализация OpenAI клиента с обработкой ошибок
try:
    openai_client = OpenAI(
        api_key=OPENAI_API_KEY,
        timeout=30.0,
        max_retries=2
    )
    logger.info("OpenAI client initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize OpenAI client: {e}")
    openai_client = None

app = FastAPI(title="ElevenLabs Voice Assistant MVP")

# Подключаем статические файлы
app.mount("/static", StaticFiles(directory="static"), name="static")

class VoiceAssistantHandler:
    """Обработчик голосового ассистента"""
    
    def __init__(self):
        self.conversation_history = []
    
    async def speech_to_text(self, audio_data):
        """Преобразование речи в текст через ElevenLabs"""
        try:
            url = "https://api.elevenlabs.io/v1/speech-to-text"
            
            # Подготавливаем форму данных
            data = aiohttp.FormData()
            data.add_field('audio', audio_data, filename='audio.webm', content_type='audio/webm')
            data.add_field('model_id', 'scribe_v1')
            
            headers = {
                'xi-api-key': ELEVENLABS_API_KEY
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=data, headers=headers) as response:
                    if response.status == 200:
                        result = await response.json()
                        transcript = result.get('text', '').strip()
                        logger.info(f"STT result: {transcript}")
                        return transcript
                    else:
                        error_text = await response.text()
                        logger.error(f"STT error {response.status}: {error_text}")
                        return "Извините, не удалось распознать речь"
                        
        except Exception as e:
            logger.error(f"STT exception: {e}")
            return "Ошибка распознавания речи"
    
    async def generate_response(self, user_text):
        """Генерация ответа через OpenAI GPT"""
        try:
            # Проверяем доступность OpenAI клиента
            if not openai_client:
                return "Извините, сервис временно недоступен. Попробуйте позже."
            
            # Добавляем сообщение пользователя в историю
            self.conversation_history.append({
                "role": "user",
                "content": user_text
            })
            
            # Ограничиваем историю последними 10 сообщениями
            if len(self.conversation_history) > 10:
                self.conversation_history = self.conversation_history[-10:]
            
            # Подготавливаем сообщения для API
            messages = [
                {"role": "system", "content": ASSISTANT_CONFIG["system_prompt"]}
            ] + self.conversation_history
            
            # Запрос к OpenAI
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                max_tokens=150,
                temperature=0.7
            )
            
            assistant_response = response.choices[0].message.content
            
            # Добавляем ответ ассистента в историю
            self.conversation_history.append({
                "role": "assistant", 
                "content": assistant_response
            })
            
            logger.info(f"LLM response: {assistant_response}")
            return assistant_response
            
        except Exception as e:
            logger.error(f"LLM error: {e}")
            return "Извините, произошла ошибка при обработке вашего запроса"
    
    async def text_to_speech_stream(self, text, websocket):
        """Преобразование текста в речь через ElevenLabs с потоковой передачей"""
        try:
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{ASSISTANT_CONFIG['voice_id']}/stream"
            
            headers = {
                'xi-api-key': ELEVENLABS_API_KEY,
                'Content-Type': 'application/json'
            }
            
            payload = {
                "text": text,
                "model_id": ASSISTANT_CONFIG["model_id"],
                "voice_settings": ASSISTANT_CONFIG["voice_settings"],
                "optimize_streaming_latency": 3
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as response:
                    if response.status == 200:
                        # Отправляем начало TTS
                        await websocket.send_json({
                            "type": "tts_start",
                            "text": text
                        })
                        
                        # Читаем аудио поток и отправляем клиенту
                        async for chunk in response.content.iter_chunked(1024):
                            if chunk:
                                # Кодируем аудио в base64 и отправляем
                                audio_b64 = base64.b64encode(chunk).decode('utf-8')
                                await websocket.send_json({
                                    "type": "audio_chunk",
                                    "audio": audio_b64
                                })
                        
                        # Отправляем завершение TTS
                        await websocket.send_json({
                            "type": "tts_end"
                        })
                        
                        logger.info("TTS completed successfully")
                    else:
                        error_text = await response.text()
                        logger.error(f"TTS error {response.status}: {error_text}")
                        await websocket.send_json({
                            "type": "error",
                            "message": "Ошибка синтеза речи"
                        })
                        
        except Exception as e:
            logger.error(f"TTS exception: {e}")
            await websocket.send_json({
                "type": "error",
                "message": "Ошибка при озвучивании ответа"
            })

@app.get("/")
async def get_main_page():
    """Главная страница с виджетом"""
    try:
        with open("static/index.html", "r", encoding="utf-8") as f:
            html_content = f.read()
        return HTMLResponse(content=html_content)
    except FileNotFoundError:
        return HTMLResponse(content="<h1>Error: static/index.html not found</h1>", status_code=404)

@app.websocket("/ws/voice")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint для голосового взаимодействия"""
    await websocket.accept()
    logger.info("WebSocket соединение установлено")
    
    handler = VoiceAssistantHandler()
    
    try:
        while True:
            # Получаем сообщение от клиента
            message = await websocket.receive_json()
            
            if message["type"] == "audio_data":
                # Обрабатываем аудио данные
                try:
                    # Преобразуем массив в bytes
                    audio_bytes = bytes(message["data"])
                    
                    # STT - преобразование речи в текст
                    logger.info("Начинаем распознавание речи...")
                    transcript = await handler.speech_to_text(audio_bytes)
                    
                    if transcript and transcript.strip():
                        # Отправляем транскрипцию клиенту
                        await websocket.send_json({
                            "type": "transcription",
                            "text": transcript
                        })
                        
                        # Генерируем ответ через LLM
                        logger.info("Генерируем ответ...")
                        response = await handler.generate_response(transcript)
                        
                        # Отправляем текст ответа клиенту
                        await websocket.send_json({
                            "type": "response", 
                            "text": response
                        })
                        
                        # TTS - преобразование в речь с потоковой передачей
                        logger.info("Начинаем синтез речи...")
                        await handler.text_to_speech_stream(response, websocket)
                        
                        # Уведомляем о завершении обработки
                        await websocket.send_json({
                            "type": "processing_complete"
                        })
                    else:
                        await websocket.send_json({
                            "type": "error",
                            "message": "Не удалось распознать речь. Попробуйте еще раз."
                        })
                        
                except Exception as e:
                    logger.error(f"Ошибка обработки аудио: {e}")
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Ошибка обработки: {str(e)}"
                    })
            
    except WebSocketDisconnect:
        logger.info("WebSocket соединение закрыто")
    except Exception as e:
        logger.error(f"WebSocket ошибка: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": "Произошла ошибка сервера"
            })
        except:
            pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
