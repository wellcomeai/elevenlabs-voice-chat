"""
🎤 Real-time Voice Assistant - Streaming STT+LLM+TTS
Версия: 5.0.0 - Real-time с классическими OpenAI API

Архитектура:
- Streaming audio input через WebSocket
- Voice Activity Detection 
- Auto-commit в Whisper STT
- Instant GPT-4o-mini processing
- Streaming TTS-1 output
- Interruption handling

Автор: AI Assistant
"""

import asyncio
import json
import logging
import base64
import time
import uuid
import os
import tempfile
import io
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass
from enum import Enum
import threading
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
import uvicorn

# ===== КОНФИГУРАЦИЯ =====

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s'
)
logger = logging.getLogger(__name__)

# API ключ OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    logger.error("🚨 OPENAI_API_KEY не установлен!")
    raise ValueError("OpenAI API key is required")

# Инициализация OpenAI клиента
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# Конфигурация реального времени
REALTIME_CONFIG = {
    "audio_chunk_duration_ms": 100,    # Размер аудио чанка в мс
    "silence_threshold": 0.01,         # Порог тишины для VAD
    "silence_duration_ms": 800,        # Длительность тишины для auto-commit
    "max_audio_buffer_duration": 30,   # Макс. длительность буфера в сек
    "vad_check_interval_ms": 50,       # Интервал проверки VAD
    "interruption_response_ms": 200,   # Время отклика на перебивание
    
    # Whisper настройки
    "whisper": {
        "model": "whisper-1",
        "language": "ru",
        "temperature": 0.0,
        "prompt": "Голосовой ассистент. Пользователь говорит на русском языке."
    },
    
    # GPT настройки  
    "gpt": {
        "model": "gpt-4o-mini",
        "max_tokens": 150,
        "temperature": 0.7,
        "stream": False  # Пока без стриминга для простоты
    },
    
    # TTS настройки
    "tts": {
        "model": "tts-1",
        "voice": "alloy", 
        "speed": 1.1,  # Чуть быстрее для реального времени
        "response_format": "mp3"
    }
}

# ===== ТИПЫ И СОСТОЯНИЯ =====

class ConversationState(Enum):
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING_STT = "processing_stt"
    PROCESSING_LLM = "processing_llm" 
    PROCESSING_TTS = "processing_tts"
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"

@dataclass
class AudioChunk:
    data: bytes
    timestamp: float
    chunk_id: int
    amplitude: float = 0.0

@dataclass
class ProcessingMetrics:
    stt_latency_ms: float = 0.0
    llm_latency_ms: float = 0.0
    tts_latency_ms: float = 0.0
    total_latency_ms: float = 0.0
    audio_duration_ms: float = 0.0

# ===== VOICE ACTIVITY DETECTOR =====

class VoiceActivityDetector:
    """Определение голосовой активности"""
    
    def __init__(self, 
                 silence_threshold: float = 0.01,
                 silence_duration_ms: int = 800):
        self.silence_threshold = silence_threshold
        self.silence_duration_ms = silence_duration_ms
        self.last_voice_time = 0.0
        self.is_voice_active = False
        
    def process_chunk(self, audio_chunk: AudioChunk) -> dict:
        """
        Обрабатывает аудио чанк и возвращает VAD результат
        """
        # Простейший VAD - по амплитуде
        # В продакшене можно заменить на более сложный алгоритм
        
        current_time = audio_chunk.timestamp
        has_voice = audio_chunk.amplitude > self.silence_threshold
        
        result = {
            "has_voice": has_voice,
            "is_speech_active": self.is_voice_active,
            "silence_duration_ms": 0,
            "should_commit": False
        }
        
        if has_voice:
            if not self.is_voice_active:
                # Начало речи
                self.is_voice_active = True
                result["speech_started"] = True
                logger.info("🎤 Speech started detected")
                
            self.last_voice_time = current_time
            
        else:
            # Тишина
            if self.is_voice_active:
                silence_duration = (current_time - self.last_voice_time) * 1000
                result["silence_duration_ms"] = silence_duration
                
                if silence_duration >= self.silence_duration_ms:
                    # Конец речи
                    self.is_voice_active = False
                    result["speech_stopped"] = True
                    result["should_commit"] = True
                    logger.info(f"🔇 Speech stopped after {silence_duration:.0f}ms silence")
        
        return result

# ===== AUDIO PROCESSOR =====

class AudioProcessor:
    """Обработка аудио в реальном времени"""
    
    def __init__(self):
        self.audio_buffer: List[AudioChunk] = []
        self.chunk_counter = 0
        self.buffer_start_time = 0.0
        
    def add_chunk(self, audio_data: bytes, timestamp: float) -> AudioChunk:
        """Добавляет аудио чанк в буфер"""
        
        # Вычисляем амплитуду для VAD
        amplitude = self._calculate_amplitude(audio_data)
        
        chunk = AudioChunk(
            data=audio_data,
            timestamp=timestamp,
            chunk_id=self.chunk_counter,
            amplitude=amplitude
        )
        
        self.audio_buffer.append(chunk)
        self.chunk_counter += 1
        
        if len(self.audio_buffer) == 1:
            self.buffer_start_time = timestamp
            
        return chunk
    
    def get_buffer_audio(self) -> bytes:
        """Возвращает объединенное аудио из буфера"""
        if not self.audio_buffer:
            return b""
            
        combined_audio = b"".join(chunk.data for chunk in self.audio_buffer)
        return combined_audio
    
    def get_buffer_duration_ms(self) -> float:
        """Возвращает длительность буфера в мс"""
        if not self.audio_buffer:
            return 0.0
        
        last_chunk = self.audio_buffer[-1]
        duration = (last_chunk.timestamp - self.buffer_start_time) * 1000
        return duration
    
    def clear_buffer(self):
        """Очищает аудио буфер"""
        chunk_count = len(self.audio_buffer)
        duration = self.get_buffer_duration_ms()
        
        self.audio_buffer.clear()
        self.buffer_start_time = 0.0
        
        logger.info(f"🧹 Buffer cleared: {chunk_count} chunks, {duration:.0f}ms")
    
    def _calculate_amplitude(self, audio_data: bytes) -> float:
        """Вычисляет среднюю амплитуду аудио чанка"""
        if len(audio_data) < 2:
            return 0.0
            
        try:
            # Предполагаем 16-bit PCM
            import struct
            sample_count = len(audio_data) // 2
            
            if sample_count == 0:
                return 0.0
                
            # Конвертируем в int16 и вычисляем RMS
            samples = struct.unpack(f"<{sample_count}h", audio_data[:sample_count * 2])
            rms = (sum(s * s for s in samples) / sample_count) ** 0.5
            
            # Нормализуем к диапазону 0-1
            normalized_rms = rms / 32768.0
            return normalized_rms
            
        except Exception as e:
            logger.warning(f"Error calculating amplitude: {e}")
            return 0.0

# ===== REALTIME CONVERSATION SESSION =====

class RealtimeConversationSession:
    """
    Управляет сессией реального времени разговора
    """
    
    def __init__(self, session_id: str, websocket: WebSocket):
        self.session_id = session_id
        self.websocket = websocket
        self.state = ConversationState.IDLE
        
        # Аудио компоненты
        self.audio_processor = AudioProcessor()
        self.vad = VoiceActivityDetector(
            silence_threshold=REALTIME_CONFIG["silence_threshold"],
            silence_duration_ms=REALTIME_CONFIG["silence_duration_ms"]
        )
        
        # Контекст разговора
        self.conversation_history: List[Dict[str, str]] = []
        self.current_processing_start = 0.0
        
        # ThreadPoolExecutor для блокирующих OpenAI вызовов
        self.executor = ThreadPoolExecutor(max_workers=3)
        
        # Метрики
        self.metrics = ProcessingMetrics()
        self.total_interactions = 0
        self.interruptions_count = 0
        
        logger.info(f"🎤 Created conversation session: {session_id}")
    
    async def process_audio_chunk(self, audio_data: bytes):
        """Обрабатывает входящий аудио чанк"""
        
        timestamp = time.time()
        
        # Добавляем в буфер
        chunk = self.audio_processor.add_chunk(audio_data, timestamp)
        
        # VAD анализ
        vad_result = self.vad.process_chunk(chunk)
        
        # Обновляем состояние на основе VAD
        if vad_result.get("speech_started"):
            await self._update_state(ConversationState.LISTENING)
            await self._send_event("speech_started", {"timestamp": timestamp})
        
        if vad_result.get("speech_stopped"):
            await self._send_event("speech_stopped", {
                "timestamp": timestamp,
                "duration_ms": self.audio_processor.get_buffer_duration_ms()
            })
            
        # Автоматический commit при окончании речи
        if vad_result.get("should_commit"):
            await self._commit_audio_buffer()
            
        # Проверяем переполнение буфера
        buffer_duration = self.audio_processor.get_buffer_duration_ms()
        if buffer_duration > REALTIME_CONFIG["max_audio_buffer_duration"] * 1000:
            logger.warning(f"Audio buffer overflow: {buffer_duration:.0f}ms")
            await self._commit_audio_buffer()
    
    async def _commit_audio_buffer(self):
        """Отправляет аудио буфер на обработку через STT"""
        
        if self.state != ConversationState.LISTENING:
            return
        
        audio_data = self.audio_processor.get_buffer_audio()
        if len(audio_data) < 1000:  # Минимальный размер
            logger.info("Audio buffer too small, skipping")
            self.audio_processor.clear_buffer()
            await self._update_state(ConversationState.IDLE)
            return
        
        duration_ms = self.audio_processor.get_buffer_duration_ms()
        logger.info(f"🎯 Committing audio buffer: {len(audio_data)} bytes, {duration_ms:.0f}ms")
        
        # Очищаем буфер сразу для приема нового аудио
        self.audio_processor.clear_buffer()
        
        # Начинаем обработку
        self.current_processing_start = time.time()
        await self._update_state(ConversationState.PROCESSING_STT)
        
        # Запускаем полный pipeline обработки
        asyncio.create_task(self._process_audio_pipeline(audio_data, duration_ms))
    
    async def _process_audio_pipeline(self, audio_data: bytes, duration_ms: float):
        """Полный pipeline: STT → LLM → TTS"""
        
        try:
            pipeline_start = time.time()
            
            # 1. STT - Whisper
            await self._update_state(ConversationState.PROCESSING_STT)
            transcript = await self._run_whisper_stt(audio_data)
            
            if not transcript or len(transcript.strip()) < 2:
                logger.info("Empty transcript, returning to idle")
                await self._update_state(ConversationState.IDLE)
                return
            
            # Отправляем транскрипцию клиенту
            await self._send_event("transcription", {
                "text": transcript,
                "duration_ms": duration_ms
            })
            
            # 2. LLM - GPT
            await self._update_state(ConversationState.PROCESSING_LLM)
            response_text = await self._run_gpt_generation(transcript)
            
            # Отправляем текстовый ответ
            await self._send_event("llm_response", {
                "text": response_text
            })
            
            # 3. TTS - OpenAI TTS
            await self._update_state(ConversationState.PROCESSING_TTS)
            await self._run_tts_synthesis(response_text)
            
            # Вычисляем итоговые метрики
            total_latency = (time.time() - pipeline_start) * 1000
            self.metrics.total_latency_ms = total_latency
            self.total_interactions += 1
            
            logger.info(f"⚡ Total pipeline latency: {total_latency:.0f}ms")
            
            await self._send_event("pipeline_complete", {
                "total_latency_ms": total_latency,
                "stt_latency_ms": self.metrics.stt_latency_ms,
                "llm_latency_ms": self.metrics.llm_latency_ms,
                "tts_latency_ms": self.metrics.tts_latency_ms
            })
            
            # Возвращаемся к ожиданию
            await self._update_state(ConversationState.IDLE)
            
        except Exception as e:
            logger.error(f"Pipeline error: {e}")
            await self._send_event("error", {
                "message": f"Ошибка обработки: {str(e)}"
            })
            await self._update_state(ConversationState.IDLE)
    
    async def _run_whisper_stt(self, audio_data: bytes) -> str:
        """Запускает Whisper STT"""
        
        start_time = time.time()
        
        def whisper_call():
            try:
                # Создаем временный файл
                with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as temp_file:
                    temp_file.write(audio_data)
                    temp_path = temp_file.name
                
                try:
                    # Вызов Whisper API
                    with open(temp_path, 'rb') as audio_file:
                        response = openai_client.audio.transcriptions.create(
                            model=REALTIME_CONFIG["whisper"]["model"],
                            file=audio_file,
                            language=REALTIME_CONFIG["whisper"]["language"],
                            temperature=REALTIME_CONFIG["whisper"]["temperature"],
                            prompt=REALTIME_CONFIG["whisper"]["prompt"]
                        )
                    
                    return response.text.strip()
                    
                finally:
                    # Удаляем временный файл
                    try:
                        os.unlink(temp_path)
                    except:
                        pass
                        
            except Exception as e:
                logger.error(f"Whisper error: {e}")
                return ""
        
        # Выполняем в отдельном потоке
        transcript = await asyncio.get_event_loop().run_in_executor(
            self.executor, whisper_call
        )
        
        latency_ms = (time.time() - start_time) * 1000
        self.metrics.stt_latency_ms = latency_ms
        
        logger.info(f"🎤 STT completed ({latency_ms:.0f}ms): {transcript}")
        return transcript
    
    async def _run_gpt_generation(self, user_message: str) -> str:
        """Запускает GPT генерацию"""
        
        start_time = time.time()
        
        # Добавляем в историю
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })
        
        # Ограничиваем историю
        if len(self.conversation_history) > 10:
            self.conversation_history = self.conversation_history[-8:]
        
        def gpt_call():
            try:
                messages = [
                    {
                        "role": "system",
                        "content": """Ты - дружелюбный голосовой ассистент.

Правила:
- Отвечай ОЧЕНЬ кратко (1-2 предложения максимум)
- Говори естественно и живо
- Проявляй энтузиазм и позитивность  
- Если не знаешь - честно скажи
- Никаких длинных объяснений

Стиль: Как настоящий человек, а не робот."""
                    }
                ] + self.conversation_history
                
                response = openai_client.chat.completions.create(
                    model=REALTIME_CONFIG["gpt"]["model"],
                    messages=messages,
                    max_tokens=REALTIME_CONFIG["gpt"]["max_tokens"],
                    temperature=REALTIME_CONFIG["gpt"]["temperature"]
                )
                
                return response.choices[0].message.content.strip()
                
            except Exception as e:
                logger.error(f"GPT error: {e}")
                return "Извините, произошла ошибка. Попробуйте еще раз."
        
        # Выполняем в отдельном потоке
        response_text = await asyncio.get_event_loop().run_in_executor(
            self.executor, gpt_call
        )
        
        latency_ms = (time.time() - start_time) * 1000
        self.metrics.llm_latency_ms = latency_ms
        
        # Добавляем ответ в историю
        self.conversation_history.append({
            "role": "assistant", 
            "content": response_text
        })
        
        logger.info(f"🧠 LLM completed ({latency_ms:.0f}ms): {response_text}")
        return response_text
    
    async def _run_tts_synthesis(self, text: str):
        """Запускает TTS синтез с потоковой передачей"""
        
        start_time = time.time()
        await self._update_state(ConversationState.SPEAKING)
        
        # Уведомляем о начале TTS
        await self._send_event("tts_started", {
            "text": text,
            "timestamp": time.time()
        })
        
        def tts_call():
            try:
                # Создаем временный файл для TTS
                with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as temp_file:
                    temp_path = temp_file.name
                
                try:
                    # Вызов TTS API
                    response = openai_client.audio.speech.create(
                        model=REALTIME_CONFIG["tts"]["model"],
                        voice=REALTIME_CONFIG["tts"]["voice"],
                        input=text,
                        speed=REALTIME_CONFIG["tts"]["speed"],
                        response_format=REALTIME_CONFIG["tts"]["response_format"]
                    )
                    
                    # Сохраняем аудио
                    response.stream_to_file(temp_path)
                    
                    # Читаем аудио файл
                    with open(temp_path, 'rb') as audio_file:
                        audio_content = audio_file.read()
                    
                    return audio_content
                    
                finally:
                    # Удаляем временный файл
                    try:
                        os.unlink(temp_path)
                    except:
                        pass
                        
            except Exception as e:
                logger.error(f"TTS error: {e}")
                return b""
        
        # Выполняем TTS в отдельном потоке
        audio_content = await asyncio.get_event_loop().run_in_executor(
            self.executor, tts_call
        )
        
        latency_ms = (time.time() - start_time) * 1000
        self.metrics.tts_latency_ms = latency_ms
        
        if audio_content:
            # Отправляем аудио чанками
            await self._stream_tts_audio(audio_content)
            
        logger.info(f"🔊 TTS completed ({latency_ms:.0f}ms)")
        
        # Уведомляем о завершении
        await self._send_event("tts_complete", {
            "latency_ms": latency_ms,
            "audio_size": len(audio_content)
        })
    
    async def _stream_tts_audio(self, audio_content: bytes):
        """Потоковая передача TTS аудио"""
        
        chunk_size = 8192  # 8KB чанки
        total_chunks = (len(audio_content) + chunk_size - 1) // chunk_size
        
        logger.info(f"📤 Streaming {len(audio_content)} bytes in {total_chunks} chunks")
        
        for i in range(0, len(audio_content), chunk_size):
            chunk = audio_content[i:i + chunk_size]
            chunk_id = i // chunk_size + 1
            
            audio_b64 = base64.b64encode(chunk).decode('utf-8')
            
            await self._send_event("audio_chunk", {
                "audio": audio_b64,
                "chunk_id": chunk_id,
                "total_chunks": total_chunks,
                "is_final": chunk_id == total_chunks
            })
            
            # Небольшая задержка между чанками для smooth playback
            await asyncio.sleep(0.01)
    
    async def handle_interruption(self):
        """Обработка перебивания пользователем"""
        
        if self.state not in [ConversationState.SPEAKING, ConversationState.PROCESSING_TTS]:
            return
            
        logger.info("⚡ Handling user interruption")
        self.interruptions_count += 1
        
        # Переходим в состояние прерывания
        await self._update_state(ConversationState.INTERRUPTED)
        
        # Уведомляем клиента о прерывании
        await self._send_event("interrupted", {
            "timestamp": time.time(),
            "previous_state": self.state.value
        })
        
        # Очищаем аудио буфер
        self.audio_processor.clear_buffer()
        
        # Быстро переходим к прослушиванию
        await asyncio.sleep(0.1)
        await self._update_state(ConversationState.IDLE)
    
    async def _update_state(self, new_state: ConversationState):
        """Обновляет состояние сессии"""
        old_state = self.state
        self.state = new_state
        
        await self._send_event("state_changed", {
            "old_state": old_state.value,
            "new_state": new_state.value,
            "timestamp": time.time()
        })
        
        logger.info(f"🔄 State: {old_state.value} → {new_state.value}")
    
    async def _send_event(self, event_type: str, data: Dict[str, Any] = None):
        """Отправляет событие клиенту"""
        try:
            message = {
                "type": event_type,
                "session_id": self.session_id,
                "timestamp": time.time()
            }
            
            if data:
                message.update(data)
            
            await self.websocket.send_json(message)
            
        except Exception as e:
            logger.warning(f"Failed to send event {event_type}: {e}")
    
    async def get_session_stats(self) -> Dict[str, Any]:
        """Возвращает статистику сессии"""
        return {
            "session_id": self.session_id,
            "current_state": self.state.value,
            "total_interactions": self.total_interactions,
            "interruptions_count": self.interruptions_count,
            "conversation_length": len(self.conversation_history),
            "metrics": {
                "avg_stt_latency_ms": self.metrics.stt_latency_ms,
                "avg_llm_latency_ms": self.metrics.llm_latency_ms,
                "avg_tts_latency_ms": self.metrics.tts_latency_ms,
                "avg_total_latency_ms": self.metrics.total_latency_ms
            }
        }
    
    async def close(self):
        """Закрывает сессию"""
        logger.info(f"🔚 Closing session: {self.session_id}")
        self.executor.shutdown(wait=False)

# ===== SESSION MANAGER =====

class SessionManager:
    """Управляет активными сессиями"""
    
    def __init__(self):
        self.sessions: Dict[str, RealtimeConversationSession] = {}
    
    async def create_session(self, websocket: WebSocket) -> RealtimeConversationSession:
        session_id = str(uuid.uuid4())
        session = RealtimeConversationSession(session_id, websocket)
        self.sessions[session_id] = session
        
        logger.info(f"✅ Session created: {session_id}")
        return session
    
    async def close_session(self, session_id: str):
        if session_id in self.sessions:
            await self.sessions[session_id].close()
            del self.sessions[session_id]
            logger.info(f"🗑️ Session removed: {session_id}")

# ===== FASTAPI APPLICATION =====

app = FastAPI(
    title="Real-time Voice Assistant v5.0",
    description="Streaming STT + LLM + TTS voice assistant",
    version="5.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Глобальный менеджер сессий
session_manager = SessionManager()

# ===== ROUTES =====

@app.get("/")
async def get_homepage():
    return HTMLResponse(content="""
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Real-time Voice Assistant v5.0</title>
    <style>
        body {
            font-family: system-ui, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            margin: 0;
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            color: white;
        }
        .container {
            text-align: center;
            background: rgba(255,255,255,0.1);
            padding: 2rem;
            border-radius: 20px;
            backdrop-filter: blur(10px);
        }
        h1 { font-size: 2.5rem; margin-bottom: 1rem; }
        .status { font-size: 1.2rem; margin: 1rem 0; }
        .voice-button {
            width: 120px;
            height: 120px;
            border-radius: 50%;
            border: none;
            background: linear-gradient(135deg, #ff6b6b, #ee5a24);
            color: white;
            font-size: 3rem;
            cursor: pointer;
            margin: 2rem auto;
            display: block;
            transition: all 0.3s ease;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
        }
        .voice-button:hover {
            transform: scale(1.05);
            box-shadow: 0 15px 40px rgba(0,0,0,0.4);
        }
        .voice-button.listening {
            background: linear-gradient(135deg, #74b9ff, #0984e3);
            animation: pulse 1.5s infinite;
        }
        .voice-button.processing {
            background: linear-gradient(135deg, #fdcb6e, #e17055);
            animation: spin 1s linear infinite;
        }
        .voice-button.speaking {
            background: linear-gradient(135deg, #00b894, #00a085);
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
        .conversation {
            max-width: 600px;
            margin: 2rem auto;
            background: rgba(255,255,255,0.1);
            border-radius: 15px;
            padding: 1rem;
            max-height: 300px;
            overflow-y: auto;
        }
        .message {
            margin: 0.5rem 0;
            padding: 0.5rem 1rem;
            border-radius: 10px;
        }
        .user { background: rgba(116, 185, 255, 0.3); text-align: right; }
        .assistant { background: rgba(0, 184, 148, 0.3); text-align: left; }
        .metrics {
            font-size: 0.9rem;
            opacity: 0.8;
            margin-top: 1rem;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎤 Real-time Voice Assistant</h1>
        <div class="status" id="status">Нажмите для начала разговора</div>
        
        <button class="voice-button" id="voiceBtn">🎤</button>
        
        <div class="conversation" id="conversation"></div>
        
        <div class="metrics" id="metrics"></div>
    </div>

    <script>
        class RealtimeVoiceClient {
            constructor() {
                this.ws = null;
                this.mediaRecorder = null;
                this.audioChunks = [];
                this.isConnected = false;
                this.isRecording = false;
                this.currentState = 'idle';
                
                this.initElements();
                this.connect();
            }
            
            initElements() {
                this.voiceBtn = document.getElementById('voiceBtn');
                this.status = document.getElementById('status');
                this.conversation = document.getElementById('conversation');
                this.metrics = document.getElementById('metrics');
                
                this.voiceBtn.addEventListener('click', () => this.toggleRecording());
            }
            
            connect() {
                const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                const wsUrl = `${protocol}//${window.location.host}/ws/voice`;
                
                this.ws = new WebSocket(wsUrl);
                
                this.ws.onopen = () => {
                    this.isConnected = true;
                    this.status.textContent = 'Подключено! Готов к работе';
                    console.log('🔗 Connected to voice assistant');
                };
                
                this.ws.onmessage = (event) => {
                    const data = JSON.parse(event.data);
                    this.handleMessage(data);
                };
                
                this.ws.onclose = () => {
                    this.isConnected = false;
                    this.status.textContent = 'Соединение потеряно';
                    console.log('❌ Disconnected from voice assistant');
                };
            }
            
            async toggleRecording() {
                if (!this.isConnected) {
                    this.status.textContent = 'Нет соединения с сервером';
                    return;
                }
                
                if (this.isRecording) {
                    this.stopRecording();
                } else {
                    await this.startRecording();
                }
            }
            
            async startRecording() {
                try {
                    const stream = await navigator.mediaDevices.getUserMedia({
                        audio: {
                            sampleRate: 16000,
                            channelCount: 1,
                            echoCancellation: true,
                            noiseSuppression: true
                        }
                    });
                    
                    this.mediaRecorder = new MediaRecorder(stream, {
                        mimeType: 'audio/webm',
                        audioBitsPerSecond: 16000
                    });
                    
                    this.mediaRecorder.ondataavailable = (event) => {
                        if (event.data.size > 0) {
                            this.sendAudioChunk(event.data);
                        }
                    };
                    
                    this.mediaRecorder.start(100); // 100ms chunks
                    this.isRecording = true;
                    this.updateUI();
                    this.status.textContent = 'Слушаю... (нажмите чтобы остановить)';
                    
                } catch (error) {
                    console.error('Recording error:', error);
                    this.status.textContent = `Ошибка микрофона: ${error.message}`;
                }
            }
            
            stopRecording() {
                if (this.mediaRecorder) {
                    this.mediaRecorder.stop();
                    this.mediaRecorder.stream.getTracks().forEach(track => track.stop());
                    this.mediaRecorder = null;
                }
                
                this.isRecording = false;
                this.updateUI();
                this.status.textContent = 'Обработка...';
            }
            
            async sendAudioChunk(audioBlob) {
                if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
                
                try {
                    const arrayBuffer = await audioBlob.arrayBuffer();
                    const audioArray = Array.from(new Uint8Array(arrayBuffer));
                    
                    this.ws.send(JSON.stringify({
                        type: 'audio_chunk',
                        data: audioArray,
                        timestamp: Date.now()
                    }));
                    
                } catch (error) {
                    console.error('Error sending audio chunk:', error);
                }
            }
            
            handleMessage(data) {
                console.log('📨 Received:', data.type, data);
                
                switch (data.type) {
                    case 'state_changed':
                        this.currentState = data.new_state;
                        this.updateUI();
                        break;
                        
                    case 'transcription':
                        this.addMessage('user', data.text);
                        break;
                        
                    case 'llm_response':
                        this.addMessage('assistant', data.text);
                        break;
                        
                    case 'pipeline_complete':
                        this.updateMetrics(data);
                        this.status.textContent = 'Готов к работе';
                        break;
                        
                    case 'error':
                        this.status.textContent = `Ошибка: ${data.message}`;
                        break;
                }
            }
            
            updateUI() {
                this.voiceBtn.className = 'voice-button';
                
                if (this.isRecording) {
                    this.voiceBtn.classList.add('listening');
                    this.voiceBtn.textContent = '⏹️';
                } else {
                    switch (this.currentState) {
                        case 'processing_stt':
                        case 'processing_llm':
                        case 'processing_tts':
                            this.voiceBtn.classList.add('processing');
                            this.voiceBtn.textContent = '⚙️';
                            break;
                        case 'speaking':
                            this.voiceBtn.classList.add('speaking');
                            this.voiceBtn.textContent = '🔊';
                            break;
                        default:
                            this.voiceBtn.textContent = '🎤';
                    }
                }
            }
            
            addMessage(role, text) {
                const messageDiv = document.createElement('div');
                messageDiv.className = `message ${role}`;
                messageDiv.textContent = text;
                
                this.conversation.appendChild(messageDiv);
                this.conversation.scrollTop = this.conversation.scrollHeight;
            }
            
            updateMetrics(data) {
                this.metrics.innerHTML = `
                    <strong>Последняя обработка:</strong><br>
                    STT: ${data.stt_latency_ms?.toFixed(0)}ms | 
                    LLM: ${data.llm_latency_ms?.toFixed(0)}ms | 
                    TTS: ${data.tts_latency_ms?.toFixed(0)}ms<br>
                    <strong>Общее время: ${data.total_latency_ms?.toFixed(0)}ms</strong>
                `;
            }
        }
        
        // Запускаем приложение
        document.addEventListener('DOMContentLoaded', () => {
            window.voiceClient = new RealtimeVoiceClient();
        });
    </script>
</body>
</html>
    """)

@app.get("/api/health")
async def health_check():
    return JSONResponse({
        "status": "healthy",
        "version": "5.0.0",
        "description": "Real-time Voice Assistant with streaming STT+LLM+TTS",
        "active_sessions": len(session_manager.sessions)
    })

# ===== WEBSOCKET ENDPOINT =====

@app.websocket("/ws/voice")
async def websocket_voice_endpoint(websocket: WebSocket):
    """
    Главный WebSocket endpoint для голосового взаимодействия
    """
    await websocket.accept()
    
    session = await session_manager.create_session(websocket)
    
    try:
        while True:
            message = await websocket.receive_json()
            message_type = message.get("type")
            
            if message_type == "audio_chunk":
                # Обрабатываем аудио чанк
                audio_data = bytes(message["data"])
                await session.process_audio_chunk(audio_data)
                
            elif message_type == "interrupt":
                # Обрабатываем перебивание
                await session.handle_interruption()
                
            elif message_type == "get_stats":
                # Отправляем статистику
                stats = await session.get_session_stats()
                await websocket.send_json({
                    "type": "session_stats",
                    **stats
                })
            
            else:
                logger.warning(f"Unknown message type: {message_type}")
    
    except WebSocketDisconnect:
        logger.info(f"Client disconnected: {session.session_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        await session_manager.close_session(session.session_id)

# ===== STARTUP =====

def main():
    logger.info("🚀 Starting Real-time Voice Assistant v5.0")
    logger.info("📋 Configuration:")
    logger.info(f"   - Audio chunk duration: {REALTIME_CONFIG['audio_chunk_duration_ms']}ms")
    logger.info(f"   - Silence duration: {REALTIME_CONFIG['silence_duration_ms']}ms")
    logger.info(f"   - VAD threshold: {REALTIME_CONFIG['silence_threshold']}")
    logger.info(f"   - Whisper model: {REALTIME_CONFIG['whisper']['model']}")
    logger.info(f"   - GPT model: {REALTIME_CONFIG['gpt']['model']}")
    logger.info(f"   - TTS model: {REALTIME_CONFIG['tts']['model']} ({REALTIME_CONFIG['tts']['voice']})")
    
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )

if __name__ == "__main__":
    main()
