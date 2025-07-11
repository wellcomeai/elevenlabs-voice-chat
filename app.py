#!/usr/bin/env python3
"""
ElevenLabs Conversational AI WebSocket Server
Полная версия с улучшенной обработкой ошибок и диагностикой
"""

import asyncio
import json
import logging
import os
import uuid
import time
from typing import Dict, Optional, Any, List
from dataclasses import dataclass, field
from enum import Enum

import aiohttp
import websockets
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# ===== CONFIGURATION =====

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s'
)
logger = logging.getLogger(__name__)

# ElevenLabs Configuration
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_AGENT_ID = os.getenv("ELEVENLABS_AGENT_ID", "agent_01jzwcew2ferttga9m1zcn3js1")

# URLs
ELEVENLABS_WS_URL = "wss://api.elevenlabs.io/v1/convai/conversation"
ELEVENLABS_API_BASE = "https://api.elevenlabs.io/v1"

# ===== DATA MODELS =====

class ConnectionState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    INITIALIZED = "initialized"
    ERROR = "error"

@dataclass
class ConversationSession:
    session_id: str
    client_ws: WebSocket
    elevenlabs_ws: Optional[websockets.WebSocketClientProtocol] = None
    conversation_id: Optional[str] = None
    state: ConnectionState = ConnectionState.DISCONNECTED
    agent_id: str = ELEVENLABS_AGENT_ID
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    is_agent_speaking: bool = False

# ===== SESSION MANAGER =====

class ElevenLabsManager:
    """Менеджер сессий ElevenLabs"""
    
    def __init__(self):
        self.sessions: Dict[str, ConversationSession] = {}
        self.active_connections = 0
        
    async def create_session(self, client_ws: WebSocket) -> ConversationSession:
        """Создание новой сессии"""
        session_id = str(uuid.uuid4())
        session = ConversationSession(
            session_id=session_id,
            client_ws=client_ws
        )
        self.sessions[session_id] = session
        self.active_connections += 1
        
        logger.info(f"🆕 Сессия создана: {session_id} (всего: {self.active_connections})")
        return session
    
    async def get_signed_url(self, agent_id: str = None) -> str:
        """Получение подписанного URL"""
        agent_id = agent_id or ELEVENLABS_AGENT_ID
        url = f"{ELEVENLABS_API_BASE}/convai/conversation/get_signed_url"
        
        headers = {
            'xi-api-key': ELEVENLABS_API_KEY,
            'Content-Type': 'application/json'
        }
        
        params = {'agent_id': agent_id}
        
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('signed_url')
                else:
                    error_text = await response.text()
                    raise Exception(f"Signed URL failed: {response.status} - {error_text}")
    
    async def check_agent_exists(self, agent_id: str = None) -> Dict[str, Any]:
        """Проверка существования агента"""
        agent_id = agent_id or ELEVENLABS_AGENT_ID
        url = f"{ELEVENLABS_API_BASE}/convai/agents/{agent_id}"
        
        headers = {'xi-api-key': ELEVENLABS_API_KEY}
        
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        agent_data = await response.json()
                        return {
                            'exists': True,
                            'agent_id': agent_id,
                            'status': 'ready',
                            'data': agent_data
                        }
                    elif response.status == 404:
                        return {
                            'exists': False,
                            'agent_id': agent_id,
                            'status': 'not_found',
                            'error': 'Agent not found'
                        }
                    else:
                        error_text = await response.text()
                        return {
                            'exists': False,
                            'agent_id': agent_id,
                            'status': 'error',
                            'error': f"API error: {response.status} - {error_text}"
                        }
        except Exception as e:
            return {
                'exists': False,
                'agent_id': agent_id,
                'status': 'error',
                'error': str(e)
            }
    
    async def connect_to_elevenlabs(self, session: ConversationSession) -> bool:
        """Подключение к ElevenLabs WebSocket"""
        try:
            session.state = ConnectionState.CONNECTING
            await self._send_to_client(session, {
                "type": "status",
                "state": "connecting",
                "message": "Подключение к ElevenLabs..."
            })
            
            # Пробуем получить signed URL
            try:
                signed_url = await self.get_signed_url(session.agent_id)
                ws_url = signed_url
                connection_method = "signed"
                logger.info(f"✅ Signed URL получен для {session.session_id}")
            except Exception as e:
                logger.warning(f"⚠️ Signed URL недоступен: {e}")
                ws_url = f"{ELEVENLABS_WS_URL}?agent_id={session.agent_id}"
                connection_method = "direct"
                logger.info(f"🔄 Прямое подключение для {session.session_id}")
            
            # Подключение
            extra_headers = {}
            if connection_method == "direct":
                extra_headers["xi-api-key"] = ELEVENLABS_API_KEY
            
            session.elevenlabs_ws = await websockets.connect(
                ws_url,
                extra_headers=extra_headers,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=10
            )
            
            session.state = ConnectionState.CONNECTED
            logger.info(f"✅ WebSocket подключен: {session.session_id}")
            
            # Запускаем обработчик сообщений
            asyncio.create_task(self._handle_elevenlabs_messages(session))
            
            # Отправляем инициализацию
            await self._send_conversation_initiation(session)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка подключения: {e}")
            session.state = ConnectionState.ERROR
            await self._send_to_client(session, {
                "type": "error",
                "message": f"Не удалось подключиться: {str(e)}"
            })
            return False
    
    async def _send_conversation_initiation(self, session: ConversationSession):
        """Отправка инициализации"""
        try:
            initiation_data = {
                "type": "conversation_initiation_client_data"
            }
            
            await session.elevenlabs_ws.send(json.dumps(initiation_data))
            logger.info(f"📤 Инициализация отправлена: {session.session_id}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации: {e}")
    
    async def _handle_elevenlabs_messages(self, session: ConversationSession):
        """Обработка сообщений от ElevenLabs"""
        try:
            async for message in session.elevenlabs_ws:
                data = json.loads(message)
                await self._process_elevenlabs_message(session, data)
                session.last_activity = time.time()
                
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"🔌 ElevenLabs соединение закрыто: {session.session_id}")
            session.state = ConnectionState.DISCONNECTED
        except Exception as e:
            logger.error(f"❌ Ошибка обработки сообщений: {e}")
            session.state = ConnectionState.ERROR
    
    async def _process_elevenlabs_message(self, session: ConversationSession, data: Dict[str, Any]):
        """Обработка сообщения от ElevenLabs"""
        message_type = data.get("type", "unknown")
        
        if message_type == "conversation_initiation_metadata":
            metadata = data.get("conversation_initiation_metadata_event", {})
            session.conversation_id = metadata.get("conversation_id")
            session.state = ConnectionState.INITIALIZED
            
        elif message_type == "agent_response":
            session.is_agent_speaking = True
            
        elif message_type == "interruption":
            session.is_agent_speaking = False
            
        elif message_type == "ping":
            ping_event = data.get("ping_event", {})
            event_id = ping_event.get("event_id", "")
            
            pong_response = {
                "type": "pong",
                "event_id": event_id
            }
            await session.elevenlabs_ws.send(json.dumps(pong_response))
            return  # Не отправляем ping клиенту
        
        # Отправляем все сообщения клиенту
        await self._send_to_client(session, data)
    
    async def send_audio_to_elevenlabs(self, session: ConversationSession, audio_data: str):
        """Отправка аудио в ElevenLabs"""
        try:
            if session.state not in [ConnectionState.CONNECTED, ConnectionState.INITIALIZED]:
                return
                
            if not session.elevenlabs_ws:
                return
            
            audio_message = {"user_audio_chunk": audio_data}
            await session.elevenlabs_ws.send(json.dumps(audio_message))
            
            session.last_activity = time.time()
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки аудио: {e}")
    
    async def send_message_to_elevenlabs(self, session: ConversationSession, message: Dict[str, Any]):
        """Отправка сообщения в ElevenLabs"""
        try:
            if session.elevenlabs_ws and session.state in [ConnectionState.CONNECTED, ConnectionState.INITIALIZED]:
                await session.elevenlabs_ws.send(json.dumps(message))
                session.last_activity = time.time()
        except Exception as e:
            logger.error(f"❌ Ошибка отправки сообщения: {e}")
    
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
                try:
                    await session.elevenlabs_ws.close()
                except:
                    pass
            
            del self.sessions[session_id]
            self.active_connections -= 1
            logger.info(f"🗑️ Сессия закрыта: {session_id}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Статистика сессий"""
        return {
            "total_sessions": len(self.sessions),
            "active_connections": self.active_connections,
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
    title="ElevenLabs Voice Chat",
    description="Голосовой ассистент на базе ElevenLabs Conversational AI",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Глобальный менеджер
manager = ElevenLabsManager()

# ===== HTTP ENDPOINTS =====

@app.get("/", response_class=HTMLResponse)
async def get_homepage():
    """Главная страница"""
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(content="""
        <!DOCTYPE html>
        <html>
        <head><title>ElevenLabs Voice Chat</title></head>
        <body style="font-family: Arial; text-align: center; padding: 50px;">
        <h1>🚨 Файл index.html не найден</h1>
        <p>Создайте файл index.html в корневой папке</p>
        <a href="/health">Проверить API</a>
        </body>
        </html>
        """)

@app.get("/health")
async def health_check():
    """Проверка здоровья сервера"""
    agent_info = await manager.check_agent_exists()
    
    return {
        "status": "healthy" if agent_info['exists'] else "partial",
        "timestamp": time.time(),
        "elevenlabs_configured": bool(ELEVENLABS_API_KEY),
        "agent_configured": bool(ELEVENLABS_AGENT_ID),
        "agent_status": agent_info,
        "sessions": manager.get_stats()
    }

@app.get("/api/agent-id")
async def get_agent_config():
    """Получение конфигурации агента"""
    agent_info = await manager.check_agent_exists()
    
    return {
        "agent_id": ELEVENLABS_AGENT_ID,
        "status": "ready" if agent_info['exists'] else "error",
        "exists": agent_info['exists'],
        "timestamp": time.time()
    }

@app.get("/api/diagnostics")
async def run_diagnostics():
    """Диагностика системы"""
    tests = {}
    recommendations = []
    
    # Проверка API ключа
    if ELEVENLABS_API_KEY:
        tests["api_key"] = "passed"
        recommendations.append("✅ API ключ настроен")
    else:
        tests["api_key"] = "failed"
        recommendations.append("❌ Настройте ELEVENLABS_API_KEY")
    
    # Проверка агента
    agent_info = await manager.check_agent_exists()
    if agent_info['exists']:
        tests["agent"] = "passed"
        recommendations.append("✅ Агент доступен")
    else:
        tests["agent"] = "failed"
        recommendations.append(f"❌ Агент недоступен: {agent_info['error']}")
    
    passed = sum(1 for result in tests.values() if result == "passed")
    total = len(tests)
    
    return {
        "timestamp": time.time(),
        "tests": tests,
        "overall": {
            "health_score": f"{passed}/{total}",
            "status": "healthy" if passed == total else "partial" if passed > 0 else "unhealthy"
        },
        "recommendations": recommendations,
        "sessions": manager.get_stats()
    }

# ===== WEBSOCKET ENDPOINT =====

@app.websocket("/ws/conversation")
async def websocket_conversation(websocket: WebSocket):
    """Главный WebSocket endpoint"""
    await websocket.accept()
    
    session = await manager.create_session(websocket)
    
    try:
        # Подключаемся к ElevenLabs
        connected = await manager.connect_to_elevenlabs(session)
        
        if not connected:
            await websocket.close(code=1011, reason="Failed to connect to ElevenLabs")
            return
        
        # Основной цикл
        while True:
            try:
                message = await websocket.receive_json()
                await handle_client_message(session, message)
                
            except WebSocketDisconnect:
                logger.info(f"👋 Клиент отключился: {session.session_id}")
                break
            except Exception as e:
                logger.error(f"❌ Ошибка: {e}")
                await manager._send_to_client(session, {
                    "type": "error",
                    "message": str(e)
                })
    
    finally:
        await manager.close_session(session.session_id)

async def handle_client_message(session: ConversationSession, message: Dict[str, Any]):
    """Обработка сообщений от клиента"""
    message_type = message.get("type", "unknown")
    
    if message_type == "user_audio_chunk":
        audio_base64 = message.get("user_audio_chunk", "")
        if audio_base64:
            await manager.send_audio_to_elevenlabs(session, audio_base64)
    
    elif message_type == "ping":
        await manager._send_to_client(session, {
            "type": "pong",
            "timestamp": time.time()
        })
    
    else:
        # Пробрасываем остальные сообщения в ElevenLabs
        await manager.send_message_to_elevenlabs(session, message)

# ===== MAIN =====

def main():
    """Запуск сервера"""
    port = int(os.getenv("PORT", 8000))
    
    if not ELEVENLABS_API_KEY:
        logger.error("❌ ELEVENLABS_API_KEY не установлен!")
        logger.info("💡 Получите ключ на: https://elevenlabs.io/")
        logger.info("💡 Установите: export ELEVENLABS_API_KEY=your_key")
        return
    
    logger.info("🚀 Запуск ElevenLabs Voice Chat")
    logger.info(f"🔑 API ключ: {'✅ Настроен' if ELEVENLABS_API_KEY else '❌ Не настроен'}")
    logger.info(f"🤖 Agent ID: {ELEVENLABS_AGENT_ID}")
    logger.info(f"🌐 Сервер: http://localhost:{port}")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )

if __name__ == "__main__":
    main()
