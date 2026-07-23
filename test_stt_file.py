"""마이크 없이 STT 테스트 (CLI).

사용 예:
  python test_stt_file.py samples/demo_ko.wav
  python test_stt_file.py --demo
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import stt
from demo_audio import DEFAULT_TEXT, make_demo_wav


def main() -> None:
    parser = argparse.ArgumentParser(description="마이크 없이 STT 테스트")
    parser.add_argument("audio", nargs="?", help="wav/mp3 파일 경로")
    parser.add_argument("--demo", action="store_true", help="Windows TTS로 데모 음성 생성 후 STT")
    parser.add_argument("--text", default=DEFAULT_TEXT)
    args = parser.parse_args()

    if args.demo:
        audio = ROOT / "samples" / "demo_ko.wav"
        make_demo_wav(audio, args.text)
        print(f"demo audio saved: {audio}")
    elif args.audio:
        audio = Path(args.audio)
    else:
        parser.error("오디오 경로를 주거나 --demo 를 사용하세요.")

    print("[STT] running…")
    result = stt.transcribe_file(audio)
    # Windows 콘솔 한글 깨짐 방지
    sys.stdout.reconfigure(encoding="utf-8")
    print("text:", result["text"] or "(empty)")
    print("language:", result["language"])


if __name__ == "__main__":
    main()
