"""AICC Phase 1 — PC 로컬 AI 전화 응답 서버.

흐름:
  수신 전화 → /voice/incoming (인사 + 음성 수집)
  사용자 말 → /voice/gather (OpenAI 응답 + 다시 수집)
"""

from __future__ import annotations

from fastapi import FastAPI, Form, Request, Response
from twilio.request_validator import RequestValidator
from twilio.twiml.voice_response import Gather, VoiceResponse

import ai
from config import (
    PORT,
    PUBLIC_BASE_URL,
    TWILIO_AUTH_TOKEN,
)

app = FastAPI(title="AICC Test Voice", version="0.1.0")

# Twilio 한국어 TTS (Amazon Polly)
VOICE = "Polly.Seoyeon"
LANGUAGE = "ko-KR"


def _base_url(request: Request) -> str:
    if PUBLIC_BASE_URL:
        return PUBLIC_BASE_URL
    # 로컬/ngrok 모두 request 기준으로 동작
    return str(request.base_url).rstrip("/")


def _validate_twilio(request: Request, form: dict) -> bool:
    """Twilio 서명 검증. AUTH_TOKEN이 없으면 개발 편의상 통과."""
    if not TWILIO_AUTH_TOKEN:
        return True
    signature = request.headers.get("X-Twilio-Signature", "")
    url = str(request.url)
    # ngrok 등에서 PUBLIC_BASE_URL을 쓰는 경우 서명 URL을 맞춤
    if PUBLIC_BASE_URL:
        url = PUBLIC_BASE_URL + request.url.path
        if request.url.query:
            url += f"?{request.url.query}"
    validator = RequestValidator(TWILIO_AUTH_TOKEN)
    return validator.validate(url, form, signature)


def _gather(
    action_url: str,
    prompt: str | None = None,
    *,
    timeout_redirect: str | None = None,
) -> VoiceResponse:
    resp = VoiceResponse()
    gather = Gather(
        input="speech",
        language=LANGUAGE,
        speech_timeout="auto",
        action=action_url,
        method="POST",
        timeout=5,
    )
    if prompt:
        gather.say(prompt, voice=VOICE, language=LANGUAGE)
    resp.append(gather)
    if timeout_redirect:
        resp.redirect(timeout_redirect)
    return resp


@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": "aicc-voice"}


@app.post("/voice/incoming")
async def voice_incoming(
    request: Request,
    CallSid: str = Form(default=""),
    From: str = Form(default=""),
) -> Response:
    form = dict(await request.form())
    if not _validate_twilio(request, form):
        return Response(content="Forbidden", status_code=403)

    if CallSid:
        ai.reset_session(CallSid)

    base = _base_url(request)
    action = f"{base}/voice/gather"
    reprompt = f"{base}/voice/reprompt"
    prompt = (
        "안녕하세요. AICC 테스트 상담센터입니다. "
        "무엇을 도와드릴까요? 말씀해 주세요."
    )
    twiml = _gather(action, prompt, timeout_redirect=reprompt)
    return Response(content=str(twiml), media_type="application/xml")


@app.post("/voice/reprompt")
async def voice_reprompt(request: Request) -> Response:
    form = dict(await request.form())
    if not _validate_twilio(request, form):
        return Response(content="Forbidden", status_code=403)

    base = _base_url(request)
    action = f"{base}/voice/gather"
    reprompt = f"{base}/voice/reprompt"
    twiml = _gather(
        action,
        "듣고 있습니다. 궁금한 점을 말씀해 주세요.",
        timeout_redirect=reprompt,
    )
    return Response(content=str(twiml), media_type="application/xml")


@app.post("/voice/gather")
async def voice_gather(
    request: Request,
    CallSid: str = Form(default=""),
    SpeechResult: str = Form(default=""),
    Confidence: str = Form(default=""),
) -> Response:
    form = dict(await request.form())
    if not _validate_twilio(request, form):
        return Response(content="Forbidden", status_code=403)

    user_text = (SpeechResult or "").strip()
    action = f"{_base_url(request)}/voice/gather"

    # 종료 키워드
    end_words = ("끊을게", "끊어요", "종료", "그만", "통화 종료", "hang up")
    if any(w in user_text for w in end_words):
        resp = VoiceResponse()
        resp.say(
            "통화를 종료합니다. 이용해 주셔서 감사합니다.",
            voice=VOICE,
            language=LANGUAGE,
        )
        resp.hangup()
        if CallSid:
            ai.reset_session(CallSid)
        return Response(content=str(resp), media_type="application/xml")

    try:
        answer = ai.reply(CallSid or "unknown", user_text)
    except Exception as exc:  # noqa: BLE001 — 통화 중에는 사용자에게 안내
        answer = f"잠시 오류가 발생했습니다. 다시 말씀해 주세요."
        print(f"[AI ERROR] {exc}")

    resp = VoiceResponse()
    gather = Gather(
        input="speech",
        language=LANGUAGE,
        speech_timeout="auto",
        action=action,
        method="POST",
        timeout=5,
    )
    gather.say(answer, voice=VOICE, language=LANGUAGE)
    gather.say("더 궁금한 점이 있으면 말씀해 주세요.", voice=VOICE, language=LANGUAGE)
    resp.append(gather)
    resp.say(
        "말씀이 없으시면 통화를 종료합니다. 감사합니다.",
        voice=VOICE,
        language=LANGUAGE,
    )
    resp.hangup()
    return Response(content=str(resp), media_type="application/xml")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("twilio_voice:app", host="0.0.0.0", port=PORT, reload=True)
