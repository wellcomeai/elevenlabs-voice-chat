"""
Конфигурация для ElevenLabs Conversational AI
"""

import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

class Config:
    """Класс конфигурации приложения"""
    
    def __init__(self):
        # Загружаем .env файл если есть
        self._load_env_file()
        
        # ElevenLabs настройки
        self.ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
        self.ELEVENLABS_AGENT_ID = os.getenv("ELEVENLABS_AGENT_ID", "agent_01jzwcew2ferttga9m1zcn3js1")
        
        # Аудио настройки
        self.SAMPLE_RATE = int(os.getenv("SAMPLE_RATE", "16000"))
        self.CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1024"))
        self.CHANNELS = int(os.getenv("CHANNELS", "1"))
        
        # Логирование
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
        self.LOG_FILE = os.getenv("LOG_FILE", "")
        
        # Сетевые настройки
        self.WEBSOCKET_TIMEOUT = int(os.getenv("WEBSOCKET_TIMEOUT", "30"))
        self.RECONNECT_ATTEMPTS = int(os.getenv("RECONNECT_ATTEMPTS", "5"))
        self.HEARTBEAT_INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL", "30"))
        
        # Дополнительные настройки
        self.DEBUG = os.getenv("DEBUG", "false").lower() == "true"
        self.ENABLE_VAD_DISPLAY = os.getenv("ENABLE_VAD_DISPLAY", "true").lower() == "true"
        
        # Валидация
        self._validate_config()
    
    def _load_env_file(self):
        """Загрузка .env файла"""
        env_file = Path(".env")
        if env_file.exists():
            try:
                with open(env_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
                            os.environ.setdefault(key.strip(), value.strip())
                
                logger.debug("✅ .env файл загружен")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка загрузки .env: {e}")
    
    def _validate_config(self):
        """Валидация конфигурации"""
        self.validation_errors = []
        
        # Проверка API ключа
        if not self.ELEVENLABS_API_KEY:
            self.validation_errors.append("ELEVENLABS_API_KEY не установлен")
        elif len(self.ELEVENLABS_API_KEY) < 20:
            self.validation_errors.append("ELEVENLABS_API_KEY слишком короткий")
        
        # Проверка Agent ID
        if not self.ELEVENLABS_AGENT_ID:
            self.validation_errors.append("ELEVENLABS_AGENT_ID не установлен")
        
        # Проверка аудио настроек
        if self.SAMPLE_RATE not in [8000, 16000, 22050, 24000, 44100]:
            self.validation_errors.append(f"Неподдерживаемая частота дискретизации: {self.SAMPLE_RATE}")
        
        if self.CHUNK_SIZE < 128 or self.CHUNK_SIZE > 8192:
            self.validation_errors.append(f"Неподходящий размер чанка: {self.CHUNK_SIZE}")
        
        if self.CHANNELS not in [1, 2]:
            self.validation_errors.append(f"Неподдерживаемое количество каналов: {self.CHANNELS}")
        
        # Проверка сетевых настроек
        if self.WEBSOCKET_TIMEOUT < 5 or self.WEBSOCKET_TIMEOUT > 300:
            self.validation_errors.append(f"Неподходящий таймаут WebSocket: {self.WEBSOCKET_TIMEOUT}")
        
        if self.RECONNECT_ATTEMPTS < 0 or self.RECONNECT_ATTEMPTS > 20:
            self.validation_errors.append(f"Неподходящее количество попыток переподключения: {self.RECONNECT_ATTEMPTS}")
    
    def validate(self) -> bool:
        """Проверка валидности конфигурации"""
        if self.validation_errors:
            logger.error("❌ Ошибки конфигурации:")
            for error in self.validation_errors:
                logger.error(f"   • {error}")
            return False
        
        logger.info("✅ Конфигурация валидна")
        return True
    
    def print_config(self):
        """Вывод конфигурации"""
        print("\n📋 Конфигурация:")
        print(f"   🔑 API Key: {'✅ Установлен' if self.ELEVENLABS_API_KEY else '❌ Не установлен'}")
        print(f"   🤖 Agent ID: {self.ELEVENLABS_AGENT_ID}")
        print(f"   🎵 Частота: {self.SAMPLE_RATE} Hz")
        print(f"   📦 Размер чанка: {self.CHUNK_SIZE}")
        print(f"   🔊 Каналы: {self.CHANNELS}")
        print(f"   📊 Уровень логов: {self.LOG_LEVEL}")
        print(f"   🔄 Попытки переподключения: {self.RECONNECT_ATTEMPTS}")
        print(f"   💓 Heartbeat: {self.HEARTBEAT_INTERVAL}с")
        
        if self.DEBUG:
            print(f"   🐛 Debug режим: Включен")
    
    def get_audio_config(self) -> dict:
        """Получение аудио конфигурации"""
        return {
            "sample_rate": self.SAMPLE_RATE,
            "chunk_size": self.CHUNK_SIZE,
            "channels": self.CHANNELS,
            "format": "PCM 16-bit"
        }
    
    def get_websocket_config(self) -> dict:
        """Получение WebSocket конфигурации"""
        return {
            "timeout": self.WEBSOCKET_TIMEOUT,
            "reconnect_attempts": self.RECONNECT_ATTEMPTS,
            "heartbeat_interval": self.HEARTBEAT_INTERVAL
        }
    
    def create_env_template(self) -> str:
        """Создание шаблона .env файла"""
        template = f"""# ElevenLabs Conversational AI - Конфигурация
# Получите API ключ на https://elevenlabs.io/

# Обязательные настройки
ELEVENLABS_API_KEY=your_api_key_here
ELEVENLABS_AGENT_ID={self.ELEVENLABS_AGENT_ID}

# Аудио настройки
SAMPLE_RATE={self.SAMPLE_RATE}
CHUNK_SIZE={self.CHUNK_SIZE}
CHANNELS={self.CHANNELS}

# Логирование
LOG_LEVEL={self.LOG_LEVEL}
LOG_FILE=

# Сетевые настройки
WEBSOCKET_TIMEOUT={self.WEBSOCKET_TIMEOUT}
RECONNECT_ATTEMPTS={self.RECONNECT_ATTEMPTS}
HEARTBEAT_INTERVAL={self.HEARTBEAT_INTERVAL}

# Дополнительные настройки
DEBUG=false
ENABLE_VAD_DISPLAY=true
"""
        return template
    
    def save_env_template(self, filename: str = ".env.example"):
        """Сохранение шаблона .env файла"""
        try:
            template = self.create_env_template()
            
            with open(filename, 'w') as f:
                f.write(template)
            
            logger.info(f"✅ Шаблон сохранен: {filename}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения шаблона: {e}")
            return False

# Глобальный экземпляр конфигурации
config = Config()
