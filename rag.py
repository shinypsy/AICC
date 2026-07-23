"""문서 기반 RAG — 검색 + LLM 답변."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from config import AI_SYSTEM_PROMPT, OPENAI_API_KEY, OPENAI_MODEL, ROOT

KNOWLEDGE_DIR = ROOT / "knowledge"


@dataclass
class Chunk:
    title: str
    text: str
    source: str


def _split_markdown(path: Path) -> list[Chunk]:
    raw = path.read_text(encoding="utf-8")
    parts = re.split(r"(?m)^##\s+", raw)
    chunks: list[Chunk] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        lines = part.splitlines()
        title = lines[0].strip()
        body = "\n".join(lines[1:]).strip()
        if not body:
            continue
        chunks.append(
            Chunk(
                title=title,
                text=f"{title}\n{body}",
                source=path.name,
            )
        )
    return chunks


@lru_cache(maxsize=1)
def load_chunks() -> tuple[Chunk, ...]:
    if not KNOWLEDGE_DIR.exists():
        return tuple()
    items: list[Chunk] = []
    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        items.extend(_split_markdown(path))
    return tuple(items)


def _tokenize(text: str) -> set[str]:
    """간단한 한국어/영문 토큰화 (공백·문장부호 기준 + 2-gram)."""
    text = text.lower()
    words = re.findall(r"[a-z0-9]+|[가-힣]+", text)
    grams: set[str] = set(words)
    for w in words:
        if len(w) >= 2 and re.search(r"[가-힣]", w):
            for i in range(len(w) - 1):
                grams.add(w[i : i + 2])
    return grams


def retrieve(query: str, top_k: int = 3) -> list[dict]:
    chunks = load_chunks()
    q = _tokenize(query)
    if not chunks or not q:
        return []

    scored: list[tuple[float, Chunk]] = []
    for ch in chunks:
        tokens = _tokenize(ch.text)
        overlap = len(q & tokens)
        # 제목 일치에 가중치
        title_tokens = _tokenize(ch.title)
        overlap += 1.5 * len(q & title_tokens)
        if overlap <= 0:
            continue
        score = overlap / (len(tokens) ** 0.3)
        scored.append((score, ch))

    scored.sort(key=lambda x: x[0], reverse=True)
    results = []
    for score, ch in scored[:top_k]:
        results.append(
            {
                "title": ch.title,
                "text": ch.text,
                "source": ch.source,
                "score": round(score, 3),
            }
        )
    return results


def _answer_with_openai(question: str, contexts: list[dict]) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=OPENAI_API_KEY)
    ctx = "\n\n".join(
        f"[{c['title']}]\n{c['text']}" for c in contexts
    ) or "(관련 문서 없음)"
    messages = [
        {
            "role": "system",
            "content": (
                f"{AI_SYSTEM_PROMPT}\n"
                "아래 참고 문서 내용만 근거로 답하세요. "
                "문서에 없으면 모른다고 짧게 말하고, 대표번호 안내가 가능하면 안내하세요. "
                "2~4문장으로 답하세요."
            ),
        },
        {
            "role": "user",
            "content": f"참고 문서:\n{ctx}\n\n질문: {question}",
        },
    ]
    completion = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=messages,
        temperature=0.2,
        max_tokens=350,
    )
    return (completion.choices[0].message.content or "").strip()


def _answer_extractive(question: str, contexts: list[dict]) -> str:
    if not contexts:
        return (
            "관련 안내를 찾지 못했습니다. "
            "대표번호 02-1234-5678 로 문의해 주세요."
        )
    top = contexts[0]
    body = top["text"].split("\n", 1)
    detail = body[1].strip() if len(body) > 1 else top["text"]
    return f"{detail}"


def answer(question: str, top_k: int = 3) -> dict:
    """질문 → 검색 → 답변."""
    q = (question or "").strip()
    if not q:
        return {
            "ok": False,
            "answer": "질문을 이해하지 못했습니다. 다시 말씀해 주세요.",
            "contexts": [],
            "mode": "none",
        }

    contexts = retrieve(q, top_k=top_k)
    mode = "extractive"
    try:
        if OPENAI_API_KEY:
            text = _answer_with_openai(q, contexts)
            mode = "openai_rag"
        else:
            text = _answer_extractive(q, contexts)
    except Exception as exc:  # noqa: BLE001
        # 할당량/네트워크 오류 시 문서 직접 인용
        text = _answer_extractive(q, contexts)
        mode = f"extractive_fallback:{type(exc).__name__}"

    return {
        "ok": True,
        "answer": text,
        "contexts": contexts,
        "mode": mode,
        "question": q,
    }


def warmup() -> None:
    load_chunks()
