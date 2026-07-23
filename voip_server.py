"""AICC VoIP + STT + RAG + TTS 서버 (1~4단계).

음성/텍스트 → Whisper(STT) → RAG → MMS-TTS → 브라우저 재생
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import rag
import stt
import tts
from config import PORT, TTS_ENABLED, WHISPER_MODEL

STATIC_DIR = Path(__file__).resolve().parent / "static"
SAMPLE_DIR = Path(__file__).resolve().parent / "samples"
SAMPLE_RATE = 16000
DEMO_TEXT = "주차는 어떻게 하나요?"


async def _rag_then_tts(text: str) -> dict:
    rag_result = await asyncio.to_thread(rag.answer, text)
    answer = rag_result.get("answer", "")
    payload = {
        "transcript": text,
        "answer": answer,
        "contexts": rag_result.get("contexts", []),
        "rag_mode": rag_result.get("mode", ""),
        "rag_ok": rag_result.get("ok", False),
        "tts_url": None,
        "tts_engine": None,
    }
    if TTS_ENABLED and answer:
        tts_result = await asyncio.to_thread(
            tts.synthesize,
            answer,
            SAMPLE_DIR / "answer_tts.wav",
        )
        if tts_result.get("ok"):
            payload["tts_url"] = tts_result.get("url")
            payload["tts_engine"] = tts_result.get("engine")
        else:
            payload["tts_error"] = tts_result.get("error")
    return payload


@asynccontextmanager
async def lifespan(_app: FastAPI):
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, stt.warmup)
    loop.run_in_executor(None, rag.warmup)
    if TTS_ENABLED:
        loop.run_in_executor(None, tts.warmup)
    SAMPLE_DIR.mkdir(exist_ok=True)
    yield


app = FastAPI(title="AICC VoIP STT RAG TTS", version="0.4.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "service": "aicc-voip-stt-rag-tts",
        "whisper_model": WHISPER_MODEL,
        "sample_rate": SAMPLE_RATE,
        "knowledge_chunks": len(rag.load_chunks()),
        "tts_enabled": TTS_ENABLED,
        "no_mic_test": True,
        "rag": True,
        "tts": True,
    }


def _make_demo_wav(text: str, out_path: Path) -> None:
    from demo_audio import make_demo_wav

    make_demo_wav(out_path, text)


@app.post("/api/ask")
async def ask_text(question: str = Form(...)) -> dict:
    """텍스트 → RAG → TTS."""
    result = await _rag_then_tts(question)
    return {"ok": True, **result, "mode": result.get("rag_mode")}


@app.post("/api/tts")
async def tts_only(text: str = Form(...)) -> dict:
    """텍스트만 TTS."""
    result = await asyncio.to_thread(
        tts.synthesize,
        text,
        SAMPLE_DIR / "answer_tts.wav",
    )
    return result


@app.post("/api/stt/upload")
async def stt_upload(file: UploadFile = File(...)) -> dict:
    suffix = Path(file.filename or "audio.wav").suffix or ".wav"
    raw = await file.read()
    if not raw:
        return {"ok": False, "text": "", "error": "빈 파일입니다."}

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(raw)
        tmp_path = Path(tmp.name)

    try:
        stt_result = await asyncio.to_thread(stt.transcribe_file, tmp_path)
        pipeline = await _rag_then_tts(stt_result.get("text", ""))
        return {
            "ok": True,
            "text": stt_result.get("text", ""),
            "language": stt_result.get("language"),
            "segments": stt_result.get("segments", []),
            "source": "upload",
            "filename": file.filename,
            **pipeline,
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "text": "", "error": str(exc)}
    finally:
        tmp_path.unlink(missing_ok=True)


@app.post("/api/stt/demo")
async def stt_demo(text: str = Form(default=DEMO_TEXT)) -> dict:
    spoken = text.strip() or DEMO_TEXT
    sample_path = SAMPLE_DIR / "demo_ko.wav"
    try:
        await asyncio.to_thread(_make_demo_wav, spoken, sample_path)
        stt_result = await asyncio.to_thread(stt.transcribe_file, sample_path)
        pipeline = await _rag_then_tts(stt_result.get("text", ""))
        return {
            "ok": True,
            "text": stt_result.get("text", ""),
            "language": stt_result.get("language"),
            "segments": stt_result.get("segments", []),
            "source": "demo",
            "original_text": spoken,
            "audio_url": "/samples/demo_ko.wav",
            **pipeline,
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "text": "", "error": str(exc)}


@app.get("/samples/{name}")
def get_sample(name: str):
    path = SAMPLE_DIR / name
    if not path.exists() or not path.is_file():
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(path)


@app.websocket("/ws/voice")
async def ws_voice(websocket: WebSocket) -> None:
    await websocket.accept()
    buffer = bytearray()
    recording = False

    await websocket.send_json(
        {
            "type": "ready",
            "sample_rate": SAMPLE_RATE,
            "message": "질문하면 STT → RAG → TTS까지 진행합니다.",
        }
    )

    try:
        while True:
            message = await websocket.receive()

            if message.get("type") == "websocket.disconnect":
                break

            if "text" in message and message["text"] is not None:
                try:
                    data = json.loads(message["text"])
                except json.JSONDecodeError:
                    await websocket.send_json({"type": "error", "message": "잘못된 JSON"})
                    continue

                msg_type = data.get("type")
                if msg_type == "start":
                    buffer.clear()
                    recording = True
                    await websocket.send_json({"type": "status", "status": "listening"})
                elif msg_type == "stop":
                    recording = False
                    await websocket.send_json({"type": "status", "status": "transcribing"})
                    pcm = bytes(buffer)
                    buffer.clear()

                    result = await asyncio.to_thread(stt.transcribe_pcm16, pcm, SAMPLE_RATE)
                    transcript = result.get("text", "")
                    await websocket.send_json(
                        {
                            "type": "transcript",
                            "text": transcript,
                            "language": result.get("language"),
                            "segments": result.get("segments", []),
                            "bytes": len(pcm),
                        }
                    )

                    await websocket.send_json({"type": "status", "status": "answering"})
                    pipeline = await _rag_then_tts(transcript)
                    await websocket.send_json(
                        {
                            "type": "answer",
                            "text": pipeline["answer"],
                            "contexts": pipeline["contexts"],
                            "rag_mode": pipeline["rag_mode"],
                            "tts_url": pipeline.get("tts_url"),
                            "tts_engine": pipeline.get("tts_engine"),
                        }
                    )
                    await websocket.send_json({"type": "status", "status": "idle"})
                elif msg_type == "ping":
                    await websocket.send_json({"type": "pong"})
                else:
                    await websocket.send_json(
                        {"type": "error", "message": f"unknown type: {msg_type}"}
                    )

            elif "bytes" in message and message["bytes"] is not None:
                if recording:
                    buffer.extend(message["bytes"])
                    max_bytes = SAMPLE_RATE * 2 * 60
                    if len(buffer) > max_bytes:
                        del buffer[:-max_bytes]

    except WebSocketDisconnect:
        return


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("voip_server:app", host="0.0.0.0", port=PORT, reload=False)
