# AICC — 모바일 브라우저 VoIP + STT + RAG + TTS

```
모바일 브라우저 → 통화 연결 → 말하기 → Whisper → FAQ → MMS-TTS 재생
```

## 모바일에서 쓰는 방법 (중요)

모바일 브라우저는 **마이크에 HTTPS**가 필요합니다.

### 1) PC에서 HTTPS 서버 실행

```powershell
cd d:\Dev\Project\AICC
.\.venv\Scripts\Activate.ps1
pip install cryptography
python voip_server.py --https
```

### 2) 폰과 PC를 같은 Wi‑Fi에 연결

화면에 안내된 주소로 접속합니다. 예:

`https://192.168.0.91:8000/`

- 처음엔 **인증서 경고**가 뜹니다 → 고급 → 계속 진행(또는 방문)
- **통화 연결** → 마이크 허용
- **탭해서 말하기** → 다시 탭해서 전송
- 답변 음성이 나오면 통화 유지한 채 이어서 질문 가능
- **통화 종료**

### 3) PC 방화벽

포트 `8000` 인바운드를 허용해야 폰에서 접속됩니다.

## PC 전용 (HTTP)

```powershell
python voip_server.py
```

`http://127.0.0.1:8000/` — PC 브라우저 테스트용

## FAQ 문서

`knowledge/faq.md`  
없으면: `답변이 곤란합니다. 상담사 연결을 원하시면 말씀해 주세요.`
