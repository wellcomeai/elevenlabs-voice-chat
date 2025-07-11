#!/usr/bin/env python3
"""
ElevenLabs Conversational AI WebSocket Server
Современный FastAPI сервер для работы с ElevenLabs Conversational AI API
"""

import asyncio
import base64
import json
import logging
import os
import uuid
from typing import Dict, Optional, Any
import time
from dataclasses import dataclass
from enum import Enum

import websockets
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx

# ===== CONFIGURATION =====

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s'
)
logger = logging.getLogger(__name__)

# ElevenLabs Configuration
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_AGENT_ID = os.getenv("ELEVENLABS_AGENT_ID")  # Ваш Agent ID

if not ELEVENLABS_API_KEY:
    logger.error("🚨 ELEVENLABS_API_KEY не установлен!")
    logger.info("💡 Получите ключ на: https://elevenlabs.io/")
    raise ValueError("ElevenLabs API key is required")

if not ELEVENLABS_AGENT_ID:
    logger.warning("⚠️ ELEVENLABS_AGENT_ID не установлен. Будет использован публичный агент.")

# WebSocket Configuration
ELEVENLABS_WS_URL = "wss://api.elevenlabs.io/v1/convai/conversation"

# Audio Configuration
AUDIO_CONFIG = {
    "sample_rate": 16000,
    "channels": 1,
    "chunk_duration_ms": 250,  # Оптимальная задержка
    "audio_format": "pcm_16000"
}

# ===== DATA MODELS =====

class ConnectionState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"

@dataclass
class ConversationSession:
    session_id: str
    client_ws: WebSocket
    elevenlabs_ws: Optional[websockets.WebSocketClientProtocol] = None
    conversation_id: Optional[str] = None
    state: ConnectionState = ConnectionState.DISCONNECTED
    created_at: float = 0.0
    
    def __post_init__(self):
        self.created_at = time.time()

# ===== SESSION MANAGER =====

class ElevenLabsSessionManager:
    """Менеджер сессий для ElevenLabs Conversational AI"""
    
    def __init__(self):
        self.sessions: Dict[str, ConversationSession] = {}
        
    async def create_session(self, client_ws: WebSocket) -> ConversationSession:
        """Создает новую сессию"""
        session_id = str(uuid.uuid4())
        session = ConversationSession(
            session_id=session_id,
            client_ws=client_ws
        )
        self.sessions[session_id] = session
        
        logger.info(f"🆕 Создана сессия: {session_id}")
        return session
    
    async def connect_to_elevenlabs(self, session: ConversationSession) -> bool:
        """Подключение к ElevenLabs WebSocket"""
        try:
            session.state = ConnectionState.CONNECTING
            
            # Формируем URL для подключения
            if ELEVENLABS_AGENT_ID:
                ws_url = f"{ELEVENLABS_WS_URL}?agent_id={ELEVENLABS_AGENT_ID}"
            else:
                # Используем публичный агент (нужно будет указать ID)
                demo_agent_id = "your_public_agent_id_here"
                ws_url = f"{ELEVENLABS_WS_URL}?agent_id={demo_agent_id}"
            
            # Подключение к ElevenLabs
            extra_headers = {}
            if ELEVENLABS_API_KEY:
                extra_headers["Authorization"] = f"Bearer {ELEVENLABS_API_KEY}"
            
            session.elevenlabs_ws = await websockets.connect(
                ws_url,
                extra_headers=extra_headers,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=10
            )
            
            session.state = ConnectionState.CONNECTED
            logger.info(f"✅ Подключен к ElevenLabs: {session.session_id}")
            
            # Запускаем обработчик сообщений от ElevenLabs
            asyncio.create_task(self._handle_elevenlabs_messages(session))
            
            # Отправляем инициализационные данные
            await self._send_conversation_initiation(session)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к ElevenLabs: {e}")
            session.state = ConnectionState.ERROR
            await self._send_to_client(session, {
                "type": "error",
                "message": f"Не удалось подключиться к ElevenLabs: {str(e)}"
            })
            return False
    
    async def _send_conversation_initiation(self, session: ConversationSession):
        """Отправляет инициализационные данные разговора"""
        try:
            initiation_data = {
                "type": "conversation_initiation_client_data",
                "conversation_config_override": {
                    "agent": {
                        "prompt": {
                            "prompt": "Ты дружелюбный AI ассистент. Отвечай кратко и естественно на русском языке."
                        },
                        "first_message": "Привет! Я AI ассистент от ElevenLabs. Как дела?",
                        "language": "ru"
                    },
                    "tts": {
                        "voice_id": "21m00Tcm4TlvDq8ikWAM"  # Популярный английский голос
                    }
                },
                "custom_llm_extra_body": {
                    "temperature": 0.7,
                    "max_tokens": 150
                }
            }
            
            await session.elevenlabs_ws.send(json.dumps(initiation_data))
            logger.info(f"📤 Отправлены инициализационные данные: {session.session_id}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки инициализации: {e}")
    
    async def _handle_elevenlabs_messages(self, session: ConversationSession):
        """Обработка сообщений от ElevenLabs"""
        try:
            async for message in session.elevenlabs_ws:
                data = json.loads(message)
                await self._process_elevenlabs_message(session, data)
                
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"🔌 ElevenLabs соединение закрыто: {session.session_id}")
            session.state = ConnectionState.DISCONNECTED
        except Exception as e:
            logger.error(f"❌ Ошибка обработки сообщений ElevenLabs: {e}")
            session.state = ConnectionState.ERROR
    
    async def _process_elevenlabs_message(self, session: ConversationSession, data: Dict[str, Any]):
        """Обработка конкретного сообщения от ElevenLabs"""
        message_type = data.get("type", "unknown")
        
        logger.debug(f"📨 ElevenLabs -> Client [{message_type}]: {session.session_id}")
        
        if message_type == "conversation_initiation_metadata":
            # Метаданные разговора
            metadata = data.get("conversation_initiation_metadata_event", {})
            session.conversation_id = metadata.get("conversation_id")
            
            await self._send_to_client(session, {
                "type": "conversation_ready",
                "conversation_id": session.conversation_id,
                "audio_format": metadata.get("agent_output_audio_format", "pcm_16000")
            })
            
        elif message_type == "user_transcript":
            # Транскрипция того, что сказал пользователь
            transcript_event = data.get("user_transcription_event", {})
            user_text = transcript_event.get("user_transcript", "")
            
            await self._send_to_client(session, {
                "type": "user_transcript",
                "text": user_text
            })
            
        elif message_type == "agent_response":
            # Текстовый ответ агента
            agent_response = data.get("agent_response_event", {})
            response_text = agent_response.get("agent_response", "")
            
            await self._send_to_client(session, {
                "type": "agent_response",
                "text": response_text
            })
            
        elif message_type == "audio_response":
            # Аудио ответ агента
            audio_event = data.get("audio_response_event", {})
            audio_data = audio_event.get("audio_base_64", "")
            
            await self._send_to_client(session, {
                "type": "audio_response",
                "audio": audio_data,
                "audio_format": "pcm_16000"
            })
            
        elif message_type == "ping":
            # Отвечаем на ping
            event_id = data.get("ping_event", {}).get("event_id", "")
            pong_response = {
                "type": "pong",
                "event_id": event_id
            }
            await session.elevenlabs_ws.send(json.dumps(pong_response))
            
        elif message_type == "vad_score":
            # Voice Activity Detection
            vad_event = data.get("vad_score_event", {})
            vad_score = vad_event.get("vad_score", 0.0)
            
            await self._send_to_client(session, {
                "type": "vad_score",
                "score": vad_score
            })
            
        elif message_type == "interruption":
            # Пользователь перебил агента
            await self._send_to_client(session, {
                "type": "interruption",
                "message": "Пользователь перебил агента"
            })
            
        else:
            logger.debug(f"🤷 Неизвестный тип сообщения от ElevenLabs: {message_type}")
    
    async def send_audio_to_elevenlabs(self, session: ConversationSession, audio_data: bytes):
        """Отправка аудио данных в ElevenLabs"""
        try:
            if session.state != ConnectionState.CONNECTED or not session.elevenlabs_ws:
                logger.warning(f"⚠️ ElevenLabs не подключен: {session.session_id}")
                return
                
            # Кодируем аудио в base64
            audio_base64 = base64.b64encode(audio_data).decode('utf-8')
            
            # Отправляем аудио чанк
            audio_message = {
                "user_audio_chunk": audio_base64
            }
            
            await session.elevenlabs_ws.send(json.dumps(audio_message))
            logger.debug(f"📤 Аудио отправлено в ElevenLabs: {len(audio_data)} байт")
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки аудио в ElevenLabs: {e}")
    
    async def _send_to_client(self, session: ConversationSession, data: Dict[str, Any]):
        """Отправка данных клиенту"""
        try:
            await session.client_ws.send_json(data)
        except Exception as e:
            logger.error(f"❌ Ошибка отправки клиенту: {e}")
    
    async def close_session(self, session_id: str):
        """Закрытие сессии"""
        if session_id in self.sessions:
            session = self.sessions[session_id]
            
            if session.elevenlabs_ws:
                await session.elevenlabs_ws.close()
            
            del self.sessions[session_id]
            logger.info(f"🗑️ Сессия закрыта: {session_id}")
    
    def get_session_stats(self) -> Dict[str, Any]:
        """Статистика сессий"""
        return {
            "total_sessions": len(self.sessions),
            "connected_sessions": len([s for s in self.sessions.values() if s.state == ConnectionState.CONNECTED]),
            "sessions": [
                {
                    "session_id": s.session_id,
                    "state": s.state.value,
                    "conversation_id": s.conversation_id,
                    "uptime": time.time() - s.created_at
                }
                for s in self.sessions.values()
            ]
        }

# ===== FASTAPI APPLICATION =====

app = FastAPI(
    title="ElevenLabs Conversational AI Server",
    description="Современный сервер для работы с ElevenLabs Conversational AI WebSocket API",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Глобальный менеджер сессий
session_manager = ElevenLabsSessionManager()

@app.get("/", response_class=HTMLResponse)
async def get_homepage():
    """Главная страница с клиентом"""
    # Читаем HTML файл клиента
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            html_content = f.read()
        return HTMLResponse(content=html_content)
    except FileNotFoundError:
        # Fallback HTML если файл не найден
        return HTMLResponse(content="""
        <!DOCTYPE html>
        <html><head><title>ElevenLabs AI</title></head>
        <body style="font-family: Arial; text-align: center; padding: 50px;">
        <h1>🚨 Файл index.html не найден</h1>
        <p>Создайте файл index.html в корневой папке проекта</p>
        <p>Или используйте HTML из артефакта выше</p>
        </body></html>
        """, status_code=200)

@app.get("/api/health")
async def health_check():
    """Проверка здоровья API"""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "service": "ElevenLabs Conversational AI Server",
        "elevenlabs_configured": bool(ELEVENLABS_API_KEY),
        "agent_configured": bool(ELEVENLABS_AGENT_ID),
        "sessions": session_manager.get_session_stats()
    }

@app.get("/api/config")
async def get_config():
    """Получение конфигурации для клиента"""
    return {
        "audio_config": AUDIO_CONFIG,
        "agent_configured": bool(ELEVENLABS_AGENT_ID),
        "features": ["real_time_conversation", "voice_activity_detection", "interruption_handling"]
    }

@app.websocket("/ws/conversation")
async def websocket_conversation_endpoint(websocket: WebSocket):
    """
    Главный WebSocket endpoint для разговора с ElevenLabs AI
    """
    await websocket.accept()
    
    # Создаем сессию
    session = await session_manager.create_session(websocket)
    
    try:
        # Подключаемся к ElevenLabs
        await session_manager.connect_to_elevenlabs(session)
        
        # Основной цикл обработки сообщений от клиента
        while True:
            try:
                message = await websocket.receive_json()
                await handle_client_message(session, message)
                
            except WebSocketDisconnect:
                logger.info(f"👋 Клиент отключился: {session.session_id}")
                break
            except Exception as e:
                logger.error(f"❌ Ошибка обработки сообщения клиента: {e}")
                await session_manager._send_to_client(session, {
                    "type": "error",
                    "message": str(e)
                })
    
    finally:
        await session_manager.close_session(session.session_id)

async def handle_client_message(session: ConversationSession, message: Dict[str, Any]):
    """Обработка сообщений от клиента"""
    message_type = message.get("type", "unknown")
    
    logger.debug(f"📨 Client -> Server [{message_type}]: {session.session_id}")
    
    if message_type == "audio_chunk":
        # Аудио данные от клиента
        audio_data = message.get("data", [])
        if audio_data:
            # Конвертируем из списка байтов в bytes
            audio_bytes = bytes(audio_data)
            await session_manager.send_audio_to_elevenlabs(session, audio_bytes)
    
    elif message_type == "start_conversation":
        # Начало разговора (если нужно что-то дополнительное)
        await session_manager._send_to_client(session, {
            "type": "conversation_started",
            "session_id": session.session_id
        })
    
    elif message_type == "end_conversation":
        # Завершение разговора
        await session_manager.close_session(session.session_id)
    
    else:
        logger.warning(f"⚠️ Неизвестный тип сообщения от клиента: {message_type}")

def main():
    """Запуск сервера"""
    import uvicorn
    
    logger.info("🚀 Запуск ElevenLabs Conversational AI Server")
    logger.info(f"🔑 ElevenLabs API: {'✅ Настроен' if ELEVENLABS_API_KEY else '❌ Не настроен'}")
    logger.info(f"🤖 Agent ID: {'✅ Настроен' if ELEVENLABS_AGENT_ID else '❌ Не настроен (будет использован публичный)'}")
    
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )

if __name__ == "__main__":
    main()
