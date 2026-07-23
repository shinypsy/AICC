"""오픈소스 TTS — Meta MMS-TTS Korean (VITS)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from transformers import AutoTokenizer, VitsModel

from config import ROOT, TTS_MODEL

SAMPLES_DIR = ROOT / "samples"
SAMPLES_DIR.mkdir(exist_ok=True)


@lru_cache(maxsize=1)
def _load() -> tuple[VitsModel, AutoTokenizer]:
    print(f"[TTS] loading {TTS_MODEL}")
    model = VitsModel.from_pretrained(TTS_MODEL)
    tokenizer = AutoTokenizer.from_pretrained(TTS_MODEL)
    model.eval()
    return model, tokenizer


def synthesize(text: str, out_path: Path | None = None) -> dict:
    """텍스트 → wav 파일. Returns {ok, path, engine, sample_rate, error?}."""
    spoken = (text or "").strip()
    if not spoken:
        return {"ok": False, "error": "빈 텍스트", "engine": "mms-tts-kor"}

    out = Path(out_path) if out_path else SAMPLES_DIR / "answer_tts.wav"
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        model, tokenizer = _load()
        inputs = tokenizer(spoken, return_tensors="pt")
        if inputs["input_ids"].dtype != torch.long:
            inputs["input_ids"] = inputs["input_ids"].long()

        with torch.no_grad():
            waveform = model(**inputs).waveform

        audio = waveform.squeeze().detach().cpu().numpy().astype(np.float32)
        sr = int(getattr(model.config, "sampling_rate", 16000))
        sf.write(str(out), audio, sr)
        return {
            "ok": True,
            "path": str(out),
            "url": f"/samples/{out.name}",
            "engine": "mms-tts-kor",
            "sample_rate": sr,
            "chars": len(spoken),
        }
    except Exception as exc:  # noqa: BLE001
        # 폴백: Windows SAPI (로컬, 오픈소스 아님)
        try:
            from demo_audio import make_demo_wav

            make_demo_wav(out, spoken)
            return {
                "ok": True,
                "path": str(out),
                "url": f"/samples/{out.name}",
                "engine": "windows-sapi-fallback",
                "sample_rate": 22050,
                "chars": len(spoken),
                "warning": str(exc),
            }
        except Exception as exc2:  # noqa: BLE001
            return {
                "ok": False,
                "error": f"tts failed: {exc}; fallback: {exc2}",
                "engine": "none",
            }


def warmup() -> None:
    _load()
