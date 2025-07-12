#!/usr/bin/env python3
"""
ElevenLabs Conversational AI - Render.com Version
Веб-сервис без аудио интерфейса для облачного деплоя
"""

import asyncio
import logging
import os
import sys
import time
from pathlib import Path
from typing import Dict, Any

# FastAPI для веб-интерфейса
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Добавляем путь к модулям
sys.path.insert(0, str(Path(__file__).parent))

from config import Config
from websocket_client import ElevenLabsWebSocketClient
from utils import setup_logging, print_banner

logger = logging.getLogger(__name__)

# ===== FastAPI Application =====

app = FastAPI(
    title="ElevenLabs Voice Assistant",
    description="Облачная версия голосового ассистента ElevenLabs",
    version="3.0-render"
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
        self.ws_client = None
        self.is_initialized = False
        self.start_time = time.time()
        self.stats = {
            "messages_received": 0,
            "connections": 0,
            "errors": 0
        }

app_state = AppState()

# ===== Startup/Shutdown =====

@app.on_event("startup")
async def startup_event():
    """Инициализация при запуске"""
    try:
        logger.info("🚀 Запуск ElevenLabs сервиса...")
        
        # Загрузка конфигурации
        app_state.config = Config()
        if not app_state.config.validate():
            logger.error("❌ Некорректная конфигурация")
            return
        
        # Инициализация WebSocket клиента (без аудио)
        app_state.ws_client = ElevenLabsWebSocketClient(
            api_key=app_state.config.ELEVENLABS_API_KEY,
            agent_id=app_state.config.ELEVENLABS_AGENT_ID,
            audio_handler=None  # Без аудио в облаке
        )
        
        app_state.is_initialized = True
        logger.info("✅ Сервис инициализирован")
        
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации: {e}")
        app_state.is_initialized = False

@app.on_event("shutdown") 
async def shutdown_event():
    """Очистка при остановке"""
    logger.info("👋 Остановка сервиса...")
    
    if app_state.ws_client:
        try:
            await app_state.ws_client.disconnect()
        except:
            pass
    
    logger.info("✅ Сервис остановлен")

# ===== HTTP Endpoints =====

@app.get("/", response_class=HTMLResponse)
async def get_homepage():
    """Главная страница"""
    return HTMLResponse(content="""
    <!DOCTYPE html>
    <html>
    <head>
        <title>ElevenLabs Voice Assistant - Cloud</title>
        <meta charset="utf-8">
        <style>
            body { font-family: Arial, sans-serif; margin: 50px; background: #f5f5f5; }
            .container { max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
            .title { color: #333; text-align: center; margin-bottom: 30px; }
            .status { padding: 10px; border-radius: 5px; margin: 10px 0; }
            .status.ok { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
            .status.error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
            .api-section { margin: 20px 0; }
            .endpoint { background: #f8f9fa; padding: 15px; border-radius: 5px; margin: 10px 0; }
            .method { display: inline-block; padding: 3px 8px; border-radius: 3px; color: white; font-weight: bold; }
            .get { background: #28a745; }
            .post { background: #007bff; }
            .ws { background: #6f42c1; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1 class="title">🎤 ElevenLabs Voice Assistant</h1>
            <h2 class="title">Cloud Version - Render.com</h2>
            
            <div class="status ok">
                ✅ Сервис работает | Время работы: <span id="uptime">calculating...</span>
            </div>
            
            <div class="api-section">
                <h3>📋 API Endpoints:</h3>
                
                <div class="endpoint">
                    <span class="method get">GET</span>
                    <strong>/health</strong> - Проверка здоровья сервиса
                </div>
                
                <div class="endpoint">
                    <span class="method get">GET</span>
                    <strong>/api/config</strong> - Конфигурация агента
                </div>
                
                <div class="endpoint">
                    <span class="method get">GET</span>
                    <strong>/api/stats</strong> - Статистика сервиса
                </div>
                
                <div class="endpoint">
                    <span class="method post">POST</span>
                    <strong>/api/test-connection</strong> - Тест подключения к ElevenLabs
                </div>
                
                <div class="endpoint">
                    <span class="method ws">WS</span>
                    <strong>/ws</strong> - WebSocket для real-time взаимодействия
                </div>
            </div>
            
            <div class="api-section">
                <h3>💡 Информация:</h3>
                <p>Это облачная версия голосового ассистента, развернутая на Render.com.</p>
                <p>🎵 <strong>Аудио интерфейс недоступен</strong> в облачной среде.</p>
                <p>💻 Для полного функционала используйте локальную версию с PyAudio.</p>
                <p>🔗 API можно использовать для интеграции с другими приложениями.</p>
            </div>
            
            <div class="api-section">
                <h3>🚀 Локальная версия:</h3>
                <pre style="background: #f8f9fa; padding: 15px; border-radius: 5px;">
git clone &lt;repository&gt;
cd elevenlabs-python-cli
pip install -r requirements.txt
python run.py
                </pre>
            </div>
        </div>
        
        <script>
            // Обновление времени работы
            function updateUptime() {
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
                        document.getElementById('uptime').textContent = 'unavailable';
                    });
            }
            
            // Обновляем каждые 5 секунд
            updateUptime();
            setInterval(updateUptime, 5000);
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
        "version": "3.0-render",
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
        "audio_format": "PCM 16kHz (not available in cloud)",
        "features": {
            "websocket_api": True,
            "rest_api": True,
            "audio_interface": False,
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
        "errors": app_state.stats["errors"]
    }
    
    # Добавляем статистику WebSocket клиента если есть
    if app_state.ws_client:
        client_stats = app_state.ws_client.get_statistics()
        stats.update({
            "elevenlabs_connected": client_stats["connected"],
            "conversation_id": client_stats["conversation_id"],
            "messages_sent": client_stats["messages_sent"]
        })
    
    return stats

@app.post("/api/test-connection")
async def test_connection():
    """Тест подключения к ElevenLabs"""
    if not app_state.is_initialized:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    try:
        # Создаем временный клиент для теста
        test_client = ElevenLabsWebSocketClient(
            api_key=app_state.config.ELEVENLABS_API_KEY,
            agent_id=app_state.config.ELEVENLABS_AGENT_ID,
            audio_handler=None
        )
        
        # Пытаемся подключиться
        result = await test_client.connect()
        
        if result:
            stats = test_client.get_statistics()
            await test_client.disconnect()
            
            return {
                "status": "success",
                "message": "Подключение к ElevenLabs успешно",
                "conversation_id": stats["conversation_id"],
                "timestamp": time.time()
            }
        else:
            return {
                "status": "error", 
                "message": "Не удалось подключиться к ElevenLabs",
                "timestamp": time.time()
            }
            
    except Exception as e:
        app_state.stats["errors"] += 1
        logger.error(f"❌ Ошибка теста подключения: {e}")
        
        return {
            "status": "error",
            "message": f"Ошибка: {str(e)}",
            "timestamp": time.time()
        }

# ===== WebSocket Endpoint =====

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket для real-time взаимодействия"""
    await websocket.accept()
    app_state.stats["connections"] += 1
    
    try:
        logger.info("🔗 Новое WebSocket подключение")
        
        # Отправляем приветствие
        await websocket.send_json({
            "type": "connection",
            "message": "Подключение к ElevenLabs Voice Assistant",
            "features": {
                "audio": False,
                "text_api": True,
                "cloud_version": True
            }
        })
        
        # Основной цикл
        while True:
            try:
                data = await websocket.receive_json()
                app_state.stats["messages_received"] += 1
                
                # Эхо ответ (можно расширить функционал)
                await websocket.send_json({
                    "type": "echo",
                    "original_message": data,
                    "timestamp": time.time(),
                    "note": "Полный функционал доступен в локальной версии"
                })
                
            except WebSocketDisconnect:
                logger.info("👋 WebSocket отключен")
                break
            except Exception as e:
                logger.error(f"❌ Ошибка WebSocket: {e}")
                await websocket.send_json({
                    "type": "error",
                    "message": str(e)
                })
                
    except Exception as e:
        logger.error(f"❌ Критическая ошибка WebSocket: {e}")
    
    finally:
        logger.info("🧹 WebSocket соединение закрыто")

# ===== Main Function =====

async def main():
    """Главная функция для CLI запуска"""
    print_banner()
    
    # Настройка логирования
    setup_logging()
    
    logger.info("🌐 Запуск в режиме веб-сервиса...")
    logger.info("💡 Это облачная версия без аудио интерфейса")
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
