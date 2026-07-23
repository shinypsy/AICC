(() => {
  const TARGET_RATE = 16000;

  const elConn = document.getElementById("conn");
  const elCallState = document.getElementById("callState");
  const elStatus = document.getElementById("status");
  const elTalk = document.getElementById("talk");
  const elTalkHint = document.getElementById("talkHint");
  const elCallBtn = document.getElementById("callBtn");
  const elHangBtn = document.getElementById("hangBtn");
  const elPreCall = document.getElementById("preCall");
  const elInCall = document.getElementById("inCall");
  const elTimer = document.getElementById("callTimer");
  const elAccessHint = document.getElementById("accessHint");
  const elTranscript = document.getElementById("transcript");
  const elAnswer = document.getElementById("answer");
  const elRagMeta = document.getElementById("ragMeta");
  const elAnswerAudio = document.getElementById("answerAudio");
  const elLevel = document.getElementById("level");
  const elLog = document.getElementById("log");
  const elFile = document.getElementById("fileInput");
  const elDemo = document.getElementById("demoBtn");
  const elAudio = document.getElementById("demoAudio");
  const elAskInput = document.getElementById("askInput");
  const elAskBtn = document.getElementById("askBtn");

  let ws = null;
  let audioCtx = null;
  let mediaStream = null;
  let processor = null;
  let source = null;
  let recording = false;
  let inCall = false;
  let busy = false; // STT/RAG/TTS 처리 중
  let callStartedAt = 0;
  let timerId = null;
  let wakeLock = null;

  function log(msg) {
    if (!elLog) return;
    const li = document.createElement("li");
    li.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
    elLog.prepend(li);
  }

  function setConn(text, cls) {
    elConn.textContent = text;
    elConn.className = `badge ${cls || ""}`;
  }

  function setCallState(text, cls) {
    elCallState.textContent = text;
    elCallState.className = `badge ${cls || ""}`;
  }

  function setStatus(text, cls) {
    elStatus.textContent = text;
    elStatus.className = `badge ${cls || ""}`;
  }

  function formatTime(sec) {
    const m = String(Math.floor(sec / 60)).padStart(2, "0");
    const s = String(sec % 60).padStart(2, "0");
    return `${m}:${s}`;
  }

  function startTimer() {
    callStartedAt = Date.now();
    elTimer.textContent = "00:00";
    clearInterval(timerId);
    timerId = setInterval(() => {
      const sec = Math.floor((Date.now() - callStartedAt) / 1000);
      elTimer.textContent = formatTime(sec);
    }, 1000);
  }

  function stopTimer() {
    clearInterval(timerId);
    timerId = null;
    elTimer.textContent = "00:00";
  }

  async function requestWakeLock() {
    try {
      if (navigator.wakeLock) {
        wakeLock = await navigator.wakeLock.request("screen");
      }
    } catch {
      /* ignore */
    }
  }

  async function releaseWakeLock() {
    try {
      await wakeLock?.release();
    } catch {
      /* ignore */
    }
    wakeLock = null;
  }

  function showAnswer(answer, contexts, mode, ttsUrl, ttsEngine) {
    elAnswer.textContent = answer || "(답변 없음)";
    const titles = (contexts || []).map((c) => c.title).join(", ");
    const parts = [];
    if (mode) parts.push(`mode=${mode}`);
    if (ttsEngine) parts.push(`tts=${ttsEngine}`);
    if (titles) parts.push(`참고: ${titles}`);
    elRagMeta.textContent = parts.join(" · ");
    if (ttsUrl) {
      elAnswerAudio.style.display = "block";
      elAnswerAudio.src = `${ttsUrl}?t=${Date.now()}`;
      const play = () => elAnswerAudio.play().catch(() => {});
      play();
      // iOS: 재생 끝난 뒤 다시 말할 수 있게
      elAnswerAudio.onended = () => {
        busy = false;
        updateTalkUi();
      };
    } else {
      busy = false;
      updateTalkUi();
    }
  }

  function wsUrl() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    return `${proto}//${location.host}/ws/voice`;
  }

  function downsample(float32, inRate, outRate) {
    if (inRate === outRate) return float32;
    const ratio = inRate / outRate;
    const newLen = Math.floor(float32.length / ratio);
    const result = new Float32Array(newLen);
    for (let i = 0; i < newLen; i++) {
      result[i] = float32[Math.floor(i * ratio)];
    }
    return result;
  }

  function floatTo16BitPCM(float32) {
    const buf = new ArrayBuffer(float32.length * 2);
    const view = new DataView(buf);
    for (let i = 0; i < float32.length; i++) {
      let s = Math.max(-1, Math.min(1, float32[i]));
      view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    }
    return buf;
  }

  function updateTalkUi() {
    if (!inCall) {
      elTalk.disabled = true;
      return;
    }
    if (busy) {
      elTalk.disabled = true;
      elTalk.textContent = "답변 처리 중…";
      elTalk.classList.remove("recording");
      elTalkHint.textContent = "답변이 끝나면 다시 말할 수 있습니다.";
      return;
    }
    elTalk.disabled = false;
    if (recording) {
      elTalk.classList.add("recording");
      elTalk.textContent = "탭해서 전송";
      elTalkHint.textContent = "다시 탭하면 질문을 보냅니다.";
    } else {
      elTalk.classList.remove("recording");
      elTalk.textContent = "탭해서 말하기";
      elTalkHint.textContent = "한 번 탭 → 녹음 시작 / 다시 탭 → 전송(STT→답변)";
    }
  }

  function connectWs() {
    ws = new WebSocket(wsUrl());
    ws.binaryType = "arraybuffer";

    ws.onopen = () => {
      setConn("연결됨", "ok");
      elCallBtn.disabled = false;
      log("WebSocket 연결");
    };

    ws.onclose = () => {
      setConn("끊김", "hot");
      elCallBtn.disabled = true;
      if (inCall) endCall(false);
      log("WebSocket 종료 — 3초 후 재연결");
      setTimeout(connectWs, 3000);
    };

    ws.onerror = () => {
      setConn("오류", "hot");
      log("WebSocket 오류");
    };

    ws.onmessage = (ev) => {
      let data;
      try {
        data = JSON.parse(ev.data);
      } catch {
        return;
      }

      if (data.type === "ready") {
        if (!busy) setStatus("idle");
        log(data.message || "ready");
      } else if (data.type === "status") {
        const cls =
          data.status === "listening"
            ? "hot"
            : data.status === "transcribing" || data.status === "answering"
              ? "warn"
              : "";
        setStatus(data.status, cls);
        if (data.status === "transcribing" || data.status === "answering") {
          busy = true;
          updateTalkUi();
        }
      } else if (data.type === "transcript") {
        elTranscript.textContent = data.text || "(인식된 내용 없음)";
        log(`STT: ${data.text}`);
      } else if (data.type === "answer") {
        showAnswer(data.text, data.contexts, data.rag_mode, data.tts_url, data.tts_engine);
        log(`RAG: ${data.text}`);
        if (data.tts_url) log(`TTS: ${data.tts_engine || "ok"}`);
        if (!data.tts_url) {
          busy = false;
          updateTalkUi();
        }
      } else if (data.type === "error") {
        busy = false;
        updateTalkUi();
        log(`오류: ${data.message}`);
      }
    };
  }

  async function ensureAudio() {
    if (mediaStream && audioCtx) {
      if (audioCtx.state === "suspended") await audioCtx.resume();
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error("이 브라우저는 마이크를 지원하지 않습니다. HTTPS로 접속해 보세요.");
    }
    if (location.protocol !== "https:" && location.hostname !== "localhost" && location.hostname !== "127.0.0.1") {
      // 일부 모바일은 HTTP LAN에서 마이크 차단
      log("경고: HTTP에서는 모바일 마이크가 막힐 수 있습니다. HTTPS로 서버를 켜 주세요.");
    }
    mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
    const Ctx = window.AudioContext || window.webkitAudioContext;
    audioCtx = new Ctx();
    source = audioCtx.createMediaStreamSource(mediaStream);
    processor = audioCtx.createScriptProcessor(4096, 1, 1);
    processor.onaudioprocess = (e) => {
      if (!recording || !ws || ws.readyState !== WebSocket.OPEN) return;
      const input = e.inputBuffer.getChannelData(0);
      let sum = 0;
      for (let i = 0; i < input.length; i++) sum += input[i] * input[i];
      elLevel.style.width = `${Math.min(100, Math.floor(Math.sqrt(sum / input.length) * 400))}%`;
      ws.send(floatTo16BitPCM(downsample(input, audioCtx.sampleRate, TARGET_RATE)));
    };
    source.connect(processor);
    const mute = audioCtx.createGain();
    mute.gain.value = 0;
    processor.connect(mute);
    mute.connect(audioCtx.destination);
    await audioCtx.resume();
  }

  function releaseAudio() {
    try {
      processor?.disconnect();
      source?.disconnect();
      mediaStream?.getTracks().forEach((t) => t.stop());
      audioCtx?.close();
    } catch {
      /* ignore */
    }
    processor = null;
    source = null;
    mediaStream = null;
    audioCtx = null;
  }

  async function startCall() {
    if (inCall) return;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      log("서버 WebSocket이 아직 연결되지 않았습니다.");
      return;
    }
    elCallBtn.disabled = true;
    try {
      await ensureAudio();
      // iOS TTS 자동재생 잠금 해제용 무음
      try {
        elAnswerAudio.src = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAESsAACJWAAACABAAZGF0YQAAAAA=";
        await elAnswerAudio.play();
        elAnswerAudio.pause();
      } catch {
        /* ignore */
      }
      inCall = true;
      busy = false;
      recording = false;
      elPreCall.hidden = true;
      elInCall.hidden = false;
      setCallState("통화중", "ok");
      setStatus("idle");
      startTimer();
      await requestWakeLock();
      updateTalkUi();
      log("통화 연결됨");
    } catch (err) {
      log(`통화 연결 실패: ${err.message || err}`);
      setCallState("실패", "hot");
      alert(
        "마이크를 사용할 수 없습니다.\n\n" +
          "1) HTTPS로 접속했는지 확인\n" +
          "2) 브라우저 마이크 권한 허용\n" +
          "3) PC와 같은 Wi‑Fi인지 확인"
      );
    } finally {
      elCallBtn.disabled = false;
    }
  }

  function endCall(userAction = true) {
    if (recording && ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "stop" }));
    }
    recording = false;
    busy = false;
    inCall = false;
    elPreCall.hidden = false;
    elInCall.hidden = true;
    elLevel.style.width = "0%";
    stopTimer();
    releaseWakeLock();
    releaseAudio();
    setCallState("대기");
    setStatus("idle");
    updateTalkUi();
    if (userAction) log("통화 종료");
  }

  async function toggleTalk() {
    if (!inCall || busy) return;
    if (!recording) {
      try {
        await ensureAudio();
        if (audioCtx.state === "suspended") await audioCtx.resume();
        recording = true;
        elLevel.style.width = "0%";
        ws.send(JSON.stringify({ type: "start" }));
        updateTalkUi();
      } catch (err) {
        log(`마이크 오류: ${err.message || err}`);
      }
    } else {
      recording = false;
      elLevel.style.width = "0%";
      busy = true;
      updateTalkUi();
      if (ws?.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "stop" }));
      }
    }
  }

  elCallBtn.addEventListener("click", startCall);
  elHangBtn.addEventListener("click", () => endCall(true));
  elTalk.addEventListener("click", (e) => {
    e.preventDefault();
    toggleTalk();
  });

  async function showPipelineResult(data, label) {
    if (!data.ok) {
      log(`${label} 실패: ${data.error || "unknown"}`);
      setStatus("idle");
      return;
    }
    elTranscript.textContent = data.text || data.transcript || "(인식된 내용 없음)";
    log(`${label} STT: ${elTranscript.textContent}`);
    if (data.audio_url) {
      elAudio.style.display = "block";
      elAudio.src = `${data.audio_url}?t=${Date.now()}`;
    }
    showAnswer(data.answer, data.contexts, data.rag_mode, data.tts_url, data.tts_engine);
    if (data.answer) log(`${label} RAG: ${data.answer}`);
    setStatus("idle");
  }

  elFile.addEventListener("change", async () => {
    const file = elFile.files && elFile.files[0];
    if (!file) return;
    setStatus("transcribing", "warn");
    const body = new FormData();
    body.append("file", file);
    try {
      const res = await fetch("/api/stt/upload", { method: "POST", body });
      await showPipelineResult(await res.json(), "파일");
    } catch (err) {
      log(`업로드 오류: ${err.message || err}`);
      setStatus("idle");
    } finally {
      elFile.value = "";
    }
  });

  elDemo.addEventListener("click", async () => {
    elDemo.disabled = true;
    setStatus("transcribing", "warn");
    const body = new FormData();
    body.append("text", "주차는 어떻게 하나요?");
    try {
      const res = await fetch("/api/stt/demo", { method: "POST", body });
      await showPipelineResult(await res.json(), "데모");
    } catch (err) {
      log(`데모 오류: ${err.message || err}`);
      setStatus("idle");
    } finally {
      elDemo.disabled = false;
    }
  });

  async function askText() {
    const q = (elAskInput.value || "").trim();
    if (!q) return;
    elAskBtn.disabled = true;
    setStatus("answering", "warn");
    elTranscript.textContent = q;
    const body = new FormData();
    body.append("question", q);
    try {
      const res = await fetch("/api/ask", { method: "POST", body });
      const data = await res.json();
      showAnswer(data.answer, data.contexts, data.mode || data.rag_mode, data.tts_url, data.tts_engine);
      log(`RAG: ${data.answer}`);
    } catch (err) {
      log(`질문 오류: ${err.message || err}`);
    } finally {
      elAskBtn.disabled = false;
      setStatus("idle");
    }
  }

  elAskBtn.addEventListener("click", askText);
  elAskInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") askText();
  });

  async function loadAccessHint() {
    try {
      const res = await fetch("/api/access");
      const data = await res.json();
      const https = data.https;
      const urls = (data.urls || []).join("\n");
      elAccessHint.textContent = https
        ? `모바일: 아래 HTTPS 주소로 접속 (인증서 경고는 고급 → 계속)\n${urls}`
        : `모바일 마이크는 HTTPS가 필요합니다. PC에서 python voip_server.py --https 로 실행하세요.\n현재: ${location.origin}`;
    } catch {
      elAccessHint.textContent =
        location.protocol === "https:"
          ? `접속 주소: ${location.origin}`
          : "모바일 마이크용으로 PC에서 python voip_server.py --https 실행을 권장합니다.";
    }
  }

  document.addEventListener("visibilitychange", async () => {
    if (document.visibilityState === "visible" && inCall) {
      await requestWakeLock();
      if (audioCtx?.state === "suspended") await audioCtx.resume();
    }
  });

  elCallBtn.disabled = true;
  loadAccessHint();
  connectWs();
})();
