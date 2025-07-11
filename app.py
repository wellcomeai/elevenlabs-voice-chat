"""
🎤 Voice Assistant - 100% OpenAI Solution
Полностью готовое к продакшену решение

Stack:
- STT: OpenAI Whisper ($0.006/min)
- LLM: OpenAI GPT-4o-mini ($0.15/1M tokens) 
- TTS: OpenAI TTS-1 ($0.015/1K chars)

Автор: AI Assistant
Версия: 4.0.0 - Production Ready
"""

import asyncio
import json
import logging
import tempfile
import os
import base64
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
import uvicorn

# ===== КОНФИГУРАЦИЯ =====

# Настройка логирования для продакшена
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('voice_assistant.log') if os.path.exists('.') else logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# API ключ OpenAI (единственный нужный!)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY or OPENAI_API_KEY == "your_openai_key":
    logger.error("🚨 OPENAI_API_KEY не установлен!")
    logger.error("Установите: export OPENAI_API_KEY=sk-your-key-here")
    raise ValueError("OpenAI API key is required")

# Полная конфигурация ассистента
ASSISTANT_CONFIG = {
    "name": "Алиса",
    "version": "4.0.0",
    "description": "100% OpenAI Voice Assistant",
    
    # Система промпт
    "system_prompt": """Ты - дружелюбный голосовой ассистент по имени Алиса.

Твоя задача:
- Отвечай кратко и по существу (1-2 предложения максимум)
- Говори естественно и дружелюбно
- Помогай пользователю решать задачи
- Если не знаешь ответ, честно скажи об этом

Стиль общения:
- Используй простые слова
- Избегай технических терминов без объяснений  
- Проявляй позитивность и энтузиазм
- Будь терпеливой и понимающей""",
    
    # OpenAI Whisper STT настройки
    "whisper": {
        "model": "whisper-1",
        "language": "ru",  # Можно убрать для автоопределения
        "temperature": 0.0,  # Для стабильности
        "prompt": "Голосовой ассистент Алиса. Пользователь говорит на русском языке."
    },
    
    # OpenAI GPT настройки
    "gpt": {
        "model": "gpt-4o-mini",
        "max_tokens": 150,
        "temperature": 0.7,
        "presence_penalty": 0.1,
        "frequency_penalty": 0.1
    },
    
    # OpenAI TTS настройки  
    "tts": {
        "model": "tts-1",  # или "tts-1-hd" для лучшего качества
        "voice": "alloy",  # alloy, echo, fable, onyx, nova, shimmer
        "speed": 1.0,      # 0.25 - 4.0
        "response_format": "mp3"
    },
    
    # Технические лимиты
    "limits": {
        "max_audio_size_mb": 25,      # Лимит OpenAI Whisper
        "min_audio_duration_ms": 500, # Минимум для обработки
        "max_conversation_history": 10,
        "websocket_timeout": 300,
        "chunk_size": 8192
    }
}

# Инициализация OpenAI клиента
try:
    openai_client = OpenAI(
        api_key=OPENAI_API_KEY,
        timeout=30.0,
        max_retries=3
    )
    
    # Тест соединения
    models = openai_client.models.list()
    logger.info("✅ OpenAI client initialized successfully")
    logger.info(f"✅ Available models: {len(models.data)}")
    
except Exception as e:
    logger.error(f"❌ Failed to initialize OpenAI client: {e}")
    raise

# Создание FastAPI приложения
app = FastAPI(
    title="Voice Assistant - 100% OpenAI",
    description="Production-ready voice assistant powered entirely by OpenAI",
    version="4.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

# CORS middleware для продакшена
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене укажите конкретные домены
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== FRONTEND HTML =====

HTML_CONTENT = """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Voice Assistant - 100% OpenAI</title>
    <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🎤</text></svg>">
    <style>
        :root {
            --primary-color: #10b981;
            --secondary-color: #3b82f6;
            --accent-color: #8b5cf6;
            --error-color: #ef4444;
            --warning-color: #f59e0b;
            --text-dark: #1f2937;
            --text-light: #6b7280;
            --bg-light: #f9fafb;
            --bg-card: rgba(255, 255, 255, 0.95);
        }
        
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: linear-gradient(135deg, var(--primary-color) 0%, var(--secondary-color) 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
            line-height: 1.6;
        }
        
        .container {
            background: var(--bg-card);
            backdrop-filter: blur(20px);
            border-radius: 24px;
            padding: 40px;
            max-width: 600px;
            width: 100%;
            text-align: center;
            box-shadow: 0 25px 50px rgba(0, 0, 0, 0.1);
            border: 1px solid rgba(255, 255, 255, 0.2);
        }
        
        .header {
            margin-bottom: 30px;
        }
        
        .title {
            font-size: 32px;
            font-weight: 800;
            color: var(--text-dark);
            margin-bottom: 8px;
            background: linear-gradient(135deg, var(--primary-color), var(--secondary-color));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        
        .subtitle {
            font-size: 16px;
            color: var(--text-light);
            font-weight: 500;
        }
        
        .badge {
            display: inline-block;
            background: linear-gradient(135deg, var(--primary-color), var(--secondary-color));
            color: white;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
            margin-top: 10px;
        }
        
        .voice-section {
            margin: 40px 0;
        }
        
        .voice-button {
            width: 140px;
            height: 140px;
            border-radius: 50%;
            border: none;
            background: linear-gradient(135deg, var(--primary-color) 0%, var(--secondary-color) 100%);
            color: white;
            font-size: 32px;
            cursor: pointer;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            margin: 20px auto;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 10px 30px rgba(16, 185, 129, 0.3);
            position: relative;
            overflow: hidden;
        }
        
        .voice-button::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: linear-gradient(45deg, transparent, rgba(255,255,255,0.1), transparent);
            transform: translateX(-100%);
            transition: transform 0.6s;
        }
        
        .voice-button:hover {
            transform: scale(1.05);
            box-shadow: 0 15px 40px rgba(16, 185, 129, 0.4);
        }
        
        .voice-button:hover::before {
            transform: translateX(100%);
        }
        
        .voice-button:active {
            transform: scale(0.95);
        }
        
        .voice-button.recording {
            background: linear-gradient(135deg, var(--error-color) 0%, #dc2626 100%);
            animation: pulse 1.5s infinite;
        }
        
        .voice-button.processing {
            background: linear-gradient(135deg, var(--warning-color) 0%, #d97706 100%);
            animation: spin 2s linear infinite;
        }
        
        .voice-button.speaking {
            background: linear-gradient(135deg, var(--accent-color) 0%, #7c3aed 100%);
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
        
        .status {
            margin-top: 20px;
            font-size: 18px;
            font-weight: 500;
            color: var(--text-dark);
            min-height: 24px;
        }
        
        .conversation {
            margin-top: 30px;
            padding: 25px;
            background: var(--bg-light);
            border-radius: 16px;
            text-align: left;
            max-height: 400px;
            overflow-y: auto;
            border: 1px solid rgba(0, 0, 0, 0.05);
        }
        
        .conversation::-webkit-scrollbar {
            width: 6px;
        }
        
        .conversation::-webkit-scrollbar-track {
            background: #f1f1f1;
            border-radius: 3px;
        }
        
        .conversation::-webkit-scrollbar-thumb {
            background: var(--primary-color);
            border-radius: 3px;
        }
        
        .conversation-title {
            font-size: 16px;
            font-weight: 600;
            color: var(--text-dark);
            margin-bottom: 20px;
            text-align: center;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
        }
        
        .message {
            margin-bottom: 15px;
            padding: 12px 16px;
            border-radius: 12px;
            line-height: 1.5;
            word-wrap: break-word;
            animation: slideIn 0.3s ease-out;
        }
        
        @keyframes slideIn {
            from {
                opacity: 0;
                transform: translateY(10px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        
        .message.user {
            background: linear-gradient(135deg, #e0f2fe 0%, #b3e5fc 100%);
            color: #0277bd;
            margin-left: 20px;
            border-left: 4px solid var(--secondary-color);
        }
        
        .message.assistant {
            background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%);
            color: #166534;
            margin-right: 20px;
            border-left: 4px solid var(--primary-color);
        }
        
        .message-label {
            font-size: 12px;
            font-weight: 600;
            opacity: 0.7;
            margin-bottom: 4px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        
        .error {
            color: var(--error-color);
            background: rgba(239, 68, 68, 0.1);
            border: 1px solid rgba(239, 68, 68, 0.2);
            padding: 15px;
            border-radius: 12px;
            margin-top: 20px;
            display: none;
            animation: shake 0.5s ease-in-out;
        }
        
        @keyframes shake {
            0%, 100% { transform: translateX(0); }
            25% { transform: translateX(-5px); }
            75% { transform: translateX(5px); }
        }
        
        .tech-stack {
            margin-top: 30px;
            padding: 20px;
            background: linear-gradient(135deg, rgba(16, 185, 129, 0.05), rgba(59, 130, 246, 0.05));
            border-radius: 16px;
            border: 1px solid rgba(16, 185, 129, 0.1);
        }
        
        .tech-stack h4 {
            color: var(--text-dark);
            margin-bottom: 15px;
            font-size: 16px;
            font-weight: 600;
        }
        
        .tech-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            text-align: left;
        }
        
        .tech-item {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 14px;
            color: var(--text-light);
        }
        
        .tech-item .icon {
            font-size: 16px;
        }
        
        .cost-info {
            margin-top: 20px;
            padding: 15px;
            background: rgba(16, 185, 129, 0.05);
            border-radius: 12px;
            font-size: 13px;
            color: var(--text-light);
            text-align: center;
        }
        
        .loading {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid #f3f3f3;
            border-top: 3px solid var(--primary-color);
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }
        
        @media (max-width: 640px) {
            .container {
                padding: 30px 20px;
            }
            
            .voice-button {
                width: 120px;
                height: 120px;
                font-size: 28px;
            }
            
            .title {
                font-size: 28px;
            }
            
            .tech-grid {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1 class="title">🎤 Голосовой Ассистент</h1>
            <p class="subtitle">100% OpenAI • Готов к продакшену</p>
            <span class="badge">v4.0.0</span>
        </div>
        
        <div class="voice-section">
            <button class="voice-button" id="voiceButton">
                <span id="buttonIcon">🎤</span>
            </button>
            
            <div class="status" id="statusText">Нажмите для начала разговора</div>
        </div>
        
        <div class="conversation" id="conversation">
            <div class="conversation-title">
                💬 История разговора
            </div>
            <div style="text-align: center; color: var(--text-light); font-style: italic;">
                Ваш разговор с Алисой появится здесь...
            </div>
        </div>
        
        <div class="error" id="errorMsg"></div>
        
        <div class="tech-stack">
            <h4>🔧 Технологический стек</h4>
            <div class="tech-grid">
                <div class="tech-item">
                    <span class="icon">🎤</span>
                    <span>STT: OpenAI Whisper</span>
                </div>
                <div class="tech-item">
                    <span class="icon">🧠</span>
                    <span>LLM: GPT-4o-mini</span>
                </div>
                <div class="tech-item">
                    <span class="icon">🔊</span>
                    <span>TTS: OpenAI TTS-1</span>
                </div>
                <div class="tech-item">
                    <span class="icon">⚡</span>
                    <span>Режим: Realtime</span>
                </div>
            </div>
            
            <div class="cost-info">
                💰 Стоимость: ~$0.01 за минуту разговора • Без внезапных блокировок
            </div>
        </div>
    </div>

    <script>
        class OpenAIVoiceAssistant {
            constructor() {
                this.ws = null;
                this.mediaRecorder = null;
                this.audioChunks = [];
                this.isRecording = false;
                this.isProcessing = false;
                this.isSpeaking = false;
                this.audioQueue = [];
                this.currentAudio = null;
                this.conversationStartTime = null;
                
                this.initElements();
                this.connect();
                this.bindEvents();
                
                console.log('🎤 OpenAI Voice Assistant v4.0.0 initialized');
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
                    console.log('✅ WebSocket connected');
                    this.status.textContent = 'Готов к работе! Нажмите для записи';
                    this.hideError();
                };
                
                this.ws.onmessage = (event) => {
                    try {
                        const data = JSON.parse(event.data);
                        this.handleMessage(data);
                    } catch (error) {
                        console.error('Failed to parse WebSocket message:', error);
                    }
                };
                
                this.ws.onclose = (event) => {
                    console.log('WebSocket disconnected:', event.code, event.reason);
                    this.status.textContent = 'Соединение потеряно';
                    this.showError('Соединение с сервером потеряно. Обновите страницу.');
                };
                
                this.ws.onerror = (error) => {
                    console.error('WebSocket error:', error);
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
                
                // Keyboard shortcuts
                document.addEventListener('keydown', (event) => {
                    if (event.code === 'Space' && !event.repeat) {
                        event.preventDefault();
                        if (!this.isRecording && !this.isProcessing) {
                            this.startRecording();
                        }
                    }
                });
                
                document.addEventListener('keyup', (event) => {
                    if (event.code === 'Space') {
                        event.preventDefault();
                        if (this.isRecording) {
                            this.stopRecording();
                        }
                    }
                });
            }
            
            async startRecording() {
                try {
                    this.hideError();
                    
                    if (!this.conversationStartTime) {
                        this.conversationStartTime = Date.now();
                    }
                    
                    const stream = await navigator.mediaDevices.getUserMedia({
                        audio: {
                            echoCancellation: true,
                            noiseSuppression: true,
                            autoGainControl: true,
                            sampleRate: 48000,
                            channelCount: 1
                        }
                    });

                    // Try different MIME types for better compatibility
                    const mimeTypes = [
                        'audio/webm;codecs=opus',
                        'audio/webm',
                        'audio/ogg;codecs=opus',
                        'audio/mp4'
                    ];
                    
                    let selectedMimeType = null;
                    for (const mimeType of mimeTypes) {
                        if (MediaRecorder.isTypeSupported(mimeType)) {
                            selectedMimeType = mimeType;
                            break;
                        }
                    }
                    
                    if (!selectedMimeType) {
                        throw new Error('No supported audio format found');
                    }

                    this.mediaRecorder = new MediaRecorder(stream, {
                        mimeType: selectedMimeType,
                        audioBitsPerSecond: 128000
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
                    this.status.textContent = 'Говорите... (Пробел для остановки)';

                } catch (error) {
                    console.error('Recording error:', error);
                    this.showError(`Ошибка доступа к микрофону: ${error.message}`);
                }
            }
            
            stopRecording() {
                if (this.mediaRecorder && this.isRecording) {
                    this.mediaRecorder.stop();
                    this.isRecording = false;
                    this.isProcessing = true;
                    this.updateUI();
                    this.status.textContent = 'OpenAI Whisper обрабатывает...';
                }
            }
            
            async processAudio() {
                try {
                    const audioBlob = new Blob(this.audioChunks, { 
                        type: this.mediaRecorder.mimeType 
                    });
                    
                    console.log(`Processing audio: ${audioBlob.size} bytes, type: ${audioBlob.type}`);
                    
                    if (audioBlob.size < 1000) {
                        this.showError('Запись слишком короткая. Попробуйте говорить дольше.');
                        this.resetState();
                        return;
                    }
                    
                    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                        const reader = new FileReader();
                        reader.onload = () => {
                            const audioData = new Uint8Array(reader.result);
                            this.ws.send(JSON.stringify({
                                type: 'audio_data',
                                data: Array.from(audioData),
                                metadata: {
                                    size: audioBlob.size,
                                    mimeType: audioBlob.type,
                                    timestamp: Date.now()
                                }
                            }));
                        };
                        reader.readAsArrayBuffer(audioBlob);
                    } else {
                        this.showError('Соединение с сервером потеряно');
                        this.resetState();
                    }

                } catch (error) {
                    console.error('Audio processing error:', error);
                    this.showError(`Ошибка обработки аудио: ${error.message}`);
                    this.resetState();
                }
            }
            
            handleMessage(data) {
                console.log('Received:', data.type, data);

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
                        this.status.textContent = 'OpenAI TTS озвучивает...';
                        this.audioQueue = [];
                        break;

                    case 'audio_chunk':
                        this.audioQueue.push(data.audio);
                        if (this.audioQueue.length === 1) {
                            this.playAudioQueue();
                        }
                        break;

                    case 'tts_end':
                        // Wait a bit for last audio chunks
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
                        
                    case 'stats':
                        console.log('Session stats:', data);
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
                    
                    // Important for mobile devices
                    this.currentAudio.playsInline = true;

                    this.currentAudio.onended = () => {
                        URL.revokeObjectURL(audioUrl);
                        if (this.audioQueue.length > 0) {
                            this.playAudioQueue();
                        } else if (!this.isSpeaking) {
                            this.resetState();
                        }
                    };

                    this.currentAudio.onerror = (error) => {
                        console.error('Audio playback error:', error);
                        URL.revokeObjectURL(audioUrl);
                        this.playAudioQueue();
                    };

                    await this.currentAudio.play();

                } catch (error) {
                    console.error('Playback error:', error);
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
                // Clear initial message
                if (role === 'user' && this.conversation.innerHTML.includes('появится здесь')) {
                    this.conversation.innerHTML = '<div class="conversation-title">💬 История разговора</div>';
                }

                const messageDiv = document.createElement('div');
                messageDiv.className = `message ${role}`;
                
                const labelDiv = document.createElement('div');
                labelDiv.className = 'message-label';
                labelDiv.textContent = role === 'user' ? 'Вы' : 'Алиса';
                
                const textDiv = document.createElement('div');
                textDiv.textContent = text;
                
                messageDiv.appendChild(labelDiv);
                messageDiv.appendChild(textDiv);
                
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
                    this.icon.innerHTML = '<div class="loading"></div>';
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
                this.status.textContent = 'Готов к работе! Нажмите для записи';
            }
            
            showError(message) {
                this.errorMsg.textContent = message;
                this.errorMsg.style.display = 'block';
                
                // Auto-hide after 5 seconds
                setTimeout(() => {
                    this.hideError();
                }, 5000);
            }
            
            hideError() {
                this.errorMsg.style.display = 'none';
            }
        }

        // Initialize when DOM is ready
        document.addEventListener('DOMContentLoaded', () => {
            window.voiceAssistant = new OpenAIVoiceAssistant();
        });
    </script>
</body>
</html>"""

# ===== ОСНОВНОЙ КЛАСС ОБРАБОТЧИКА =====

class OpenAIVoiceHandler:
    """
    Полный обработчик голосового ассистента на OpenAI
    
    Возможности:
    - STT через OpenAI Whisper
    - LLM через OpenAI GPT-4o-mini  
    - TTS через OpenAI TTS-1
    - Управление сессиями и контекстом
    - Подробная статистика использования
    """
    
    def __init__(self):
        self.session_id = str(uuid.uuid4())
        self.conversation_history = []
        self.stats = {
            "session_start": time.time(),
            "messages_processed": 0,
            "total_audio_duration": 0,
            "total_characters_spoken": 0,
            "whisper_calls": 0,
            "gpt_calls": 0,
            "tts_calls": 0,
            "errors": 0
        }
        
        logger.info(f"🎤 New voice session started: {self.session_id}")
    
    async def process_audio_to_text(self, audio_data: bytes) -> str:
        """
        STT через OpenAI Whisper API
        """
        try:
            start_time = time.time()
            
            logger.info(f"[WHISPER] Processing {len(audio_data)} bytes")
            
            # Проверки
            if len(audio_data) < 1000:
                logger.warning("[WHISPER] Audio too short")
                return "Запись слишком короткая. Попробуйте говорить дольше."
            
            if len(audio_data) > ASSISTANT_CONFIG["limits"]["max_audio_size_mb"] * 1024 * 1024:
                logger.warning(f"[WHISPER] Audio too large: {len(audio_data)} bytes")
                return "Аудио файл слишком большой. Максимум 25MB."
            
            # Создаем временный файл
            temp_file = None
            try:
                with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as f:
                    f.write(audio_data)
                    temp_file = f.name
                
                logger.info(f"[WHISPER] Temp file created: {temp_file}")
                
                # Вызов OpenAI Whisper API
                with open(temp_file, 'rb') as audio_file:
                    transcript_response = openai_client.audio.transcriptions.create(
                        model=ASSISTANT_CONFIG["whisper"]["model"],
                        file=audio_file,
                        language=ASSISTANT_CONFIG["whisper"]["language"],
                        temperature=ASSISTANT_CONFIG["whisper"]["temperature"],
                        prompt=ASSISTANT_CONFIG["whisper"]["prompt"]
                    )
                
                transcript = transcript_response.text.strip()
                
                # Статистика
                duration = time.time() - start_time
                self.stats["whisper_calls"] += 1
                self.stats["total_audio_duration"] += duration
                
                if transcript and len(transcript) > 1:
                    logger.info(f"[WHISPER] Success ({duration:.2f}s): {transcript}")
                    return transcript
                else:
                    logger.warning("[WHISPER] Empty transcript")
                    return "Не удалось распознать речь. Попробуйте говорить четче."
                
            finally:
                # Очистка временного файла
                if temp_file and os.path.exists(temp_file):
                    try:
                        os.unlink(temp_file)
                        logger.debug(f"[WHISPER] Temp file deleted: {temp_file}")
                    except Exception as e:
                        logger.warning(f"[WHISPER] Failed to delete temp file: {e}")
            
        except Exception as e:
            self.stats["errors"] += 1
            logger.error(f"[WHISPER] Error: {e}")
            return f"Ошибка распознавания речи: {str(e)}"
    
    async def generate_response(self, user_message: str) -> str:
        """
        Генерация ответа через OpenAI GPT
        """
        try:
            start_time = time.time()
            
            logger.info(f"[GPT] Generating response for: {user_message[:50]}...")
            
            # Обновляем историю
            self.conversation_history.append({
                "role": "user", 
                "content": user_message
            })
            
            # Ограничиваем историю
            max_history = ASSISTANT_CONFIG["limits"]["max_conversation_history"]
            if len(self.conversation_history) > max_history:
                self.conversation_history = self.conversation_history[-max_history:]
            
            # Формируем сообщения для GPT
            messages = [
                {
                    "role": "system", 
                    "content": ASSISTANT_CONFIG["system_prompt"]
                }
            ] + self.conversation_history
            
            # Вызов OpenAI GPT API
            completion = openai_client.chat.completions.create(
                model=ASSISTANT_CONFIG["gpt"]["model"],
                messages=messages,
                max_tokens=ASSISTANT_CONFIG["gpt"]["max_tokens"],
                temperature=ASSISTANT_CONFIG["gpt"]["temperature"],
                presence_penalty=ASSISTANT_CONFIG["gpt"]["presence_penalty"],
                frequency_penalty=ASSISTANT_CONFIG["gpt"]["frequency_penalty"]
            )
            
            assistant_response = completion.choices[0].message.content.strip()
            
            # Обновляем историю
            self.conversation_history.append({
                "role": "assistant",
                "content": assistant_response
            })
            
            # Статистика
            duration = time.time() - start_time
            self.stats["gpt_calls"] += 1
            self.stats["messages_processed"] += 1
            
            logger.info(f"[GPT] Success ({duration:.2f}s): {assistant_response}")
            return assistant_response
            
        except Exception as e:
            self.stats["errors"] += 1
            logger.error(f"[GPT] Error: {e}")
            return "Извините, произошла ошибка при генерации ответа. Попробуйте еще раз."
    
    async def synthesize_speech(self, text: str, websocket: WebSocket) -> None:
        """
        TTS через OpenAI TTS API с потоковой передачей
        """
        try:
            start_time = time.time()
            
            logger.info(f"[TTS] Synthesizing: {text[:50]}...")
            
            # Уведомляем о начале
            await websocket.send_json({
                "type": "tts_start",
                "text": text
            })
            
            # Создаем временный файл для TTS
            temp_file = None
            try:
                with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f:
                    temp_file = f.name
                
                # Вызов OpenAI TTS API
                tts_response = openai_client.audio.speech.create(
                    model=ASSISTANT_CONFIG["tts"]["model"],
                    voice=ASSISTANT_CONFIG["tts"]["voice"],
                    input=text,
                    speed=ASSISTANT_CONFIG["tts"]["speed"],
                    response_format=ASSISTANT_CONFIG["tts"]["response_format"]
                )
                
                # Сохраняем аудио
                tts_response.stream_to_file(temp_file)
                
                logger.info(f"[TTS] Audio generated: {temp_file}")
                
                # Читаем и отправляем чанками
                with open(temp_file, 'rb') as audio_file:
                    audio_content = audio_file.read()
                
                chunk_size = ASSISTANT_CONFIG["limits"]["chunk_size"]
                chunk_count = 0
                
                for i in range(0, len(audio_content), chunk_size):
                    chunk = audio_content[i:i + chunk_size]
                    chunk_count += 1
                    
                    audio_b64 = base64.b64encode(chunk).decode('utf-8')
                    await websocket.send_json({
                        "type": "audio_chunk",
                        "audio": audio_b64,
                        "chunk_id": chunk_count
                    })
                
                # Уведомляем о завершении
                await websocket.send_json({
                    "type": "tts_end",
                    "total_chunks": chunk_count,
                    "total_size": len(audio_content)
                })
                
                # Статистика
                duration = time.time() - start_time
                self.stats["tts_calls"] += 1
                self.stats["total_characters_spoken"] += len(text)
                
                logger.info(f"[TTS] Success ({duration:.2f}s): {chunk_count} chunks, {len(audio_content)} bytes")
                
            finally:
                # Очистка
                if temp_file and os.path.exists(temp_file):
                    try:
                        os.unlink(temp_file)
                        logger.debug(f"[TTS] Temp file deleted: {temp_file}")
                    except Exception as e:
                        logger.warning(f"[TTS] Failed to delete temp file: {e}")
            
        except Exception as e:
            self.stats["errors"] += 1
            logger.error(f"[TTS] Error: {e}")
            
            # Fallback: отправляем текст вместо аудио
            await websocket.send_json({
                "type": "response",
                "text": text
            })
            
            await websocket.send_json({
                "type": "processing_complete"
            })
    
    def get_session_stats(self) -> dict:
        """Получить статистику сессии"""
        session_duration = time.time() - self.stats["session_start"]
        
        return {
            "session_id": self.session_id,
            "session_duration_minutes": round(session_duration / 60, 2),
            "messages_processed": self.stats["messages_processed"],
            "total_audio_duration_seconds": round(self.stats["total_audio_duration"], 2),
            "total_characters_spoken": self.stats["total_characters_spoken"],
            "api_calls": {
                "whisper": self.stats["whisper_calls"],
                "gpt": self.stats["gpt_calls"],
                "tts": self.stats["tts_calls"]
            },
            "errors": self.stats["errors"]
        }

# ===== API ENDPOINTS =====

@app.get("/")
async def get_homepage():
    """Главная страница приложения"""
    return HTMLResponse(content=HTML_CONTENT)

@app.get("/api/health")
async def health_check():
    """Health check endpoint для мониторинга"""
    try:
        # Тест OpenAI соединения
        models = openai_client.models.list()
        
        return JSONResponse({
            "status": "healthy",
            "service": "Voice Assistant",
            "version": ASSISTANT_CONFIG["version"],
            "description": ASSISTANT_CONFIG["description"],
            "components": {
                "openai_client": "connected",
                "available_models": len(models.data),
                "whisper_model": ASSISTANT_CONFIG["whisper"]["model"],
                "gpt_model": ASSISTANT_CONFIG["gpt"]["model"],
                "tts_model": ASSISTANT_CONFIG["tts"]["model"],
                "tts_voice": ASSISTANT_CONFIG["tts"]["voice"]
            },
            "limits": ASSISTANT_CONFIG["limits"],
            "timestamp": time.time()
        })
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail=f"Service unhealthy: {e}")

@app.get("/api/config")
async def get_config():
    """Получить конфигурацию ассистента"""
    return JSONResponse({
        "name": ASSISTANT_CONFIG["name"],
        "version": ASSISTANT_CONFIG["version"],
        "models": {
            "whisper": ASSISTANT_CONFIG["whisper"]["model"],
            "gpt": ASSISTANT_CONFIG["gpt"]["model"],
            "tts": ASSISTANT_CONFIG["tts"]["model"]
        },
        "voice": ASSISTANT_CONFIG["tts"]["voice"],
        "limits": ASSISTANT_CONFIG["limits"]
    })

# ===== WEBSOCKET ENDPOINT =====

@app.websocket("/ws/voice")
async def websocket_voice_endpoint(websocket: WebSocket):
    """
    Основной WebSocket endpoint для голосового взаимодействия
    """
    await websocket.accept()
    
    handler = OpenAIVoiceHandler()
    logger.info(f"[WS] Client connected: {handler.session_id}")
    
    try:
        while True:
            # Получаем сообщение от клиента
            message = await websocket.receive_json()
            message_type = message.get("type")
            
            if message_type == "audio_data":
                try:
                    # Извлекаем аудио данные
                    audio_bytes = bytes(message["data"])
                    metadata = message.get("metadata", {})
                    
                    logger.info(f"[WS] Received audio: {len(audio_bytes)} bytes")
                    
                    # 1. STT - Whisper
                    transcript = await handler.process_audio_to_text(audio_bytes)
                    
                    if transcript and not transcript.startswith("Ошибка") and not transcript.startswith("Запись"):
                        # Отправляем транскрипцию
                        await websocket.send_json({
                            "type": "transcription",
                            "text": transcript
                        })
                        
                        # 2. LLM - GPT
                        response = await handler.generate_response(transcript)
                        
                        # Отправляем текстовый ответ
                        await websocket.send_json({
                            "type": "response",
                            "text": response
                        })
                        
                        # 3. TTS - OpenAI TTS
                        await handler.synthesize_speech(response, websocket)
                        
                        # Отправляем сигнал завершения
                        await websocket.send_json({
                            "type": "processing_complete"
                        })
                        
                    else:
                        # Ошибка STT
                        await websocket.send_json({
                            "type": "error",
                            "message": transcript
                        })
                    
                except Exception as e:
                    logger.error(f"[WS] Error processing audio: {e}")
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Ошибка обработки: {str(e)}"
                    })
            
            elif message_type == "get_stats":
                # Отправляем статистику
                stats = handler.get_session_stats()
                await websocket.send_json({
                    "type": "stats",
                    "data": stats
                })
            
            else:
                logger.warning(f"[WS] Unknown message type: {message_type}")
    
    except WebSocketDisconnect:
        stats = handler.get_session_stats()
        logger.info(f"[WS] Client disconnected: {handler.session_id}")
        logger.info(f"[WS] Session stats: {stats}")
    
    except Exception as e:
        logger.error(f"[WS] Unexpected error: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": "Внутренняя ошибка сервера"
            })
        except:
            pass

# ===== ЗАПУСК ПРИЛОЖЕНИЯ =====

def main():
    """Точка входа для запуска приложения"""
    
    logger.info("🚀 Starting OpenAI Voice Assistant v4.0.0")
    logger.info(f"🔑 OpenAI API configured: {bool(OPENAI_API_KEY)}")
    logger.info(f"🎤 Whisper model: {ASSISTANT_CONFIG['whisper']['model']}")
    logger.info(f"🧠 GPT model: {ASSISTANT_CONFIG['gpt']['model']}")
    logger.info(f"🔊 TTS model: {ASSISTANT_CONFIG['tts']['model']} ({ASSISTANT_CONFIG['tts']['voice']})")
    
    # Порт для Render.com или локальной разработки
    port = int(os.getenv("PORT", 8000))
    
    # Запуск сервера
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info",
        access_log=True,
        server_header=False,
        date_header=False
    )

if __name__ == "__main__":
    main()
