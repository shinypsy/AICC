"""오픈소스 STT — faster-whisper."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
from faster_whisper import WhisperModel

from config import (
    WHISPER_COMPUTE_TYPE,
    WHISPER_DEVICE,
    WHISPER_LANGUAGE,
    WHISPER_MODEL,
)


@lru_cache(maxsize=1)
def get_model() -> WhisperModel:
    print(
        f"[STT] loading Whisper model={WHISPER_MODEL} "
        f"device={WHISPER_DEVICE} compute={WHISPER_COMPUTE_TYPE}"
    )
    return WhisperModel(
        WHISPER_MODEL,
        device=WHISPER_DEVICE,
        compute_type=WHISPER_COMPUTE_TYPE,
    )


def pcm16_bytes_to_float32(pcm: bytes) -> np.ndarray:
    """16-bit little-endian mono PCM → float32 [-1, 1]."""
    if not pcm:
        return np.zeros(0, dtype=np.float32)
    audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    return audio / 32768.0


def transcribe_pcm16(pcm: bytes, sample_rate: int = 16000) -> dict:
    """
    PCM16 mono 오디오를 텍스트로 변환합니다.

    Returns:
        {"text": str, "language": str, "segments": list[str]}
    """
    audio = pcm16_bytes_to_float32(pcm)
    if audio.size < sample_rate * 0.2:  # 0.2초 미만은 무시
        return {"text": "", "language": WHISPER_LANGUAGE, "segments": []}

    model = get_model()
    segments_iter, info = model.transcribe(
        audio,
        language=WHISPER_LANGUAGE or None,
        beam_size=3,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 400},
    )
    segments = []
    parts: list[str] = []
    for seg in segments_iter:
        t = (seg.text or "").strip()
        if t:
            parts.append(t)
            segments.append(t)

    text = " ".join(parts).strip()
    return {
        "text": text,
        "language": getattr(info, "language", WHISPER_LANGUAGE) or WHISPER_LANGUAGE,
        "segments": segments,
    }


def transcribe_file(path: str | Path) -> dict:
    """wav/mp3 등 오디오 파일을 텍스트로 변환합니다."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(str(path))

    model = get_model()
    segments_iter, info = model.transcribe(
        str(path),
        language=WHISPER_LANGUAGE or None,
        beam_size=3,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 400},
    )
    segments = []
    parts: list[str] = []
    for seg in segments_iter:
        t = (seg.text or "").strip()
        if t:
            parts.append(t)
            segments.append(t)

    return {
        "text": " ".join(parts).strip(),
        "language": getattr(info, "language", WHISPER_LANGUAGE) or WHISPER_LANGUAGE,
        "segments": segments,
    }


def warmup() -> None:
    """서버 기동 시 모델 미리 로드."""
    get_model()
