#!/usr/bin/env python3
"""
Скрипт для запуска ElevenLabs Voice Assistant MVP
"""

import uvicorn
import sys
import os

def main():
    """Запуск сервера"""
    print("🚀 Запуск ElevenLabs Voice Assistant MVP...")
    print("📋 Конфигурация:")
    print("   - Порт: 8000")
    print("   - Хост: 0.0.0.0 (доступен извне)")
    print("   - Голос: Josh (ElevenLabs)")
    print("   - LLM: GPT-4o-mini")
    print("   - TTS: ElevenLabs Flash v2.5")
    print("\n🔗 Откройте в браузере: http://localhost:8000")
    print("💡 Для остановки: Ctrl+C\n")
    
    try:
        uvicorn.run(
            "app:app",
            host="0.0.0.0", 
            port=8000,
            log_level="info",
            reload=False
        )
    except KeyboardInterrupt:
        print("\n👋 Сервер остановлен!")
    except Exception as e:
        print(f"\n❌ Ошибка запуска: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
