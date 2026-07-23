"""환경 변수 로더."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "").strip()

PORT = int(os.getenv("PORT", "8000"))
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")

AI_SYSTEM_PROMPT = os.getenv(
    "AI_SYSTEM_PROMPT",
    "당신은 AICC 테스트 상담원입니다. 한국어로 짧고 명확하게 답하세요.",
).strip()

# Whisper STT (오픈소스)
# tiny / base / small / medium / large-v3
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small").strip()
# cpu 또는 cuda
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu").strip()
# cpu: int8 | cuda: float16 권장
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8").strip()
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "ko").strip()

# TTS (오픈소스 Meta MMS)
TTS_MODEL = os.getenv("TTS_MODEL", "facebook/mms-tts-kor").strip()
TTS_ENABLED = os.getenv("TTS_ENABLED", "1").strip() not in {"0", "false", "False"}
