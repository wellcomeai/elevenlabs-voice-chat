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

# Инициализация OpenAI клиента
openai_client = OpenAI(api_key=OPENAI_API_KEY)

app = FastAPI(title="ElevenLabs Voice Assistant MVP")

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
    html_content = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ElevenLabs Voice Assistant</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }

        .assistant-container {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(20px);
            border-radius: 24px;
            padding: 40px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.1);
            max-width: 500px;
            width: 100%;
            text-align: center;
        }

        .assistant-header {
            margin-bottom: 30px;
        }

        .assistant-title {
            font-size: 32px;
            font-weight: 700;
            color: #2d3748;
            margin-bottom: 8px;
        }

        .assistant-subtitle {
            font-size: 16px;
            color: #64748b;
            font-weight: 500;
        }

        .voice-button {
            width: 140px;
            height: 140px;
            border-radius: 50%;
            border: none;
            background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
            color: white;
            font-size: 32px;
            cursor: pointer;
            transition: all 0.3s ease;
            position: relative;
            overflow: hidden;
            margin: 20px auto;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 10px 30px rgba(79, 70, 229, 0.3);
        }

        .voice-button:hover {
            transform: scale(1.05);
            box-shadow: 0 15px 40px rgba(79, 70, 229, 0.4);
        }

        .voice-button:active {
            transform: scale(0.95);
        }

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

        @keyframes pulse {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.1); }
        }

        @keyframes spin {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
        }

        @keyframes wave {
            0%, 100% { transform: scale(1); }
            25% { transform: scale(1.05); }
            75% { transform: scale(0.95); }
        }

        .status-text {
            margin-top: 25px;
            font-size: 18px;
            font-weight: 500;
            color: #475569;
            min-height: 24px;
        }

        .conversation-display {
            margin-top: 40px;
            padding: 25px;
            background: rgba(248, 250, 252, 0.8);
            border-radius: 16px;
            min-height: 120px;
            text-align: left;
        }

        .conversation-title {
            font-size: 16px;
            font-weight: 600;
            color: #334155;
            margin-bottom: 15px;
            text-align: center;
        }

        .message {
            margin-bottom: 15px;
            padding: 12px 16px;
            border-radius: 12px;
            line-height: 1.5;
        }

        .message.user {
            background: linear-gradient(135deg, #e0e7ff 0%, #c7d2fe 100%);
            color: #3730a3;
            margin-left: 20px;
        }

        .message.assistant {
            background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%);
            color: #166534;
            margin-right: 20px;
        }

        .message-label {
            font-size: 12px;
            font-weight: 600;
            opacity: 0.7;
            margin-bottom: 4px;
        }

        .connection-indicator {
            position: absolute;
            top: 20px;
            right: 20px;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            background: #ef4444;
            transition: all 0.3s ease;
        }

        .connection-indicator.connected {
            background: #10b981;
            box-shadow: 0 0 10px rgba(16, 185, 129, 0.5);
        }

        .error-message {
            margin-top: 20px;
            padding: 15px;
            background: rgba(239, 68, 68, 0.1);
            border: 1px solid rgba(239, 68, 68, 0.2);
            border-radius: 12px;
            color: #dc2626;
            font-size: 14px;
            display: none;
        }

        .wave-effect {
            position: absolute;
            inset: -20px;
            border: 2px solid currentColor;
            border-radius: 50%;
            opacity: 0;
            animation: wave-expand 2s infinite;
        }

        @keyframes wave-expand {
            0% {
                transform: scale(1);
                opacity: 0.7;
            }
            100% {
                transform: scale(1.5);
                opacity: 0;
            }
        }

        .intro-text {
            margin-bottom: 30px;
            font-size: 18px;
            color: #64748b;
            line-height: 1.6;
        }
    </style>
</head>
<body>
    <div class="assistant-container">
        <div class="connection-indicator" id="connectionStatus"></div>
        
        <div class="assistant-header">
            <h1 class="assistant-title">🎤 Алиса</h1>
            <p class="assistant-subtitle">Голосовой ассистент на ElevenLabs + GPT</p>
        </div>

        <div class="intro-text">
            Привет! Я Алиса, ваш голосовой помощник. Нажмите на кнопку и начните говорить!
        </div>

        <button class="voice-button" id="voiceButton">
            <span id="buttonIcon">🎤</span>
            <div class="wave-effect"></div>
        </button>

        <div class="status-text" id="statusText">Нажмите, чтобы начать разговор</div>

        <div class="conversation-display">
            <div class="conversation-title">💬 Наш разговор</div>
            <div id="conversationHistory">
                <div style="text-align: center; color: #94a3b8; font-style: italic;">
                    Здесь будет отображаться наша беседа...
                </div>
            </div>
        </div>

        <div class="error-message" id="errorMessage"></div>
    </div>

    <script>
        class VoiceAssistant {
            constructor() {
                this.ws = null;
                this.isRecording = false;
                this.isProcessing = false;
                this.isSpeaking = false;
                this.mediaRecorder = null;
                this.audioChunks = [];
                this.currentAudio = null;
                this.audioQueue = [];

                this.initializeElements();
                this.connectWebSocket();
                this.bindEvents();
            }

            initializeElements() {
                this.voiceButton = document.getElementById('voiceButton');
                this.buttonIcon = document.getElementById('buttonIcon');
                this.statusText = document.getElementById('statusText');
                this.connectionStatus = document.getElementById('connectionStatus');
                this.errorMessage = document.getElementById('errorMessage');
                this.conversationHistory = document.getElementById('conversationHistory');
            }

            connectWebSocket() {
                const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                const wsUrl = `${protocol}//${window.location.host}/ws/voice`;
                
                this.ws = new WebSocket(wsUrl);
                
                this.ws.onopen = () => {
                    console.log('WebSocket соединение установлено');
                    this.updateConnectionStatus(true);
                    this.statusText.textContent = 'Готов к работе! Нажмите для начала';
                };
                
                this.ws.onmessage = (event) => {
                    this.handleWebSocketMessage(JSON.parse(event.data));
                };
                
                this.ws.onclose = () => {
                    console.log('WebSocket соединение закрыто');
                    this.updateConnectionStatus(false);
                    this.statusText.textContent = 'Соединение потеряно. Обновите страницу';
                };
                
                this.ws.onerror = (error) => {
                    console.error('WebSocket ошибка:', error);
                    this.showError('Ошибка соединения с сервером');
                };
            }

            bindEvents() {
                this.voiceButton.addEventListener('click', () => {
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
                    this.clearError();
                    
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
                    this.statusText.textContent = 'Говорите... Нажмите, чтобы остановить';

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
                    this.statusText.textContent = 'Обрабатываю...';
                }
            }

            async processAudio() {
                try {
                    const audioBlob = new Blob(this.audioChunks, { type: 'audio/webm' });
                    
                    // Отправляем аудио на сервер
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

            handleWebSocketMessage(data) {
                console.log('Получено сообщение:', data);

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
                        this.statusText.textContent = 'Говорю... Нажмите для прерывания';
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
                if (role === 'user' && this.conversationHistory.innerHTML.includes('Здесь будет')) {
                    this.conversationHistory.innerHTML = '';
                }

                const messageDiv = document.createElement('div');
                messageDiv.className = `message ${role}`;
                
                const labelDiv = document.createElement('div');
                labelDiv.className = 'message-label';
                labelDiv.textContent = role === 'user' ? 'Вы:' : 'Алиса:';
                
                const textDiv = document.createElement('div');
                textDiv.textContent = text;
                
                messageDiv.appendChild(labelDiv);
                messageDiv.appendChild(textDiv);
                
                this.conversationHistory.appendChild(messageDiv);
                this.conversationHistory.scrollTop = this.conversationHistory.scrollHeight;
            }

            updateUI() {
                this.voiceButton.className = 'voice-button';

                if (this.isRecording) {
                    this.voiceButton.classList.add('recording');
                    this.buttonIcon.textContent = '⏹️';
                } else if (this.isProcessing) {
                    this.voiceButton.classList.add('processing');
                    this.buttonIcon.textContent = '⚙️';
                } else if (this.isSpeaking) {
                    this.voiceButton.classList.add('speaking');
                    this.buttonIcon.textContent = '🔊';
                } else {
                    this.buttonIcon.textContent = '🎤';
                }
            }

            resetState() {
                this.isRecording = false;
                this.isProcessing = false;
                this.isSpeaking = false;
                this.updateUI();
                this.statusText.textContent = 'Готов к работе! Нажмите для начала';
            }

            updateConnectionStatus(connected) {
                if (connected) {
                    this.connectionStatus.classList.add('connected');
                } else {
                    this.connectionStatus.classList.remove('connected');
                }
            }

            showError(message) {
                this.errorMessage.textContent = message;
                this.errorMessage.style.display = 'block';
                setTimeout(() => {
                    this.errorMessage.style.display = 'none';
                }, 5000);
            }

            clearError() {
                this.errorMessage.style.display = 'none';
            }
        }

        // Запускаем ассистента при загрузке страницы
        document.addEventListener('DOMContentLoaded', () => {
            new VoiceAssistant();
        });
    </script>
</body>
</html>
    """
    
    return HTMLResponse(content=html_content)

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
