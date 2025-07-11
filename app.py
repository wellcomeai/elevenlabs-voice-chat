#!/usr/bin/env python3
"""
Улучшенный ElevenLabs Conversational AI сервер
Объединяет лучшие возможности Node.js и Python версий
"""

import asyncio
import base64
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
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn

# ===== CONFIGURATION =====

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s'
)
logger = logging.getLogger(__name__)

# ElevenLabs Configuration
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "your_api_key")
ELEVENLABS_AGENT_ID = os.getenv("ELEVENLABS_AGENT_ID", "agent_01jzwcew2ferttga9m1zcn3js1")

if not ELEVENLABS_API_KEY or ELEVENLABS_API_KEY == "your_api_key":
    logger.warning("⚠️ ELEVENLABS_API_KEY не установлен!")
    logger.info("💡 Получите ключ на: https://elevenlabs.io/")

# WebSocket URLs
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
    audio_queue: List[str] = field(default_factory=list)
    
# ===== SESSION MANAGER =====

class ElevenLabsManager:
    """Улучшенный менеджер для ElevenLabs Conversational AI"""
    
    def __init__(self):
        self.sessions: Dict[str, ConversationSession] = {}
        self.active_connections = 0
        
    async def create_session(self, client_ws: WebSocket) -> ConversationSession:
        """Создает новую сессию"""
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
        """Получение подписанного URL для WebSocket соединения"""
        agent_id = agent_id or ELEVENLABS_AGENT_ID
        url = f"{ELEVENLABS_API_BASE}/convai/conversation/get_signed_url"
        
        headers = {
            'xi-api-key': ELEVENLABS_API_KEY,
            'Content-Type': 'application/json'
        }
        
        params = {'agent_id': agent_id}
        
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.get(url, headers=headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('signed_url')
                else:
                    error_text = await response.text()
                    raise Exception(f"Failed to get signed URL: {response.status} - {error_text}")
    
    async def check_agent_exists(self, agent_id: str = None) -> Dict[str, Any]:
        """Проверка существования агента"""
        agent_id = agent_id or ELEVENLABS_AGENT_ID
        url = f"{ELEVENLABS_API_BASE}/convai/agents/{agent_id}"
        
        headers = {'xi-api-key': ELEVENLABS_API_KEY}
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
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
                logger.info(f"✅ Используем signed URL для {session.session_id}")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось получить signed URL: {e}")
                ws_url = f"{ELEVENLABS_WS_URL}?agent_id={session.agent_id}"
                connection_method = "direct"
                logger.info(f"🔄 Используем прямое подключение для {session.session_id}")
            
            # Подключение к ElevenLabs
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
            logger.info(f"✅ WebSocket подключен: {session.session_id} ({connection_method})")
            
            # Запускаем обработчик сообщений
            asyncio.create_task(self._handle_elevenlabs_messages(session))
            
            # Отправляем инициализацию
            await self._send_conversation_initiation(session)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к ElevenLabs: {e}")
            session.state = ConnectionState.ERROR
            await self._send_to_client(session, {
                "type": "error",
                "message": f"Не удалось подключиться: {str(e)}"
            })
            return False
    
    async def _send_conversation_initiation(self, session: ConversationSession):
        """Отправка инициализационных данных"""
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
            logger.error(f"❌ Ошибка обработки сообщений ElevenLabs: {e}")
            session.state = ConnectionState.ERROR
    
    async def _process_elevenlabs_message(self, session: ConversationSession, data: Dict[str, Any]):
        """Обработка конкретного сообщения от ElevenLabs"""
        message_type = data.get("type", "unknown")
        
        logger.debug(f"📨 ElevenLabs [{message_type}]: {session.session_id}")
        
        if message_type == "conversation_initiation_metadata":
            # Инициализация завершена
            metadata = data.get("conversation_initiation_metadata_event", {})
            session.conversation_id = metadata.get("conversation_id")
            session.state = ConnectionState.INITIALIZED
            
            await self._send_to_client(session, {
                "type": "conversation_initiation_metadata",
                "conversation_initiation_metadata_event": metadata
            })
            
        elif message_type == "user_transcript":
            # Транскрипция пользователя
            await self._send_to_client(session, data)
            
        elif message_type == "agent_response":
            # Ответ агента
            session.is_agent_speaking = True
            await self._send_to_client(session, data)
            
        elif message_type == "audio":
            # Аудио от агента
            audio_event = data.get("audio_event", {})
            audio_base64 = audio_event.get("audio_base_64", "")
            
            # Добавляем в очередь
            session.audio_queue.append(audio_base64)
            
            await self._send_to_client(session, data)
            
        elif message_type == "interruption":
            # Прерывание
            session.is_agent_speaking = False
            session.audio_queue.clear()
            await self._send_to_client(session, data)
            
        elif message_type == "ping":
            # Пинг от ElevenLabs
            ping_event = data.get("ping_event", {})
            event_id = ping_event.get("event_id", "")
            
            pong_response = {
                "type": "pong",
                "event_id": event_id
            }
            await session.elevenlabs_ws.send(json.dumps(pong_response))
            
        elif message_type == "vad_score":
            # Voice Activity Detection
            await self._send_to_client(session, data)
            
        else:
            # Пробрасываем все остальные сообщения
            await self._send_to_client(session, data)
    
    async def send_audio_to_elevenlabs(self, session: ConversationSession, audio_data: str):
        """Отправка аудио в ElevenLabs"""
        try:
            if session.state not in [ConnectionState.CONNECTED, ConnectionState.INITIALIZED]:
                logger.warning(f"⚠️ ElevenLabs не готов: {session.session_id}")
                return
                
            if not session.elevenlabs_ws:
                logger.warning(f"⚠️ WebSocket не подключен: {session.session_id}")
                return
            
            # Отправляем аудио чанк
            audio_message = {"user_audio_chunk": audio_data}
            await session.elevenlabs_ws.send(json.dumps(audio_message))
            
            session.last_activity = time.time()
            logger.debug(f"📤 Аудио отправлено: {session.session_id}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки аудио: {e}")
    
    async def send_message_to_elevenlabs(self, session: ConversationSession, message: Dict[str, Any]):
        """Отправка любого сообщения в ElevenLabs"""
        try:
            if session.elevenlabs_ws and session.state in [ConnectionState.CONNECTED, ConnectionState.INITIALIZED]:
                await session.elevenlabs_ws.send(json.dumps(message))
                session.last_activity = time.time()
                logger.debug(f"📤 Сообщение отправлено: {message.get('type', 'unknown')}")
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
            logger.info(f"🗑️ Сессия закрыта: {session_id} (осталось: {self.active_connections})")
    
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
                    "is_agent_speaking": s.is_agent_speaking,
                    "audio_queue_length": len(s.audio_queue),
                    "uptime": time.time() - s.created_at,
                    "last_activity": time.time() - s.last_activity
                }
                for s in self.sessions.values()
            ]
        }

# ===== FASTAPI APPLICATION =====

app = FastAPI(
    title="ElevenLabs Voice Chat Pro",
    description="Улучшенный сервер для ElevenLabs Conversational AI",
    version="2.0.0"
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
        # Пробуем загрузить index.html
        with open("index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        # Fallback HTML
        return HTMLResponse(content="""
        <!DOCTYPE html>
        <html lang="ru">
        <head>
            <meta charset="UTF-8">
            <title>ElevenLabs Voice Chat Pro</title>
            <style>
                body { font-family: Arial; text-align: center; padding: 50px; background: #f0f0f0; }
                .container { max-width: 600px; margin: 0 auto; background: white; padding: 40px; border-radius: 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.1); }
                .btn { padding: 15px 30px; background: #4f46e5; color: white; border: none; border-radius: 10px; cursor: pointer; font-size: 16px; margin: 10px; }
                .btn:hover { background: #3730a3; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🎤 ElevenLabs Voice Chat Pro</h1>
                <p>Улучшенный голосовой ассистент</p>
                <p>⚠️ Файл index.html не найден. Создайте клиентскую часть.</p>
                <button class="btn" onclick="location.href='/health'">🩺 Проверить API</button>
                <button class="btn" onclick="location.href='/debug'">🔍 Отладка</button>
            </div>
        </body>
        </html>
        """)

@app.get("/debug", response_class=HTMLResponse)
async def debug_page():
    """Страница отладки"""
    try:
        with open("debug.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(content="<h1>Debug панель не найдена</h1><p>Создайте файл debug.html</p>")

@app.get("/health")
async def health_check():
    """Проверка здоровья сервера"""
    agent_info = await manager.check_agent_exists()
    
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "service": "ElevenLabs Voice Chat Pro v2.0",
        "elevenlabs_configured": bool(ELEVENLABS_API_KEY and ELEVENLABS_API_KEY != "your_api_key"),
        "agent_configured": bool(ELEVENLABS_AGENT_ID),
        "agent_status": agent_info,
        "sessions": manager.get_stats(),
        "message": "Готов к работе!" if agent_info['exists'] else "Проблемы с агентом"
    }

@app.get("/api/agent-id")
async def get_agent_config():
    """Получение конфигурации агента"""
    agent_info = await manager.check_agent_exists()
    
    if agent_info['exists']:
        return {
            "agent_id": ELEVENLABS_AGENT_ID,
            "status": "ready",
            "source": "verified",
            "message": "Агент готов к работе",
            "timestamp": time.time(),
            "agent_data": agent_info.get('data', {})
        }
    else:
        return {
            "agent_id": ELEVENLABS_AGENT_ID,
            "status": "error", 
            "source": "check_failed",
            "error": agent_info['error'],
            "timestamp": time.time()
        }

@app.get("/api/signed-url")
async def get_signed_url():
    """Получение подписанного URL"""
    try:
        signed_url = await manager.get_signed_url()
        return {
            "signed_url": signed_url,
            "agent_id": ELEVENLABS_AGENT_ID,
            "status": "ready",
            "timestamp": time.time()
        }
    except Exception as e:
        return {
            "error": "Не удалось получить signed URL",
            "fallback_url": f"{ELEVENLABS_WS_URL}?agent_id={ELEVENLABS_AGENT_ID}",
            "agent_id": ELEVENLABS_AGENT_ID,
            "details": str(e),
            "status": "fallback",
            "timestamp": time.time()
        }

@app.get("/api/diagnostics")
async def run_diagnostics():
    """Полная диагностика системы"""
    tests = {}
    recommendations = []
    
    # Тест 1: API ключ
    if ELEVENLABS_API_KEY and ELEVENLABS_API_KEY != "your_api_key":
        tests["api_key_configured"] = "passed"
        recommendations.append("✅ API ключ настроен")
    else:
        tests["api_key_configured"] = "failed"
        recommendations.append("❌ Настройте ELEVENLABS_API_KEY")
    
    # Тест 2: Агент
    agent_info = await manager.check_agent_exists()
    if agent_info['exists']:
        tests["agent_accessibility"] = "passed"
        recommendations.append("✅ Агент доступен")
    else:
        tests["agent_accessibility"] = "failed"
        recommendations.append(f"❌ Агент недоступен: {agent_info['error']}")
    
    # Тест 3: Signed URL
    try:
        await manager.get_signed_url()
        tests["signed_url_generation"] = "passed"
        recommendations.append("✅ Signed URL работает")
    except Exception as e:
        tests["signed_url_generation"] = "failed"
        recommendations.append(f"⚠️ Signed URL проблемы: {str(e)}")
    
    # Общая оценка
    passed_tests = sum(1 for result in tests.values() if result == "passed")
    total_tests = len(tests)
    
    return {
        "timestamp": time.time(),
        "tests": tests,
        "overall": {
            "health_score": f"{passed_tests}/{total_tests}",
            "status": "healthy" if passed_tests == total_tests else "partial" if passed_tests > 0 else "unhealthy",
            "ready_for_connection": passed_tests >= 1
        },
        "recommendations": recommendations,
        "sessions": manager.get_stats(),
        "system": {
            "elevenlabs_api_key": "configured" if ELEVENLABS_API_KEY != "your_api_key" else "missing",
            "elevenlabs_agent_id": ELEVENLABS_AGENT_ID
        }
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
                logger.error(f"❌ Ошибка обработки сообщения: {e}")
                await manager._send_to_client(session, {
                    "type": "error",
                    "message": str(e)
                })
    
    finally:
        await manager.close_session(session.session_id)

async def handle_client_message(session: ConversationSession, message: Dict[str, Any]):
    """Обработка сообщений от клиента"""
    message_type = message.get("type", "unknown")
    
    logger.debug(f"📨 Client [{message_type}]: {session.session_id}")
    
    if message_type == "user_audio_chunk":
        # Аудио от пользователя
        audio_base64 = message.get("user_audio_chunk", "")
        if audio_base64:
            await manager.send_audio_to_elevenlabs(session, audio_base64)
    
    elif message_type == "ping":
        # Пинг от клиента
        await manager._send_to_client(session, {
            "type": "pong",
            "timestamp": time.time()
        })
    
    elif message_type == "end_of_stream":
        # Завершение потока
        await manager.send_message_to_elevenlabs(session, message)
    
    else:
        # Пробрасываем остальные сообщения в ElevenLabs
        await manager.send_message_to_elevenlabs(session, message)

# ===== STARTUP =====

def main():
    """Запуск сервера"""
    logger.info("🚀 Запуск ElevenLabs Voice Chat Pro v2.0")
    logger.info(f"🔑 API ключ: {'✅ Настроен' if ELEVENLABS_API_KEY != 'your_api_key' else '❌ Не настроен'}")
    logger.info(f"🤖 Agent ID: {ELEVENLABS_AGENT_ID}")
    
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )

if __name__ == "__main__":
    main()
