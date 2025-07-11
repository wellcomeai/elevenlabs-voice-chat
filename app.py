"""
🎤 Hands-Free Real-time Voice Assistant v6.1 - ИСПРАВЛЕННАЯ ВЕРСИЯ
Исправления:
- Правильная логика детекции перебивания (только в состоянии SPEAKING)
- Дебаунсинг для предотвращения спама
- Улучшенные пороги VAD
- Четкое разделение логики состояний
- Подробное логирование для отладки
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
import wave
from typing import Optional, Dict, Any, List, Set
from dataclasses import dataclass
from enum import Enum
import threading
from concurrent.futures import ThreadPoolExecutor
import collections

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

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    logger.error("🚨 OPENAI_API_KEY не установлен!")
    raise ValueError("OpenAI API key is required")

openai_client = OpenAI(api_key=OPENAI_API_KEY)

# ИСПРАВЛЕННАЯ конфигурация для стабильной работы
HANDS_FREE_CONFIG = {
    # Аудио настройки
    "audio_chunk_duration_ms": 100,
    "sample_rate": 16000,
    "channels": 1,
    
    # ИСПРАВЛЕННЫЕ VAD настройки - более консервативные
    "vad_threshold": 0.015,              # Увеличен для уменьшения ложных срабатываний
    "vad_hang_time_ms": 800,             # Больше времени до завершения речи
    "vad_attack_time_ms": 300,           # Больше времени подтверждения начала речи
    "min_speech_duration_ms": 600,       # Минимальная длительность речи
    "max_speech_duration_ms": 25000,     # Максимальная длительность речи
    
    # ИСПРАВЛЕННЫЕ настройки перебивания
    "interrupt_threshold": 0.025,        # Значительно выше обычного порога
    "interrupt_confirmation_ms": 500,    # Длительное подтверждение
    "interrupt_cooldown_ms": 1000,       # Защита от спама перебивания
    "interrupt_min_speaking_time_ms": 1000,  # Минимальное время говорения до возможности перебить
    
    # Эхо-подавление
    "echo_suppression_duration_ms": 2000,   # Увеличено время подавления
    "echo_suppression_factor": 0.3,         # Сильнее подавление
    
    # Буферизация
    "audio_buffer_size": 50,
    "processing_overlap_ms": 200,
    
    # OpenAI настройки
    "whisper": {
        "model": "whisper-1",
        "language": "ru",
        "temperature": 0.0,
        "prompt": "Разговор с голосовым ассистентом. Четкая речь пользователя."
    },
    
    "gpt": {
        "model": "gpt-4o-mini",
        "max_tokens": 100,
        "temperature": 0.8,
        "stream": False
    },
    
    "tts": {
        "model": "tts-1",
        "voice": "alloy",
        "speed": 1.1,
        "response_format": "mp3"
    }
}

# ===== СОСТОЯНИЯ =====

class ConversationState(Enum):
    INITIALIZING = "initializing"
    LISTENING = "listening"
    SPEECH_DETECTED = "speech_detected"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"
    ERROR = "error"
    PAUSED = "paused"

@dataclass
class AudioChunk:
    data: bytes
    timestamp: float
    amplitude: float
    chunk_id: int
    is_echo_suppressed: bool = False

@dataclass
class SpeechSegment:
    start_time: float
    end_time: float
    audio_data: bytes
    confidence: float = 0.0

# ===== ИСПРАВЛЕННЫЙ VAD =====

class FixedAdvancedVAD:
    """ИСПРАВЛЕННЫЙ детектор голосовой активности с правильной логикой"""
    
    def __init__(self, config: dict):
        self.threshold = config["vad_threshold"]
        self.hang_time_ms = config["vad_hang_time_ms"]
        self.attack_time_ms = config["vad_attack_time_ms"]
        
        # ИСПРАВЛЕННЫЕ настройки перебивания
        self.interrupt_threshold = config["interrupt_threshold"]
        self.interrupt_confirmation_ms = config["interrupt_confirmation_ms"]
        self.interrupt_cooldown_ms = config["interrupt_cooldown_ms"]
        self.interrupt_min_speaking_time_ms = config["interrupt_min_speaking_time_ms"]
        
        # Состояние VAD
        self.is_speech_active = False
        self.speech_start_time = 0.0
        self.last_speech_time = 0.0
        self.potential_speech_start = 0.0
        
        # ИСПРАВЛЕННОЕ состояние перебивания
        self.interrupt_candidate_start = 0.0
        self.last_interrupt_time = 0.0          # Для cooldown
        self.speaking_start_time = 0.0          # Когда начал говорить ассистент
        self.interrupt_detection_enabled = False # Включается только в состоянии SPEAKING
        
        # Скользящие окна для сглаживания
        self.amplitude_window = collections.deque(maxlen=5)
        self.long_term_noise = collections.deque(maxlen=50)
        
        # Эхо-подавление
        self.echo_suppression_until = 0.0
        self.echo_factor = config.get("echo_suppression_factor", 0.3)
        
        logger.info(f"🔧 VAD инициализирован: threshold={self.threshold}, interrupt_threshold={self.interrupt_threshold}")
        
    def set_echo_suppression(self, duration_ms: float):
        """Устанавливает время подавления эха"""
        self.echo_suppression_until = time.time() + (duration_ms / 1000.0)
        logger.debug(f"🔇 Эхо-подавление на {duration_ms}ms")
        
    def enable_interrupt_detection(self, speaking_started: bool = True):
        """ИСПРАВЛЕНО: Включает детекцию перебивания только при говорении ассистента"""
        if speaking_started:
            self.interrupt_detection_enabled = True
            self.speaking_start_time = time.time()
            self.interrupt_candidate_start = 0.0
            logger.debug("🔊 Детекция перебивания ВКЛЮЧЕНА")
        else:
            self.interrupt_detection_enabled = False
            self.speaking_start_time = 0.0
            self.interrupt_candidate_start = 0.0
            logger.debug("🔇 Детекция перебивания ОТКЛЮЧЕНА")
    
    def disable_interrupt_detection(self):
        """Отключает детекцию перебивания"""
        self.interrupt_detection_enabled = False
        self.speaking_start_time = 0.0
        self.interrupt_candidate_start = 0.0
        logger.debug("❌ Детекция перебивания отключена")
        
    def process_chunk(self, chunk: AudioChunk, current_state: ConversationState) -> Dict[str, Any]:
        """ИСПРАВЛЕННЫЙ анализ аудио чанка с правильной логикой состояний"""
        
        current_time = chunk.timestamp
        amplitude = chunk.amplitude
        
        # Обновляем окна
        self.amplitude_window.append(amplitude)
        self.long_term_noise.append(amplitude)
        
        # Сглаженная амплитуда
        smooth_amplitude = sum(self.amplitude_window) / len(self.amplitude_window)
        
        # Адаптивный порог на основе фонового шума
        if len(self.long_term_noise) > 10:
            noise_floor = sum(sorted(self.long_term_noise)[:20]) / 20
            adaptive_threshold = max(self.threshold, noise_floor * 2.5)
        else:
            adaptive_threshold = self.threshold
        
        # Эхо-подавление
        effective_amplitude = smooth_amplitude
        if current_time < self.echo_suppression_until:
            effective_amplitude *= self.echo_factor
            chunk.is_echo_suppressed = True
        
        result = {
            "timestamp": current_time,
            "amplitude": amplitude,
            "smooth_amplitude": smooth_amplitude,
            "effective_amplitude": effective_amplitude,
            "adaptive_threshold": adaptive_threshold,
            "is_speech_active": self.is_speech_active,
            "is_echo_suppressed": chunk.is_echo_suppressed,
            "current_state": current_state.value
        }
        
        # === ОСНОВНАЯ ДЕТЕКЦИЯ РЕЧИ ===
        has_voice = effective_amplitude > adaptive_threshold
        
        if has_voice:
            if not self.is_speech_active:
                # Потенциальное начало речи
                if self.potential_speech_start == 0:
                    self.potential_speech_start = current_time
                    logger.debug(f"🎤 Потенциальное начало речи: {effective_amplitude:.4f} > {adaptive_threshold:.4f}")
                    
                # Подтверждение речи после attack time
                elif (current_time - self.potential_speech_start) * 1000 >= self.attack_time_ms:
                    self.is_speech_active = True
                    self.speech_start_time = self.potential_speech_start
                    result["speech_started"] = True
                    result["speech_start_time"] = self.speech_start_time
                    logger.info(f"🎤 Начало речи подтверждено (state: {current_state.value})")
                    
            self.last_speech_time = current_time
            
        else:
            # Тишина
            self.potential_speech_start = 0  # Сброс потенциального начала
            
            if self.is_speech_active:
                silence_duration = (current_time - self.last_speech_time) * 1000
                
                if silence_duration >= self.hang_time_ms:
                    # Конец речи
                    self.is_speech_active = False
                    speech_duration = (self.last_speech_time - self.speech_start_time) * 1000
                    
                    result["speech_ended"] = True
                    result["speech_duration_ms"] = speech_duration
                    result["should_process"] = speech_duration >= HANDS_FREE_CONFIG["min_speech_duration_ms"]
                    
                    logger.info(f"🔇 Конец речи. Длительность: {speech_duration:.0f}ms (state: {current_state.value})")
        
        # === ИСПРАВЛЕННАЯ ДЕТЕКЦИЯ ПЕРЕБИВАНИЯ ===
        # ВАЖНО: Перебивание работает ТОЛЬКО в состоянии SPEAKING
        if (current_state == ConversationState.SPEAKING and 
            self.interrupt_detection_enabled and
            effective_amplitude > self.interrupt_threshold):
            
            # Проверяем cooldown
            if (current_time - self.last_interrupt_time) * 1000 < self.interrupt_cooldown_ms:
                # В cooldown периоде, игнорируем
                pass
            
            # Проверяем минимальное время говорения
            elif (current_time - self.speaking_start_time) * 1000 < self.interrupt_min_speaking_time_ms:
                # Ассистент говорит слишком мало времени, игнорируем
                pass
            
            else:
                # Начинаем отслеживание потенциального перебивания
                if self.interrupt_candidate_start == 0:
                    self.interrupt_candidate_start = current_time
                    logger.debug(f"⚡ Потенциальное перебивание: {effective_amplitude:.4f} > {self.interrupt_threshold:.4f}")
                    
                # Проверяем длительность перебивания
                elif (current_time - self.interrupt_candidate_start) * 1000 >= self.interrupt_confirmation_ms:
                    result["interrupt_detected"] = True
                    result["interrupt_amplitude"] = effective_amplitude
                    self.last_interrupt_time = current_time
                    self.interrupt_candidate_start = 0
                    logger.info(f"⚡ ПЕРЕБИВАНИЕ ПОДТВЕРЖДЕНО! Амплитуда: {effective_amplitude:.4f}")
        
        else:
            # Сброс кандидата на перебивание при снижении амплитуды или неправильном состоянии
            if self.interrupt_candidate_start > 0:
                self.interrupt_candidate_start = 0
                
        return result
    
    def reset_interrupt_detection(self):
        """Сброс состояния детекции перебивания"""
        self.interrupt_candidate_start = 0
        self.last_interrupt_time = 0
        self.speaking_start_time = 0
        logger.debug("🔄 Сброс детекции перебивания")

# ===== КОЛЬЦЕВОЙ АУДИО БУФЕР =====

class CircularAudioBuffer:
    """Кольцевой буфер для постоянного хранения аудио"""
    
    def __init__(self, max_size: int = 50):
        self.buffer = collections.deque(maxlen=max_size)
        self.speech_start_index = None
        self.total_chunks = 0
        
    def add_chunk(self, chunk: AudioChunk):
        """Добавляет чанк в буфер"""
        chunk.chunk_id = self.total_chunks
        self.buffer.append(chunk)
        self.total_chunks += 1
        
    def mark_speech_start(self, timestamp: float):
        """Отмечает начало речи в буфере"""
        for i, chunk in enumerate(self.buffer):
            if abs(chunk.timestamp - timestamp) < 0.15:  # 150ms tolerance
                self.speech_start_index = len(self.buffer) - len(self.buffer) + i
                logger.debug(f"📍 Отмечено начало речи в буфере: индекс {i}")
                break
        
    def extract_speech_segment(self, end_timestamp: float) -> Optional[bytes]:
        """Извлекает сегмент речи из буфера"""
        if self.speech_start_index is None:
            logger.warning("❌ Начало речи не отмечено в буфере")
            return None
            
        speech_chunks = []
        speech_started = False
        
        for chunk in self.buffer:
            if not speech_started and chunk.timestamp >= (self.buffer[0].timestamp if self.speech_start_index == 0 else self.buffer[self.speech_start_index].timestamp):
                speech_started = True
                
            if speech_started:
                speech_chunks.append(chunk.data)
                
                if chunk.timestamp >= end_timestamp:
                    break
        
        if speech_chunks:
            logger.debug(f"🎯 Извлечен сегмент речи: {len(speech_chunks)} чанков")
            return b''.join(speech_chunks)
        return None
    
    def clear_speech_markers(self):
        """Очищает маркеры речи"""
        self.speech_start_index = None

# ===== ИСПРАВЛЕННАЯ HANDS-FREE СЕССИЯ =====

class FixedHandsFreeSession:
    """ИСПРАВЛЕННАЯ сессия hands-free голосового ассистента"""
    
    def __init__(self, session_id: str, websocket: WebSocket):
        self.session_id = session_id
        self.websocket = websocket
        self.state = ConversationState.INITIALIZING
        
        # Компоненты
        self.vad = FixedAdvancedVAD(HANDS_FREE_CONFIG)
        self.audio_buffer = CircularAudioBuffer(HANDS_FREE_CONFIG["audio_buffer_size"])
        
        # Обработка
        self.executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="OpenAI")
        self.current_processing_task = None
        self.current_playback_task = None
        
        # Состояние
        self.conversation_history = []
        self.is_active = True
        self.last_interaction = time.time()
        
        # Метрики
        self.total_exchanges = 0
        self.interruptions_count = 0
        self.false_positives = 0
        
        logger.info(f"🎤 Создана ИСПРАВЛЕННАЯ hands-free сессия: {session_id}")
    
    async def initialize(self):
        """Инициализация сессии"""
        await self._update_state(ConversationState.LISTENING)
        await self._send_event("session_ready", {
            "message": "Голосовой ассистент готов. Говорите в любое время!",
            "config": {
                "vad_threshold": HANDS_FREE_CONFIG["vad_threshold"],
                "interrupt_threshold": HANDS_FREE_CONFIG["interrupt_threshold"],
                "interrupt_enabled": True,
                "echo_suppression": True
            }
        })
        logger.info("✅ ИСПРАВЛЕННАЯ hands-free сессия инициализирована")
    
    async def process_audio_chunk(self, audio_data: bytes):
        """Непрерывная обработка аудио чанков"""
        
        if not self.is_active:
            return
            
        try:
            # Создаем чанк
            timestamp = time.time()
            amplitude = self._calculate_amplitude(audio_data)
            
            chunk = AudioChunk(
                data=audio_data,
                timestamp=timestamp,
                amplitude=amplitude,
                chunk_id=0  # Будет установлен в буфере
            )
            
            # Добавляем в кольцевой буфер
            self.audio_buffer.add_chunk(chunk)
            
            # VAD анализ с передачей текущего состояния
            vad_result = self.vad.process_chunk(chunk, self.state)
            
            # Обрабатываем VAD события
            await self._handle_vad_events(vad_result)
            
            # Отправляем состояние (каждые 20 чанков для экономии)
            if chunk.chunk_id % 20 == 0:
                await self._send_audio_status(vad_result)
                
        except Exception as e:
            logger.error(f"Ошибка обработки аудио: {e}")
            await self._send_event("error", {"message": str(e)})
    
    async def _handle_vad_events(self, vad_result: Dict[str, Any]):
        """ИСПРАВЛЕННАЯ обработка событий VAD"""
        
        # Начало речи
        if vad_result.get("speech_started"):
            if self.state == ConversationState.LISTENING:
                await self._update_state(ConversationState.SPEECH_DETECTED)
                self.audio_buffer.mark_speech_start(vad_result["speech_start_time"])
                await self._send_event("speech_detection", {
                    "type": "started",
                    "timestamp": vad_result["speech_start_time"]
                })
            
            elif self.state == ConversationState.SPEAKING:
                # Речь во время воспроизведения - это потенциальное перебивание
                logger.debug("🎤 Речь обнаружена во время воспроизведения")
        
        # Конец речи
        if vad_result.get("speech_ended"):
            if self.state == ConversationState.SPEECH_DETECTED:
                speech_duration = vad_result["speech_duration_ms"]
                should_process = vad_result["should_process"]
                
                await self._send_event("speech_detection", {
                    "type": "ended",
                    "duration_ms": speech_duration,
                    "will_process": should_process
                })
                
                if should_process:
                    # Извлекаем речевой сегмент и запускаем обработку
                    speech_audio = self.audio_buffer.extract_speech_segment(vad_result["timestamp"])
                    if speech_audio:
                        await self._process_speech_segment(speech_audio, speech_duration)
                    else:
                        logger.warning("❌ Не удалось извлечь речевой сегмент")
                        await self._update_state(ConversationState.LISTENING)
                else:
                    # Слишком короткая речь
                    self.false_positives += 1
                    logger.info(f"❌ Ложное срабатывание VAD: {speech_duration:.0f}ms < {HANDS_FREE_CONFIG['min_speech_duration_ms']}ms")
                    await self._update_state(ConversationState.LISTENING)
                
                self.audio_buffer.clear_speech_markers()
        
        # ИСПРАВЛЕННАЯ обработка перебивания
        if vad_result.get("interrupt_detected"):
            if self.state == ConversationState.SPEAKING:
                await self._handle_interruption(vad_result)
            else:
                logger.warning(f"⚠️ Ложное перебивание в состоянии {self.state.value}")
    
    async def _process_speech_segment(self, audio_data: bytes, duration_ms: float):
        """Обработка речевого сегмента через STT->LLM->TTS"""
        
        await self._update_state(ConversationState.PROCESSING)
        
        # Отключаем детекцию перебивания
        self.vad.disable_interrupt_detection()
        
        # Отменяем предыдущую обработку если есть
        if self.current_processing_task and not self.current_processing_task.done():
            self.current_processing_task.cancel()
        
        self.current_processing_task = asyncio.create_task(
            self._full_processing_pipeline(audio_data, duration_ms)
        )
    
    async def _full_processing_pipeline(self, audio_data: bytes, duration_ms: float):
        """ИСПРАВЛЕННЫЙ полный pipeline обработки"""
        
        try:
            pipeline_start = time.time()
            
            # 1. STT
            await self._send_event("processing_stage", {"stage": "stt", "status": "started"})
            transcript = await self._run_stt(audio_data)
            
            if not transcript or len(transcript.strip()) < 2:
                logger.info("Пустая транскрипция, возвращаемся к прослушиванию")
                await self._update_state(ConversationState.LISTENING)
                return
            
            await self._send_event("transcription", {"text": transcript})
            
            # 2. LLM
            await self._send_event("processing_stage", {"stage": "llm", "status": "started"})
            response_text = await self._run_llm(transcript)
            
            await self._send_event("llm_response", {"text": response_text})
            
            # 3. TTS и воспроизведение
            await self._send_event("processing_stage", {"stage": "tts", "status": "started"})
            await self._run_tts_and_play(response_text)
            
            # Статистика
            total_latency = (time.time() - pipeline_start) * 1000
            self.total_exchanges += 1
            
            await self._send_event("processing_complete", {
                "total_latency_ms": total_latency,
                "total_exchanges": self.total_exchanges
            })
            
            # Возвращаемся к прослушиванию
            await self._update_state(ConversationState.LISTENING)
            
        except asyncio.CancelledError:
            logger.info("Обработка отменена")
            await self._update_state(ConversationState.LISTENING)
        except Exception as e:
            logger.error(f"Ошибка в pipeline: {e}")
            await self._send_event("error", {"message": f"Ошибка обработки: {str(e)}"})
            await self._update_state(ConversationState.LISTENING)
    
    async def _run_stt(self, audio_data: bytes) -> str:
        """Запуск Whisper STT"""
        
        def whisper_call():
            try:
                # Конвертируем в WAV
                wav_data = self._convert_to_wav(audio_data)
                
                # Проверяем размер файла
                if len(wav_data) < 1000:
                    logger.warning("⚠️ Аудио файл слишком мал для Whisper")
                    return ""
                
                with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                    temp_file.write(wav_data)
                    temp_path = temp_file.name
                
                try:
                    with open(temp_path, 'rb') as audio_file:
                        response = openai_client.audio.transcriptions.create(
                            model=HANDS_FREE_CONFIG["whisper"]["model"],
                            file=audio_file,
                            language=HANDS_FREE_CONFIG["whisper"]["language"],
                            temperature=HANDS_FREE_CONFIG["whisper"]["temperature"],
                            prompt=HANDS_FREE_CONFIG["whisper"]["prompt"]
                        )
                    return response.text.strip()
                finally:
                    try:
                        os.unlink(temp_path)
                    except:
                        pass
                        
            except Exception as e:
                logger.error(f"Whisper ошибка: {e}")
                return ""
        
        return await asyncio.get_event_loop().run_in_executor(self.executor, whisper_call)
    
    async def _run_llm(self, user_text: str) -> str:
        """Запуск GPT"""
        
        # Обновляем историю
        self.conversation_history.append({"role": "user", "content": user_text})
        
        # Ограничиваем историю
        if len(self.conversation_history) > 8:
            self.conversation_history = self.conversation_history[-6:]
        
        def gpt_call():
            try:
                messages = [
                    {
                        "role": "system",
                        "content": """Ты голосовой ассистент в режиме живого разговора.

Правила:
- Отвечай ОЧЕНЬ кратко (1-2 предложения)
- Говори естественно, как в телефонном разговоре
- Пользователь может тебя перебивать - это нормально
- Если тебя перебили, не обижайся, продолжай диалог
- Будь дружелюбным и отзывчивым
- Не повторяй "как дела" постоянно

Стиль: Живой разговор, а не формальные ответы."""
                    }
                ] + self.conversation_history
                
                response = openai_client.chat.completions.create(
                    model=HANDS_FREE_CONFIG["gpt"]["model"],
                    messages=messages,
                    max_tokens=HANDS_FREE_CONFIG["gpt"]["max_tokens"],
                    temperature=HANDS_FREE_CONFIG["gpt"]["temperature"]
                )
                
                return response.choices[0].message.content.strip()
                
            except Exception as e:
                logger.error(f"GPT ошибка: {e}")
                return "Извините, не расслышал. Повторите, пожалуйста."
        
        response = await asyncio.get_event_loop().run_in_executor(self.executor, gpt_call)
        
        # Добавляем ответ в историю
        self.conversation_history.append({"role": "assistant", "content": response})
        
        return response
    
    async def _run_tts_and_play(self, text: str):
        """ИСПРАВЛЕННЫЙ TTS и воспроизведение с правильной детекцией перебивания"""
        
        await self._update_state(ConversationState.SPEAKING)
        
        # ИСПРАВЛЕНО: Включаем детекцию перебивания при начале говорения
        self.vad.enable_interrupt_detection(speaking_started=True)
        
        # Устанавливаем эхо-подавление
        self.vad.set_echo_suppression(HANDS_FREE_CONFIG["echo_suppression_duration_ms"])
        
        def tts_call():
            try:
                with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as temp_file:
                    temp_path = temp_file.name
                
                response = openai_client.audio.speech.create(
                    model=HANDS_FREE_CONFIG["tts"]["model"],
                    voice=HANDS_FREE_CONFIG["tts"]["voice"],
                    input=text,
                    speed=HANDS_FREE_CONFIG["tts"]["speed"],
                    response_format=HANDS_FREE_CONFIG["tts"]["response_format"]
                )
                
                response.stream_to_file(temp_path)
                
                with open(temp_path, 'rb') as audio_file:
                    audio_content = audio_file.read()
                
                try:
                    os.unlink(temp_path)
                except:
                    pass
                    
                return audio_content
                
            except Exception as e:
                logger.error(f"TTS ошибка: {e}")
                return b""
        
        # Генерируем TTS
        audio_content = await asyncio.get_event_loop().run_in_executor(self.executor, tts_call)
        
        if audio_content and self.state == ConversationState.SPEAKING:
            # Потоковое воспроизведение
            await self._stream_audio_with_interruption(audio_content)
        
        # Отключаем детекцию перебивания после завершения
        self.vad.disable_interrupt_detection()
    
    async def _stream_audio_with_interruption(self, audio_content: bytes):
        """Потоковое воспроизведение с проверкой перебивания"""
        
        chunk_size = 4096
        total_chunks = (len(audio_content) + chunk_size - 1) // chunk_size
        
        await self._send_event("tts_start", {
            "total_chunks": total_chunks,
            "total_size": len(audio_content)
        })
        
        for i in range(0, len(audio_content), chunk_size):
            # Проверяем состояние - могли перебить
            if self.state != ConversationState.SPEAKING:
                logger.info("🛑 Воспроизведение прервано")
                break
                
            chunk = audio_content[i:i + chunk_size]
            chunk_id = i // chunk_size + 1
            
            audio_b64 = base64.b64encode(chunk).decode('utf-8')
            
            await self._send_event("audio_chunk", {
                "audio": audio_b64,
                "chunk_id": chunk_id,
                "total_chunks": total_chunks,
                "is_final": chunk_id == total_chunks
            })
            
            # Небольшая задержка между чанками
            await asyncio.sleep(0.02)
        
        if self.state == ConversationState.SPEAKING:
            await self._send_event("tts_complete", {"interrupted": False})
    
    async def _handle_interruption(self, vad_result: Dict[str, Any]):
        """ИСПРАВЛЕННАЯ обработка перебивания пользователем"""
        
        logger.info("⚡ Обрабатываем ПОДТВЕРЖДЕННОЕ перебивание")
        self.interruptions_count += 1
        
        # Останавливаем воспроизведение
        if self.current_playback_task and not self.current_playback_task.done():
            self.current_playback_task.cancel()
        
        # Отключаем детекцию перебивания
        self.vad.disable_interrupt_detection()
        
        await self._update_state(ConversationState.INTERRUPTED)
        
        await self._send_event("interrupted", {
            "timestamp": vad_result["timestamp"],
            "amplitude": vad_result.get("interrupt_amplitude", 0),
            "interruptions_count": self.interruptions_count
        })
        
        # Быстро переходим к прослушиванию нового сообщения
        await asyncio.sleep(0.1)
        await self._update_state(ConversationState.LISTENING)
        
        # Сброс эхо-подавления при перебивании
        self.vad.echo_suppression_until = 0
    
    async def pause_session(self):
        """Приостановка сессии"""
        self.is_active = False
        self.vad.disable_interrupt_detection()
        await self._update_state(ConversationState.PAUSED)
        await self._send_event("session_paused", {"timestamp": time.time()})
    
    async def resume_session(self):
        """Возобновление сессии"""
        self.is_active = True
        await self._update_state(ConversationState.LISTENING)
        await self._send_event("session_resumed", {"timestamp": time.time()})
    
    async def close(self):
        """Закрытие сессии"""
        self.is_active = False
        
        # Отключаем детекцию перебивания
        self.vad.disable_interrupt_detection()
        
        # Отменяем активные задачи
        if self.current_processing_task and not self.current_processing_task.done():
            self.current_processing_task.cancel()
        if self.current_playback_task and not self.current_playback_task.done():
            self.current_playback_task.cancel()
        
        self.executor.shutdown(wait=False)
        
        # Статистика
        await self._send_event("session_stats", {
            "total_exchanges": self.total_exchanges,
            "interruptions_count": self.interruptions_count,
            "false_positives": self.false_positives,
            "session_duration": time.time() - self.last_interaction
        })
        
        logger.info(f"🔚 ИСПРАВЛЕННАЯ hands-free сессия закрыта: {self.session_id}")
    
    def _calculate_amplitude(self, audio_data: bytes) -> float:
        """Вычисление амплитуды аудио"""
        if len(audio_data) < 2:
            return 0.0
            
        try:
            # Предполагаем 16-bit PCM
            sample_count = len(audio_data) // 2
            if sample_count == 0:
                return 0.0
                
            samples = [int.from_bytes(audio_data[i:i+2], byteorder='little', signed=True) 
                      for i in range(0, len(audio_data), 2)]
            
            rms = (sum(s * s for s in samples) / len(samples)) ** 0.5
            return rms / 32768.0  # Нормализация к 0-1
            
        except Exception as e:
            logger.warning(f"Ошибка расчета амплитуды: {e}")
            return 0.0
    
    def _convert_to_wav(self, audio_data: bytes) -> bytes:
        """Конвертация аудио в WAV формат"""
        try:
            # Если уже WAV - возвращаем как есть
            if audio_data.startswith(b'RIFF') and b'WAVE' in audio_data[:20]:
                return audio_data
            
            # Создаем WAV из сырых данных
            sample_rate = HANDS_FREE_CONFIG["sample_rate"]
            channels = HANDS_FREE_CONFIG["channels"]
            
            wav_buffer = io.BytesIO()
            
            with wave.open(wav_buffer, 'wb') as wav_file:
                wav_file.setnchannels(channels)
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(audio_data)
            
            return wav_buffer.getvalue()
            
        except Exception as e:
            logger.error(f"Ошибка конвертации в WAV: {e}")
            return audio_data
    
    async def _update_state(self, new_state: ConversationState):
        """ИСПРАВЛЕННОЕ обновление состояния с правильным управлением детекцией перебивания"""
        old_state = self.state
        self.state = new_state
        
        # ИСПРАВЛЕНО: Управляем детекцией перебивания в зависимости от состояния
        if new_state == ConversationState.SPEAKING:
            # Детекция перебивания будет включена в _run_tts_and_play
            pass
        else:
            # Во всех остальных состояниях отключаем детекцию перебивания
            if old_state == ConversationState.SPEAKING:
                self.vad.disable_interrupt_detection()
        
        await self._send_event("state_changed", {
            "old_state": old_state.value,
            "new_state": new_state.value,
            "timestamp": time.time()
        })
        
        logger.debug(f"🔄 Состояние: {old_state.value} → {new_state.value}")
    
    async def _send_event(self, event_type: str, data: Dict[str, Any] = None):
        """Отправка события клиенту"""
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
            logger.warning(f"Ошибка отправки события {event_type}: {e}")
    
    async def _send_audio_status(self, vad_result: Dict[str, Any]):
        """Отправка статуса аудио (периодически)"""
        await self._send_event("audio_status", {
            "amplitude": vad_result.get("amplitude", 0),
            "smooth_amplitude": vad_result.get("smooth_amplitude", 0),
            "is_speech_active": vad_result.get("is_speech_active", False),
            "is_echo_suppressed": vad_result.get("is_echo_suppressed", False),
            "state": self.state.value,
            "interrupt_detection_enabled": self.vad.interrupt_detection_enabled
        })

# ===== SESSION MANAGER =====

class HandsFreeSessionManager:
    """Менеджер hands-free сессий"""
    
    def __init__(self):
        self.sessions: Dict[str, FixedHandsFreeSession] = {}
    
    async def create_session(self, websocket: WebSocket) -> FixedHandsFreeSession:
        session_id = str(uuid.uuid4())
        session = FixedHandsFreeSession(session_id, websocket)
        self.sessions[session_id] = session
        
        await session.initialize()
        
        logger.info(f"✅ Создана ИСПРАВЛЕННАЯ hands-free сессия: {session_id}")
        return session
    
    async def close_session(self, session_id: str):
        if session_id in self.sessions:
            await self.sessions[session_id].close()
            del self.sessions[session_id]
            logger.info(f"🗑️ Удалена сессия: {session_id}")
    
    def get_active_sessions_count(self) -> int:
        return len([s for s in self.sessions.values() if s.is_active])

# ===== FASTAPI APPLICATION =====

app = FastAPI(
    title="Fixed Hands-Free Voice Assistant v6.1",
    description="Исправленный голосовой ассистент с правильной логикой перебивания",
    version="6.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

session_manager = HandsFreeSessionManager()

@app.get("/")
async def get_homepage():
    return HTMLResponse(content="""
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Fixed Hands-Free Voice Assistant v6.1</title>
    <style>
        body {
            font-family: 'Inter', system-ui, sans-serif;
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            margin: 0;
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            color: white;
            overflow: hidden;
        }
        
        .container {
            text-align: center;
            background: rgba(255,255,255,0.1);
            padding: 3rem;
            border-radius: 30px;
            backdrop-filter: blur(20px);
            border: 1px solid rgba(255,255,255,0.2);
            max-width: 500px;
            width: 100%;
        }
        
        h1 {
            font-size: 2.8rem;
            margin-bottom: 0.5rem;
            background: linear-gradient(45deg, #fff, #a8c8ff);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        
        .subtitle {
            font-size: 1.1rem;
            margin-bottom: 1rem;
            opacity: 0.9;
        }
        
        .version-badge {
            display: inline-block;
            padding: 0.3rem 1rem;
            background: linear-gradient(45deg, #00b894, #00a085);
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: 600;
            margin-bottom: 2rem;
        }
        
        .main-button {
            width: 160px;
            height: 160px;
            border-radius: 50%;
            border: none;
            background: linear-gradient(135deg, #ff6b6b, #ee5a24);
            color: white;
            font-size: 3.5rem;
            cursor: pointer;
            margin: 1.5rem auto;
            display: block;
            transition: all 0.4s ease;
            box-shadow: 0 20px 40px rgba(0,0,0,0.3);
            position: relative;
            overflow: hidden;
        }
        
        .main-button:hover {
            transform: scale(1.05);
            box-shadow: 0 25px 50px rgba(0,0,0,0.4);
        }
        
        .main-button.active {
            background: linear-gradient(135deg, #74b9ff, #0984e3);
            animation: pulse-active 2s infinite;
        }
        
        .main-button.speaking {
            background: linear-gradient(135deg, #00b894, #00a085);
            animation: wave-speaking 0.8s ease-in-out infinite;
        }
        
        .main-button.processing {
            background: linear-gradient(135deg, #fdcb6e, #e17055);
            animation: spin-processing 1.2s linear infinite;
        }
        
        @keyframes pulse-active {
            0%, 100% { transform: scale(1); box-shadow: 0 20px 40px rgba(116, 185, 255, 0.4); }
            50% { transform: scale(1.08); box-shadow: 0 30px 60px rgba(116, 185, 255, 0.6); }
        }
        
        @keyframes wave-speaking {
            0%, 100% { transform: scale(1); }
            25% { transform: scale(1.05); }
            75% { transform: scale(0.95); }
        }
        
        @keyframes spin-processing {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
        }
        
        .status {
            font-size: 1.3rem;
            margin: 1.5rem 0;
            min-height: 1.6rem;
            font-weight: 500;
        }
        
        .audio-visualizer {
            height: 60px;
            background: rgba(255,255,255,0.1);
            border-radius: 30px;
            margin: 2rem 0;
            position: relative;
            overflow: hidden;
        }
        
        .audio-bar {
            height: 100%;
            background: linear-gradient(90deg, #74b9ff, #0984e3, #74b9ff);
            width: 0%;
            border-radius: 30px;
            transition: width 0.1s ease;
            position: relative;
        }
        
        .stats {
            margin-top: 2rem;
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1rem;
            font-size: 0.9rem;
        }
        
        .stat-item {
            background: rgba(255,255,255,0.1);
            padding: 1rem;
            border-radius: 15px;
            backdrop-filter: blur(10px);
        }
        
        .stat-value {
            font-size: 1.4rem;
            font-weight: 700;
            color: #74b9ff;
        }
        
        .controls {
            margin: 1.5rem 0;
            display: flex;
            gap: 0.5rem;
            justify-content: center;
        }
        
        .control-btn {
            padding: 0.5rem 1rem;
            border: none;
            border-radius: 20px;
            background: rgba(255,255,255,0.2);
            color: white;
            cursor: pointer;
            font-size: 0.8rem;
            transition: all 0.3s;
        }
        
        .control-btn:hover {
            background: rgba(255,255,255,0.3);
        }
        
        .control-btn.active {
            background: #74b9ff;
        }
        
        .conversation {
            margin-top: 2rem;
            max-height: 200px;
            overflow-y: auto;
            text-align: left;
            background: rgba(0,0,0,0.2);
            border-radius: 15px;
            padding: 1rem;
        }
        
        .message {
            margin: 0.5rem 0;
            padding: 0.5rem;
            border-radius: 8px;
            font-size: 0.9rem;
        }
        
        .message.user {
            background: rgba(116, 185, 255, 0.3);
            text-align: right;
        }
        
        .message.assistant {
            background: rgba(0, 184, 148, 0.3);
        }
        
        .connection-indicator {
            position: absolute;
            top: 20px;
            right: 20px;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            background: #ef4444;
            transition: all 0.3s;
        }
        
        .connection-indicator.connected {
            background: #10b981;
            box-shadow: 0 0 15px rgba(16, 185, 129, 0.6);
        }
        
        .fixes-list {
            text-align: left;
            background: rgba(0, 184, 148, 0.1);
            border: 1px solid rgba(0, 184, 148, 0.3);
            border-radius: 15px;
            padding: 1rem;
            margin: 1rem 0;
            font-size: 0.85rem;
        }
        
        .fixes-list h4 {
            margin: 0 0 0.5rem 0;
            color: #00b894;
        }
        
        .fixes-list ul {
            margin: 0;
            padding-left: 1.2rem;
        }
        
        .fixes-list li {
            margin: 0.3rem 0;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="connection-indicator" id="connectionStatus"></div>
        
        <h1>🎤 Алиса Fixed</h1>
        <p class="subtitle">Исправленный голосовой ассистент</p>
        <div class="version-badge">v6.1 - ИСПРАВЛЕНО</div>
        
        <div class="fixes-list">
            <h4>✅ Исправления:</h4>
            <ul>
                <li>Детекция перебивания только при говорении</li>
                <li>Убран спам перебиваний</li>
                <li>Добавлен cooldown защиты</li>
                <li>Улучшены пороги VAD</li>
                <li>Правильная логика состояний</li>
            </ul>
        </div>
        
        <button class="main-button" id="mainButton">📞</button>
        
        <div class="status" id="status">Нажмите чтобы начать разговор</div>
        
        <div class="audio-visualizer">
            <div class="audio-bar" id="audioBar"></div>
        </div>
        
        <div class="controls">
            <button class="control-btn" id="pauseBtn">⏸️ Пауза</button>
            <button class="control-btn active" id="autoBtn">🤖 Авто</button>
        </div>
        
        <div class="stats">
            <div class="stat-item">
                <div class="stat-value" id="exchangeCount">0</div>
                <div>Диалогов</div>
            </div>
            <div class="stat-item">
                <div class="stat-value" id="interruptCount">0</div>
                <div>Перебиваний</div>
            </div>
        </div>
        
        <div class="conversation" id="conversation">
            <div style="text-align: center; opacity: 0.7; font-style: italic;">
                Начните разговор...
            </div>
        </div>
    </div>

    <script>
        class FixedHandsFreeVoiceAssistant {
            constructor() {
                this.ws = null;
                this.mediaRecorder = null;
                this.isActive = false;
                this.isPaused = false;
                this.currentState = 'initializing';
                
                this.totalExchanges = 0;
                this.totalInterruptions = 0;
                
                this.initElements();
                this.connectWebSocket();
            }
            
            initElements() {
                this.mainButton = document.getElementById('mainButton');
                this.status = document.getElementById('status');
                this.connectionStatus = document.getElementById('connectionStatus');
                this.audioBar = document.getElementById('audioBar');
                this.conversation = document.getElementById('conversation');
                this.exchangeCount = document.getElementById('exchangeCount');
                this.interruptCount = document.getElementById('interruptCount');
                
                this.pauseBtn = document.getElementById('pauseBtn');
                this.autoBtn = document.getElementById('autoBtn');
                
                // События
                this.mainButton.addEventListener('click', () => this.toggleSession());
                this.pauseBtn.addEventListener('click', () => this.togglePause());
            }
            
            connectWebSocket() {
                const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                const wsUrl = `${protocol}//${window.location.host}/ws/hands-free`;
                
                this.ws = new WebSocket(wsUrl);
                
                this.ws.onopen = () => {
                    console.log('🔗 Подключено к ИСПРАВЛЕННОМУ hands-free ассистенту');
                    this.connectionStatus.classList.add('connected');
                    this.status.textContent = 'Подключено! Нажмите для начала разговора';
                };
                
                this.ws.onmessage = (event) => {
                    const data = JSON.parse(event.data);
                    this.handleMessage(data);
                };
                
                this.ws.onclose = () => {
                    console.log('❌ Соединение потеряно');
                    this.connectionStatus.classList.remove('connected');
                    this.status.textContent = 'Соединение потеряно - перезагрузите страницу';
                    this.isActive = false;
                    this.updateUI();
                };
            }
            
            async toggleSession() {
                if (this.isActive) {
                    await this.stopSession();
                } else {
                    await this.startSession();
                }
            }
            
            async startSession() {
                try {
                    const stream = await navigator.mediaDevices.getUserMedia({
                        audio: {
                            sampleRate: 16000,
                            channelCount: 1,
                            echoCancellation: true,
                            noiseSuppression: true,
                            autoGainControl: true
                        }
                    });
                    
                    this.mediaRecorder = new MediaRecorder(stream, {
                        mimeType: 'audio/webm;codecs=opus',
                        audioBitsPerSecond: 16000
                    });
                    
                    this.mediaRecorder.ondataavailable = (event) => {
                        if (event.data.size > 0 && this.isActive) {
                            this.sendAudioChunk(event.data);
                        }
                    };
                    
                    this.mediaRecorder.start(100); // 100ms чанки
                    this.isActive = true;
                    this.updateUI();
                    
                } catch (error) {
                    console.error('Ошибка доступа к микрофону:', error);
                    this.status.textContent = 'Ошибка доступа к микрофону: ' + error.message;
                }
            }
            
            async stopSession() {
                this.isActive = false;
                
                if (this.mediaRecorder) {
                    this.mediaRecorder.stop();
                    this.mediaRecorder.stream.getTracks().forEach(track => track.stop());
                    this.mediaRecorder = null;
                }
                
                if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                    this.ws.send(JSON.stringify({ type: 'stop_session' }));
                }
                
                this.updateUI();
            }
            
            async sendAudioChunk(audioBlob) {
                if (!this.ws || this.ws.readyState !== WebSocket.OPEN || !this.isActive) return;
                
                try {
                    const arrayBuffer = await audioBlob.arrayBuffer();
                    const audioArray = Array.from(new Uint8Array(arrayBuffer));
                    
                    this.ws.send(JSON.stringify({
                        type: 'audio_chunk',
                        data: audioArray,
                        timestamp: Date.now()
                    }));
                    
                } catch (error) {
                    console.error('Ошибка отправки аудио:', error);
                }
            }
            
            handleMessage(data) {
                switch (data.type) {
                    case 'session_ready':
                        this.status.textContent = 'Слушаю... Говорите в любое время!';
                        break;
                        
                    case 'state_changed':
                        this.currentState = data.new_state;
                        this.updateUI();
                        this.updateStatus(data.new_state);
                        break;
                        
                    case 'audio_status':
                        this.updateAudioVisualizer(data);
                        break;
                        
                    case 'speech_detection':
                        if (data.type === 'started') {
                            this.status.textContent = '🎤 Слышу вас...';
                        } else if (data.type === 'ended') {
                            this.status.textContent = data.will_process ? 
                                '⚙️ Обрабатываю...' : '⏳ Слишком коротко, слушаю дальше...';
                        }
                        break;
                        
                    case 'transcription':
                        this.addMessage('user', data.text);
                        break;
                        
                    case 'llm_response':
                        this.addMessage('assistant', data.text);
                        break;
                        
                    case 'processing_complete':
                        this.totalExchanges = data.total_exchanges || this.totalExchanges + 1;
                        this.exchangeCount.textContent = this.totalExchanges;
                        break;
                        
                    case 'interrupted':
                        this.totalInterruptions = data.interruptions_count || this.totalInterruptions + 1;
                        this.interruptCount.textContent = this.totalInterruptions;
                        this.status.textContent = '⚡ Перебили! Слушаю вас...';
                        break;
                        
                    case 'tts_start':
                        this.status.textContent = '🔊 Говорю... (можете перебить)';
                        break;
                        
                    case 'error':
                        this.status.textContent = '❌ ' + data.message;
                        break;
                }
            }
            
            updateStatus(state) {
                const statusMap = {
                    'listening': '👂 Слушаю...',
                    'speech_detected': '🎤 Слышу речь...',
                    'processing': '⚙️ Думаю...',
                    'speaking': '🔊 Отвечаю...',
                    'interrupted': '⚡ Перебили!',
                    'paused': '⏸️ На паузе'
                };
                
                if (statusMap[state]) {
                    this.status.textContent = statusMap[state];
                }
            }
            
            updateAudioVisualizer(data) {
                const amplitude = data.smooth_amplitude || 0;
                const percentage = Math.min(amplitude * 800, 100); // Настроен для новых порогов
                this.audioBar.style.width = percentage + '%';
            }
            
            updateUI() {
                this.mainButton.className = 'main-button';
                
                if (!this.isActive) {
                    this.mainButton.textContent = '📞';
                    this.status.textContent = 'Нажмите для начала разговора';
                } else {
                    switch (this.currentState) {
                        case 'listening':
                        case 'speech_detected':
                            this.mainButton.classList.add('active');
                            this.mainButton.textContent = '🎤';
                            break;
                        case 'processing':
                            this.mainButton.classList.add('processing');
                            this.mainButton.textContent = '⚙️';
                            break;
                        case 'speaking':
                            this.mainButton.classList.add('speaking');
                            this.mainButton.textContent = '🔊';
                            break;
                        default:
                            this.mainButton.classList.add('active');
                            this.mainButton.textContent = '📞';
                    }
                }
            }
            
            addMessage(role, text) {
                if (this.conversation.innerHTML.includes('Начните разговор')) {
                    this.conversation.innerHTML = '';
                }
                
                const messageDiv = document.createElement('div');
                messageDiv.className = `message ${role}`;
                messageDiv.textContent = text;
                
                this.conversation.appendChild(messageDiv);
                this.conversation.scrollTop = this.conversation.scrollHeight;
            }
            
            togglePause() {
                this.isPaused = !this.isPaused;
                this.pauseBtn.classList.toggle('active', this.isPaused);
                this.pauseBtn.textContent = this.isPaused ? '▶️ Продолжить' : '⏸️ Пауза';
                
                if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                    this.ws.send(JSON.stringify({
                        type: this.isPaused ? 'pause_session' : 'resume_session'
                    }));
                }
            }
        }
        
        // Запуск приложения
        document.addEventListener('DOMContentLoaded', () => {
            window.assistant = new FixedHandsFreeVoiceAssistant();
        });
    </script>
</body>
</html>
    """)

@app.get("/api/health")
async def health_check():
    return JSONResponse({
        "status": "healthy",
        "version": "6.1.0",
        "description": "Fixed Hands-Free Voice Assistant",
        "active_sessions": session_manager.get_active_sessions_count(),
        "features": ["fixed_interruption_logic", "debounced_vad", "proper_state_management"],
        "fixes": ["interrupt_only_when_speaking", "cooldown_protection", "improved_thresholds"]
    })

@app.websocket("/ws/hands-free")
async def websocket_hands_free_endpoint(websocket: WebSocket):
    """
    Главный WebSocket endpoint для ИСПРАВЛЕННОГО hands-free режима
    """
    await websocket.accept()
    
    session = await session_manager.create_session(websocket)
    
    try:
        while True:
            message = await websocket.receive_json()
            message_type = message.get("type")
            
            if message_type == "audio_chunk":
                # Непрерывная обработка аудио
                audio_data = bytes(message["data"])
                await session.process_audio_chunk(audio_data)
                
            elif message_type == "pause_session":
                await session.pause_session()
                
            elif message_type == "resume_session":
                await session.resume_session()
                
            elif message_type == "stop_session":
                break
            
            else:
                logger.warning(f"Неизвестный тип сообщения: {message_type}")
    
    except WebSocketDisconnect:
        logger.info(f"Клиент отключился: {session.session_id}")
    except Exception as e:
        logger.error(f"WebSocket ошибка: {e}")
    finally:
        await session_manager.close_session(session.session_id)

def main():
    logger.info("🚀 Запуск ИСПРАВЛЕННОГО Hands-Free Voice Assistant v6.1")
    logger.info("🔧 ИСПРАВЛЕНИЯ:")
    logger.info("   - Детекция перебивания только в состоянии SPEAKING")
    logger.info("   - Добавлен cooldown для предотвращения спама")
    logger.info("   - Улучшены пороги VAD для стабильности")
    logger.info("   - Правильная логика управления состояниями")
    logger.info(f"   - VAD порог: {HANDS_FREE_CONFIG['vad_threshold']}")
    logger.info(f"   - Порог перебивания: {HANDS_FREE_CONFIG['interrupt_threshold']}")
    logger.info(f"   - Cooldown перебивания: {HANDS_FREE_CONFIG['interrupt_cooldown_ms']}ms")
    
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )

if __name__ == "__main__":
    main()
