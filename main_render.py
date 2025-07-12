#!/usr/bin/env python3
"""
ElevenLabs Conversational AI - Complete Render Version
HTML встроен прямо в код для надежности
"""

import os
import logging
import time
from typing import Optional
import aiohttp
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPI приложение
app = FastAPI(
    title="ElevenLabs Voice Assistant",
    description="Python версия с прямым подключением к ElevenLabs",
    version="1.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Конфигурация
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "sk_95a5725ca01fdba20e15bd662d8b76152971016ff045377f")
AGENT_ID = os.getenv("AGENT_ID", "agent_01jzwcew2ferttga9m1zcn3js1")

# Состояние
app_state = {
    "start_time": time.time(),
    "api_key_configured": bool(ELEVENLABS_API_KEY),
    "agent_id": AGENT_ID
}

@app.on_event("startup")
async def startup_event():
    """Инициализация при запуске"""
    logger.info(f"🚀 Запуск сервера...")
    logger.info(f"🔑 API Key: {'Configured' if ELEVENLABS_API_KEY else 'Missing'}")
    logger.info(f"🤖 Agent ID: {AGENT_ID}")

@app.get("/", response_class=HTMLResponse)
async def get_homepage():
    """Главная страница со встроенным HTML"""
    return HTMLResponse(content="""
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ElevenLabs Voice Chat</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #333;
        }

        .container {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            padding: 2rem;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
            width: 100%;
            max-width: 500px;
            text-align: center;
        }

        .header {
            margin-bottom: 2rem;
        }

        .title {
            font-size: 2rem;
            font-weight: bold;
            background: linear-gradient(45deg, #667eea, #764ba2);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.5rem;
        }

        .subtitle {
            color: #666;
            font-size: 1rem;
        }

        .status {
            margin: 1rem 0;
            padding: 1rem;
            border-radius: 10px;
            font-weight: 500;
            transition: all 0.3s ease;
        }

        .status.disconnected {
            background: #fee;
            color: #c53030;
            border-left: 4px solid #c53030;
        }

        .status.connecting {
            background: #fef5e7;
            color: #d69e2e;
            border-left: 4px solid #d69e2e;
        }

        .status.connected {
            background: #f0fff4;
            color: #38a169;
            border-left: 4px solid #38a169;
        }

        .status.listening {
            background: #e6fffa;
            color: #319795;
            border-left: 4px solid #319795;
            animation: listening-pulse 2s infinite;
        }

        .status.speaking {
            background: #ebf8ff;
            color: #3182ce;
            border-left: 4px solid #3182ce;
            animation: pulse 1.5s infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.7; }
        }

        @keyframes listening-pulse {
            0%, 100% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.8; transform: scale(1.02); }
        }

        .controls {
            margin: 2rem 0;
            display: flex;
            gap: 1rem;
            justify-content: center;
            flex-wrap: wrap;
        }

        .btn {
            padding: 1rem 2rem;
            border: none;
            border-radius: 50px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
        }

        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
        }

        .btn:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
        }

        .btn-primary {
            background: linear-gradient(45deg, #667eea, #764ba2);
            color: white;
        }

        .btn-danger {
            background: linear-gradient(45deg, #ff6b6b, #ee5a52);
            color: white;
        }

        .chat-area {
            background: #f8f9fa;
            border-radius: 15px;
            padding: 1.5rem;
            margin: 1rem 0;
            min-height: 200px;
            max-height: 300px;
            overflow-y: auto;
            text-align: left;
        }

        .message {
            margin: 0.5rem 0;
            padding: 0.75rem 1rem;
            border-radius: 10px;
            max-width: 80%;
            word-wrap: break-word;
        }

        .message.user {
            background: linear-gradient(45deg, #667eea, #764ba2);
            color: white;
            margin-left: auto;
            text-align: right;
        }

        .message.assistant {
            background: #e9ecef;
            color: #333;
            border-left: 3px solid #667eea;
        }

        .message.system {
            background: #fff3cd;
            color: #856404;
            text-align: center;
            margin: 0 auto;
            font-style: italic;
        }

        .mic-animation {
            width: 80px;
            height: 80px;
            border-radius: 50%;
            background: linear-gradient(45deg, #667eea, #764ba2);
            margin: 1rem auto;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-size: 2rem;
            transition: all 0.3s ease;
        }

        .mic-animation.recording {
            animation: mic-recording 1.5s infinite;
            background: linear-gradient(45deg, #ff4757, #ff3742);
        }

        .mic-animation.listening {
            animation: mic-listening 2s infinite;
            background: linear-gradient(45deg, #2ed573, #1e90ff);
        }

        @keyframes mic-recording {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.1); }
        }

        @keyframes mic-listening {
            0%, 100% { transform: scale(1); opacity: 1; }
            50% { transform: scale(1.05); opacity: 0.8; }
        }

        .volume-indicator {
            width: 100%;
            height: 6px;
            background: #e9ecef;
            border-radius: 3px;
            margin: 1rem 0;
            overflow: hidden;
        }

        .volume-bar {
            height: 100%;
            background: linear-gradient(45deg, #667eea, #764ba2);
            border-radius: 3px;
            transition: width 0.1s ease;
            width: 0%;
        }

        .footer {
            margin-top: 2rem;
            padding-top: 1rem;
            border-top: 1px solid #e9ecef;
            color: #666;
            font-size: 0.9rem;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1 class="title">🎤 Voice Assistant</h1>
            <p class="subtitle">Powered by ElevenLabs AI</p>
        </div>

        <div id="status" class="status disconnected">
            🔴 Отключен
        </div>

        <div class="controls">
            <button id="connectBtn" class="btn btn-primary">
                🔗 Подключиться
            </button>
            <button id="disconnectBtn" class="btn btn-danger" disabled>
                ⛔ Отключиться
            </button>
        </div>

        <div class="mic-animation" id="micAnimation">
            🎤
        </div>

        <div class="volume-indicator">
            <div class="volume-bar" id="volumeBar"></div>
        </div>

        <div class="chat-area" id="chatArea">
            <div class="message system">
                Нажмите "Подключиться" чтобы начать разговор
            </div>
        </div>

        <div class="footer">
            <p>Agent ID: <span id="agentId">Загрузка...</span></p>
        </div>
    </div>

    <script>
        class VoiceChat {
            constructor() {
                console.log('🚀 VoiceChat constructor started');
                
                this.ws = null;
                this.isConnected = false;
                this.isInitialized = false;
                this.agentId = null;
                this.conversationId = null;
                
                this.audioStream = null;
                this.audioContext = null;
                this.audioProcessor = null;
                this.isAgentSpeaking = false;
                
                this.initializeElements();
                this.loadAgentConfig();
            }

            initializeElements() {
                this.connectBtn = document.getElementById('connectBtn');
                this.disconnectBtn = document.getElementById('disconnectBtn');
                this.status = document.getElementById('status');
                this.chatArea = document.getElementById('chatArea');
                this.micAnimation = document.getElementById('micAnimation');
                this.volumeBar = document.getElementById('volumeBar');
                this.agentIdSpan = document.getElementById('agentId');

                this.connectBtn.addEventListener('click', () => this.connect());
                this.disconnectBtn.addEventListener('click', () => this.disconnect());
            }

            async loadAgentConfig() {
                try {
                    console.log('📡 Loading agent config');
                    const response = await fetch('/api/agent-id');
                    const data = await response.json();
                    
                    console.log('Agent config:', data);
                    
                    if (data.agent_id && data.status === 'ready') {
                        this.agentId = data.agent_id;
                        this.agentIdSpan.textContent = this.agentId.substring(0, 12) + '...';
                        this.addMessage('system', '✅ Агент готов');
                        this.connectBtn.disabled = false;
                    }
                } catch (error) {
                    console.error('Failed to load agent:', error);
                    this.addMessage('system', '❌ Ошибка загрузки агента');
                }
            }

            async connect() {
                if (!this.agentId) {
                    this.addMessage('system', '❌ Агент не готов');
                    return;
                }

                try {
                    this.updateStatus('connecting', '🟡 Подключение...');
                    
                    // Запрашиваем микрофон
                    this.audioStream = await navigator.mediaDevices.getUserMedia({ 
                        audio: {
                            sampleRate: 16000,
                            channelCount: 1,
                            echoCancellation: true,
                            noiseSuppression: true,
                            autoGainControl: true
                        } 
                    });

                    // Получаем URL для подключения
                    let wsUrl;
                    try {
                        const signedResponse = await fetch('/api/signed-url');
                        const signedData = await signedResponse.json();
                        
                        if (signedResponse.ok && signedData.signed_url) {
                            wsUrl = signedData.signed_url;
                            console.log('✅ Using signed URL');
                        } else {
                            wsUrl = signedData.fallback_url || 
                                   `wss://api.elevenlabs.io/v1/convai/conversation?agent_id=${this.agentId}`;
                            console.log('⚠️ Using fallback URL');
                        }
                    } catch (error) {
                        wsUrl = `wss://api.elevenlabs.io/v1/convai/conversation?agent_id=${this.agentId}`;
                        console.log('⚠️ Using direct URL');
                    }

                    // ВАЖНО: Подключаемся НАПРЯМУЮ к ElevenLabs!
                    console.log('🔗 Connecting to ElevenLabs:', wsUrl);
                    this.ws = new WebSocket(wsUrl);
                    
                    this.ws.onopen = () => this.onWebSocketOpen();
                    this.ws.onmessage = (event) => this.onWebSocketMessage(event);
                    this.ws.onclose = (event) => this.onWebSocketClose(event);
                    this.ws.onerror = (error) => this.onWebSocketError(error);

                } catch (error) {
                    console.error('Connection failed:', error);
                    this.addMessage('system', `❌ Ошибка: ${error.message}`);
                    this.updateStatus('disconnected', '🔴 Отключен');
                }
            }

            onWebSocketOpen() {
                console.log('✅ WebSocket connected');
                this.isConnected = true;
                this.updateStatus('connecting', '🟡 Инициализация...');
                
                // Отправляем инициализацию
                const initMessage = {
                    type: "conversation_initiation_client_data"
                };
                
                this.ws.send(JSON.stringify(initMessage));
                this.startKeepAlive();
            }

            onWebSocketMessage(event) {
                try {
                    const data = JSON.parse(event.data);
                    console.log('Received:', data.type);

                    switch (data.type) {
                        case 'conversation_initiation_metadata':
                            this.handleInitiation(data);
                            break;
                        case 'user_transcript':
                            this.handleUserTranscript(data);
                            break;
                        case 'agent_response':
                            this.handleAgentResponse(data);
                            break;
                        case 'audio':
                            this.handleAudioResponse(data);
                            break;
                        case 'interruption':
                            this.isAgentSpeaking = false;
                            this.updateStatus('listening', '🟢 Слушаю...');
                            break;
                    }
                } catch (error) {
                    console.error('Error parsing message:', error);
                }
            }

            handleInitiation(data) {
                const metadata = data.conversation_initiation_metadata_event;
                this.isInitialized = true;
                this.conversationId = metadata.conversation_id;
                this.updateStatus('listening', '🟢 Слушаю...');
                
                this.addMessage('system', '✅ Готов к разговору');
                
                this.connectBtn.disabled = true;
                this.disconnectBtn.disabled = false;
                
                this.startRecording();
            }

            handleUserTranscript(data) {
                const transcript = data.user_transcription_event.user_transcript;
                if (transcript.trim()) {
                    this.addMessage('user', transcript);
                }
            }

            handleAgentResponse(data) {
                const response = data.agent_response_event.agent_response;
                this.addMessage('assistant', response);
                this.isAgentSpeaking = true;
                this.updateStatus('speaking', '🔊 Говорю...');
            }

            async handleAudioResponse(data) {
                try {
                    const audioBase64 = data.audio_event.audio_base_64;
                    
                    // Декодируем base64
                    const audioData = atob(audioBase64);
                    const pcmArray = new Uint8Array(audioData.length);
                    
                    for (let i = 0; i < audioData.length; i++) {
                        pcmArray[i] = audioData.charCodeAt(i);
                    }

                    // Создаем WAV
                    const wavBlob = this.createWavBlob(pcmArray, 16000, 1, 16);
                    const audioUrl = URL.createObjectURL(wavBlob);
                    
                    // Воспроизводим
                    const audio = new Audio(audioUrl);
                    audio.onended = () => {
                        URL.revokeObjectURL(audioUrl);
                        if (!this.isAgentSpeaking) {
                            this.updateStatus('listening', '🟢 Слушаю...');
                        }
                    };
                    
                    await audio.play();
                    
                } catch (error) {
                    console.error('Error playing audio:', error);
                }
            }

            onWebSocketClose(event) {
                console.log('WebSocket closed:', event);
                this.isConnected = false;
                this.updateStatus('disconnected', '🔴 Отключен');
                this.addMessage('system', '🔌 Соединение закрыто');
                
                this.stopRecording();
                this.stopKeepAlive();
                
                this.connectBtn.disabled = false;
                this.disconnectBtn.disabled = true;
            }

            onWebSocketError(error) {
                console.error('WebSocket error:', error);
                this.addMessage('system', '❌ Ошибка соединения');
            }

            async startRecording() {
                if (!this.audioStream) return;

                try {
                    this.audioContext = new (window.AudioContext || window.webkitAudioContext)({
                        sampleRate: 16000
                    });
                    
                    const source = this.audioContext.createMediaStreamSource(this.audioStream);
                    this.audioProcessor = this.audioContext.createScriptProcessor(4096, 1, 1);
                    
                    this.audioProcessor.onaudioprocess = (event) => {
                        if (this.ws && this.ws.readyState === WebSocket.OPEN && 
                            !this.isAgentSpeaking && this.isInitialized) {
                            
                            const channelData = event.inputBuffer.getChannelData(0);
                            
                            // Конвертируем в PCM16
                            const pcmData = this.convertToPCM16(channelData);
                            const base64Audio = this.arrayBufferToBase64(pcmData);
                            
                            // Отправляем
                            const message = {
                                user_audio_chunk: base64Audio
                            };
                            
                            this.ws.send(JSON.stringify(message));
                            
                            // Обновляем индикатор
                            const volume = this.calculateVolume(channelData);
                            this.volumeBar.style.width = (volume * 100) + '%';
                        }
                    };
                    
                    source.connect(this.audioProcessor);
                    this.audioProcessor.connect(this.audioContext.destination);
                    
                    this.micAnimation.classList.add('listening');
                    console.log('✅ Recording started');
                    
                } catch (error) {
                    console.error('Failed to start recording:', error);
                }
            }

            stopRecording() {
                if (this.audioProcessor) {
                    this.audioProcessor.disconnect();
                    this.audioProcessor = null;
                }
                
                if (this.audioContext && this.audioContext.state !== 'closed') {
                    this.audioContext.close();
                    this.audioContext = null;
                }
                
                this.micAnimation.classList.remove('listening', 'recording');
                this.volumeBar.style.width = '0%';
            }

            disconnect() {
                if (this.ws) {
                    this.ws.close();
                }
                
                if (this.audioStream) {
                    this.audioStream.getTracks().forEach(track => track.stop());
                    this.audioStream = null;
                }
                
                this.stopRecording();
                this.stopKeepAlive();
            }

            startKeepAlive() {
                this.keepAliveInterval = setInterval(() => {
                    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                        this.ws.send(JSON.stringify({ type: "keep_alive" }));
                    }
                }, 15000);
            }

            stopKeepAlive() {
                if (this.keepAliveInterval) {
                    clearInterval(this.keepAliveInterval);
                    this.keepAliveInterval = null;
                }
            }

            convertToPCM16(float32Array) {
                const buffer = new ArrayBuffer(float32Array.length * 2);
                const view = new DataView(buffer);
                
                for (let i = 0; i < float32Array.length; i++) {
                    let sample = Math.max(-1, Math.min(1, float32Array[i]));
                    const pcmSample = sample < 0 ? sample * 0x8000 : sample * 0x7FFF;
                    view.setInt16(i * 2, pcmSample, true);
                }
                
                return new Uint8Array(buffer);
            }

            arrayBufferToBase64(buffer) {
                let binary = '';
                const bytes = new Uint8Array(buffer);
                for (let i = 0; i < bytes.byteLength; i++) {
                    binary += String.fromCharCode(bytes[i]);
                }
                return btoa(binary);
            }

            calculateVolume(channelData) {
                let sum = 0;
                for (let i = 0; i < channelData.length; i++) {
                    sum += channelData[i] * channelData[i];
                }
                return Math.sqrt(sum / channelData.length);
            }

            createWavBlob(pcmArray, sampleRate, numChannels, bitsPerSample) {
                const length = pcmArray.length;
                const arrayBuffer = new ArrayBuffer(44 + length);
                const view = new DataView(arrayBuffer);
                
                const writeString = (offset, string) => {
                    for (let i = 0; i < string.length; i++) {
                        view.setUint8(offset + i, string.charCodeAt(i));
                    }
                };
                
                writeString(0, 'RIFF');
                view.setUint32(4, 36 + length, true);
                writeString(8, 'WAVE');
                writeString(12, 'fmt ');
                view.setUint32(16, 16, true);
                view.setUint16(20, 1, true);
                view.setUint16(22, numChannels, true);
                view.setUint32(24, sampleRate, true);
                view.setUint32(28, sampleRate * numChannels * (bitsPerSample / 8), true);
                view.setUint16(32, numChannels * (bitsPerSample / 8), true);
