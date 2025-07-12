#!/usr/bin/env python3
"""
ElevenLabs Conversational AI - Fixed Render.com Version
Следует архитектуре Node.js версии - без проксирования WebSocket
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
    description="Python версия без WebSocket проксирования",
    version="1.0-fixed"
)

# CORS для поддержки запросов из браузера
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Конфигурация из переменных окружения
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "sk_95a5725ca01fdba20e15bd662d8b76152971016ff045377f")
AGENT_ID = os.getenv("AGENT_ID", "agent_01jzwcew2ferttga9m1zcn3js1")

# Глобальное состояние
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
    """Главная страница с голосовым интерфейсом"""
    # Используем тот же HTML что и в Node.js версии, но адаптированный
    return HTMLResponse(content=open("index.html", "r", encoding="utf-8").read())

@app.get("/health")
async def health_check():
    """Проверка здоровья сервиса"""
    return {
        "status": "healthy",
        "uptime": time.time() - app_state["start_time"],
        "agent_id": AGENT_ID,
        "api_key_configured": app_state["api_key_configured"]
    }

@app.get("/api/agent-id")
async def get_agent_id():
    """Получение ID агента - аналог Node.js версии"""
    try:
        # Проверяем существование агента
        agent_exists = await check_agent_exists()
        
        if agent_exists:
            return JSONResponse({
                "agent_id": AGENT_ID,
                "api_key": ELEVENLABS_API_KEY,
                "status": "ready",
                "source": "verified",
                "message": "Агент подтвержден и готов к работе",
                "timestamp": time.time()
            })
        else:
            return JSONResponse(
                status_code=404,
                content={
                    "error": "Agent not found",
                    "status": "error",
                    "agent_id": AGENT_ID
                }
            )
    except Exception as e:
        logger.error(f"Error checking agent: {e}")
        # Fallback response
        return JSONResponse({
            "agent_id": AGENT_ID,
            "api_key": ELEVENLABS_API_KEY,
            "status": "ready",
            "source": "fallback",
            "warning": "Could not verify agent status"
        })

@app.get("/api/signed-url")
async def get_signed_url():
    """Получение signed URL для прямого подключения к ElevenLabs"""
    try:
        signed_url = await fetch_signed_url()
        
        return JSONResponse({
            "signed_url": signed_url,
            "agent_id": AGENT_ID,
            "status": "ready",
            "timestamp": time.time()
        })
        
    except Exception as e:
        logger.error(f"Failed to get signed URL: {e}")
        
        # Fallback to direct URL
        fallback_url = f"wss://api.elevenlabs.io/v1/convai/conversation?agent_id={AGENT_ID}"
        
        return JSONResponse(
            status_code=500,
            content={
                "error": "Signed URL failed",
                "fallback_url": fallback_url,
                "agent_id": AGENT_ID,
                "details": str(e)
            }
        )

async def check_agent_exists() -> bool:
    """Проверка существования агента"""
    try:
        headers = {
            "xi-api-key": ELEVENLABS_API_KEY,
            "User-Agent": "ElevenLabs-Voice-Chat/1.0"
        }
        
        url = f"https://api.elevenlabs.io/v1/convai/agents/{AGENT_ID}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=10) as response:
                if response.status == 200:
                    logger.info("✅ Agent exists")
                    return True
                elif response.status == 404:
                    logger.warning("❌ Agent not found")
                    return False
                else:
                    logger.warning(f"Unexpected status: {response.status}")
                    return False
                    
    except Exception as e:
        logger.error(f"Error checking agent: {e}")
        raise

async def fetch_signed_url() -> str:
    """Получение signed URL от ElevenLabs"""
    try:
        headers = {
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json"
        }
        
        # Правильный endpoint с подчеркиванием
        url = f"https://api.elevenlabs.io/v1/convai/conversation/get_signed_url?agent_id={AGENT_ID}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=15) as response:
                if response.status == 200:
                    data = await response.json()
                    signed_url = data.get("signed_url")
                    if signed_url:
                        logger.info("✅ Signed URL obtained")
                        return signed_url
                    else:
                        raise Exception("No signed_url in response")
                else:
                    text = await response.text()
                    raise Exception(f"API error {response.status}: {text}")
                    
    except Exception as e:
        logger.error(f"Failed to get signed URL: {e}")
        raise

@app.post("/api/retry-agent")
async def retry_agent():
    """Повторная попытка проверки агента"""
    try:
        exists = await check_agent_exists()
        
        return JSONResponse({
            "success": exists,
            "agent_id": AGENT_ID,
            "status": "ready" if exists else "not_found"
        })
        
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e),
                "agent_id": AGENT_ID
            }
        )

@app.get("/api/diagnostics")
async def diagnostics():
    """Диагностика системы"""
    diagnostics_data = {
        "timestamp": time.time(),
        "server": {
            "status": "running",
            "uptime": time.time() - app_state["start_time"]
        },
        "configuration": {
            "agent_id": AGENT_ID,
            "api_key_configured": app_state["api_key_configured"]
        }
    }
    
    # Тесты
    tests = {}
    
    # Тест API подключения
    try:
        await check_agent_exists()
        tests["api_connectivity"] = "passed"
    except:
        tests["api_connectivity"] = "failed"
    
    # Тест signed URL
    try:
        await fetch_signed_url()
        tests["signed_url_generation"] = "passed"
    except:
        tests["signed_url_generation"] = "failed"
    
    diagnostics_data["tests"] = tests
    
    return JSONResponse(diagnostics_data)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
