"""
ElevenLabs Voice Assistant - Минимальная рабочая версия
Исправления на основе анализа логов и widget.js
"""

import asyncio
import json
import logging
import aiohttp
import websockets
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
import base64
import tempfile
import os
from pathlib import Path
import uuid

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# API ключи из переменных окружения - ИСПРАВЛЕНЫ
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "your_elevenlabs_key")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "your_openai_key")

# ВАЖНО: Используйте ваши реальные ключи!
if ELEVENLABS_API_KEY == "your_elevenlabs_key" or not ELEVENLABS_API_KEY:
    logger.warning("⚠️  ELEVENLABS_API_KEY не установлен! Установите переменную окружения.")
    logger.warning("⚠️  STT функция будет работать с ошибками!")

if OPENAI_API_KEY == "your_openai_key" or not OPENAI_API_KEY:
    logger.warning("⚠️  OPENAI_API_KEY не установлен! Установите переменную окружения.")
    logger.warning("⚠️  LLM функция будет работать с ошибками!")

# Конфигурация ассистента
ASSISTANT_CONFIG = {
    "name": "Алиса",
    "voice_id": "JBFqnCBsd6RMkjVDRZzb",  # Josh voice
    "model_id": "eleven_flash_v2_5",
    "system_prompt": """Ты - дружелюбный голосовой ассистент по имени Алиса. 
Отвечай кратко (1-2 предложения максимум), естественно и по существу.""",
    "voice_settings": {
        "stability": 0.5,
        "similarity_boost": 0.8,
        "style": 0.2,
        "use_speaker_boost": True
    }
}

# Инициализация OpenAI клиента с проверкой
try:
    openai_client = OpenAI(
        api_key=OPENAI_API_KEY,
        timeout=30.0,
        max_retries=2
    )
    # Тест соединения
    test_response = openai_client.models.list()
    logger.info("✅ OpenAI клиент инициализирован и протестирован")
except Exception as e:
    logger.error(f"❌ Ошибка инициализации OpenAI: {e}")
    openai_client = None

# Создание FastAPI приложения
app = FastAPI(
    title="ElevenLabs Voice Assistant", 
    description="Минимальная рабочая версия голосового ассистента",
    version="2.1.0"
)

# HTML контент - ОБНОВЛЕННЫЙ с лучшими практиками из widget.js
HTML_CONTENT = """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Voice Assistant - Минимальная версия</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        .container {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 24px;
            padding: 40px;
            max-width: 500px;
            width: 100%;
            text-align: center;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.1);
        }
        .title {
            font-size: 28px;
            font-weight: 700;
            color: #2d3748;
            margin-bottom: 20px;
        }
        .voice-button {
            width: 120px;
            height: 120px;
            border-radius: 50%;
            border: none;
            background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
            color: white;
            font-size: 28px;
            cursor: pointer;
            transition: all 0.3s ease;
            margin: 20px auto;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 10px 30px rgba(79, 70, 229, 0.3);
        }
        .voice-button:hover { transform: scale(1.05); }
        .voice-button.recording {
            background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
            animation: pulse 1.5s infinite;
        }
        .voice-button.processing {
            background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
            animation: spin 1s linear infinite;
        }
        .voice-button.speaking {
            background: linear-gradient(135deg, #10b981 0%, #059669 100%);
            animation: wave 1s ease-in-out infinite;
        }
        @keyframes pulse { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.1); } }
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        @keyframes wave { 0%, 100% { transform: scale(1); } 25% { transform: scale(1.05); } 75% { transform: scale(0.95); } }
        .status { margin-top: 20px; font-size: 16px; color: #475569; }
        .conversation {
            margin-top: 30px;
            padding: 20px;
            background: rgba(248, 250, 252, 0.8);
            border-radius: 16px;
            text-align: left;
            max-height: 300px;
            overflow-y: auto;
        }
        .message {
            margin-bottom: 10px;
            padding: 10px;
            border-radius: 8px;
            line-height: 1.4;
        }
        .message.user {
            background: #e0e7ff;
            color: #3730a3;
            margin-left: 20px;
        }
        .message.assistant {
            background: #f0fdf4;
            color: #166534;
            margin-right: 20px;
        }
        .error {
            color: #ef4444;
            background: rgba(254, 226, 226, 0.8);
            padding: 10px;
            border-radius: 8px;
            margin-top: 15px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1 class="title">🎤 Голосовой Ассистент</h1>
        <p>Минимальная рабочая версия</p>
        
        <button class="voice-button" id="voiceButton">
            <span id="buttonIcon">🎤</span>
        </button>
        
        <div class="status" id="statusText">Нажмите для начала разговора</div>
        
        <div class="conversation" id="conversation">
            <div style="text-align: center; color: #94a3b8; font-style: italic;">
                История разговора появится здесь...
            </div>
        </div>
        
        <div class="error" id="errorMsg" style="display: none;"></div>
    </div>

    <script>
        class VoiceAssistant {
            constructor() {
                this.ws = null;
                this.mediaRecorder = null;
                this.audioChunks = [];
                this.isRecording = false;
                this.isProcessing = false;
                this.isSpeaking = false;
                this.audioQueue = [];
                this.currentAudio = null;
                
                this.initElements();
                this.connect();
                this.bindEvents();
            }
            
            initElements() {
                this.button = document.getElementById('voiceButton');
                this.icon = document.getElementById('buttonIcon');
                this.status = document.getElementById('statusText');
                this.conversation = document.getElementById('conversation');
                this.errorMsg = document.getElementById('errorMsg');
            }
            
            connect() {
                const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                const wsUrl = `${protocol}//${window.location.host}/ws/voice`;
                
                this.ws = new WebSocket(wsUrl);
                
                this.ws.onopen = () => {
                    console.log('WebSocket соединение установлено');
                    this.status.textContent = 'Готов! Нажмите для записи';
                    this.hideError();
                };
                
                this.ws.onmessage = (event) => {
                    this.handleMessage(JSON.parse(event.data));
                };
                
                this.ws.onclose = () => {
                    console.log('WebSocket соединение закрыто');
                    this.status.textContent = 'Соединение потеряно';
                    this.showError('Соединение с сервером потеряно. Обновите страницу.');
                };
                
                this.ws.onerror = (error) => {
                    console.error('WebSocket ошибка:', error);
                    this.showError('Ошибка соединения с сервером');
                };
            }
            
            bindEvents() {
                this.button.addEventListener('click', () => {
                    if (this.isSpeaking) {
                        this.stopSpeaking();
                    } else if (this.isRecording) {
                        this.stopRecording();
                    } else {
                        this.startRecording();
                    }
                });
            }
            
            async startRecording() {
                try {
                    this.hideError();
                    
                    const stream = await navigator.mediaDevices.getUserMedia({
                        audio: {
                            echoCancellation: true,
                            noiseSuppression: true,
                            autoGainControl: true,
                            sampleRate: 44100
                        }
                    });

                    this.mediaRecorder = new MediaRecorder(stream, {
                        mimeType: 'audio/webm;codecs=opus'
                    });

                    this.audioChunks = [];

                    this.mediaRecorder.ondataavailable = (event) => {
                        if (event.data.size > 0) {
                            this.audioChunks.push(event.data);
                        }
                    };

                    this.mediaRecorder.onstop = () => {
                        stream.getTracks().forEach(track => track.stop());
                        this.processAudio();
                    };

                    this.mediaRecorder.start();
                    this.isRecording = true;
                    this.updateUI();
                    this.status.textContent = 'Говорите... Нажмите для остановки';

                } catch (error) {
                    this.showError('Не удалось получить доступ к микрофону: ' + error.message);
                }
            }
            
            stopRecording() {
                if (this.mediaRecorder && this.isRecording) {
                    this.mediaRecorder.stop();
                    this.isRecording = false;
                    this.isProcessing = true;
                    this.updateUI();
                    this.status.textContent = 'Обрабатываю...';
                }
            }
            
            async processAudio() {
                try {
                    const audioBlob = new Blob(this.audioChunks, { type: 'audio/webm' });
                    
                    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                        const reader = new FileReader();
                        reader.onload = () => {
                            const audioData = new Uint8Array(reader.result);
                            this.ws.send(JSON.stringify({
                                type: 'audio_data',
                                data: Array.from(audioData)
                            }));
                        };
                        reader.readAsArrayBuffer(audioBlob);
                    }

                } catch (error) {
                    this.showError('Ошибка обработки аудио: ' + error.message);
                    this.resetState();
                }
            }
            
            handleMessage(data) {
                console.log('Получено:', data);

                switch (data.type) {
                    case 'transcription':
                        this.addMessage('user', data.text);
                        break;

                    case 'response':
                        this.addMessage('assistant', data.text);
                        break;

                    case 'tts_start':
                        this.isSpeaking = true;
                        this.updateUI();
                        this.status.textContent = 'Говорю... Нажмите для прерывания';
                        this.audioQueue = [];
                        break;

                    case 'audio_chunk':
                        this.audioQueue.push(data.audio);
                        if (this.audioQueue.length === 1) {
                            this.playAudioQueue();
                        }
                        break;

                    case 'tts_end':
                        setTimeout(() => {
                            if (!this.audioQueue.length) {
                                this.resetState();
                            }
                        }, 1000);
                        break;

                    case 'processing_complete':
                        this.isProcessing = false;
                        this.updateUI();
                        break;

                    case 'error':
                        this.showError(data.message);
                        this.resetState();
                        break;
                }
            }
            
            async playAudioQueue() {
                if (!this.audioQueue.length || !this.isSpeaking) return;

                try {
                    const audioData = this.audioQueue.shift();
                    const audioBlob = new Blob([
                        Uint8Array.from(atob(audioData), c => c.charCodeAt(0))
                    ], { type: 'audio/mpeg' });

                    const audioUrl = URL.createObjectURL(audioBlob);
                    this.currentAudio = new Audio(audioUrl);

                    this.currentAudio.onended = () => {
                        URL.revokeObjectURL(audioUrl);
                        if (this.audioQueue.length > 0) {
                            this.playAudioQueue();
                        } else if (!this.isSpeaking) {
                            this.resetState();
                        }
                    };

                    this.currentAudio.onerror = () => {
                        URL.revokeObjectURL(audioUrl);
                        console.error('Ошибка воспроизведения аудио');
                        this.playAudioQueue();
                    };

                    await this.currentAudio.play();

                } catch (error) {
                    console.error('Ошибка воспроизведения:', error);
                    this.playAudioQueue();
                }
            }
            
            stopSpeaking() {
                this.isSpeaking = false;
                this.audioQueue = [];
                
                if (this.currentAudio) {
                    this.currentAudio.pause();
                    this.currentAudio.currentTime = 0;
                }
                
                this.resetState();
            }
            
            addMessage(role, text) {
                if (role === 'user' && this.conversation.innerHTML.includes('История разговора')) {
                    this.conversation.innerHTML = '';
                }

                const messageDiv = document.createElement('div');
                messageDiv.className = `message ${role}`;
                messageDiv.innerHTML = `<strong>${role === 'user' ? 'Вы:' : 'Ассистент:'}</strong> ${text}`;
                
                this.conversation.appendChild(messageDiv);
                this.conversation.scrollTop = this.conversation.scrollHeight;
            }
            
            updateUI() {
                this.button.className = 'voice-button';

                if (this.isRecording) {
                    this.button.classList.add('recording');
                    this.icon.textContent = '⏹️';
                } else if (this.isProcessing) {
                    this.button.classList.add('processing');
                    this.icon.textContent = '⚙️';
                } else if (this.isSpeaking) {
                    this.button.classList.add('speaking');
                    this.icon.textContent = '🔊';
                } else {
                    this.icon.textContent = '🎤';
                }
            }
            
            resetState() {
                this.isRecording = false;
                this.isProcessing = false;
                this.isSpeaking = false;
                this.updateUI();
                this.status.textContent = 'Готов! Нажмите для записи';
            }
            
            showError(message) {
                this.errorMsg.textContent = message;
                this.errorMsg.style.display = 'block';
            }
            
            hideError() {
                this.errorMsg.style.display = 'none';
            }
        }

        document.addEventListener('DOMContentLoaded', () => {
            new VoiceAssistant();
        });
    </script>
</body>
</html>"""

class VoiceAssistantHandler:
    """Обработчик голосового ассистента - ИСПРАВЛЕННАЯ версия"""
    
    def __init__(self):
        self.conversation_history = []
        self.session_id = str(uuid.uuid4())
    
    async def speech_to_text(self, audio_data):
        """Преобразование речи в текст через ElevenLabs - ИСПРАВЛЕНО"""
        try:
            logger.info(f"[STT] Обработка аудио: {len(audio_data)} байт")
            
            if len(audio_data) < 1000:
                logger.warning("[STT] Аудио слишком короткое")
                return "Запись слишком короткая. Попробуйте говорить дольше."
            
            # ИСПРАВЛЕНИЕ: Правильная работа с временным файлом
            temp_file_path = None
            try:
                # Создаем временный файл и записываем данные
                with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as temp_file:
                    temp_file.write(audio_data)
                    temp_file_path = temp_file.name
                
                logger.info(f"[STT] Временный файл создан: {temp_file_path}")
                
                # Проверяем что файл существует и не пуст
                if not os.path.exists(temp_file_path):
                    logger.error("[STT] Временный файл не найден")
                    return "Ошибка создания временного файла"
                
                file_size = os.path.getsize(temp_file_path)
                logger.info(f"[STT] Размер файла: {file_size} байт")
                
                if file_size == 0:
                    logger.error("[STT] Временный файл пуст")
                    return "Ошибка: пустой файл"
                
                url = "https://api.elevenlabs.io/v1/speech-to-text"
                headers = {'xi-api-key': ELEVENLABS_API_KEY}
                
                # ИСПРАВЛЕНИЕ: Правильное чтение файла для FormData
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                    # Читаем весь файл в память для FormData
                    with open(temp_file_path, 'rb') as audio_file:
                        audio_content = audio_file.read()
                    
                    logger.info(f"[STT] Прочитано из файла: {len(audio_content)} байт")
                    
                    data = aiohttp.FormData()
                    data.add_field('audio', audio_content, 
                                 filename='audio.webm', 
                                 content_type='audio/webm')
                    data.add_field('model_id', 'eleven_multilingual_sts_v2')
                    
                    logger.info("[STT] Отправляем запрос к ElevenLabs...")
                    
                    async with session.post(url, data=data, headers=headers) as response:
                        logger.info(f"[STT] Ответ от ElevenLabs: {response.status}")
                        
                        if response.status == 200:
                            result = await response.json()
                            transcript = result.get('text', '').strip()
                            
                            if transcript and len(transcript) > 1:
                                logger.info(f"[STT] Успешно: {transcript}")
                                return transcript
                            else:
                                logger.warning("[STT] Пустой результат")
                                return "Не удалось распознать речь."
                        else:
                            error_text = await response.text()
                            logger.error(f"[STT] Ошибка {response.status}: {error_text}")
                            
                            # Попробуем другую модель
                            if response.status == 400:
                                return await self._try_alternative_stt(temp_file_path)
                            
                            return "Ошибка распознавания речи. Попробуйте еще раз."
                        
            finally:
                # Очищаем временный файл
                if temp_file_path and os.path.exists(temp_file_path):
                    try:
                        os.unlink(temp_file_path)
                        logger.info(f"[STT] Временный файл удален: {temp_file_path}")
                    except Exception as cleanup_error:
                        logger.warning(f"[STT] Не удалось удалить временный файл: {cleanup_error}")
                        
        except Exception as e:
            logger.error(f"[STT] Общая ошибка: {e}")
            return "Ошибка распознавания речи. Проверьте подключение."
    
    async def _try_alternative_stt(self, file_path):
        """Попытка с альтернативной моделью STT"""
        try:
            logger.info("[STT ALT] Пробуем альтернативную модель")
            
            if not os.path.exists(file_path):
                logger.error("[STT ALT] Файл не найден")
                return "Файл не найден для альтернативной обработки"
            
            url = "https://api.elevenlabs.io/v1/speech-to-text"
            headers = {'xi-api-key': ELEVENLABS_API_KEY}
            
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                # Читаем файл в память
                with open(file_path, 'rb') as audio_file:
                    audio_content = audio_file.read()
                
                logger.info(f"[STT ALT] Прочитано: {len(audio_content)} байт")
                
                data = aiohttp.FormData()
                data.add_field('audio', audio_content, 
                             filename='audio.webm', 
                             content_type='audio/webm')
                data.add_field('model_id', 'eleven_english_sts_v2')
                
                async with session.post(url, data=data, headers=headers) as response:
                    logger.info(f"[STT ALT] Ответ: {response.status}")
                    
                    if response.status == 200:
                        result = await response.json()
                        transcript = result.get('text', '').strip()
                        
                        if transcript and len(transcript) > 1:
                            logger.info(f"[STT ALT] Успешно: {transcript}")
                            return transcript
                    else:
                        error_text = await response.text()
                        logger.error(f"[STT ALT] Ошибка {response.status}: {error_text}")
            
            return "Не удалось распознать речь. Попробуйте говорить четче."
            
        except Exception as e:
            logger.error(f"[STT ALT] Ошибка: {e}")
            return "Ошибка распознавания речи."
    
    async def generate_response(self, user_text):
        """Генерация ответа через OpenAI GPT - ИСПРАВЛЕНО"""
        try:
            if not openai_client:
                return "Извините, сервис временно недоступен."
            
            logger.info(f"[LLM] Генерируем ответ для: {user_text}")
            
            self.conversation_history.append({"role": "user", "content": user_text})
            
            # Ограничиваем историю
            if len(self.conversation_history) > 10:
                self.conversation_history = self.conversation_history[-10:]
            
            messages = [
                {"role": "system", "content": ASSISTANT_CONFIG["system_prompt"]}
            ] + self.conversation_history
            
            # ИСПРАВЛЕНИЕ: Правильные параметры для новой версии OpenAI API
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",  # Используем более доступную модель
                messages=messages,
                max_tokens=150,
                temperature=0.7,
                timeout=15
            )
            
            assistant_response = response.choices[0].message.content
            
            self.conversation_history.append({
                "role": "assistant", 
                "content": assistant_response
            })
            
            logger.info(f"[LLM] Ответ: {assistant_response}")
            return assistant_response
            
        except Exception as e:
            logger.error(f"[LLM] Ошибка: {e}")
            return "Извините, произошла ошибка. Попробуйте еще раз."
    
    async def text_to_speech_stream(self, text, websocket):
        """Преобразование текста в речь через ElevenLabs - ИСПРАВЛЕНО"""
        try:
            logger.info(f"[TTS] Начинаем синтез для: {text[:50]}...")
            
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{ASSISTANT_CONFIG['voice_id']}/stream"
            
            headers = {
                'xi-api-key': ELEVENLABS_API_KEY,
                'Content-Type': 'application/json',
                'Accept': 'audio/mpeg'  # ИСПРАВЛЕНИЕ: указываем формат
            }
            
            payload = {
                "text": text,
                "model_id": ASSISTANT_CONFIG["model_id"],
                "voice_settings": ASSISTANT_CONFIG["voice_settings"],
                "optimize_streaming_latency": 2,
                "output_format": "mp3_44100_128"
            }
            
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as session:
                async with session.post(url, json=payload, headers=headers) as response:
                    if response.status == 200:
                        await websocket.send_json({"type": "tts_start", "text": text})
                        
                        chunk_count = 0
                        async for chunk in response.content.iter_chunked(2048):
                            if chunk:
                                chunk_count += 1
                                audio_b64 = base64.b64encode(chunk).decode('utf-8')
                                await websocket.send_json({
                                    "type": "audio_chunk",
                                    "audio": audio_b64
                                })
                        
                        await websocket.send_json({
                            "type": "tts_end",
                            "total_chunks": chunk_count
                        })
                        
                        logger.info(f"[TTS] Завершен. Отправлено {chunk_count} чанков")
                    else:
                        error_text = await response.text()
                        logger.error(f"[TTS] Ошибка {response.status}: {error_text}")
                        
                        # ИСПРАВЛЕНИЕ: Возвращаем текстовый ответ при ошибке TTS
                        await websocket.send_json({
                            "type": "response",
                            "text": text  # Отправляем текст вместо аудио
                        })
                        
                        await websocket.send_json({
                            "type": "processing_complete"
                        })
                        
        except Exception as e:
            logger.error(f"[TTS] Исключение: {e}")
            
            # ИСПРАВЛЕНИЕ: При ошибке TTS отправляем текст
            await websocket.send_json({
                "type": "response",
                "text": text
            })
            
            await websocket.send_json({
                "type": "processing_complete"
            })

@app.get("/")
async def get_main_page():
    """Главная страница"""
    return HTMLResponse(content=HTML_CONTENT)

@app.get("/health")
async def health_check():
    """Health check для проверки статуса"""
    elevenlabs_configured = ELEVENLABS_API_KEY and ELEVENLABS_API_KEY != "your_elevenlabs_key"
    openai_configured = OPENAI_API_KEY and OPENAI_API_KEY != "your_openai_key"
    
    return JSONResponse({
        "status": "healthy",
        "service": "Voice Assistant",
        "version": "2.1.0",
        "openai_status": "connected" if openai_client else "disconnected", 
        "elevenlabs_key": "configured" if elevenlabs_configured else "missing",
        "openai_key": "configured" if openai_configured else "missing",
        "issues": [
            "ElevenLabs API key not set" if not elevenlabs_configured else None,
            "OpenAI API key not set" if not openai_configured else None,
            "OpenAI client failed to initialize" if not openai_client else None
        ]
    })

@app.websocket("/ws/voice")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint для голосового взаимодействия - ИСПРАВЛЕНО"""
    await websocket.accept()
    logger.info("[WS] WebSocket соединение установлено")
    
    handler = VoiceAssistantHandler()
    
    try:
        while True:
            message = await websocket.receive_json()
            
            if message["type"] == "audio_data":
                try:
                    audio_bytes = bytes(message["data"])
                    logger.info(f"[WS] Получены аудио данные: {len(audio_bytes)} байт")
                    
                    # STT
                    transcript = await handler.speech_to_text(audio_bytes)
                    
                    if transcript and transcript.strip() and not transcript.startswith("Ошибка") and not transcript.startswith("Запись"):
                        await websocket.send_json({
                            "type": "transcription",
                            "text": transcript
                        })
                        
                        # Генерируем ответ
                        response = await handler.generate_response(transcript)
                        
                        await websocket.send_json({
                            "type": "response", 
                            "text": response
                        })
                        
                        # TTS
                        await handler.text_to_speech_stream(response, websocket)
                        
                        await websocket.send_json({
                            "type": "processing_complete"
                        })
                    else:
                        # Отправляем ошибку
                        await websocket.send_json({
                            "type": "error",
                            "message": transcript
                        })
                        
                except Exception as e:
                    logger.error(f"[WS] Ошибка обработки аудио: {e}")
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Ошибка обработки: {str(e)}"
                    })
            
    except WebSocketDisconnect:
        logger.info("[WS] WebSocket соединение закрыто")
    except Exception as e:
        logger.error(f"[WS] WebSocket ошибка: {e}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    
    # Проверка конфигурации перед запуском
    logger.info("🚀 Запуск Voice Assistant...")
    logger.info(f"🔑 ElevenLabs API: {'✅ Настроен' if ELEVENLABS_API_KEY != 'your_elevenlabs_key' else '❌ Не настроен'}")
    logger.info(f"🔑 OpenAI API: {'✅ Настроен' if OPENAI_API_KEY != 'your_openai_key' else '❌ Не настроен'}")
    logger.info(f"🌐 Запуск на порту: {port}")
    
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
