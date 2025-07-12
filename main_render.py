#!/usr/bin/env python3
"""
ElevenLabs Conversational AI - Render.com Version с прямым WebSocket
"""

import asyncio
import logging
import os
import sys
import time
import json
import base64
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
    description="Облачная версия голосового ассистента ElevenLabs с прямым WebSocket",
    version="3.0-render-direct"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
        logger.info("🚀 Запуск ElevenLabs сервиса с прямым WebSocket...")
        
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
    return HTMLResponse(content="""
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ElevenLabs Conversational AI</title>
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
            color: #333;
        }
        
        .container {
            max-width: 700px;
            width: 90%;
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            padding: 30px;
            box-shadow: 0 15px 35px rgba(0, 0, 0, 0.2);
            margin: 20px;
        }
        
        .header {
            text-align: center;
            margin-bottom: 30px;
        }
        
        .title {
            font-size: 2.2rem;
            margin-bottom: 5px;
            background: linear-gradient(45deg, #667eea, #764ba2);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-weight: 700;
        }
        
        .subtitle {
            color: #666;
            font-size: 1rem;
        }
        
        .status-badge {
            display: inline-block;
            padding: 8px 16px;
            border-radius: 50px;
            font-weight: 600;
            font-size: 0.9rem;
            margin: 15px 0;
            text-align: center;
            transition: all 0.3s ease;
        }
        
        .status-badge.disconnected {
            background: linear-gradient(to right, #ff6b6b, #ee5253);
            color: white;
        }
        
        .status-badge.connecting {
            background: linear-gradient(to right, #f7b731, #f7971e);
            color: white;
            animation: pulse 1.5s infinite;
        }
        
        .status-badge.connected {
            background: linear-gradient(to right, #2ecc71, #1abc9c);
            color: white;
        }
        
        .status-badge.speaking {
            background: linear-gradient(to right, #00cec9, #0984e3);
            color: white;
            animation: speaking-pulse 1.5s infinite;
        }
        
        .status-badge.listening {
            background: linear-gradient(to right, #6c5ce7, #74b9ff);
            color: white;
            animation: listening-pulse 2s infinite;
        }
        
        .status-badge.thinking {
            background: linear-gradient(to right, #a29bfe, #74b9ff);
            color: white;
            animation: thinking-pulse 1.5s infinite;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 0.8; }
            50% { opacity: 1; }
        }
        
        @keyframes speaking-pulse {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.03); }
        }
        
        @keyframes listening-pulse {
            0%, 100% { transform: scale(1); opacity: 0.9; }
            50% { transform: scale(1.05); opacity: 1; }
        }
        
        @keyframes thinking-pulse {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.02); }
        }
        
        .microphone-btn {
            width: 120px;
            height: 120px;
            border-radius: 50%;
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
            font-size: 3rem;
            border: none;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 30px auto;
            cursor: pointer;
            transition: all 0.3s ease;
            box-shadow: 0 10px 20px rgba(0, 0, 0, 0.15);
        }
        
        .microphone-btn:hover {
            transform: scale(1.05);
            box-shadow: 0 15px 30px rgba(0, 0, 0, 0.2);
        }
        
        .microphone-btn.listening {
            background: linear-gradient(135deg, #6c5ce7, #74b9ff);
            animation: mic-pulse 1.5s infinite;
        }
        
        .microphone-btn.speaking {
            background: linear-gradient(135deg, #00cec9, #0984e3);
            animation: mic-wave 1s infinite;
        }
        
        .microphone-btn.thinking {
            background: linear-gradient(135deg, #a29bfe, #74b9ff);
            animation: mic-thinking 1.5s infinite;
        }
        
        @keyframes mic-pulse {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.08); }
        }
        
        @keyframes mic-wave {
            0%, 100% { transform: scale(1); }
            25% { transform: scale(1.03); }
            75% { transform: scale(0.97); }
        }
        
        @keyframes mic-thinking {
            0%, 100% { box-shadow: 0 0 0 rgba(108, 92, 231, 0.4); }
            50% { box-shadow: 0 0 30px rgba(108, 92, 231, 0.6); }
        }
        
        .volume-meter {
            height: 6px;
            background: #eee;
            border-radius: 3px;
            overflow: hidden;
            margin: 20px auto;
            max-width: 400px;
        }
        
        .volume-level {
            height: 100%;
            width: 0%;
            background: linear-gradient(to right, #667eea, #764ba2);
            border-radius: 3px;
            transition: width 0.1s ease;
        }
        
        .conversation {
            background: #f8f9fa;
            border-radius: 15px;
            padding: 20px;
            max-height: 300px;
            overflow-y: auto;
            margin: 30px 0;
        }
        
        .message {
            margin-bottom: 15px;
            padding: 12px 16px;
            border-radius: 12px;
            max-width: 80%;
            line-height: 1.4;
        }
        
        .message.user {
            background: #e3f2fd;
            margin-left: auto;
            text-align: right;
            color: #0a58ca;
        }
        
        .message.assistant {
            background: #e9e5fd;
            color: #5d48c9;
            border-left: 3px solid #6c5ce7;
        }
        
        .message.system {
            background: #fff3cd;
            color: #856404;
            text-align: center;
            font-style: italic;
            margin: 10px auto;
            max-width: 90%;
        }
        
        .controls {
            display: flex;
            justify-content: center;
            gap: 15px;
            margin: 20px 0;
            flex-wrap: wrap;
        }
        
        .btn {
            padding: 10px 20px;
            border-radius: 50px;
            border: none;
            background: #f0f0f0;
            color: #333;
            cursor: pointer;
            font-weight: 600;
            transition: all 0.3s ease;
        }
        
        .btn:hover {
            background: #e0e0e0;
            transform: translateY(-2px);
        }
        
        .btn.primary {
            background: linear-gradient(to right, #667eea, #764ba2);
            color: white;
        }
        
        .btn.primary:hover {
            box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
        }
        
        .settings {
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #eee;
        }
        
        .settings h3 {
            color: #666;
            font-size: 1rem;
            margin-bottom: 15px;
        }
        
        .setting-group {
            margin-bottom: 15px;
        }
        
        .setting-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }
        
        .setting-label {
            font-size: 0.9rem;
            color: #666;
        }
        
        select, input {
            padding: 8px 12px;
            border-radius: 8px;
            border: 1px solid #ddd;
            background: #f9f9f9;
            font-size: 0.9rem;
        }
        
        .footer {
            text-align: center;
            margin-top: 30px;
            color: #666;
            font-size: 0.9rem;
        }
        
        .debug-info {
            margin-top: 20px;
            font-size: 0.8rem;
            color: #666;
            text-align: left;
            max-height: 100px;
            overflow-y: auto;
            background: #f9f9f9;
            padding: 10px;
            border-radius: 8px;
            display: none;
        }
        
        @media (max-width: 768px) {
            .container {
                padding: 20px;
            }
            
            .title {
                font-size: 1.8rem;
            }
            
            .microphone-btn {
                width: 100px;
                height: 100px;
                font-size: 2.5rem;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1 class="title">ElevenLabs Voice Assistant</h1>
            <p class="subtitle">Разговаривайте с ИИ через прямой WebSocket</p>
            <div class="status-badge disconnected" id="statusBadge">Отключено</div>
        </div>
        
        <button class="microphone-btn" id="micButton">🎤</button>
        
        <div class="volume-meter">
            <div class="volume-level" id="volumeLevel"></div>
        </div>
        
        <div class="controls">
            <button class="btn primary" id="connectBtn">🔗 Подключиться</button>
            <button class="btn" id="disconnectBtn" disabled>⛔ Отключиться</button>
            <button class="btn" id="debugBtn">🔧 Отладка</button>
        </div>
        
        <div class="conversation" id="conversation">
            <div class="message system">
                Нажмите "Подключиться", чтобы начать разговор с голосовым ассистентом
            </div>
        </div>
        
        <div class="settings">
            <h3>⚙️ Настройки голоса и модели</h3>
            <div class="setting-group">
                <div class="setting-row">
                    <span class="setting-label">Голос:</span>
                    <select id="voiceSelect">
                        <option value="21m00Tcm4TlvDq8ikWAM">Rachel (женский)</option>
                        <option value="pNInz6obpgDQGcFmaJgB">Adam (мужской)</option>
                        <option value="D38z5RcWu1voky8WS1ja">Domi (женский)</option>
                        <option value="jsCqWAovK2LkecY7zXl4">Dave (мужской)</option>
                        <option value="XB0fDUnXU5powFXDhCwa">Dorothy (женский)</option>
                    </select>
                </div>
                <div class="setting-row">
                    <span class="setting-label">Модель:</span>
                    <select id="modelSelect">
                        <option value="eleven_turbo_v2">Eleven Turbo v2 (быстрая)</option>
                        <option value="eleven_multilingual_v2">Multilingual v2 (многоязычная)</option>
                    </select>
                </div>
                <div class="setting-row">
                    <span class="setting-label">Stability:</span>
                    <input type="range" id="stabilitySlider" min="0" max="1" step="0.1" value="0.5">
                </div>
                <div class="setting-row">
                    <span class="setting-label">Similarity:</span>
                    <input type="range" id="similaritySlider" min="0" max="1" step="0.1" value="0.8">
                </div>
            </div>
        </div>
        
        <div class="debug-info" id="debugInfo"></div>
        
        <div class="footer">
            <p>Powered by ElevenLabs Conversational AI • <span id="apiKeyStatus">API Key: проверка...</span></p>
        </div>
    </div>

    <script>
        // Основной класс для работы с ElevenLabs Conversational AI
        class ElevenLabsConversationalAI {
            constructor() {
                // Инициализация переменных
                this.ws = null;
                this.audioContext = null;
                this.mediaRecorder = null;
                this.audioStream = null;
                this.isConnected = false;
                this.isRecording = false;
                this.assistantState = 'idle';
                this.audioChunks = [];
                this.debugMode = false;
                
                // Инициализация UI элементов
                this.initializeUI();
                
                // Настройка обработчиков событий
                this.setupEventListeners();
                
                // Проверка API ключа
                this.checkAPIKey();
                
                this.log('ElevenLabsConversationalAI initialized');
            }
            
            // Инициализация UI элементов
            initializeUI() {
                this.micButton = document.getElementById('micButton');
                this.connectBtn = document.getElementById('connectBtn');
                this.disconnectBtn = document.getElementById('disconnectBtn');
                this.debugBtn = document.getElementById('debugBtn');
                this.statusBadge = document.getElementById('statusBadge');
                this.volumeLevel = document.getElementById('volumeLevel');
                this.conversation = document.getElementById('conversation');
                this.debugInfo = document.getElementById('debugInfo');
                this.apiKeyStatus = document.getElementById('apiKeyStatus');
                
                // Настройки голоса
                this.voiceSelect = document.getElementById('voiceSelect');
                this.modelSelect = document.getElementById('modelSelect');
                this.stabilitySlider = document.getElementById('stabilitySlider');
                this.similaritySlider = document.getElementById('similaritySlider');
            }
            
            // Настройка обработчиков событий
            setupEventListeners() {
                // Кнопка подключения
                this.connectBtn.addEventListener('click', () => {
                    this.connect();
                });
                
                // Кнопка отключения
                this.disconnectBtn.addEventListener('click', () => {
                    this.disconnect();
                });
                
                // Кнопка микрофона
                this.micButton.addEventListener('click', () => {
                    if (this.isConnected) {
                        if (this.isRecording) {
                            this.stopRecording();
                        } else {
                            this.startRecording();
                        }
                    } else {
                        this.showMessage('system', 'Сначала подключитесь к серверу');
                    }
                });
                
                // Кнопка отладки
                this.debugBtn.addEventListener('click', () => {
                    this.debugMode = !this.debugMode;
                    this.debugInfo.style.display = this.debugMode ? 'block' : 'none';
                    this.debugBtn.textContent = this.debugMode ? '🔧 Скрыть отладку' : '🔧 Отладка';
                });
                
                // Обработчик нажатия клавиш (пробел для записи)
                document.addEventListener('keydown', (e) => {
                    if (e.code === 'Space' && this.isConnected && !this.isRecording && 
                        this.assistantState !== 'speaking' && this.assistantState !== 'thinking') {
                        e.preventDefault();
                        this.startRecording();
                    }
                });
                
                document.addEventListener('keyup', (e) => {
                    if (e.code === 'Space' && this.isConnected && this.isRecording) {
                        e.preventDefault();
                        this.stopRecording();
                    }
                });
            }
            
            // Проверка API ключа
            async checkAPIKey() {
                try {
                    const response = await fetch('/api/config');
                    if (response.ok) {
                        const data = await response.json();
                        if (data.api_key_configured) {
                            this.apiKeyStatus.textContent = 'API Key: настроен';
                            this.apiKeyStatus.style.color = '#2ecc71';
                        } else {
                            this.apiKeyStatus.textContent = 'API Key: не настроен';
                            this.apiKeyStatus.style.color = '#e74c3c';
                            this.showMessage('system', '⚠️ API Key не настроен. Обратитесь к администратору.');
                        }
                    }
                } catch (error) {
                    this.log('Error checking API key:', error);
                    this.apiKeyStatus.textContent = 'API Key: ошибка проверки';
                    this.apiKeyStatus.style.color = '#e74c3c';
                }
            }
            
            // Подключение к серверу
            async connect() {
                if (this.isConnected) return;
                
                try {
                    this.updateStatus('connecting', 'Подключение...');
                    this.log('Connecting to server...');
                    
                    // Инициализация WebSocket
                    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                    const wsUrl = `${protocol}//${window.location.host}/ws/voice`;
                    
                    this.ws = new WebSocket(wsUrl);
                    
                    this.ws.onopen = this.handleWebSocketOpen.bind(this);
                    this.ws.onmessage = this.handleWebSocketMessage.bind(this);
                    this.ws.onclose = this.handleWebSocketClose.bind(this);
                    this.ws.onerror = this.handleWebSocketError.bind(this);
                    
                } catch (error) {
                    this.log('Connection error:', error);
                    this.updateStatus('disconnected', 'Ошибка подключения');
                    this.showMessage('system', `❌ Ошибка подключения: ${error.message}`);
                }
            }
            
            // Обработка открытия WebSocket
            handleWebSocketOpen() {
                this.log('WebSocket connected');
                this.isConnected = true;
                this.updateStatus('connected', 'Подключено');
                this.showMessage('system', '✅ Подключено к серверу');
                
                // Отправляем конфигурацию
                this.sendVoiceConfiguration();
                
                // Обновляем состояние кнопок
                this.connectBtn.disabled = true;
                this.disconnectBtn.disabled = false;
            }
            
            // Отправка конфигурации голоса
            sendVoiceConfiguration() {
                if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
                
                const config = {
                    type: 'configuration',
                    voice_id: this.voiceSelect.value,
                    model_id: this.modelSelect.value,
                    enable_maas: true,
                    voice_settings: {
                        stability: parseFloat(this.stabilitySlider.value),
                        similarity_boost: parseFloat(this.similaritySlider.value)
                    }
                };
                
                this.ws.send(JSON.stringify(config));
                this.log('Sent voice configuration:', config);
                
                this.showMessage('system', '🎵 Конфигурация голоса отправлена');
            }
            
            // Обработка сообщений от WebSocket
            handleWebSocketMessage(event) {
                try {
                    const data = JSON.parse(event.data);
                    this.log('Received message:', data);
                    
                    // Обработка состояния
                    if (data.state) {
                        this.handleStateChange(data.state);
                    }
                    
                    // Обработка распознанного текста
                    if (data.input_text) {
                        this.showMessage('user', data.input_text);
                    }
                    
                    // Обработка ответа ассистента
                    if (data.text) {
                        this.showMessage('assistant', data.text);
                    }
                    
                    // Обработка аудио
                    if (data.audio) {
                        this.playAudio(data.audio);
                    }
                    
                    // Обработка ошибок
                    if (data.error) {
                        this.showMessage('system', `❌ Ошибка: ${data.error}`);
                    }
                    
                } catch (error) {
                    this.log('Error parsing message:', error);
                }
            }
            
            // Обработка изменения состояния ассистента
            handleStateChange(state) {
                this.assistantState = state;
                
                switch (state) {
                    case 'listening':
                        this.updateStatus('listening', '🎧 Слушаю...');
                        this.micButton.classList.remove('speaking', 'thinking');
                        this.micButton.classList.add('listening');
                        break;
                        
                    case 'thinking':
                        this.updateStatus('thinking', '🤔 Думаю...');
                        this.micButton.classList.remove('listening', 'speaking');
                        this.micButton.classList.add('thinking');
                        break;
                        
                    case 'speaking':
                        this.updateStatus('speaking', '🗣️ Говорю...');
                        this.micButton.classList.remove('listening', 'thinking');
                        this.micButton.classList.add('speaking');
                        break;
                        
                    default:
                        this.updateStatus('connected', 'Подключено');
                        this.micButton.classList.remove('listening', 'thinking', 'speaking');
                }
            }
            
            // Обработка закрытия WebSocket
            handleWebSocketClose(event) {
                this.log(`WebSocket closed: ${event.code} ${event.reason}`);
                
                this.isConnected = false;
                this.updateStatus('disconnected', 'Отключено');
                
                if (this.isRecording) {
                    this.stopRecording();
                }
                
                // Обновляем состояние кнопок
                this.connectBtn.disabled = false;
                this.disconnectBtn.disabled = true;
                
                // Показываем сообщение
                if (event.code !== 1000) {
                    this.showMessage('system', `❌ Соединение закрыто: ${event.reason || 'Неизвестная причина'}`);
                } else {
                    this.showMessage('system', 'Соединение закрыто');
                }
            }
            
            // Обработка ошибок WebSocket
            handleWebSocketError(error) {
                this.log('WebSocket error:', error);
                this.showMessage('system', 'Ошибка соединения с сервером');
            }
            
            // Отключение от сервера
            disconnect() {
                if (!this.isConnected) return;
                
                this.log('Disconnecting...');
                
                // Останавливаем запись если она идет
                if (this.isRecording) {
                    this.stopRecording();
                }
                
                // Закрываем WebSocket
                if (this.ws) {
                    this.ws.close(1000, 'Нормальное закрытие');
                }
                
                this.isConnected = false;
                this.updateStatus('disconnected', 'Отключено');
                
                // Обновляем состояние кнопок
                this.connectBtn.disabled = false;
                this.disconnectBtn.disabled = true;
            }
            
            // Начало записи аудио
            async startRecording() {
                if (!this.isConnected || this.isRecording || 
                    this.assistantState === 'speaking' || this.assistantState === 'thinking') return;
                
                try {
                    this.log('Starting recording...');
                    
                    // Запрашиваем доступ к микрофону
                    this.audioStream = await navigator.mediaDevices.getUserMedia({
                        audio: {
                            echoCancellation: true,
                            noiseSuppression: true,
                            autoGainControl: true,
                            sampleRate: 16000
                        }
                    });
                    
                    // Создаем AudioContext для анализа громкости
                    this.audioContext = new (window.AudioContext || window.webkitAudioContext)({
                        sampleRate: 16000
                    });
                    
                    // Настраиваем анализатор громкости
                    this.setupVolumeAnalyzer();
                    
                    // Создаем MediaRecorder
                    this.mediaRecorder = new MediaRecorder(this.audioStream);
                    this.audioChunks = [];
                    
                    this.mediaRecorder.ondataavailable = (event) => {
                        if (event.data.size > 0) {
                            this.audioChunks.push(event.data);
                            this.processAudioChunk(event.data);
                        }
                    };
                    
                    this.mediaRecorder.start(250); // Запись по 250мс
                    this.isRecording = true;
                    
                    // Обновляем UI
                    this.micButton.classList.add('listening');
                    this.updateStatus('listening', '🎧 Говорите...');
                    
                } catch (error) {
                    this.log('Recording error:', error);
                    this.showMessage('system', `❌ Ошибка записи: ${error.message}`);
                }
            }
            
            // Настройка анализатора громкости
            setupVolumeAnalyzer() {
                if (!this.audioContext || !this.audioStream) return;
                
                const source = this.audioContext.createMediaStreamSource(this.audioStream);
                const analyzer = this.audioContext.createAnalyser();
                
                analyzer.fftSize = 256;
                analyzer.smoothingTimeConstant = 0.8;
                
                source.connect(analyzer);
                
                const bufferLength = analyzer.frequencyBinCount;
                const dataArray = new Uint8Array(bufferLength);
                
                const updateVolume = () => {
                    if (!this.isRecording) return;
                    
                    analyzer.getByteFrequencyData(dataArray);
                    
                    // Вычисляем средний уровень громкости
                    let sum = 0;
                    for (let i = 0; i < bufferLength; i++) {
                        sum += dataArray[i];
                    }
                    
                    const average = sum / bufferLength;
                    const volume = Math.min(100, Math.max(0, average * 1.5));
                    
                    // Обновляем индикатор громкости
                    this.volumeLevel.style.width = `${volume}%`;
                    
                    // Изменяем цвет в зависимости от громкости
                    if (volume > 70) {
                        this.volumeLevel.style.background = 'linear-gradient(to right, #ff4757, #ff6b81)';
                    } else if (volume > 30) {
                        this.volumeLevel.style.background = 'linear-gradient(to right, #1e90ff, #70a1ff)';
                    } else {
                        this.volumeLevel.style.background = 'linear-gradient(to right, #667eea, #764ba2)';
                    }
                    
                    requestAnimationFrame(updateVolume);
                };
                
                updateVolume();
                
                // Сохраняем ссылки
                this.audioSource = source;
                this.audioAnalyzer = analyzer;
            }
            
            // Обработка аудио чанка
            async processAudioChunk(chunk) {
                if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
                
                try {
                    // Конвертируем blob в arrayBuffer
                    const arrayBuffer = await chunk.arrayBuffer();
                    
                    // Конвертируем в base64
                    const base64Audio = this.arrayBufferToBase64(arrayBuffer);
                    
                    // Отправляем на сервер
                    this.ws.send(JSON.stringify({
                        audio: base64Audio
                    }));
                    
                } catch (error) {
                    this.log('Error processing audio chunk:', error);
                }
            }
            
            // Остановка записи
            stopRecording() {
                if (!this.isRecording) return;
                
                this.log('Stopping recording...');
                
                // Останавливаем MediaRecorder
                if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
                    this.mediaRecorder.stop();
                }
                
                // Останавливаем аудио поток
                if (this.audioStream) {
                    this.audioStream.getTracks().forEach(track => track.stop());
                }
                
                // Очищаем AudioContext
                if (this.audioContext) {
                    if (this.audioSource) {
                        this.audioSource.disconnect();
                    }
                    
                    this.audioContext.close();
                }
                
                this.isRecording = false;
                
                // Обновляем UI
                this.micButton.classList.remove('listening');
                this.volumeLevel.style.width = '0%';
                
                // Отправляем пустое сообщение, чтобы сигнализировать конец речи
                if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                    this.ws.send(JSON.stringify({}));
                    this.log('Sent end-of-speech signal');
                }
                
                this.updateStatus('connected', 'Обработка...');
            }
            
            // Воспроизведение аудио
            playAudio(base64Audio) {
                try {
                    // Декодируем base64
                    const binaryString = atob(base64Audio);
                    const bytes = new Uint8Array(binaryString.length);
                    
                    for (let i = 0; i < binaryString.length; i++) {
                        bytes[i] = binaryString.charCodeAt(i);
                    }
                    
                    // Создаем AudioContext если нужно
                    if (!this.playbackContext) {
                        this.playbackContext = new (window.AudioContext || window.webkitAudioContext)();
                    }
                    
                    // Преобразуем PCM в WAV
                    const wavData = this.createWavFromPcm(bytes, 16000, 1);
                    
                    // Декодируем и воспроизводим
                    this.playbackContext.decodeAudioData(wavData, (buffer) => {
                        const source = this.playbackContext.createBufferSource();
                        source.buffer = buffer;
                        source.connect(this.playbackContext.destination);
                        source.start(0);
                    });
                    
                } catch (error) {
                    this.log('Error playing audio:', error);
                }
            }
            
            // Создание WAV из PCM
            createWavFromPcm(pcmData, sampleRate, numChannels) {
                const bitsPerSample = 16;
                const bytesPerSample = bitsPerSample / 8;
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
                view.setUint16(34, bitsPerSample, true);
                
                // data sub-chunk
                this.writeString(view, 36, 'data');
                view.setUint32(40, dataSize, true);
                
                // Write PCM data
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
            
            // Конвертация ArrayBuffer в base64
            arrayBufferToBase64(buffer) {
                const bytes = new Uint8Array(buffer);
                let binary = '';
                
                for (let i = 0; i < bytes.byteLength; i++) {
                    binary += String.fromCharCode(bytes[i]);
                }
                
                return btoa(binary);
            }
            
            // Обновление статуса
            updateStatus(state, text) {
                this.statusBadge.className = `status-badge ${state}`;
                this.statusBadge.textContent = text;
            }
            
            // Показать сообщение в чате
            showMessage(type, text) {
                const messageEl = document.createElement('div');
                messageEl.className = `message ${type}`;
                messageEl.textContent = text;
                
                this.conversation.appendChild(messageEl);
                this.conversation.scrollTop = this.conversation.scrollHeight;
            }
            
            // Логирование
            log(...args) {
                console.log('[ElevenLabsAI]', ...args);
                
                if (this.debugMode) {
                    const message = args.map(arg => 
                        typeof arg === 'object' ? JSON.stringify(arg) : arg
                    ).join(' ');
                    
                    const logEntry = document.createElement('div');
                    logEntry.textContent = `${new Date().toLocaleTimeString()}: ${message}`;
                    
                    this.debugInfo.appendChild(logEntry);
                    this.debugInfo.scrollTop = this.debugInfo.scrollHeight;
                    
                    // Ограничиваем количество записей
                    if (this.debugInfo.children.length > 50) {
                        this.debugInfo.removeChild(this.debugInfo.children[0]);
                    }
                }
            }
        }

        // Инициализация при загрузке страницы
        document.addEventListener('DOMContentLoaded', () => {
            window.elevenlabsAI = new ElevenLabsConversationalAI();
        });
    </script>
</body>
</html>
    """)

@app.get("/health")
async def health_check():
    """Проверка здоровья сервиса"""
    if not app_state.is_initialized:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    return {
        "status": "healthy",
        "service": "ElevenLabs Voice Assistant",
        "version": "3.0-render-direct",
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
        "api_key_configured": bool(app_state.config.ELEVENLABS_API_KEY),
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

# ===== WebSocket Endpoints =====

@app.websocket("/ws/voice")
async def websocket_voice(websocket: WebSocket):
    """WebSocket для голосового интерфейса по прямому протоколу"""
    await websocket.accept()
    
    # Добавляем соединение в список активных
    app_state.active_connections.append(websocket)
    app_state.stats["connections"] += 1
    
    # Уникальный ID для этого соединения
    connection_id = f"voice_{time.time()}_{id(websocket)}"
    elevenlabs_ws = None
    
    try:
        logger.info(f"🎤 Новое голосовое WebSocket подключение: {connection_id}")
        
        # Ждем инициализационное сообщение от клиента
        try:
            init_message = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            config = json.loads(init_message)
            
            logger.info(f"📝 Получено сообщение инициализации: {config}")
            
            # Устанавливаем соединение с ElevenLabs Conversational API
            try:
                # URL для соединения с ElevenLabs
                ws_url = "wss://api.elevenlabs.io/v1/conversational"
                
                # Создаем сессию
                async with aiohttp.ClientSession() as session:
                    # Заменяем API ключ из конфигурации клиента на серверный
                    if "xi_api_key" in config:
                        config["xi_api_key"] = app_state.config.ELEVENLABS_API_KEY
                    elif "type" in config and config["type"] == "configuration":
                        # Формируем правильную конфигурацию
                        config = {
                            "xi_api_key": app_state.config.ELEVENLABS_API_KEY,
                            "voice_id": config.get("voice_id", "21m00Tcm4TlvDq8ikWAM"),
                            "model_id": config.get("model_id", "eleven_turbo_v2"),
                            "enable_maas": True,
                            "voice_settings": config.get("voice_settings", {
                                "stability": 0.5,
                                "similarity_boost": 0.8
                            })
                        }
                    
                    logger.info(f"🔄 Подключение к ElevenLabs Conversational API...")
                    
                    # Подключаемся к ElevenLabs
                    async with session.ws_connect(ws_url) as elevenlabs_ws:
                        app_state.elevenlabs_connections[connection_id] = elevenlabs_ws
                        
                        # Отправляем инициализационное сообщение
                        await elevenlabs_ws.send_str(json.dumps(config))
                        logger.info(f"📤 Инициализационное сообщение отправлено")
                        
                        # Создаем две задачи для пересылки сообщений
                        client_to_elevenlabs = asyncio.create_task(
                            forward_websocket_messages(websocket, elevenlabs_ws, connection_id, "client_to_elevenlabs")
                        )
                        
                        elevenlabs_to_client = asyncio.create_task(
                            forward_websocket_messages(elevenlabs_ws, websocket, connection_id, "elevenlabs_to_client")
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
                    "error": f"Ошибка подключения к ElevenLabs: {str(e)}"
                })
                
        except asyncio.TimeoutError:
            logger.warning(f"⏱️ Таймаут ожидания инициализации от клиента: {connection_id}")
            await websocket.send_json({
                "error": "Таймаут ожидания инициализации"
            })
            
        except json.JSONDecodeError:
            logger.error(f"❌ Ошибка декодирования JSON: {connection_id}")
            await websocket.send_json({
                "error": "Неверный формат инициализационного сообщения"
            })
    
    except WebSocketDisconnect:
        logger.info(f"👋 WebSocket отключен клиентом: {connection_id}")
    
    except Exception as e:
        logger.error(f"❌ Ошибка WebSocket: {e}")
        try:
            await websocket.send_json({
                "error": f"Ошибка сервера: {str(e)}"
            })
        except:
            pass
    
    finally:
        # Закрываем соединение с ElevenLabs
        if connection_id in app_state.elevenlabs_connections:
            elevenlabs_ws = app_state.elevenlabs_connections.pop(connection_id, None)
            if elevenlabs_ws and not elevenlabs_ws.closed:
                await elevenlabs_ws.close()
        
        # Удаляем из списка активных соединений
        if websocket in app_state.active_connections:
            app_state.active_connections.remove(websocket)
        
        logger.info(f"🧹 Голосовое WebSocket соединение закрыто: {connection_id}")

async def forward_websocket_messages(source, target, connection_id, direction):
    """Пересылка сообщений между WebSocket соединениями"""
    try:
        if direction == "client_to_elevenlabs":
            # От клиента к ElevenLabs
            async for message in source:
                if isinstance(message, str):
                    # Текстовое сообщение
                    try:
                        data = json.loads(message)
                        await target.send_str(json.dumps(data))
                        app_state.stats["messages_received"] += 1
                        
                        # Если это аудио
                        if "audio" in data:
                            app_state.stats["audio_chunks_sent"] += 1
                            
                        logger.debug(f"📤 {direction}: {type(message)} отправлено")
                    except:
                        # Просто пересылаем как есть
                        await target.send_str(message)
                        
                elif isinstance(message, bytes):
                    # Бинарное сообщение
                    await target.send_bytes(message)
                    logger.debug(f"📤 {direction}: бинарные данные отправлены")
                    
                else:
                    # WebSocketMessage
                    if message.type == aiohttp.WSMsgType.TEXT:
                        try:
                            data = json.loads(message.data)
                            await target.send_str(json.dumps(data))
                            
                            if "audio" in data:
                                app_state.stats["audio_chunks_sent"] += 1
                                
                        except:
                            # Просто пересылаем как есть
                            await target.send_str(message.data)
                            
                    elif message.type == aiohttp.WSMsgType.BINARY:
                        await target.send_bytes(message.data)
                        
                    elif message.type == aiohttp.WSMsgType.CLOSED:
                        logger.info(f"WebSocket закрыт: {direction}")
                        break
                        
                    elif message.type == aiohttp.WSMsgType.ERROR:
                        logger.error(f"WebSocket ошибка: {message.data}")
                        break
        
        else:
            # От ElevenLabs к клиенту
            async for message in source:
                if isinstance(message, str):
                    # Текстовое сообщение
                    try:
                        data = json.loads(message)
                        await target.send_text(json.dumps(data))
                        
                        # Если это аудио
                        if "audio" in data:
                            app_state.stats["audio_chunks_received"] += 1
                            
                        logger.debug(f"📤 {direction}: {type(message)} отправлено")
                    except:
                        # Просто пересылаем как есть
                        await target.send_text(message)
                        
                elif isinstance(message, bytes):
                    # Бинарное сообщение
                    await target.send_bytes(message)
                    logger.debug(f"📤 {direction}: бинарные данные отправлены")
                    
                else:
                    # WebSocketMessage
                    if message.type == aiohttp.WSMsgType.TEXT:
                        try:
                            data = json.loads(message.data)
                            await target.send_text(json.dumps(data))
                            
                            if "audio" in data:
                                app_state.stats["audio_chunks_received"] += 1
                                
                        except:
                            # Просто пересылаем как есть
                            await target.send_text(message.data)
                            
                    elif message.type == aiohttp.WSMsgType.BINARY:
                        await target.send_bytes(message.data)
                        
                    elif message.type == aiohttp.WSMsgType.CLOSED:
                        logger.info(f"WebSocket закрыт: {direction}")
                        break
                        
                    elif message.type == aiohttp.WSMsgType.ERROR:
                        logger.error(f"WebSocket ошибка: {message.data}")
                        break
    
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
    
    logger.info("🌐 Запуск в режиме веб-сервиса с прямым WebSocket...")
    logger.info("💡 Это полная версия с поддержкой голосового интерфейса")
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
