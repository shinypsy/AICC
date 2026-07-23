"""문서 기반 FAQ 답변.

문서에 있으면 해당 내용을 읽고, 없으면 고정 멘트로 응답합니다.
(OpenAI 없이도 AI 상담처럼 동작)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from config import RAG_FALLBACK_MESSAGE, RAG_MIN_SCORE, ROOT

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


def _body_from_chunk(chunk: dict) -> str:
    body = chunk["text"].split("\n", 1)
    return body[1].strip() if len(body) > 1 else chunk["text"]


def answer(question: str, top_k: int = 3) -> dict:
    """질문 → 문서 검색 → 문서 답변 또는 고정 멘트."""
    q = (question or "").strip()
    if not q:
        return {
            "ok": False,
            "answer": "질문을 이해하지 못했습니다. 다시 말씀해 주세요.",
            "contexts": [],
            "mode": "none",
            "matched": False,
        }

    contexts = retrieve(q, top_k=top_k)
    best = contexts[0]["score"] if contexts else 0.0

    if not contexts or best < RAG_MIN_SCORE:
        return {
            "ok": True,
            "answer": RAG_FALLBACK_MESSAGE,
            "contexts": contexts,
            "mode": "fallback_no_match",
            "matched": False,
            "best_score": best,
            "question": q,
        }

    return {
        "ok": True,
        "answer": _body_from_chunk(contexts[0]),
        "contexts": contexts,
        "mode": "document",
        "matched": True,
        "best_score": best,
        "question": q,
    }


def warmup() -> None:
    load_chunks.cache_clear()
    load_chunks()
