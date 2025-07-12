"""
WebSocket клиент для ElevenLabs Conversational AI API
"""

import asyncio
import json
import logging
import time
from typing import Optional, Dict, Any
import aiohttp
import websockets

logger = logging.getLogger(__name__)

class ElevenLabsWebSocketClient:
    """WebSocket клиент для ElevenLabs"""
    
    def __init__(self, api_key: str, agent_id: str, audio_handler=None):
        self.api_key = api_key
        self.agent_id = agent_id
        self.audio_handler = audio_handler
        
        # WebSocket
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.is_connected = False
        self.conversation_id: Optional[str] = None
        
        # Состояние
        self.is_agent_speaking = False
        self.last_activity = time.time()
        
        # Статистика
        self.messages_sent = 0
        self.audio_chunks_sent = 0
        self.audio_chunks_received = 0
        self.start_time = time.time()
        
        # Heartbeat
        self.heartbeat_task: Optional[asyncio.Task] = None
        self.heartbeat_interval = 30.0  # секунд
        
        # Reconnect
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        
        # URLs
        self.ws_url = f"wss://api.elevenlabs.io/v1/convai/conversation?agent_id={agent_id}"
        self.signed_url_endpoint = "https://api.elevenlabs.io/v1/convai/conversation/get_signed_url"
    
    async def connect(self):
        """Подключение к ElevenLabs WebSocket"""
        try:
            logger.info("🔗 Подключение к ElevenLabs...")
            
            # Пытаемся получить signed URL
            ws_url = await self._get_signed_url()
            
            # Подключаемся
            extra_headers = {}
            if "token=" not in ws_url:
                extra_headers["xi-api-key"] = self.api_key
            
            self.ws = await websockets.connect(
                ws_url,
                extra_headers=extra_headers,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=10
            )
            
            self.is_connected = True
            self.reconnect_attempts = 0
            
            logger.info("✅ WebSocket подключен")
            
            # Настраиваем callback для аудио
            if self.audio_handler:
                self.audio_handler.set_audio_callback(self._on_audio_chunk)
            
            # Запускаем обработчики
            asyncio.create_task(self._message_handler())
            asyncio.create_task(self._start_heartbeat())
            
            # Отправляем инициализацию
            await self._send_conversation_initiation()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка подключения: {e}")
            self.is_connected = False
            return False
    
    async def _get_signed_url(self) -> str:
        """Получение signed URL"""
        try:
            headers = {
                'xi-api-key': self.api_key,
                'Content-Type': 'application/json'
            }
            
            params = {'agent_id': self.agent_id}
            
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    self.signed_url_endpoint, 
                    headers=headers, 
                    params=params
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        signed_url = data.get('signed_url')
                        logger.info("✅ Signed URL получен")
                        return signed_url
                    else:
                        logger.warning(f"⚠️ Signed URL недоступен: {response.status}")
                        return self.ws_url
                        
        except Exception as e:
            logger.warning(f"⚠️ Ошибка получения signed URL: {e}")
            return self.ws_url
    
    async def _send_conversation_initiation(self):
        """Отправка инициализации разговора"""
        try:
            initiation_data = {
                "type": "conversation_initiation_client_data",
                "conversation_config_override": {
                    "agent": {
                        "language": "en"
                    }
                }
            }
            
            await self._send_message(initiation_data)
            logger.info("📤 Инициализация отправлена")
            
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации: {e}")
    
    async def _message_handler(self):
        """Обработчик входящих сообщений"""
        try:
            async for message in self.ws:
                try:
                    data = json.loads(message)
                    await self._process_message(data)
                    self.last_activity = time.time()
                    
                except json.JSONDecodeError as e:
                    logger.error(f"❌ Ошибка JSON: {e}")
                except Exception as e:
                    logger.error(f"❌ Ошибка обработки сообщения: {e}")
                    
        except websockets.exceptions.ConnectionClosed as e:
            logger.info(f"🔌 Соединение закрыто: {e}")
            self.is_connected = False
            await self._handle_disconnect()
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка обработки: {e}")
            self.is_connected = False
    
    async def _process_message(self, data: Dict[str, Any]):
        """Обработка сообщения от ElevenLabs"""
        message_type = data.get("type", "unknown")
        
        logger.debug(f"📨 Получено: {message_type}")
        
        if message_type == "conversation_initiation_metadata":
            await self._handle_conversation_metadata(data)
            
        elif message_type == "user_transcript":
            await self._handle_user_transcript(data)
            
        elif message_type == "agent_response":
            await self._handle_agent_response(data)
            
        elif message_type == "audio":
            await self._handle_audio_response(data)
            
        elif message_type == "vad_score":
            await self._handle_vad_score(data)
            
        elif message_type == "interruption":
            await self._handle_interruption(data)
            
        elif message_type == "ping":
            await self._handle_ping(data)
            
        elif message_type == "agent_response_correction":
            await self._handle_agent_correction(data)
            
        elif message_type == "internal_tentative_agent_response":
            # Внутренний предварительный ответ
            logger.debug("📝 Предварительный ответ получен")
            
        else:
            logger.debug(f"❓ Неизвестный тип: {message_type}")
    
    async def _handle_conversation_metadata(self, data: Dict[str, Any]):
        """Обработка метаданных разговора"""
        metadata = data.get("conversation_initiation_metadata_event", {})
        self.conversation_id = metadata.get("conversation_id")
        
        audio_format = metadata.get("agent_output_audio_format", "pcm_16000")
        
        logger.info(f"✅ Разговор готов: {self.conversation_id}")
        logger.info(f"🎵 Аудио формат: {audio_format}")
        
        print("\n🎉 Готов к разговору!")
        print("   Нажмите ENTER чтобы начать говорить")
    
    async def _handle_user_transcript(self, data: Dict[str, Any]):
        """Обработка транскрипции пользователя"""
        transcript_event = data.get("user_transcription_event", {})
        user_text = transcript_event.get("user_transcript", "")
        
        if user_text:
            print(f"\n👤 Вы: {user_text}")
    
    async def _handle_agent_response(self, data: Dict[str, Any]):
        """Обработка ответа агента"""
        response_event = data.get("agent_response_event", {})
        agent_text = response_event.get("agent_response", "")
        
        if agent_text:
            self.is_agent_speaking = True
            print(f"\n🤖 AI: {agent_text}")
    
    async def _handle_audio_response(self, data: Dict[str, Any]):
        """Обработка аудио ответа"""
        audio_event = data.get("audio_event", {})
        audio_base64 = audio_event.get("audio_base_64")
        
        if audio_base64 and self.audio_handler:
            try:
                await self.audio_handler.play_audio(audio_base64)
                self.audio_chunks_received += 1
                logger.debug("🔊 Воспроизведение аудио")
                
            except Exception as e:
                logger.error(f"❌ Ошибка воспроизведения: {e}")
    
    async def _handle_vad_score(self, data: Dict[str, Any]):
        """Обработка VAD score"""
        vad_event = data.get("vad_score_event", {})
        vad_score = vad_event.get("vad_score", 0.0)
        
        # Показываем активность голоса
        if vad_score > 0.5:
            print("🎤", end="", flush=True)
        else:
            print(".", end="", flush=True)
    
    async def _handle_interruption(self, data: Dict[str, Any]):
        """Обработка прерывания"""
        self.is_agent_speaking = False
        print("\n⚡ Прерывание обнаружено")
    
    async def _handle_ping(self, data: Dict[str, Any]):
        """Обработка ping"""
        ping_event = data.get("ping_event", {})
        event_id = ping_event.get("event_id", "")
        
        # Отвечаем pong
        pong_response = {
            "type": "pong",
            "event_id": event_id
        }
        
        await self._send_message(pong_response)
    
    async def _handle_agent_correction(self, data: Dict[str, Any]):
        """Обработка коррекции ответа агента"""
        correction_event = data.get("agent_response_correction_event", {})
        corrected_text = correction_event.get("corrected_agent_response", "")
        
        if corrected_text:
            print(f"\n🔄 AI (исправлено): {corrected_text}")
    
    async def _on_audio_chunk(self, audio_base64: str):
        """Callback для аудио чанков"""
        try:
            message = {
                "user_audio_chunk": audio_base64
            }
            
            await self._send_message(message)
            self.audio_chunks_sent += 1
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки аудио: {e}")
    
    async def _send_message(self, message: Dict[str, Any]):
        """Отправка сообщения"""
        if not self.ws or not self.is_connected:
            raise Exception("WebSocket не подключен")
        
        try:
            await self.ws.send(json.dumps(message))
            self.messages_sent += 1
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки: {e}")
            raise
    
    async def _start_heartbeat(self):
        """Запуск heartbeat"""
        self.heartbeat_task = asyncio.create_task(self._heartbeat_worker())
    
    async def _heartbeat_worker(self):
        """Рабочий поток heartbeat"""
        try:
            while self.is_connected:
                await asyncio.sleep(self.heartbeat_interval)
                
                if self.is_connected and self.ws:
                    try:
                        ping_message = {
                            "type": "ping",
                            "timestamp": int(time.time() * 1000)
                        }
                        await self._send_message(ping_message)
                        logger.debug("📡 Heartbeat ping отправлен")
                        
                    except Exception as e:
                        logger.warning(f"⚠️ Ошибка heartbeat: {e}")
                        break
                        
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"❌ Ошибка heartbeat: {e}")
    
    async def _handle_disconnect(self):
        """Обработка отключения"""
        if self.reconnect_attempts < self.max_reconnect_attempts:
            self.reconnect_attempts += 1
            delay = min(2 ** self.reconnect_attempts, 30)
            
            logger.info(f"🔄 Переподключение через {delay}с (попытка {self.reconnect_attempts})")
            await asyncio.sleep(delay)
            
            try:
                await self.connect()
            except Exception as e:
                logger.error(f"❌ Ошибка переподключения: {e}")
        else:
            logger.error("❌ Превышено количество попыток переподключения")
    
    async def disconnect(self):
        """Отключение"""
        logger.info("👋 Отключение от ElevenLabs...")
        
        self.is_connected = False
        
        # Останавливаем heartbeat
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
            try:
                await self.heartbeat_task
            except asyncio.CancelledError:
                pass
        
        # Закрываем WebSocket
        if self.ws:
            try:
                await self.ws.close()
            except Exception as e:
                logger.warning(f"⚠️ Ошибка закрытия WebSocket: {e}")
        
        logger.info("✅ Отключено")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Получение статистики"""
        uptime = time.time() - self.start_time
        
        return {
            "connected": self.is_connected,
            "conversation_id": self.conversation_id,
            "messages_sent": self.messages_sent,
            "audio_chunks_sent": self.audio_chunks_sent,
            "audio_chunks_received": self.audio_chunks_received,
            "uptime": uptime,
            "is_agent_speaking": self.is_agent_speaking,
            "reconnect_attempts": self.reconnect_attempts
        }
