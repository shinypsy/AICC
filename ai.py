"""OpenAI 기반 상담 응답."""

from __future__ import annotations

from openai import OpenAI

from config import OPENAI_API_KEY, OPENAI_MODEL, AI_SYSTEM_PROMPT

_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# call_sid -> 대화 이력
_sessions: dict[str, list[dict[str, str]]] = {}


def reset_session(call_sid: str) -> None:
    _sessions.pop(call_sid, None)


def reply(call_sid: str, user_text: str) -> str:
    """사용자 발화를 받아 AI 응답 텍스트를 반환합니다."""
    if not _client:
        return "서버에 OpenAI API 키가 설정되지 않았습니다. 관리자에게 문의해 주세요."

    text = (user_text or "").strip()
    if not text:
        return "잘 들리지 않았어요. 다시 한 번 말씀해 주시겠어요?"

    history = _sessions.setdefault(
        call_sid,
        [{"role": "system", "content": AI_SYSTEM_PROMPT}],
    )
    history.append({"role": "user", "content": text})

    # 토큰/비용 관리: system + 최근 12턴만 유지
    messages = [history[0]] + history[1:][-12:]

    completion = _client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=messages,
        temperature=0.4,
        max_tokens=300,
    )
    answer = (completion.choices[0].message.content or "").strip()
    if not answer:
        answer = "잠시 문제가 있어요. 다른 방식으로 말씀해 주시겠어요?"

    history.append({"role": "assistant", "content": answer})
    return answer
