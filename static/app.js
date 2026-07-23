(() => {
  const TARGET_RATE = 16000;

  const elConn = document.getElementById("conn");
  const elStatus = document.getElementById("status");
  const elTalk = document.getElementById("talk");
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

  function log(msg) {
    const li = document.createElement("li");
    const t = new Date().toLocaleTimeString();
    li.textContent = `[${t}] ${msg}`;
    elLog.prepend(li);
  }

  function setConn(text, cls) {
    elConn.textContent = text;
    elConn.className = `badge ${cls || ""}`;
  }

  function setStatus(text, cls) {
    elStatus.textContent = text;
    elStatus.className = `badge ${cls || ""}`;
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
      elAnswerAudio.play().catch(() => {});
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

  function connect() {
    ws = new WebSocket(wsUrl());
    ws.binaryType = "arraybuffer";

    ws.onopen = () => {
      setConn("연결됨", "ok");
      elTalk.disabled = false;
      log("WebSocket 연결");
    };

    ws.onclose = () => {
      setConn("끊김", "hot");
      elTalk.disabled = true;
      log("WebSocket 종료 — 3초 후 재연결");
      setTimeout(connect, 3000);
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
        setStatus("idle");
        log(data.message || "ready");
      } else if (data.type === "status") {
        const cls =
          data.status === "listening"
            ? "hot"
            : data.status === "transcribing" || data.status === "answering"
              ? "warn"
              : "";
        setStatus(data.status, cls);
      } else if (data.type === "transcript") {
        const text = data.text || "(인식된 내용 없음)";
        elTranscript.textContent = text;
        log(`STT: ${text}`);
      } else if (data.type === "answer") {
        showAnswer(data.text, data.contexts, data.rag_mode, data.tts_url, data.tts_engine);
        log(`RAG: ${data.text}`);
        if (data.tts_url) log(`TTS: ${data.tts_engine || "ok"}`);
      } else if (data.type === "error") {
        log(`오류: ${data.message}`);
      }
    };
  }

  async function ensureAudio() {
    if (audioCtx) return;
    mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
    audioCtx = new AudioContext();
    source = audioCtx.createMediaStreamSource(mediaStream);
    processor = audioCtx.createScriptProcessor(4096, 1, 1);
    processor.onaudioprocess = (e) => {
      if (!recording || !ws || ws.readyState !== WebSocket.OPEN) return;
      const input = e.inputBuffer.getChannelData(0);
      let sum = 0;
      for (let i = 0; i < input.length; i++) sum += input[i] * input[i];
      const rms = Math.sqrt(sum / input.length);
      elLevel.style.width = `${Math.min(100, Math.floor(rms * 400))}%`;
      const down = downsample(input, audioCtx.sampleRate, TARGET_RATE);
      ws.send(floatTo16BitPCM(down));
    };
    source.connect(processor);
    const mute = audioCtx.createGain();
    mute.gain.value = 0;
    processor.connect(mute);
    mute.connect(audioCtx.destination);
  }

  async function startTalk() {
    if (recording) return;
    try {
      await ensureAudio();
      if (audioCtx.state === "suspended") await audioCtx.resume();
      recording = true;
      elTalk.classList.add("recording");
      elTalk.textContent = "녹음 중…";
      ws.send(JSON.stringify({ type: "start" }));
    } catch (err) {
      log(`마이크 오류: ${err.message || err}`);
      setConn("마이크 거부", "hot");
    }
  }

  function stopTalk() {
    if (!recording) return;
    recording = false;
    elTalk.classList.remove("recording");
    elTalk.textContent = "눌러서 말하기";
    elLevel.style.width = "0%";
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "stop" }));
    }
  }

  elTalk.addEventListener("mousedown", (e) => {
    e.preventDefault();
    startTalk();
  });
  elTalk.addEventListener("mouseup", (e) => {
    e.preventDefault();
    stopTalk();
  });
  elTalk.addEventListener("mouseleave", stopTalk);
  elTalk.addEventListener("touchstart", (e) => {
    e.preventDefault();
    startTalk();
  }, { passive: false });
  elTalk.addEventListener("touchend", (e) => {
    e.preventDefault();
    stopTalk();
  });
  elTalk.addEventListener("touchcancel", stopTalk);

  async function showPipelineResult(data, label) {
    if (!data.ok) {
      log(`${label} 실패: ${data.error || "unknown"}`);
      setStatus("idle");
      return;
    }
    const text = data.text || data.transcript || "(인식된 내용 없음)";
    elTranscript.textContent = text;
    log(`${label} STT: ${text}`);
    if (data.original_text) log(`원문: ${data.original_text}`);
    if (data.audio_url) {
      elAudio.style.display = "block";
      elAudio.src = `${data.audio_url}?t=${Date.now()}`;
    }
    showAnswer(data.answer, data.contexts, data.rag_mode, data.tts_url, data.tts_engine);
    if (data.answer) log(`${label} RAG: ${data.answer}`);
    if (data.tts_url) log(`${label} TTS: ${data.tts_engine || "ok"}`);
    setStatus("idle");
  }

  elFile.addEventListener("change", async () => {
    const file = elFile.files && elFile.files[0];
    if (!file) return;
    setStatus("transcribing", "warn");
    log(`파일 업로드: ${file.name}`);
    const body = new FormData();
    body.append("file", file);
    try {
      const res = await fetch("/api/stt/upload", { method: "POST", body });
      const data = await res.json();
      await showPipelineResult(data, "파일");
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
    log("데모: 주차 문의 (TTS → STT → RAG)…");
    const body = new FormData();
    body.append("text", "주차는 어떻게 하나요?");
    try {
      const res = await fetch("/api/stt/demo", { method: "POST", body });
      const data = await res.json();
      await showPipelineResult(data, "데모");
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
    log(`텍스트 질문: ${q}`);
    const body = new FormData();
    body.append("question", q);
    try {
      const res = await fetch("/api/ask", { method: "POST", body });
      const data = await res.json();
      showAnswer(data.answer, data.contexts, data.mode || data.rag_mode, data.tts_url, data.tts_engine);
      log(`RAG: ${data.answer}`);
      if (data.tts_url) log(`TTS: ${data.tts_engine || "ok"}`);
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

  connect();
})();
