#!/usr/bin/env python3
"""
ElevenLabs Conversational AI - Render.com Version с аудио в браузере
"""

import asyncio
import logging
import os
import sys
import time
import json
from pathlib import Path
from typing import Dict, Any, List, Optional

# FastAPI для веб-интерфейса и WebSocket
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn

# Для WebSocket клиента к ElevenLabs
import aiohttp

# Добавляем путь к модулям
sys.path.insert(0, str(Path(__file__).parent))

from config import Config
from utils import setup_logging, print_banner

logger = logging.getLogger(__name__)

# ===== FastAPI Application =====

app = FastAPI(
    title="ElevenLabs Voice Assistant",
    description="Облачная версия голосового ассистента ElevenLabs с поддержкой аудио в браузере",
    version="3.0-render-audio"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Загружаем HTML и статические файлы
try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
except Exception as e:
    logger.warning(f"Не удалось смонтировать статические файлы: {e}")

# ===== Global State =====

class AppState:
    def __init__(self):
        self.config = None
        self.is_initialized = False
        self.start_time = time.time()
        self.stats = {
            "messages_received": 0,
            "connections": 0,
            "errors": 0,
            "audio_chunks_sent": 0,
            "audio_chunks_received": 0,
            "ws_connections": 0
        }
        # Активные WebSocket соединения
        self.active_connections: List[WebSocket] = []
        # Прокси соединения к ElevenLabs
        self.elevenlabs_connections: Dict[str, aiohttp.ClientWebSocketResponse] = {}

app_state = AppState()

# ===== Startup/Shutdown =====

@app.on_event("startup")
async def startup_event():
    """Инициализация при запуске"""
    try:
        logger.info("🚀 Запуск ElevenLabs сервиса с поддержкой аудио в браузере...")
        
        # Загрузка конфигурации
        app_state.config = Config()
        if not app_state.config.validate():
            logger.error("❌ Некорректная конфигурация")
            return
        
        app_state.is_initialized = True
        logger.info("✅ Сервис инициализирован")
        
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации: {e}")
        app_state.is_initialized = False

@app.on_event("shutdown") 
async def shutdown_event():
    """Очистка при остановке"""
    logger.info("👋 Остановка сервиса...")
    
    # Закрываем все WebSocket соединения
    for connection in app_state.active_connections:
        try:
            await connection.close()
        except:
            pass
    
    # Закрываем все соединения с ElevenLabs
    for connection_id, ws in app_state.elevenlabs_connections.items():
        try:
            await ws.close()
        except:
            pass
    
    logger.info("✅ Сервис остановлен")

# ===== HTTP Endpoints =====

@app.get("/", response_class=HTMLResponse)
async def get_homepage():
    """Главная страница с аудио интерфейсом"""
    try:
        with open(Path(__file__).parent / "static" / "index.html") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        # Возвращаем встроенный HTML если файл не найден
        return HTMLResponse(content="""
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ElevenLabs Voice Assistant</title>
    <style>
        body { 
            font-family: 'Inter', -apple-system, sans-serif; 
            margin: 0; 
            padding: 0;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex; 
            justify-content: center;
            align-items: center;
        }
        .container { 
            max-width: 800px; 
            width: 90%;
            margin: 20px auto; 
            background: white; 
            padding: 30px; 
            border-radius: 15px; 
            box-shadow: 0 10px 30px rgba(0,0,0,0.2); 
        }
        .title { 
            color: #333; 
            text-align: center; 
            margin-bottom: 20px; 
        }
        .status { 
            padding: 15px; 
            border-radius: 8px; 
            margin: 15px 0; 
            font-weight: 500;
        }
        .status.ok { 
            background: #d4edda; 
            color: #155724; 
        }
        .status.error { 
            background: #f8d7da; 
            color: #721c24; 
        }
        .chat-interface {
            margin-top: 30px;
            border: 1px solid #e0e0e0;
            border-radius: 10px;
            overflow: hidden;
        }
        .chat-messages {
            height: 300px;
            overflow-y: auto;
            padding: 15px;
            background: #f9f9f9;
        }
        .message {
            margin-bottom: 15px;
            padding: 10px 15px;
            border-radius: 10px;
            max-width: 80%;
        }
        .user-message {
            background: #e3f2fd;
            margin-left: auto;
            text-align: right;
        }
        .bot-message {
            background: #f1f8e9;
        }
        .chat-input {
            display: flex;
            padding: 10px;
            background: #fff;
            border-top: 1px solid #e0e0e0;
        }
        .chat-input input {
            flex: 1;
            padding: 10px 15px;
            border: 1px solid #ddd;
            border-radius: 20px;
            outline: none;
        }
        .chat-input button {
            margin-left: 10px;
            padding: 10px 20px;
            background: #4f46e5;
            color: white;
            border: none;
            border-radius: 20px;
            cursor: pointer;
        }
        .chat-input button:hover {
            background: #3730a3;
        }
        .mic-button {
            width: 80px;
            height: 80px;
            border-radius: 50%;
            background: linear-gradient(45deg, #667eea, #764ba2);
            margin: 20px auto;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-size: 30px;
            cursor: pointer;
            transition: all 0.3s ease;
        }
        .mic-button:hover {
            transform: scale(1.05);
        }
        .mic-button.recording {
            background: linear-gradient(45deg, #f44336, #d32f2f);
            animation: pulse 1.5s infinite;
        }
        @keyframes pulse {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.1); }
        }
        .volume-bar {
            height: 4px;
            background: #e0e0e0;
            border-radius: 2px;
            margin: 10px 0;
            overflow: hidden;
        }
        .volume-level {
            height: 100%;
            width: 0%;
            background: linear-gradient(90deg, #667eea, #764ba2);
            transition: width 0.1s ease;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1 class="title">🎤 ElevenLabs Voice Assistant</h1>
        <p class="title" style="font-size: 1rem; margin-top: -10px;">Веб-версия с аудио в браузере</p>
        
        <div class="status ok" id="statusBadge">
            ✅ Сервис работает | Время работы: <span id="uptime">calculating...</span>
        </div>
        
        <div class="mic-button" id="micButton">
            🎤
        </div>
        
        <div class="volume-bar">
            <div class="volume-level" id="volumeLevel"></div>
        </div>
        
        <div style="text-align: center; margin: 10px 0; color: #666;" id="micStatus">
            Нажмите на кнопку микрофона, чтобы начать разговор
        </div>
        
        <div class="chat-interface">
            <div class="chat-messages" id="chatMessages">
                <div class="message bot-message">
                    Привет! Я голосовой ассистент ElevenLabs. Как я могу вам помочь?
                </div>
            </div>
            <div class="chat-input">
                <input type="text" id="messageInput" placeholder="Или введите сообщение здесь...">
                <button id="sendButton">Отправить</button>
            </div>
        </div>
        
        <div style="margin-top: 20px; text-align: center; color: #666; font-size: 0.8rem;">
            <p>Используется WebSocket для связи с ElevenLabs API</p>
            <p>ID агента: <span id="agentId">загрузка...</span></p>
            <p>Состояние: <span id="connectionState">не подключен</span></p>
        </div>
    </div>

    <script>
        // Основной класс для работы с голосовым ассистентом
        class VoiceAssistant {
            constructor() {
                // Инициализация переменных
                this.ws = null;
                this.isConnected = false;
                this.isRecording = false;
                this.isAgentSpeaking = false;
                this.mediaRecorder = null;
                this.audioStream = null;
                this.agentId = null;
                
                // Инициализация элементов UI
                this.micButton = document.getElementById('micButton');
                this.micStatus = document.getElementById('micStatus');
                this.volumeLevel = document.getElementById('volumeLevel');
                this.chatMessages = document.getElementById('chatMessages');
                this.messageInput = document.getElementById('messageInput');
                this.sendButton = document.getElementById('sendButton');
                this.connectionState = document.getElementById('connectionState');
                this.agentId = document.getElementById('agentId');
                this.statusBadge = document.getElementById('statusBadge');
                this.uptime = document.getElementById('uptime');
                
                // Загрузка информации о агенте
                this.loadAgentInfo();
                
                // Подключаем обработчики событий
                this.setupEventListeners();
                
                // Обновляем статус каждые 5 секунд
                setInterval(() => this.updateStatus(), 5000);
            }
            
            // Загрузка информации о агенте
            async loadAgentInfo() {
                try {
                    const response = await fetch('/api/config');
                    if (response.ok) {
                        const data = await response.json();
                        this.agentId.textContent = data.agent_id || 'не найден';
                    } else {
                        this.agentId.textContent = 'ошибка загрузки';
                    }
                } catch (error) {
                    console.error('Ошибка загрузки информации о агенте:', error);
                    this.agentId.textContent = 'ошибка загрузки';
                }
            }
            
            // Настройка обработчиков событий
            setupEventListeners() {
                // Обработчик клика по кнопке микрофона
                this.micButton.addEventListener('click', () => {
                    if (this.isRecording) {
                        this.stopRecording();
                    } else {
                        this.startRecording();
                    }
                });
                
                // Обработчик клика по кнопке отправки сообщения
                this.sendButton.addEventListener('click', () => {
                    this.sendTextMessage();
                });
                
                // Обработчик нажатия Enter в поле ввода
                this.messageInput.addEventListener('keyup', (e) => {
                    if (e.key === 'Enter') {
                        this.sendTextMessage();
                    }
                });
            }
            
            // Подключение к WebSocket
            async connectWebSocket() {
                try {
                    if (this.ws) {
                        this.ws.close();
                    }
                    
                    this.connectionState.textContent = 'подключение...';
                    
                    // Подключаемся к нашему WebSocket серверу
                    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                    const wsUrl = `${protocol}//${window.location.host}/ws/conversation`;
                    
                    this.ws = new WebSocket(wsUrl);
                    
                    this.ws.onopen = () => {
                        this.isConnected = true;
                        this.connectionState.textContent = 'подключено';
                        this.addSystemMessage('Соединение установлено');
                        console.log('WebSocket подключен');
                    };
                    
                    this.ws.onmessage = (event) => {
                        this.handleWebSocketMessage(event);
                    };
                    
                    this.ws.onclose = () => {
                        this.isConnected = false;
                        this.connectionState.textContent = 'отключено';
                        this.addSystemMessage('Соединение закрыто');
                        console.log('WebSocket отключен');
                    };
                    
                    this.ws.onerror = (error) => {
                        this.connectionState.textContent = 'ошибка';
                        this.addSystemMessage('Ошибка соединения');
                        console.error('WebSocket ошибка:', error);
                    };
                    
                } catch (error) {
                    console.error('Ошибка подключения к WebSocket:', error);
                    this.addSystemMessage('Ошибка подключения: ' + error.message);
                }
            }
            
            // Обработка сообщений от сервера
            handleWebSocketMessage(event) {
                try {
                    const data = JSON.parse(event.data);
                    console.log('Получено сообщение:', data);
                    
                    switch (data.type) {
                        case 'user_transcript':
                            const transcript = data.user_transcription_event?.user_transcript;
                            if (transcript) {
                                this.addUserMessage(transcript);
                            }
                            break;
                            
                        case 'agent_response':
                            const response = data.agent_response_event?.agent_response;
                            if (response) {
                                this.addAssistantMessage(response);
                                this.isAgentSpeaking = true;
                                this.micStatus.textContent = 'Ассистент говорит...';
                            }
                            break;
                            
                        case 'audio':
                            const audioData = data.audio_event?.audio_base_64 || data.audio_data;
                            if (audioData) {
                                this.playAudio(audioData);
                            }
                            break;
                            
                        case 'conversation_initiation_metadata':
                            const metadata = data.conversation_initiation_metadata_event;
                            if (metadata) {
                                console.log('Инициализация разговора:', metadata);
                                this.addSystemMessage('Разговор начат');
                            }
                            break;
                            
                        case 'vad_score':
                            const vadScore = data.vad_score_event?.vad_score;
                            if (typeof vadScore === 'number') {
                                this.updateVolumeLevel(vadScore);
                            }
                            break;
                            
                        case 'interruption':
                            this.isAgentSpeaking = false;
                            this.addSystemMessage('Прерывание обнаружено');
                            break;
                            
                        case 'error':
                            this.addSystemMessage('Ошибка: ' + (data.message || 'Неизвестная ошибка'));
                            break;
                    }
                    
                } catch (error) {
                    console.error('Ошибка обработки сообщения:', error);
                }
            }
            
            // Начало записи аудио
            async startRecording() {
                if (this.isRecording) return;
                
                try {
                    // Запрашиваем доступ к микрофону
                    this.audioStream = await navigator.mediaDevices.getUserMedia({ 
                        audio: {
                            echoCancellation: true,
                            noiseSuppression: true,
                            autoGainControl: true
                        } 
                    });
                    
                    // Если не подключены к WebSocket, подключаемся
                    if (!this.isConnected) {
                        await this.connectWebSocket();
                    }
                    
                    // Настройка MediaRecorder
                    this.mediaRecorder = new MediaRecorder(this.audioStream);
                    
                    this.mediaRecorder.ondataavailable = (event) => {
                        if (event.data.size > 0 && this.ws && this.ws.readyState === WebSocket.OPEN && !this.isAgentSpeaking) {
                            this.sendAudioChunk(event.data);
                        }
                    };
                    
                    this.mediaRecorder.start(250); // Запись по 250мс
                    this.isRecording = true;
                    this.micButton.classList.add('recording');
                    this.micStatus.textContent = 'Запись... Говорите';
                    
                    // Анализ громкости
                    this.setupVolumeAnalysis();
                    
                } catch (error) {
                    console.error('Ошибка начала записи:', error);
                    this.addSystemMessage('Ошибка доступа к микрофону: ' + error.message);
                }
            }
            
            // Настройка анализа громкости
            setupVolumeAnalysis() {
                try {
                    const audioContext = new (window.AudioContext || window.webkitAudioContext)();
                    const analyzer = audioContext.createAnalyser();
                    const microphone = audioContext.createMediaStreamSource(this.audioStream);
                    const javascriptNode = audioContext.createScriptProcessor(2048, 1, 1);
                    
                    analyzer.smoothingTimeConstant = 0.8;
                    analyzer.fftSize = 1024;
                    
                    microphone.connect(analyzer);
                    analyzer.connect(javascriptNode);
                    javascriptNode.connect(audioContext.destination);
                    
                    javascriptNode.onaudioprocess = () => {
                        const array = new Uint8Array(analyzer.frequencyBinCount);
                        analyzer.getByteFrequencyData(array);
                        
                        let values = 0;
                        for (let i = 0; i < array.length; i++) {
                            values += array[i];
                        }
                        
                        const average = values / array.length;
                        const volume = Math.min(100, Math.max(0, average * 1.5));
                        
                        this.updateVolumeLevel(volume / 100);
                    };
                    
                    // Сохраняем ссылки для очистки
                    this.audioContext = audioContext;
                    this.javascriptNode = javascriptNode;
                    this.analyzer = analyzer;
                    this.microphone = microphone;
                    
                } catch (error) {
                    console.error('Ошибка анализа громкости:', error);
                }
            }
            
            // Обновление индикатора громкости
            updateVolumeLevel(level) {
                if (this.volumeLevel) {
                    this.volumeLevel.style.width = `${level * 100}%`;
                    
                    // Изменение цвета в зависимости от громкости
                    if (level > 0.7) {
                        this.volumeLevel.style.background = 'linear-gradient(90deg, #4CAF50, #8BC34A)';
                    } else if (level > 0.4) {
                        this.volumeLevel.style.background = 'linear-gradient(90deg, #03A9F4, #2196F3)';
                    } else {
                        this.volumeLevel.style.background = 'linear-gradient(90deg, #667eea, #764ba2)';
                    }
                }
            }
            
            // Отправка аудио чанка
            async sendAudioChunk(blob) {
                if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
                
                try {
                    const buffer = await blob.arrayBuffer();
                    const base64Audio = this.arrayBufferToBase64(buffer);
                    
                    this.ws.send(JSON.stringify({
                        type: 'user_audio_chunk',
                        user_audio_chunk: base64Audio
                    }));
                    
                } catch (error) {
                    console.error('Ошибка отправки аудио:', error);
                }
            }
            
            // Остановка записи
            stopRecording() {
                if (!this.isRecording) return;
                
                try {
                    if (this.mediaRecorder) {
                        this.mediaRecorder.stop();
                    }
                    
                    if (this.audioStream) {
                        this.audioStream.getTracks().forEach(track => track.stop());
                    }
                    
                    // Очистка аудио анализа
                    if (this.javascriptNode) {
                        this.javascriptNode.disconnect();
                    }
                    
                    if (this.microphone) {
                        this.microphone.disconnect();
                    }
                    
                    if (this.analyzer) {
                        this.analyzer.disconnect();
                    }
                    
                    if (this.audioContext) {
                        this.audioContext.close();
                    }
                    
                    this.isRecording = false;
                    this.micButton.classList.remove('recording');
                    this.micStatus.textContent = 'Запись остановлена';
                    this.volumeLevel.style.width = '0%';
                    
                } catch (error) {
                    console.error('Ошибка остановки записи:', error);
                }
            }
            
            // Отправка текстового сообщения
            sendTextMessage() {
                const message = this.messageInput.value.trim();
                if (!message) return;
                
                // Если не подключены к WebSocket, подключаемся
                if (!this.isConnected) {
                    this.connectWebSocket();
                }
                
                if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                    this.ws.send(JSON.stringify({
                        type: 'text_message',
                        text: message
                    }));
                    
                    this.addUserMessage(message);
                    this.messageInput.value = '';
                } else {
                    this.addSystemMessage('Не удалось отправить сообщение: нет подключения');
                }
            }
            
            // Воспроизведение аудио от ассистента
            playAudio(base64Audio) {
                try {
                    // Для воспроизведения PCM аудио от ElevenLabs
                    const audioData = this.base64ToArrayBuffer(base64Audio);
                    
                    // Создаем WAV из PCM
                    const wavData = this.createWavFromPcm(audioData, 16000, 1);
                    const blob = new Blob([wavData], { type: 'audio/wav' });
                    const url = URL.createObjectURL(blob);
                    
                    const audio = new Audio(url);
                    
                    audio.onended = () => {
                        URL.revokeObjectURL(url);
                        
                        // Если это был последний аудио чанк
                        if (!this.isMoreAudioExpected) {
                            this.isAgentSpeaking = false;
                            this.micStatus.textContent = 'Ассистент закончил говорить';
                        }
                    };
                    
                    audio.onerror = (error) => {
                        console.error('Ошибка воспроизведения аудио:', error);
                        URL.revokeObjectURL(url);
                    };
                    
                    audio.play().catch(error => {
                        console.error('Ошибка воспроизведения аудио:', error);
                    });
                    
                } catch (error) {
                    console.error('Ошибка обработки аудио:', error);
                }
            }
            
            // Создание WAV из PCM данных
            createWavFromPcm(pcmData, sampleRate, numChannels) {
                const bitDepth = 16;
                const bytesPerSample = bitDepth / 8;
                const blockAlign = numChannels * bytesPerSample;
                const byteRate = sampleRate * blockAlign;
                const dataSize = pcmData.length;
                
                const buffer = new ArrayBuffer(44 + dataSize);
                const view = new DataView(buffer);
                
                // RIFF chunk descriptor
                this.writeString(view, 0, 'RIFF');
                view.setUint32(4, 36 + dataSize, true);
                this.writeString(view, 8, 'WAVE');
                
                // fmt sub-chunk
                this.writeString(view, 12, 'fmt ');
                view.setUint32(16, 16, true);
                view.setUint16(20, 1, true);
                view.setUint16(22, numChannels, true);
                view.setUint32(24, sampleRate, true);
                view.setUint32(28, byteRate, true);
                view.setUint16(32, blockAlign, true);
                view.setUint16(34, bitDepth, true);
                
                // data sub-chunk
                this.writeString(view, 36, 'data');
                view.setUint32(40, dataSize, true);
                
                // Запись PCM данных
                for (let i = 0; i < dataSize; i++) {
                    view.setUint8(44 + i, pcmData[i]);
                }
                
                return buffer;
            }
            
            // Запись строки в DataView
            writeString(view, offset, string) {
                for (let i = 0; i < string.length; i++) {
                    view.setUint8(offset + i, string.charCodeAt(i));
                }
            }
            
            // Конвертация из base64 в ArrayBuffer
            base64ToArrayBuffer(base64) {
                const binaryString = atob(base64);
                const bytes = new Uint8Array(binaryString.length);
                for (let i = 0; i < binaryString.length; i++) {
                    bytes[i] = binaryString.charCodeAt(i);
                }
                return bytes;
            }
            
            // Конвертация из ArrayBuffer в base64
            arrayBufferToBase64(buffer) {
                const bytes = new Uint8Array(buffer);
                let binary = '';
                for (let i = 0; i < bytes.byteLength; i++) {
                    binary += String.fromCharCode(bytes[i]);
                }
                return btoa(binary);
            }
            
            // Добавление сообщения пользователя в чат
            addUserMessage(text) {
                const messageDiv = document.createElement('div');
                messageDiv.className = 'message user-message';
                messageDiv.textContent = text;
                this.chatMessages.appendChild(messageDiv);
                this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
            }
            
            // Добавление сообщения ассистента в чат
            addAssistantMessage(text) {
                const messageDiv = document.createElement('div');
                messageDiv.className = 'message bot-message';
                messageDiv.textContent = text;
                this.chatMessages.appendChild(messageDiv);
                this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
            }
            
            // Добавление системного сообщения в чат
            addSystemMessage(text) {
                const messageDiv = document.createElement('div');
                messageDiv.className = 'message';
                messageDiv.style.backgroundColor = '#fff3cd';
                messageDiv.style.color = '#856404';
                messageDiv.style.textAlign = 'center';
                messageDiv.style.margin = '10px auto';
                messageDiv.style.fontStyle = 'italic';
                messageDiv.textContent = text;
                this.chatMessages.appendChild(messageDiv);
                this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
            }
            
            // Обновление статуса и времени работы
            async updateStatus() {
                try {
                    const response = await fetch('/api/stats');
                    if (response.ok) {
                        const data = await response.json();
                        
                        // Обновляем время работы
                        const uptime = Math.floor(data.uptime);
                        const hours = Math.floor(uptime / 3600);
                        const minutes = Math.floor((uptime % 3600) / 60);
                        const seconds = uptime % 60;
                        this.uptime.textContent = `${hours}ч ${minutes}м ${seconds}с`;
                        
                        // Обновляем класс статуса
                        if (data.initialized) {
                            this.statusBadge.className = 'status ok';
                        } else {
                            this.statusBadge.className = 'status error';
                        }
                    }
                } catch (error) {
                    console.error('Ошибка обновления статуса:', error);
                }
            }
        }
        
        // Инициализация при загрузке страницы
        document.addEventListener('DOMContentLoaded', () => {
            window.voiceAssistant = new VoiceAssistant();
        });
        
        // Обновление времени работы каждые 5 секунд
        setInterval(() => {
            fetch('/api/stats')
                .then(response => response.json())
                .then(data => {
                    const uptime = Math.floor(data.uptime);
                    const hours = Math.floor(uptime / 3600);
                    const minutes = Math.floor((uptime % 3600) / 60);
                    const seconds = uptime % 60;
                    document.getElementById('uptime').textContent = 
                        `${hours}ч ${minutes}м ${seconds}с`;
                })
                .catch(() => {
                    document.getElementById('uptime').textContent = 'недоступно';
                });
        }, 5000);
    </script>
</body>
</html>
        """)

@app.get("/debug", response_class=HTMLResponse)
async def get_debug():
    """Страница отладки"""
    try:
        with open(Path(__file__).parent / "debug.html") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(content="<h1>Debug page not found</h1>")

@app.get("/health")
async def health_check():
    """Проверка здоровья сервиса"""
    if not app_state.is_initialized:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    return {
        "status": "healthy",
        "service": "ElevenLabs Voice Assistant",
        "version": "3.0-render-audio",
        "timestamp": time.time(),
        "uptime": time.time() - app_state.start_time,
        "config": {
            "elevenlabs_configured": bool(app_state.config.ELEVENLABS_API_KEY),
            "agent_id": app_state.config.ELEVENLABS_AGENT_ID
        }
    }

@app.get("/api/config")
async def get_config():
    """Получение конфигурации"""
    if not app_state.is_initialized:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    return {
        "agent_id": app_state.config.ELEVENLABS_AGENT_ID,
        "audio_format": "PCM 16kHz",
        "features": {
            "websocket_api": True,
            "rest_api": True,
            "audio_interface": True,
            "cloud_deployment": True
        }
    }

@app.get("/api/stats")
async def get_stats():
    """Получение статистики"""
    uptime = time.time() - app_state.start_time
    
    stats = {
        "uptime": uptime,
        "uptime_formatted": f"{uptime:.1f}s",
        "initialized": app_state.is_initialized,
        "messages_received": app_state.stats["messages_received"],
        "connections": app_state.stats["connections"],
        "errors": app_state.stats["errors"],
        "audio_chunks_sent": app_state.stats["audio_chunks_sent"],
        "audio_chunks_received": app_state.stats["audio_chunks_received"],
        "active_connections": len(app_state.active_connections)
    }
    
    return stats

@app.get("/api/signed-url")
async def get_signed_url():
    """Получение signed URL для WebSocket"""
    if not app_state.is_initialized:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    try:
        # URL для получения signed URL
        url = f"https://api.elevenlabs.io/v1/convai/conversation/get_signed_url?agent_id={app_state.config.ELEVENLABS_AGENT_ID}"
        
        headers = {
            "xi-api-key": app_state.config.ELEVENLABS_API_KEY,
            "Content-Type": "application/json"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        "signed_url": data["signed_url"],
                        "agent_id": app_state.config.ELEVENLABS_AGENT_ID
                    }
                else:
                    error_text = await response.text()
                    logger.error(f"Ошибка получения signed URL: {response.status} - {error_text}")
                    return {
                        "error": f"Ошибка получения signed URL: {response.status}",
                        "fallback_url": f"wss://api.elevenlabs.io/v1/convai/conversation?agent_id={app_state.config.ELEVENLABS_AGENT_ID}",
                        "agent_id": app_state.config.ELEVENLABS_AGENT_ID
                    }
    except Exception as e:
        logger.error(f"Исключение при получении signed URL: {e}")
        return {
            "error": f"Ошибка: {str(e)}",
            "fallback_url": f"wss://api.elevenlabs.io/v1/convai/conversation?agent_id={app_state.config.ELEVENLABS_AGENT_ID}",
            "agent_id": app_state.config.ELEVENLABS_AGENT_ID
        }

# ===== WebSocket Endpoints =====

@app.websocket("/ws/conversation")
async def websocket_conversation(websocket: WebSocket):
    """WebSocket для разговора с ElevenLabs"""
    await websocket.accept()
    
    # Добавляем соединение в список активных
    app_state.active_connections.append(websocket)
    app_state.stats["connections"] += 1
    app_state.stats["ws_connections"] += 1
    
    # Уникальный ID для этого соединения
    connection_id = f"conn_{time.time()}_{id(websocket)}"
    elevenlabs_ws = None
    
    try:
        logger.info(f"🔗 Новое WebSocket подключение: {connection_id}")
        
        # Отправляем статус подключения
        await websocket.send_json({
            "type": "status",
            "state": "connecting",
            "message": "Подключение к ElevenLabs..."
        })
        
        # Подключаемся к ElevenLabs
        try:
            # Сначала пытаемся получить signed URL
            signed_url_response = await get_signed_url()
            
            if "signed_url" in signed_url_response:
                ws_url = signed_url_response["signed_url"]
                logger.info(f"🔐 Используем signed URL для {connection_id}")
            else:
                ws_url = signed_url_response.get("fallback_url", f"wss://api.elevenlabs.io/v1/convai/conversation?agent_id={app_state.config.ELEVENLABS_AGENT_ID}")
                logger.warning(f"⚠️ Используем fallback URL для {connection_id}")
            
            # Заголовки для WebSocket подключения
            headers = {}
            if "token=" not in ws_url:
                headers["xi-api-key"] = app_state.config.ELEVENLABS_API_KEY
            
            # Подключаемся к ElevenLabs WebSocket
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(ws_url, headers=headers) as elevenlabs_ws:
                    app_state.elevenlabs_connections[connection_id] = elevenlabs_ws
                    
                    # Отправляем инициализацию
                    await elevenlabs_ws.send_json({
                        "type": "conversation_initiation_client_data"
                    })
                    
                    # Создаем две задачи для двунаправленной передачи
                    client_to_elevenlabs = asyncio.create_task(
                        forward_messages(websocket, elevenlabs_ws, connection_id, "client_to_elevenlabs")
                    )
                    
                    elevenlabs_to_client = asyncio.create_task(
                        forward_messages(elevenlabs_ws, websocket, connection_id, "elevenlabs_to_client")
                    )
                    
                    # Ждем завершения любой из задач
                    done, pending = await asyncio.wait(
                        [client_to_elevenlabs, elevenlabs_to_client],
                        return_when=asyncio.FIRST_COMPLETED
                    )
                    
                    # Отменяем оставшиеся задачи
                    for task in pending:
                        task.cancel()
                    
                    # Проверяем на ошибки
                    for task in done:
                        try:
                            task.result()
                        except Exception as e:
                            logger.error(f"❌ Ошибка в задаче пересылки: {e}")
        
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к ElevenLabs: {e}")
            await websocket.send_json({
                "type": "error",
                "message": f"Ошибка подключения к ElevenLabs: {str(e)}"
            })
    
    except WebSocketDisconnect:
        logger.info(f"👋 WebSocket отключен клиентом: {connection_id}")
    
    except Exception as e:
        logger.error(f"❌ Ошибка WebSocket: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": f"Ошибка сервера: {str(e)}"
            })
        except:
            pass
    
    finally:
        # Закрываем соединение с ElevenLabs
        if connection_id in app_state.elevenlabs_connections:
            elevenlabs_ws = app_state.elevenlabs_connections[connection_id]
            if elevenlabs_ws and not elevenlabs_ws.closed:
                await elevenlabs_ws.close()
            del app_state.elevenlabs_connections[connection_id]
        
        # Удаляем из списка активных соединений
        if websocket in app_state.active_connections:
            app_state.active_connections.remove(websocket)
        
        logger.info(f"🧹 WebSocket соединение закрыто: {connection_id}")

async def forward_messages(source_ws, target_ws, connection_id, direction):
    """Пересылка сообщений между WebSocket соединениями"""
    try:
        async for message in source_ws:
            try:
                if isinstance(message, str):
                    # Текстовое сообщение
                    data = json.loads(message)
                    
                    # Преобразование формата сообщений если нужно
                    if direction == "client_to_elevenlabs":
                        # От клиента к ElevenLabs
                        if "type" in data and data["type"] == "text_message":
                            # Преобразуем текстовое сообщение в transcription
                            data = {
                                "text": data["text"]
                            }
                        
                        elif "user_audio_chunk" in data:
                            # Аудио чанк от клиента
                            app_state.stats["audio_chunks_sent"] += 1
                        
                        # Отправляем сообщение в ElevenLabs
                        await target_ws.send_json(data)
                    
                    else:
                        # От ElevenLabs к клиенту
                        if "audio_event" in data and "audio_base_64" in data["audio_event"]:
                            app_state.stats["audio_chunks_received"] += 1
                        
                        # Отправляем сообщение клиенту
                        await target_ws.send_str(message)
                
                elif isinstance(message, bytes):
                    # Бинарное сообщение (для будущих версий)
                    await target_ws.send_bytes(message)
                
                else:
                    # Другие типы сообщений (WebSocketMessage)
                    if message.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(message.data)
                        
                        if direction == "elevenlabs_to_client":
                            # Отправляем сообщение клиенту
                            await target_ws.send_json(data)
                            
                            if "audio_event" in data and "audio_base_64" in data["audio_event"]:
                                app_state.stats["audio_chunks_received"] += 1
                    
                    elif message.type == aiohttp.WSMsgType.BINARY:
                        await target_ws.send_bytes(message.data)
                    
                    elif message.type == aiohttp.WSMsgType.CLOSED:
                        logger.info(f"WebSocket закрыт: {direction}")
                        break
                    
                    elif message.type == aiohttp.WSMsgType.ERROR:
                        logger.error(f"WebSocket ошибка: {message.data}")
                        break
            
            except Exception as e:
                logger.error(f"❌ Ошибка пересылки сообщения ({direction}): {e}")
                if direction == "elevenlabs_to_client":
                    try:
                        await target_ws.send_json({
                            "type": "error",
                            "message": f"Ошибка пересылки: {str(e)}"
                        })
                    except:
                        pass
    
    except (WebSocketDisconnect, aiohttp.ClientError) as e:
        logger.info(f"👋 WebSocket отключен ({direction}): {e}")
    
    except Exception as e:
        logger.error(f"❌ Критическая ошибка в пересылке ({direction}): {e}")

# ===== Main Function =====

async def main():
    """Главная функция для CLI запуска"""
    print_banner()
    
    # Настройка логирования
    setup_logging()
    
    logger.info("🌐 Запуск в режиме веб-сервиса с поддержкой аудио в браузере...")
    logger.info("💡 Это облачная версия с аудио через Web Audio API")
    logger.info("🔗 Откройте http://localhost:8000 для веб-интерфейса")
    
    # Запуск через uvicorn
    config = uvicorn.Config(
        app=app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        log_level="info"
    )
    
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Сервис остановлен")
        sys.exit(0)
