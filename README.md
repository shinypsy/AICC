# AICC — VoIP + STT + RAG + TTS (1~4단계)

```
질문 → Whisper(STT) → 지식 RAG → MMS-TTS(음성) → 브라우저 재생
```

## 실행

```powershell
cd d:\Dev\Project\AICC
.\.venv\Scripts\Activate.ps1
python voip_server.py
```

브라우저: http://127.0.0.1:8000/

## 구성

| 단계 | 기술 | 비고 |
|------|------|------|
| 1 VoIP | 브라우저 WebSocket | Softphone/Twilio 불필요 |
| 2 STT | faster-whisper | 오픈소스 |
| 3 RAG | `knowledge/faq.md` 검색 + (가능 시) OpenAI | 할당량 없으면 문서 인용 |
| 4 TTS | **Meta MMS-TTS Korean** (`facebook/mms-tts-kor`) | 오픈소스, 로컬 |

## 테스트

1. **텍스트로 질문** → 답변 텍스트 + 음성 자동 재생  
2. **데모: 주차 문의** → TTS→STT→RAG→TTS  
3. 마이크가 있으면 **눌러서 말하기**

## 설정

`.env` 예:

```
TTS_ENABLED=1
TTS_MODEL=facebook/mms-tts-kor
```
