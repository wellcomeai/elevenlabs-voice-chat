"""
Обработчик аудио для ElevenLabs Conversational AI
Работа с микрофоном и динамиками
"""

import asyncio
import logging
import base64
import threading
import queue
import numpy as np
from typing import Callable, Optional
import pyaudio

logger = logging.getLogger(__name__)

class AudioHandler:
    """Обработчик аудио ввода/вывода"""
    
    def __init__(self, sample_rate: int = 16000, chunk_size: int = 1024, channels: int = 1):
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.channels = channels
        self.format = pyaudio.paInt16
        
        # PyAudio объекты
        self.pyaudio = None
        self.input_stream = None
        self.output_stream = None
        
        # Состояние
        self.is_recording = False
        self.is_playing = False
        
        # Очереди для аудио
        self.audio_queue = queue.Queue()
        self.playback_queue = queue.Queue()
        
        # Callback функции
        self.on_audio_chunk: Optional[Callable[[str], None]] = None
        
        # Потоки
        self.recording_thread = None
        self.playback_thread = None
        
        self._initialize_audio()
    
    def _initialize_audio(self):
        """Инициализация PyAudio"""
        try:
            self.pyaudio = pyaudio.PyAudio()
            
            # Поиск устройств
            self._find_audio_devices()
            
            logger.info("✅ PyAudio инициализирован")
            
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации PyAudio: {e}")
            raise
    
    def _find_audio_devices(self):
        """Поиск аудио устройств"""
        logger.info("🔍 Поиск аудио устройств...")
        
        device_count = self.pyaudio.get_device_count()
        
        for i in range(device_count):
            device_info = self.pyaudio.get_device_info_by_index(i)
            
            if device_info["maxInputChannels"] > 0:
                logger.debug(f"   🎤 Вход {i}: {device_info['name']}")
            
            if device_info["maxOutputChannels"] > 0:
                logger.debug(f"   🔊 Выход {i}: {device_info['name']}")
    
    async def start_recording(self):
        """Начало записи с микрофона"""
        if self.is_recording:
            return
        
        try:
            logger.info("🎤 Начинаю запись...")
            
            # Открываем поток ввода
            self.input_stream = self.pyaudio.open(
                format=self.format,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.chunk_size
            )
            
            self.is_recording = True
            
            # Запускаем поток записи
            self.recording_thread = threading.Thread(target=self._recording_worker)
            self.recording_thread.daemon = True
            self.recording_thread.start()
            
            logger.info("✅ Запись началась")
            
        except Exception as e:
            logger.error(f"❌ Ошибка начала записи: {e}")
            self.is_recording = False
            raise
    
    async def stop_recording(self):
        """Остановка записи"""
        if not self.is_recording:
            return
        
        try:
            logger.info("⏹️ Останавливаю запись...")
            
            self.is_recording = False
            
            # Ждем завершения потока
            if self.recording_thread:
                self.recording_thread.join(timeout=2.0)
            
            # Закрываем поток
            if self.input_stream:
                self.input_stream.stop_stream()
                self.input_stream.close()
                self.input_stream = None
            
            logger.info("✅ Запись остановлена")
            
        except Exception as e:
            logger.error(f"❌ Ошибка остановки записи: {e}")
    
    def _recording_worker(self):
        """Рабочий поток записи"""
        logger.debug("🔄 Поток записи запущен")
        
        try:
            while self.is_recording and self.input_stream:
                try:
                    # Читаем аудио данные
                    audio_data = self.input_stream.read(
                        self.chunk_size, 
                        exception_on_overflow=False
                    )
                    
                    # Конвертируем в base64
                    audio_base64 = base64.b64encode(audio_data).decode('utf-8')
                    
                    # Отправляем через callback
                    if self.on_audio_chunk:
                        try:
                            self.on_audio_chunk(audio_base64)
                        except Exception as e:
                            logger.error(f"❌ Ошибка callback: {e}")
                    
                except Exception as e:
                    if self.is_recording:
                        logger.error(f"❌ Ошибка чтения аудио: {e}")
                    break
                    
        except Exception as e:
            logger.error(f"❌ Критическая ошибка записи: {e}")
        
        logger.debug("🔄 Поток записи завершен")
    
    async def play_audio(self, audio_base64: str):
        """Воспроизведение аудио"""
        try:
            # Добавляем в очередь воспроизведения
            self.playback_queue.put(audio_base64)
            
            # Запускаем поток воспроизведения если нужно
            if not self.is_playing:
                await self._start_playback()
                
        except Exception as e:
            logger.error(f"❌ Ошибка добавления аудио: {e}")
    
    async def _start_playback(self):
        """Запуск воспроизведения"""
        if self.is_playing:
            return
        
        try:
            logger.debug("🔊 Начинаю воспроизведение...")
            
            # Открываем поток вывода
            self.output_stream = self.pyaudio.open(
                format=self.format,
                channels=self.channels,
                rate=self.sample_rate,
                output=True,
                frames_per_buffer=self.chunk_size
            )
            
            self.is_playing = True
            
            # Запускаем поток воспроизведения
            self.playback_thread = threading.Thread(target=self._playback_worker)
            self.playback_thread.daemon = True
            self.playback_thread.start()
            
        except Exception as e:
            logger.error(f"❌ Ошибка начала воспроизведения: {e}")
            self.is_playing = False
    
    def _playback_worker(self):
        """Рабочий поток воспроизведения"""
        logger.debug("🔄 Поток воспроизведения запущен")
        
        try:
            while self.is_playing:
                try:
                    # Получаем аудио из очереди
                    audio_base64 = self.playback_queue.get(timeout=1.0)
                    
                    # Декодируем base64
                    audio_data = base64.b64decode(audio_base64)
                    
                    # Воспроизводим
                    if self.output_stream:
                        self.output_stream.write(audio_data)
                    
                    self.playback_queue.task_done()
                    
                except queue.Empty:
                    # Если очередь пуста долго - останавливаем
                    if self.playback_queue.empty():
                        break
                        
                except Exception as e:
                    logger.error(f"❌ Ошибка воспроизведения: {e}")
                    break
        
        except Exception as e:
            logger.error(f"❌ Критическая ошибка воспроизведения: {e}")
        
        finally:
            self._stop_playback()
        
        logger.debug("🔄 Поток воспроизведения завершен")
    
    def _stop_playback(self):
        """Остановка воспроизведения"""
        try:
            self.is_playing = False
            
            if self.output_stream:
                self.output_stream.stop_stream()
                self.output_stream.close()
                self.output_stream = None
                
        except Exception as e:
            logger.error(f"❌ Ошибка остановки воспроизведения: {e}")
    
    def set_audio_callback(self, callback: Callable[[str], None]):
        """Установка callback для аудио данных"""
        self.on_audio_chunk = callback
    
    async def cleanup(self):
        """Очистка ресурсов"""
        logger.info("🧹 Очистка аудио ресурсов...")
        
        # Останавливаем запись
        await self.stop_recording()
        
        # Останавливаем воспроизведение
        self._stop_playback()
        
        # Ждем завершения потоков
        if self.playback_thread:
            self.playback_thread.join(timeout=2.0)
        
        # Закрываем PyAudio
        if self.pyaudio:
            self.pyaudio.terminate()
            self.pyaudio = None
        
        logger.info("✅ Аудио ресурсы очищены")
    
    def get_audio_info(self) -> dict:
        """Получение информации об аудио"""
        return {
            "sample_rate": self.sample_rate,
            "chunk_size": self.chunk_size,
            "channels": self.channels,
            "format": "PCM 16-bit",
            "is_recording": self.is_recording,
            "is_playing": self.is_playing,
            "queue_size": self.playback_queue.qsize()
        }
