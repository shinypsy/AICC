"""Windows SAPI로 한국어 데모 음성(WAV) 생성."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

DEFAULT_TEXT = (
    "안녕하세요. AICC 테스트입니다. "
    "마이크 없이 음성 인식이 되는지 확인합니다."
)


def make_demo_wav(out_path: Path, text: str = DEFAULT_TEXT) -> Path:
    """ko-KR 음성(Heami 등)으로 wav 저장. Windows 전용."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # PowerShell 인자 한글 깨짐 방지: UTF-8 파일로 전달
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8-sig",
        suffix=".txt",
        delete=False,
    ) as tf:
        tf.write(text)
        text_file = Path(tf.name)

    wav = str(out_path.resolve())
    txt = str(text_file.resolve())
    ps = f"""
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::UTF8
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.SetOutputToWaveFile('{wav.replace("'", "''")}')
$s.Rate = -1
try {{
  $s.SelectVoiceByHints(
    [System.Speech.Synthesis.VoiceGender]::Female,
    [System.Speech.Synthesis.VoiceAge]::Adult,
    0,
    [System.Globalization.CultureInfo]::GetCultureInfo('ko-KR')
  )
}} catch {{}}
$speakText = Get-Content -LiteralPath '{txt.replace("'", "''")}' -Raw -Encoding UTF8
$s.Speak($speakText)
$s.Dispose()
"""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0 or not out_path.exists() or out_path.stat().st_size < 1000:
            raise RuntimeError(
                "Windows 음성 합성 실패. "
                f"stderr={result.stderr.strip() or '(없음)'}"
            )
        return out_path
    finally:
        text_file.unlink(missing_ok=True)
