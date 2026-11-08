/* SkinSync AI assistant controller.
 *
 * Voice mode talks directly to the Gemini Live API with a short-lived token
 * issued by Django. Text mode posts messages to Django, which calls Gemini on
 * the server. The Gemini API key never reaches this file.
 */
(function () {
  "use strict";

  var configNode = document.getElementById("assistant-config");
  if (!configNode) {
    return;
  }

  var config;
  try {
    config = JSON.parse(configNode.textContent || "{}");
  } catch (error) {
    return;
  }

  var INPUT_RATE = 16000;
  var OUTPUT_RATE = 24000;
  var CAPTURE_BUFFER = 2048;

  var state = {
    runId: 0,
    mode: null,
    sessionId: null,
    active: false,
    starting: false,
    finishing: false,
    textSending: false,
    timeUp: false,
    muted: false,
    ready: false,
    ws: null,
    userEnded: false,
    micStream: null,
    captureCtx: null,
    captureSource: null,
    captureProcessor: null,
    captureSink: null,
    playbackCtx: null,
    playbackGain: null,
    playbackTime: 0,
    activeSources: [],
    speakTimer: null,
    speaking: false,
    maxSeconds: 0,
    remaining: 0,
    timerId: null,
    conversation: [],
    pendingUser: null,
    pendingAssistant: null
  };

  var els = {
    setupPanel: document.getElementById("setup-panel"),
    startBtn: document.getElementById("start-btn"),
    setupError: document.getElementById("setup-error"),
    setupErrorText: document.getElementById("setup-error-text"),
    conversationPanel: document.getElementById("conversation-panel"),
    statusDot: document.getElementById("status-dot"),
    statusText: document.getElementById("status-text"),
    modeLabel: document.getElementById("mode-label"),
    timer: document.getElementById("timer"),
    timerText: document.getElementById("timer-text"),
    muteBtn: document.getElementById("mute-btn"),
    orb: document.getElementById("assistant-orb"),
    liveCaption: document.getElementById("live-caption"),
    liveSubcaption: document.getElementById("live-subcaption"),
    transcript: document.getElementById("transcript"),
    textForm: document.getElementById("text-form"),
    textInput: document.getElementById("text-input"),
    sendBtn: document.getElementById("send-btn"),
    typing: document.getElementById("typing-indicator"),
    conversationError: document.getElementById("conversation-error"),
    conversationErrorText: document.getElementById("conversation-error-text"),
    resultsPanel: document.getElementById("results-panel"),
    resultsContent: document.getElementById("results-content"),
    analysisLink: document.getElementById("analysis-link")
  };

  /* ---------------------------------------------------------------- utils */

  function make(tag, className, text) {
    var node = document.createElement(tag);
    if (className) {
      node.className = className;
    }
    if (text !== undefined && text !== null) {
      node.textContent = String(text);
    }
    return node;
  }

  function csrfToken() {
    var input = document.querySelector("input[name=csrfmiddlewaretoken]");
    if (input && input.value) {
      return input.value;
    }
    var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function postJson(url, payload) {
    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken(),
        "X-Requested-With": "XMLHttpRequest"
      },
      body: JSON.stringify(payload || {})
    }).then(function (response) {
      return response
        .json()
        .catch(function () {
          return {};
        })
        .then(function (data) {
          if (!response.ok) {
            var error = new Error(
              (data && data.error) || "The request could not be completed (" + response.status + ")."
            );
            error.status = response.status;
            error.retryable = Boolean(data && data.retryable);
            throw error;
          }
          return data;
        });
    }).catch(function (error) {
      if (!error.status && error && error.name === "TypeError") {
        throw new Error("Could not reach the SkinSync server. Check your connection and try again.");
      }
      throw error;
    });
  }

  function isPlainObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function labelize(value) {
    var text = String(value || "").trim();
    if (!text) {
      return "";
    }
    return text.charAt(0).toUpperCase() + text.slice(1).toLowerCase();
  }

  function setStatus(text, variant) {
    if (els.statusText) {
      els.statusText.textContent = text;
    }
    if (els.statusDot) {
      els.statusDot.className = "assistant-status-dot" + (variant ? " is-" + variant : "");
    }
  }

  function setCaption(caption, subcaption) {
    if (els.liveCaption && caption !== undefined) {
      els.liveCaption.textContent = caption;
    }
    if (els.liveSubcaption && subcaption !== undefined) {
      els.liveSubcaption.textContent = subcaption;
    }
  }

  function setOrb(mode) {
    if (!els.orb) {
      return;
    }
    els.orb.className = "assistant-orb";
    if (mode === "listening" || mode === "speaking" || mode === "off") {
      els.orb.classList.add("is-" + mode);
    }
  }

  function showSetupError(message) {
    if (!els.setupError) {
      return;
    }
    els.setupErrorText.textContent = message;
    els.setupError.hidden = false;
  }

  function clearSetupError() {
    if (els.setupError) {
      els.setupError.hidden = true;
    }
  }

  function showConversationError(message) {
    if (!els.conversationError) {
      return;
    }
    els.conversationErrorText.textContent = message;
    els.conversationError.hidden = false;
  }

  function clearConversationError() {
    if (els.conversationError) {
      els.conversationError.hidden = true;
    }
  }

  function scrollTranscript() {
    if (!els.transcript) {
      return;
    }
    els.transcript.scrollTop = els.transcript.scrollHeight;
  }

  function formatTime(totalSeconds) {
    var seconds = Math.max(0, Math.floor(totalSeconds));
    var minutes = Math.floor(seconds / 60);
    var rest = seconds % 60;
    return minutes + ":" + (rest < 10 ? "0" : "") + rest;
  }

  function durationSeconds(value) {
    if (typeof value === "number") {
      return value;
    }
    var match = /([\d.]+)\s*s?/i.exec(String(value || ""));
    return match ? parseFloat(match[1]) : 0;
  }

  function resample(input, sourceRate, targetRate) {
    if (!input || !input.length || sourceRate === targetRate) {
      return input || new Float32Array(0);
    }
    var ratio = sourceRate / targetRate;
    var length = Math.max(1, Math.floor(input.length / ratio));
    var output = new Float32Array(length);
    for (var i = 0; i < length; i += 1) {
      var position = i * ratio;
      var index = Math.floor(position);
      var fraction = position - index;
      var first = input[index] || 0;
      var second = input[index + 1];
      if (second === undefined) {
        second = first;
      }
      output[i] = first + (second - first) * fraction;
    }
    return output;
  }

  function floatTo16BitPcm(input) {
    var output = new Int16Array(input.length);
    for (var i = 0; i < input.length; i += 1) {
      var sample = Math.max(-1, Math.min(1, input[i]));
      output[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
    }
    return output;
  }

  function bytesToBase64(bytes) {
    var binary = "";
    var chunk = 0x8000;
    for (var i = 0; i < bytes.length; i += chunk) {
      binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
    }
    return window.btoa(binary);
  }

  function base64ToBytes(value) {
    var binary = window.atob(value);
    var bytes = new Uint8Array(binary.length);
    for (var i = 0; i < binary.length; i += 1) {
      bytes[i] = binary.charCodeAt(i);
    }
    return bytes;
  }

  function stripAssessmentMarker(text) {
    return String(text || "").replace(/\[\[\s*ASSESSMENT_READY\s*\]\]/gi, "").trim();
  }

  /* ------------------------------------------------------------- messages */

  function addMessage(role, text, options) {
    options = options || {};
    var wrapper = make("div", "assistant-msg assistant-msg-" + role);
    if (options.live) {
      wrapper.classList.add("assistant-msg-live");
    }
    var roleLabel = role === "user" ? "You" : role === "assistant" ? "SkinSync AI" : "Notice";
    wrapper.appendChild(make("span", "assistant-msg-role", roleLabel));
    var bubble = make("div", "assistant-msg-bubble", text || "");
    wrapper.appendChild(bubble);
    if (els.transcript) {
      els.transcript.appendChild(wrapper);
      scrollTranscript();
    }
    return { wrapper: wrapper, bubble: bubble };
  }

  function addSystemMessage(text) {
    addMessage("system", text);
  }

  function commitPendingUser() {
    if (!state.pendingUser) {
      return;
    }
    var text = state.pendingUser.bubble.textContent.trim();
    state.pendingUser.wrapper.classList.remove("assistant-msg-live");
    if (text) {
      state.conversation.push({ role: "user", text: text });
    }
    state.pendingUser = null;
  }

  function commitPendingAssistant() {
    if (!state.pendingAssistant) {
      return;
    }
    var text = stripAssessmentMarker(state.pendingAssistant.bubble.textContent);
    state.pendingAssistant.bubble.textContent = text;
    state.pendingAssistant.wrapper.classList.remove("assistant-msg-live");
    if (text) {
      state.conversation.push({ role: "assistant", text: text });
    }
    state.pendingAssistant = null;
  }

  function appendInputTranscription(text) {
    if (!text) {
      return;
    }
    if (!state.pendingUser) {
      state.pendingUser = addMessage("user", "", { live: true });
      // Input transcription is not guaranteed to arrive before the model's
      // output, so keep the displayed order user-then-assistant.
      if (state.pendingAssistant && els.transcript) {
        try {
          els.transcript.insertBefore(state.pendingUser.wrapper, state.pendingAssistant.wrapper);
        } catch (error) {
          /* wrapper was already moved */
        }
      }
    }
    state.pendingUser.bubble.textContent += text;
    scrollTranscript();
    if (!state.speaking) {
      setStatus("Listening\u2026", "live");
    }
  }

  function appendOutputTranscription(text) {
    if (!text) {
      return;
    }
    if (!state.pendingAssistant) {
      state.pendingAssistant = addMessage("assistant", "", { live: true });
    }
    state.pendingAssistant.bubble.textContent += text;
    scrollTranscript();
  }

  /* --------------------------------------------------------------- audio */

  function ensurePlaybackContext() {
    if (!state.playbackCtx) {
      var Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) {
        throw new Error("This browser does not support audio playback.");
      }
      try {
        state.playbackCtx = new Ctx({ sampleRate: OUTPUT_RATE });
      } catch (error) {
        state.playbackCtx = new Ctx();
      }
      state.playbackGain = state.playbackCtx.createGain();
      state.playbackGain.gain.value = 1;
      state.playbackGain.connect(state.playbackCtx.destination);
      state.playbackTime = 0;
    }
    if (state.playbackCtx.state === "suspended") {
      state.playbackCtx.resume().catch(function () {});
    }
    return state.playbackCtx;
  }

  function markSpeaking() {
    state.speaking = true;
    setOrb("speaking");
    setStatus("SkinSync AI is speaking", "speaking");
    if (state.speakTimer) {
      window.clearTimeout(state.speakTimer);
    }
    var playbackCtx = state.playbackCtx;
    var delay = 900;
    if (playbackCtx) {
      delay = Math.max(700, (state.playbackTime - playbackCtx.currentTime + 0.25) * 1000);
    }
    state.speakTimer = window.setTimeout(function () {
      state.speaking = false;
      if (state.active && state.ws && state.ws.readyState === WebSocket.OPEN) {
        showListening();
      }
    }, delay);
  }

  function playAudioChunk(base64, mimeType) {
    if (!base64) {
      return;
    }
    var rate = OUTPUT_RATE;
    var match = /rate=(\d+)/i.exec(mimeType || "");
    if (match) {
      rate = parseInt(match[1], 10) || OUTPUT_RATE;
    }

    var bytes;
    try {
      bytes = base64ToBytes(base64);
    } catch (error) {
      return;
    }
    if (bytes.length < 2) {
      return;
    }

    var ctx = ensurePlaybackContext();
    var sampleCount = Math.floor(bytes.length / 2);
    var buffer = ctx.createBuffer(1, sampleCount, rate);
    var channel = buffer.getChannelData(0);
    var view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    for (var i = 0; i < sampleCount; i += 1) {
      channel[i] = view.getInt16(i * 2, true) / 32768;
    }

    var source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(state.playbackGain);

    var now = ctx.currentTime;
    if (state.playbackTime < now + 0.03) {
      state.playbackTime = now + 0.03;
    }
    source.start(state.playbackTime);
    state.playbackTime += buffer.duration;
    state.activeSources.push(source);
    source.onended = function () {
      var index = state.activeSources.indexOf(source);
      if (index !== -1) {
        state.activeSources.splice(index, 1);
      }
    };
    markSpeaking();
  }

  function stopPlayback() {
    if (state.speakTimer) {
      window.clearTimeout(state.speakTimer);
      state.speakTimer = null;
    }
    state.activeSources.forEach(function (source) {
      try {
        source.stop();
      } catch (error) {
        /* already stopped */
      }
      try {
        source.disconnect();
      } catch (error) {
        /* already disconnected */
      }
    });
    state.activeSources = [];
    if (state.playbackCtx) {
      state.playbackTime = state.playbackCtx.currentTime;
    }
    state.speaking = false;
  }

  function disposePlayback() {
    stopPlayback();
    if (state.playbackCtx) {
      try {
        state.playbackCtx.close();
      } catch (error) {
        /* already closed */
      }
      state.playbackCtx = null;
      state.playbackGain = null;
    }
    state.playbackTime = 0;
  }

  function showListening() {
    if (!state.active || state.finishing) {
      return;
    }
    if (state.muted) {
      setStatus("Microphone muted", "warning");
      setOrb("off");
      return;
    }
    state.speaking = false;
    setStatus("Listening\u2026", "live");
    setOrb("listening");
    setCaption("Go ahead \u2014 I'm listening.", "Speak naturally, and ask anything about your skin.");
  }

  /* ----------------------------------------------------------- microphone */

  function microphoneErrorMessage(error) {
    var name = error && error.name ? error.name : "";
    if (name === "NotAllowedError" || name === "PermissionDeniedError") {
      return "Microphone access was blocked. Allow microphone access in your browser settings, or choose text conversation instead.";
    }
    if (name === "NotFoundError" || name === "DevicesNotFoundError") {
      return "No microphone was found. Connect a microphone, or choose text conversation instead.";
    }
    if (name === "NotReadableError" || name === "TrackStartError") {
      return "Your microphone is already in use by another app. Close the other app, or choose text conversation instead.";
    }
    if (name === "SecurityError") {
      return "Microphone access requires a secure connection. Open SkinSync over HTTPS or on localhost.";
    }
    return (error && error.message) || "The microphone could not be started. Please try again or choose text conversation.";
  }

  function startMicrophone() {
    if (!window.isSecureContext) {
      return Promise.reject(new Error("Microphone access requires a secure connection. Open SkinSync over HTTPS or on localhost."));
    }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      return Promise.reject(new Error("This browser does not support microphone input. Please use a recent browser or choose text conversation."));
    }
    var Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) {
      return Promise.reject(new Error("This browser does not support audio processing. Please choose text conversation."));
    }

    return navigator.mediaDevices
      .getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      })
      .then(function (stream) {
        state.micStream = stream;
        var ctx = new Ctx();
        state.captureCtx = ctx;
        return ctx.resume().catch(function () {}).then(function () {
          state.captureSource = ctx.createMediaStreamSource(stream);
          var processor = ctx.createScriptProcessor(CAPTURE_BUFFER, 1, 1);
          state.captureProcessor = processor;
          var sink = ctx.createGain();
          sink.gain.value = 0;
          state.captureSink = sink;

          processor.onaudioprocess = function (event) {
            if (!state.active || state.muted || state.finishing) {
              return;
            }
            if (!state.ws || state.ws.readyState !== WebSocket.OPEN || !state.ready) {
              return;
            }
            var input = event.inputBuffer.getChannelData(0);
            var resampled = resample(input, ctx.sampleRate, INPUT_RATE);
            var pcm = floatTo16BitPcm(resampled);
            if (!pcm.length) {
              return;
            }
            var bytes = new Uint8Array(pcm.buffer);
            try {
              state.ws.send(
                JSON.stringify({
                  realtimeInput: {
                    audio: {
                      mimeType: "audio/pcm;rate=" + INPUT_RATE,
                      data: bytesToBase64(bytes)
                    }
                  }
                })
              );
            } catch (error) {
              /* The socket closed between checks. */
            }
          };

          state.captureSource.connect(processor);
          processor.connect(sink);
          sink.connect(ctx.destination);
        });
      })
      .catch(function (error) {
        stopMicrophone();
        throw error;
      });
  }

  function stopMicrophone() {
    if (state.captureProcessor) {
      state.captureProcessor.onaudioprocess = null;
      try {
        state.captureProcessor.disconnect();
      } catch (error) {
        /* already disconnected */
      }
      state.captureProcessor = null;
    }
    if (state.captureSource) {
      try {
        state.captureSource.disconnect();
      } catch (error) {
        /* already disconnected */
      }
      state.captureSource = null;
    }
    if (state.captureSink) {
      try {
        state.captureSink.disconnect();
      } catch (error) {
        /* already disconnected */
      }
      state.captureSink = null;
    }
    if (state.captureCtx) {
      try {
        state.captureCtx.close();
      } catch (error) {
        /* already closed */
      }
      state.captureCtx = null;
    }
    if (state.micStream) {
      state.micStream.getTracks().forEach(function (track) {
        try {
          track.stop();
        } catch (error) {
          /* already stopped */
        }
      });
      state.micStream = null;
    }
    state.muted = false;
    updateMuteButton();
  }

  function updateMuteButton() {
    if (!els.muteBtn) {
      return;
    }
    els.muteBtn.classList.toggle("is-muted", state.muted);
    els.muteBtn.setAttribute("aria-pressed", state.muted ? "true" : "false");
    els.muteBtn.setAttribute("title", state.muted ? "Unmute microphone" : "Mute microphone");
    var icon = els.muteBtn.querySelector("i");
    if (icon) {
      icon.className = state.muted ? "fa-solid fa-microphone-slash" : "fa-solid fa-microphone";
    }
    var label = els.muteBtn.querySelector("span");
    if (label) {
      label.textContent = state.muted ? "Unmute microphone" : "Mute microphone";
    }
  }

  function toggleMute() {
    if (!state.micStream || state.mode !== "voice" || state.timeUp) {
      return;
    }
    state.muted = !state.muted;
    state.micStream.getAudioTracks().forEach(function (track) {
      track.enabled = !state.muted;
    });
    updateMuteButton();
    if (state.muted) {
      setStatus("Microphone muted", "warning");
      setOrb("off");
      setCaption("Microphone muted", "Unmute whenever you're ready to keep talking.");
      if (state.ws && state.ws.readyState === WebSocket.OPEN && state.ready) {
        try {
          state.ws.send(JSON.stringify({ realtimeInput: { audioStreamEnd: true } }));
        } catch (error) {
          /* socket closed */
        }
      }
    } else {
      showListening();
    }
  }

  /* ------------------------------------------------------------- live API */

  function websocketUrl(wsUrl, token) {
    if (!wsUrl) {
      return "";
    }
    var separator = wsUrl.indexOf("?") === -1 ? "?" : "&";
    return wsUrl + separator + "access_token=" + encodeURIComponent(token || "");
  }

  function buildSetupPayload(data) {
    var model = String(data.model || config.liveModel || "").replace(/^models\//, "");
    var voice = String(data.voice || "").trim();
    var generationConfig = { responseModalities: ["AUDIO"] };
    if (voice) {
      generationConfig.speechConfig = {
        voiceConfig: {
          prebuiltVoiceConfig: { voiceName: voice }
        }
      };
    }
    var payload = {
      setup: {
        model: "models/" + model,
        generationConfig: generationConfig,
        inputAudioTranscription: {},
        outputAudioTranscription: {}
      }
    };
    if (data.system_instruction) {
      payload.setup.systemInstruction = { parts: [{ text: data.system_instruction }] };
    }
    return payload;
  }

  function sendKickoff() {
    if (!state.ws || state.ws.readyState !== WebSocket.OPEN) {
      return;
    }
    try {
      state.ws.send(
        JSON.stringify({
          clientContent: {
            turns: [
              {
                role: "user",
                parts: [
                  {
                    text: "Hello, I'm ready to begin. Please introduce yourself briefly and let me know how you can help with my skin."
                  }
                ]
              }
            ],
            turnComplete: true
          }
        })
      );
    } catch (error) {
      showConversationError(
        "The opening message could not be sent. Please try again."
      );
    }
  }

  function connectVoiceSocket(data) {
    return new Promise(function (resolve, reject) {
      var url = websocketUrl(data.ws_url, data.token);
      if (!url) {
        reject(new Error("The voice session did not include a connection address. Please try again."));
        return;
      }

      var socket;
      try {
        socket = new WebSocket(url);
      } catch (error) {
        reject(new Error("The voice connection could not be opened. Please try again."));
        return;
      }

      state.ws = socket;
      socket.binaryType = "arraybuffer";
      var settled = false;
      var timeout = window.setTimeout(function () {
        if (settled) {
          return;
        }
        settled = true;
        try {
          socket.close();
        } catch (error) {
          /* already closing */
        }
        reject(new Error("The voice connection timed out. Check your internet connection and try again."));
      }, 20000);

      socket.onopen = function () {
        try {
          socket.send(JSON.stringify(buildSetupPayload(data)));
        } catch (error) {
          if (!settled) {
            settled = true;
            window.clearTimeout(timeout);
            reject(new Error("The voice session could not be started. Please try again."));
          }
        }
      };

      socket.onmessage = function (event) {
        if (state.ws !== socket) {
          return;
        }
        var raw = event.data;
        var handleText = function (text) {
          if (!text) {
            return;
          }
          var message;
          try {
            message = JSON.parse(text);
          } catch (error) {
            return;
          }
          if (message.setupComplete) {
            if (!settled) {
              settled = true;
              window.clearTimeout(timeout);
              resolve();
            }
            handleSetupComplete();
            return;
          }
          try {
            handleServerMessage(message);
          } catch (error) {
            showConversationError(
              "Part of the voice response could not be handled. Please try again."
            );
          }
        };

        if (typeof raw === "string") {
          handleText(raw);
        } else if (raw instanceof ArrayBuffer) {
          handleText(new TextDecoder("utf-8").decode(new Uint8Array(raw)));
        } else if (raw && typeof raw.text === "function") {
          raw
            .text()
            .then(handleText)
            .catch(function () {});
        }
      };

      socket.onerror = function () {
        if (state.ws !== socket) {
          return;
        }
        if (settled) {
          return;
        }
        settled = true;
        window.clearTimeout(timeout);
        reject(new Error("Could not connect to the voice service. Check your internet connection and try again."));
      };

      socket.onclose = function (event) {
        window.clearTimeout(timeout);
        state.ready = false;
        stopPlayback();
        if (!settled) {
          settled = true;
          reject(new Error("The voice connection closed before it was ready. Please try again."));
          return;
        }
        if (state.ws !== socket) {
          return;
        }
        handleSocketClose(event);
      };
    });
  }

  function handleSetupComplete() {
    state.ready = true;
    state.muted = false;
    updateMuteButton();
    if (els.muteBtn) {
      els.muteBtn.hidden = false;
    }
    showListening();
    sendKickoff();
  }

  function handleSocketClose(event) {
    state.ready = false;
    stopPlayback();
    stopMicrophone();
    if (state.userEnded || state.finishing || !state.active) {
      return;
    }
    var detail = event && event.reason ? " (" + event.reason + ")" : "";
    stopTimer();
    showConversationError(
      "The voice connection ended unexpectedly" + detail + ". Refresh the page to start a new conversation."
    );
    setStatus("Disconnected", "error");
    setOrb("off");
    setCaption("Connection lost", "Refresh the page to start a new conversation.");
  }

  function handleServerMessage(message) {
    if (!message || typeof message !== "object") {
      return;
    }
    if (state.finishing || state.userEnded) {
      return;
    }

    if (message.error) {
      var detail = message.error.message || "";
      showConversationError(
        detail
          ? "Gemini reported a problem: " + detail
          : "Gemini reported a problem with the voice session. Please refresh the page and try again."
      );
      setStatus("Connection problem", "error");
      setOrb("off");
      return;
    }

    if (message.goAway) {
      var seconds = durationSeconds(message.goAway.timeLeft);
      addSystemMessage(
        "The voice session is about to close" +
          (seconds ? " in about " + Math.max(1, Math.round(seconds)) + " seconds" : "") +
          "."
      );
      return;
    }

    var content = message.serverContent;
    if (!content) {
      return;
    }

    if (content.interrupted) {
      stopPlayback();
      commitPendingAssistant();
      showListening();
    }

    if (content.inputTranscription) {
      if (content.inputTranscription.text) {
        appendInputTranscription(content.inputTranscription.text);
      }
    }

    if (content.outputTranscription) {
      if (content.outputTranscription.text) {
        appendOutputTranscription(content.outputTranscription.text);
      }
    }

    if (content.modelTurn && Array.isArray(content.modelTurn.parts)) {
      content.modelTurn.parts.forEach(function (part) {
        if (!part || part.thought) {
          return;
        }
        var inline = part.inlineData || part.inline_data;
        if (inline && inline.data) {
          try {
            playAudioChunk(inline.data, inline.mimeType || inline.mime_type);
          } catch (error) {
            /* Audio playback can fail if the browser blocks audio contexts. */
          }
        }
      });
    }

    if (content.turnComplete) {
      commitPendingUser();
      commitPendingAssistant();
      if (state.active && !state.finishing) {
        showListening();
      }
    }
  }

  function closeSocket(silent) {
    state.userEnded = true;
    var socket = state.ws;
    state.ws = null;
    state.ready = false;
    if (!socket) {
      return;
    }
    try {
      if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) {
        socket.close(1000, silent ? "Client ended" : "Conversation finished");
      }
    } catch (error) {
      /* already closed */
    }
  }

  /* --------------------------------------------------------------- timer */

  function updateTimerDisplay() {
    if (els.timerText) {
      els.timerText.textContent = formatTime(state.remaining);
    }
  }

  function startTimer(seconds) {
    window.clearInterval(state.timerId);
    state.timeUp = false;
    state.maxSeconds = Math.max(1, Number(seconds) || Number(config.maxSeconds) || 840);
    state.remaining = state.maxSeconds;
    if (els.timer) {
      els.timer.hidden = false;
    }
    updateTimerDisplay();
    state.timerId = window.setInterval(function () {
      if (!state.active) {
        return;
      }
      state.remaining -= 1;
      updateTimerDisplay();
      if (state.remaining === 60) {
        addSystemMessage("About one minute left in this voice session.");
      }
      if (state.remaining <= 0) {
        window.clearInterval(state.timerId);
        state.timerId = null;
        handleTimeUp();
      }
    }, 1000);
  }

  function stopTimer() {
    window.clearInterval(state.timerId);
    state.timerId = null;
  }

  function handleTimeUp() {
    if (!state.active) {
      return;
    }
    state.timeUp = true;
    if (state.mode === "voice") {
      state.muted = true;
      if (state.micStream) {
        state.micStream.getAudioTracks().forEach(function (track) {
          track.enabled = false;
        });
      }
      updateMuteButton();
      setOrb("off");
      setStatus("Time limit reached", "warning");
    }
    setCaption("Time limit reached", "The session has ended. Refresh the page to start a new conversation.");
    showConversationError("The session reached its time limit and has ended.");
  }

  /* ----------------------------------------------------------- UI resets */

  function prepareConversationView(mode) {
    clearSetupError();
    clearConversationError();
    if (els.setupPanel) {
      els.setupPanel.hidden = true;
    }
    if (els.resultsPanel) {
      els.resultsPanel.hidden = true;
    }
    if (els.conversationPanel) {
      els.conversationPanel.hidden = false;
    }
    if (els.transcript) {
      els.transcript.textContent = "";
    }
    if (els.modeLabel) {
      els.modeLabel.textContent = mode === "text" ? "Text" : "Voice";
    }
    if (els.textForm) {
      els.textForm.hidden = mode !== "text";
    }
    if (els.muteBtn) {
      els.muteBtn.hidden = mode !== "voice";
      els.muteBtn.classList.remove("is-muted");
      updateMuteButton();
    }
    if (els.timer) {
      els.timer.hidden = true;
    }
    if (els.typing) {
      els.typing.hidden = true;
    }
    if (els.sendBtn) {
      els.sendBtn.disabled = false;
    }
    setStatus("Connecting\u2026", "");
    setOrb("off");
    setCaption("Preparing your conversation\u2026", "SkinSync AI's greeting will appear here.");
    if (els.conversationPanel) {
      els.conversationPanel.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  function resetData() {
    state.mode = null;
    state.sessionId = null;
    state.active = false;
    state.starting = false;
    state.finishing = false;
    state.textSending = false;
    state.timeUp = false;
    state.muted = false;
    state.ready = false;
    state.ws = null;
    state.userEnded = false;
    state.maxSeconds = 0;
    state.remaining = 0;
    state.conversation = [];
    state.pendingUser = null;
    state.pendingAssistant = null;
  }

  function resetView() {
    if (els.setupPanel) {
      els.setupPanel.hidden = false;
    }
    if (els.conversationPanel) {
      els.conversationPanel.hidden = true;
    }
    if (els.resultsPanel) {
      els.resultsPanel.hidden = true;
    }
    if (els.transcript) {
      els.transcript.textContent = "";
    }
    if (els.resultsContent) {
      els.resultsContent.textContent = "";
    }
    if (els.textInput) {
      els.textInput.value = "";
    }
    if (els.textForm) {
      els.textForm.hidden = true;
    }
    if (els.typing) {
      els.typing.hidden = true;
    }
    if (els.timer) {
      els.timer.hidden = true;
    }
    if (els.muteBtn) {
      els.muteBtn.hidden = true;
      state.muted = false;
      updateMuteButton();
    }
    if (els.modeLabel) {
      els.modeLabel.textContent = "Voice";
    }
    if (els.analysisLink) {
      els.analysisLink.hidden = true;
      els.analysisLink.href = "#";
    }
    if (els.sendBtn) {
      els.sendBtn.disabled = false;
    }
    if (els.startBtn) {
      els.startBtn.disabled = !config.apiConfigured;
      var startLabel = els.startBtn.querySelector("span");
      if (startLabel) {
        startLabel.textContent = "Start Conversation";
      }
    }
    clearSetupError();
    clearConversationError();
    setStatus("Ready", "");
    setOrb("off");
    setCaption("Preparing your conversation\u2026", "SkinSync AI's greeting will appear here.");
  }

  function stopEverything() {
    state.userEnded = true;
    closeSocket(true);
    stopMicrophone();
    disposePlayback();
    stopTimer();
    state.active = false;
    state.ready = false;
    state.finishing = false;
    state.speaking = false;
  }

  function returnToSetup(message) {
    stopEverything();
    resetData();
    resetView();
    if (message) {
      showSetupError(message);
    }
  }

  /* --------------------------------------------------------------- start */

  function startConversation() {
    if (state.starting || state.active) {
      return;
    }
    if (!config.apiConfigured) {
      showSetupError(
        "Gemini is not configured. Add GEMINI_API_KEY to the project's .env file, then restart the Django server."
      );
      return;
    }

    var selected = document.querySelector('input[name="assistant-mode"]:checked');
    var mode = selected && selected.value === "text" ? "text" : "voice";

    state.runId += 1;
    var runId = state.runId;
    state.starting = true;
    state.userEnded = false;
    clearSetupError();

    if (els.startBtn) {
      els.startBtn.disabled = true;
      var label = els.startBtn.querySelector("span");
      if (label) {
        label.textContent = "Starting\u2026";
      }
    }

    // Create and unlock playback inside the click gesture so the browser's
    // autoplay policy does not block Gemini's first spoken reply.
    if (mode === "voice") {
      try {
        ensurePlaybackContext();
      } catch (error) {
        /* Text mode remains available if audio is unsupported. */
      }
    }

    prepareConversationView(mode);

    var begin = mode === "voice" ? beginVoice(runId) : beginText(runId);

    begin
      .catch(function (error) {
        if (runId !== state.runId) {
          return;
        }
        var sessionId = state.sessionId;
        var wasActive = state.active;
        returnToSetup(microphoneErrorMessage(error));
        if (sessionId && wasActive) {
          postJson(config.abandonUrl, { session_id: sessionId }).catch(function () {});
        }
      })
      .finally(function () {
        if (runId !== state.runId) {
          return;
        }
        state.starting = false;
        if (!state.active && els.startBtn) {
          els.startBtn.disabled = !config.apiConfigured;
          var startLabel = els.startBtn.querySelector("span");
          if (startLabel) {
            startLabel.textContent = "Start Conversation";
          }
        }
      });
  }

  function beginText(runId) {
    return postJson(config.sessionUrl, { mode: "text" }).then(function (data) {
      if (runId !== state.runId) {
        if (data.session_id) {
          postJson(config.abandonUrl, { session_id: data.session_id }).catch(function () {});
        }
        return;
      }
      if (!data || !data.session_id) {
        throw new Error("The conversation could not be created. Your session may have expired \u2014 refresh the page and sign in again.");
      }

      state.mode = "text";
      state.sessionId = data.session_id;
      state.active = true;
      state.maxSeconds = data.max_seconds || config.maxSeconds;

      var greeting = data.greeting || "Hi! I'm SkinSync AI. Ask me anything about your skin.";
      addMessage("assistant", greeting);
      state.conversation.push({ role: "assistant", text: greeting });

      setStatus("Waiting for your message", "live");
      setOrb("listening");
      setCaption("Your turn", "Type your question below. I'll answer anything about your skin.");
      if (els.textInput) {
        els.textInput.focus();
      }
    });
  }

  function beginVoice(runId) {
    return startMicrophone()
      .then(function () {
        if (runId !== state.runId) {
          stopMicrophone();
          return null;
        }
        setStatus("Authorising voice session\u2026", "");
        setCaption("Connecting to Gemini\u2026", "The first question will appear here.");
        return postJson(config.sessionUrl, { mode: "voice" });
      })
      .then(function (data) {
        if (!data) {
          return null;
        }
        if (runId !== state.runId) {
          if (data.session_id) {
            postJson(config.abandonUrl, { session_id: data.session_id }).catch(function () {});
          }
          return null;
        }
        if (!data.session_id || !data.token || !data.ws_url) {
          throw new Error("The voice session could not be created. Your session may have expired \u2014 refresh the page and sign in again.");
        }

        state.mode = "voice";
        state.sessionId = data.session_id;
        state.active = true;
        state.maxSeconds = data.max_seconds || config.maxSeconds;

        if (els.muteBtn) {
          els.muteBtn.hidden = false;
        }
        startTimer(state.maxSeconds);
        setCaption("Connecting to Gemini\u2026", "Allow a moment for the voice session to open.");

        return connectVoiceSocket(data).then(function () {
          if (runId !== state.runId) {
            return;
          }
          state.ready = true;
          showListening();
        });
      });
  }

  /* ----------------------------------------------------------------- text */

  function sendTextMessage(event) {
    if (event) {
      event.preventDefault();
    }
    if (state.textSending || !state.active || state.mode !== "text" || state.finishing) {
      return;
    }
    var text = els.textInput ? els.textInput.value.trim() : "";
    if (!text) {
      return;
    }

    var runId = state.runId;
    clearConversationError();
    var bubble = addMessage("user", text);
    state.conversation.push({ role: "user", text: text });
    if (els.textInput) {
      els.textInput.value = "";
    }
    state.textSending = true;
    if (els.sendBtn) {
      els.sendBtn.disabled = true;
    }
    if (els.typing) {
      els.typing.hidden = false;
    }
    setStatus("SkinSync AI is thinking\u2026", "speaking");
    setOrb("speaking");
    setCaption("SkinSync AI is thinking\u2026", "It will reply in a moment.");

    postJson(config.chatUrl, { session_id: state.sessionId, message: text })
      .then(function (data) {
        if (runId !== state.runId) {
          return;
        }
        if (!data || data.success !== true || !data.reply) {
          throw new Error("The reply could not be loaded. Your session may have expired \u2014 refresh the page and sign in again.");
        }
        var reply = data.reply;
        addMessage("assistant", reply);
        state.conversation.push({ role: "assistant", text: reply });

        setStatus("Waiting for your message", "live");
        setOrb("listening");
        setCaption("Your turn", "Type your next message below.");
      })
      .catch(function (error) {
        if (runId !== state.runId) {
          return;
        }
        if (bubble && bubble.wrapper && bubble.wrapper.parentNode) {
          bubble.wrapper.parentNode.removeChild(bubble.wrapper);
        }
        var index = state.conversation.length - 1;
        if (index >= 0 && state.conversation[index].role === "user" && state.conversation[index].text === text) {
          state.conversation.pop();
        }
        if (els.textInput) {
          els.textInput.value = text;
          els.textInput.focus();
        }
        showConversationError(
          error && error.message
            ? error.message
            : "Your message could not be sent. Check your connection and try again."
        );
        setStatus("Message not sent", "error");
        setOrb("off");
      })
      .finally(function () {
        if (runId !== state.runId) {
          return;
        }
        state.textSending = false;
        if (els.sendBtn) {
          els.sendBtn.disabled = false;
        }
        if (els.typing) {
          els.typing.hidden = true;
        }
      });
  }

  /* -------------------------------------------------------------- results */

  function resultStat(label, value) {
    var node = make("div", "assistant-result-stat");
    node.appendChild(make("span", "", label));
    node.appendChild(make("strong", "", value || "\u2014"));
    return node;
  }

  function resultCard(options) {
    var card = make("div", "assistant-result-card" + (options.wide ? " is-wide" : ""));
    var heading = make("h3");
    if (options.icon) {
      var icon = make("i", "fa-solid " + options.icon);
      heading.appendChild(icon);
    }
    heading.appendChild(document.createTextNode(options.title));
    card.appendChild(heading);

    if (options.paragraph) {
      card.appendChild(make("p", "", options.paragraph));
    }

    if (options.list && options.list.length) {
      var list = make("ul");
      options.list.forEach(function (item) {
        list.appendChild(make("li", "", item));
      });
      card.appendChild(list);
    }

    if (options.tags && options.tags.length) {
      var tags = make("div", "assistant-result-tags");
      options.tags.forEach(function (item) {
        tags.appendChild(make("span", "assistant-result-tag", item));
      });
      card.appendChild(tags);
    }

    return card;
  }

  function listOf(value) {
    if (!Array.isArray(value)) {
      return [];
    }
    return value
      .map(function (item) {
        return String(item || "").trim();
      })
      .filter(function (item) {
        return item.length > 0;
      });
  }

  function renderResults(data) {
    if (!els.resultsContent) {
      return;
    }
    var assessment = isPlainObject(data.assessment) ? data.assessment : {};
    var routine = isPlainObject(assessment.routine) ? assessment.routine : {};
    var sufficient = Boolean(assessment.information_sufficient);
    var primary = assessment.primary_skin_type_label || labelize(assessment.primary_skin_type) || "Uncertain";
    var sensitivity = assessment.sensitivity_level_label || labelize(assessment.sensitivity_level) || "Unknown";
    var observations = listOf(assessment.observations);
    var ingredients = listOf(assessment.ingredients);
    var precautions = listOf(assessment.precautions);
    var followUps = listOf(assessment.follow_up_questions);

    els.resultsContent.textContent = "";

    var hero = make("div", "assistant-result-hero");
    hero.appendChild(resultStat("Primary skin type", primary));
    hero.appendChild(resultStat("Sensitivity", sensitivity));
    els.resultsContent.appendChild(hero);

    if (!sufficient) {
      var note = make("div", "assistant-result-note");
      note.appendChild(make("i", "fa-solid fa-circle-info"));
      note.appendChild(
        make(
          "span",
          "",
          "There was not enough consistent detail for a firm estimate, so the result is marked Uncertain. Nothing has been guessed or filled in."
        )
      );
      els.resultsContent.appendChild(note);
    }

    els.resultsContent.appendChild(
      resultCard({
        title: "Summary",
        icon: "fa-circle-info",
        wide: true,
        paragraph:
          assessment.summary ||
          "No summary was returned. This is an AI-generated estimate, not a medical diagnosis."
      })
    );

    els.resultsContent.appendChild(
      resultCard({
        title: "What you shared",
        icon: "fa-list-check",
        wide: true,
        list: observations.length
          ? observations
          : ["No specific observations were recorded in this conversation."]
      })
    );

    var grid = make("div", "assistant-result-grid");
    grid.appendChild(
      resultCard({
        title: "Morning routine",
        icon: "fa-sun",
        list: listOf(routine.morning)
      })
    );
    grid.appendChild(
      resultCard({
        title: "Evening routine",
        icon: "fa-moon",
        list: listOf(routine.evening)
      })
    );
    grid.appendChild(
      resultCard({
        title: "Ingredients to look for",
        icon: "fa-flask",
        tags: ingredients
      })
    );
    grid.appendChild(
      resultCard({
        title: "Precautions",
        icon: "fa-shield-heart",
        list: precautions
      })
    );
    els.resultsContent.appendChild(grid);

    if (!sufficient && followUps.length) {
      els.resultsContent.appendChild(
        resultCard({
          title: "Questions that would sharpen the estimate",
          icon: "fa-circle-question",
          wide: true,
          list: followUps
        })
      );
    }

    els.resultsContent.appendChild(
      make(
        "p",
        "assistant-result-disclaimer",
        assessment.disclaimer || "This is an AI-generated estimate, not a medical diagnosis."
      )
    );

    if (els.analysisLink) {
      if (data.analysis_url) {
        els.analysisLink.href = data.analysis_url;
        els.analysisLink.hidden = false;
      } else {
        els.analysisLink.hidden = true;
        els.analysisLink.href = "#";
      }
    }

    if (els.conversationPanel) {
      els.conversationPanel.hidden = true;
    }
    if (els.setupPanel) {
      els.setupPanel.hidden = true;
    }
    if (els.resultsPanel) {
      els.resultsPanel.hidden = false;
      els.resultsPanel.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  /* --------------------------------------------------------------- wiring */

  if (els.startBtn) {
    els.startBtn.addEventListener("click", startConversation);
  }
  if (els.muteBtn) {
    els.muteBtn.addEventListener("click", toggleMute);
  }
  if (els.textForm) {
    els.textForm.addEventListener("submit", sendTextMessage);
  }
  if (els.textInput) {
    els.textInput.addEventListener("keydown", function (event) {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        sendTextMessage();
      }
    });
  }

  window.addEventListener("beforeunload", function () {
    state.userEnded = true;
    closeSocket(true);
    stopMicrophone();
    disposePlayback();
    stopTimer();
  });

  resetView();
})();
