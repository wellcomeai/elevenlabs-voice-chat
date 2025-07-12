#!/usr/bin/env python3
"""
ElevenLabs Conversational AI - Python CLI Application
Голосовой ассистент с CLI интерфейсом
"""

import asyncio
import logging
import sys
import signal
from pathlib import Path

from config import Config
from audio_handler import AudioHandler
from websocket_client import ElevenLabsWebSocketClient
from utils import setup_logging, print_banner, print_help

logger = logging.getLogger(__name__)

class VoiceAssistant:
    """Главный класс голосового ассистента"""
    
    def __init__(self):
        self.config = Config()
        self.audio_handler = None
        self.ws_client = None
        self.is_running = False
        self.is_listening = False
        
    async def initialize(self):
        """Инициализация компонентов"""
        try:
            logger.info("🔧 Инициализация голосового ассистента...")
            
            # Инициализируем аудио обработчик
            self.audio_handler = AudioHandler(
                sample_rate=self.config.SAMPLE_RATE,
                chunk_size=self.config.CHUNK_SIZE,
                channels=self.config.CHANNELS
            )
            
            # Инициализируем WebSocket клиент
            self.ws_client = ElevenLabsWebSocketClient(
                api_key=self.config.ELEVENLABS_API_KEY,
                agent_id=self.config.ELEVENLABS_AGENT_ID,
                audio_handler=self.audio_handler
            )
            
            # Подключаемся к ElevenLabs
            await self.ws_client.connect()
            
            logger.info("✅ Инициализация завершена")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации: {e}")
            return False
    
    async def start_conversation(self):
        """Запуск разговора"""
        self.is_running = True
        
        print("\n🎤 Голосовой ассистент готов!")
        print("📋 Команды:")
        print("   ПРОБЕЛ - Начать/закончить запись")
        print("   'q' + ENTER - Выход")
        print("   'h' + ENTER - Помощь")
        print("   's' + ENTER - Статистика")
        print("\n💬 Начните говорить...")
        
        # Запускаем обработку команд
        input_task = asyncio.create_task(self.handle_input())
        
        try:
            # Основной цикл
            while self.is_running:
                await asyncio.sleep(0.1)
                
        except KeyboardInterrupt:
            logger.info("👋 Получен сигнал прерывания")
        finally:
            input_task.cancel()
            await self.cleanup()
    
    async def handle_input(self):
        """Обработка пользовательского ввода"""
        try:
            while self.is_running:
                try:
                    # Асинхронное чтение ввода
                    line = await asyncio.to_thread(input, "")
                    command = line.strip().lower()
                    
                    if command == 'q':
                        logger.info("👋 Выход из приложения")
                        self.is_running = False
                        break
                    elif command == 'h':
                        print_help()
                    elif command == 's':
                        await self.print_statistics()
                    elif command == 'r':
                        await self.toggle_recording()
                    elif command == '':
                        # Пустая строка - переключение записи
                        await self.toggle_recording()
                    else:
                        print(f"❓ Неизвестная команда: {command}")
                        
                except EOFError:
                    # Ctrl+D
                    self.is_running = False
                    break
                    
        except asyncio.CancelledError:
            pass
    
    async def toggle_recording(self):
        """Переключение записи"""
        if not self.is_listening:
            await self.start_listening()
        else:
            await self.stop_listening()
    
    async def start_listening(self):
        """Начало записи"""
        if self.is_listening:
            return
            
        try:
            print("🎤 Начинаю запись... (нажмите ENTER для остановки)")
            self.is_listening = True
            await self.audio_handler.start_recording()
            
        except Exception as e:
            logger.error(f"❌ Ошибка начала записи: {e}")
            self.is_listening = False
    
    async def stop_listening(self):
        """Остановка записи"""
        if not self.is_listening:
            return
            
        try:
            print("⏹️ Останавливаю запись...")
            self.is_listening = False
            await self.audio_handler.stop_recording()
            
        except Exception as e:
            logger.error(f"❌ Ошибка остановки записи: {e}")
    
    async def print_statistics(self):
        """Вывод статистики"""
        if self.ws_client:
            stats = self.ws_client.get_statistics()
            print("\n📊 Статистика:")
            print(f"   🔗 Подключение: {'✅ Активно' if stats['connected'] else '❌ Отключено'}")
            print(f"   💬 Сообщений: {stats['messages_sent']}")
            print(f"   🎵 Аудио чанков: {stats['audio_chunks_sent']}")
            print(f"   🔊 Воспроизведено: {stats['audio_chunks_received']}")
            print(f"   ⏱️ Время работы: {stats['uptime']:.1f}с")
            print()
    
    async def cleanup(self):
        """Очистка ресурсов"""
        logger.info("🧹 Очистка ресурсов...")
        
        if self.is_listening:
            await self.stop_listening()
        
        if self.audio_handler:
            await self.audio_handler.cleanup()
        
        if self.ws_client:
            await self.ws_client.disconnect()
        
        logger.info("✅ Очистка завершена")

def signal_handler(signum, frame):
    """Обработчик сигналов"""
    logger.info(f"📡 Получен сигнал {signum}")
    # asyncio.get_event_loop().stop()

async def main():
    """Главная функция"""
    
    # Настройка логирования
    setup_logging()
    
    # Баннер
    print_banner()
    
    # Проверка конфигурации
    config = Config()
    if not config.validate():
        logger.error("❌ Некорректная конфигурация")
        return 1
    
    # Обработчики сигналов
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Создание и запуск ассистента
    assistant = VoiceAssistant()
    
    try:
        # Инициализация
        if not await assistant.initialize():
            return 1
        
        # Запуск разговора
        await assistant.start_conversation()
        
        return 0
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        return 1
    
    finally:
        await assistant.cleanup()

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n👋 До свидания!")
        sys.exit(0)
