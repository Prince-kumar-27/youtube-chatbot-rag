// Runs on youtube.com. Adds an "Ask AI" button and a chat panel to video pages.
(() => {
  "use strict";
  if (window.__ytragLoaded) return;
  window.__ytragLoaded = true;

  // Languages we prefer when a video has several caption tracks
  const PREFERRED_LANGUAGES = ["en", "hi"];

  const state = {
    videoId: null,
    prepared: false, // has the backend indexed this video?
    preparing: null, // promise while indexing is in progress
    busy: false,
  };
  let host = null;
  let ui = {};

  // ---------------------------------------------------------------- page helpers
  function getVideoId() {
    const url = new URL(location.href);
    return url.pathname === "/watch" ? url.searchParams.get("v") : null;
  }

  function seekTo(seconds) {
    const video = document.querySelector("video.html5-main-video") || document.querySelector("video");
    if (!video) return;
    video.currentTime = seconds;
    if (video.paused) video.play();
  }

  function parseTime(text) {
    const parts = text.split(":").map(Number);
    return parts.reduce((total, part) => total * 60 + part, 0);
  }

  // ---------------------------------------------------------------- talking to the background worker
  function sendToBackground(type, payload) {
    return new Promise((resolve, reject) => {
      if (!chrome.runtime || !chrome.runtime.id) {
        reject(new Error("The extension was updated. Please refresh this page."));
        return;
      }
      chrome.runtime.sendMessage({ type, ...payload }, (response) => {
        if (chrome.runtime.lastError) {
          reject(new Error(chrome.runtime.lastError.message));
        } else if (!response) {
          reject(new Error("No response from the extension background worker."));
        } else if (response.ok) {
          resolve(response.data);
        } else {
          reject(new Error(response.error));
        }
      });
    });
  }

  // ---------------------------------------------------------------- reading the transcript in the browser
  // YouTube keeps changing how captions can be fetched, so we try several methods in order.
  // If all of them fail we return null and the backend tries to fetch the captions itself.
  // Open the browser console on a YouTube tab to see which method worked ("[YouTube RAG] ...").
  const log = (...args) => console.info("[YouTube RAG]", ...args);
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  async function waitFor(check, timeoutMs, stepMs = 200) {
    const end = Date.now() + timeoutMs;
    while (Date.now() < end) {
      const value = check();
      if (value) return value;
      await sleep(stepMs);
    }
    return null;
  }

  function extractJsonAfter(text, marker) {
    const at = text.indexOf(marker);
    if (at === -1) return null;
    const start = text.indexOf("{", at + marker.length);
    if (start === -1) return null;

    let depth = 0;
    let inString = false;
    let escaped = false;
    for (let i = start; i < text.length; i++) {
      const c = text[i];
      if (inString) {
        if (escaped) escaped = false;
        else if (c === "\\") escaped = true;
        else if (c === '"') inString = false;
      } else if (c === '"') {
        inString = true;
      } else if (c === "{") {
        depth++;
      } else if (c === "}") {
        depth--;
        if (depth === 0) {
          try {
            return JSON.parse(text.slice(start, i + 1));
          } catch (e) {
            return null;
          }
        }
      }
    }
    return null;
  }

  function pickCaptionTrack(tracks) {
    const language = (track) => (track.languageCode || "").split("-")[0];
    // Prefer human-written captions over auto-generated ones ("asr")
    for (const wantHuman of [true, false]) {
      for (const lang of PREFERRED_LANGUAGES) {
        const hit = tracks.find((t) => language(t) === lang && (t.kind !== "asr") === wantHuman);
        if (hit) return hit;
      }
    }
    return tracks[0];
  }

  function parseJson3(body) {
    const segments = [];
    for (const event of JSON.parse(body).events || []) {
      if (!event.segs) continue;
      const text = event.segs.map((s) => s.utf8 || "").join("").replace(/\s+/g, " ").trim();
      if (text) segments.push({ text, start: (event.tStartMs || 0) / 1000 });
    }
    return segments.length ? segments : null;
  }

  async function fetchJson3(url) {
    const target = new URL(url, location.origin);
    target.searchParams.set("fmt", "json3");
    const response = await fetch(target.toString());
    if (!response.ok) return null;
    const body = await response.text();
    return body ? parseJson3(body) : null; // an empty body means YouTube wants a token for this URL
  }

  // Method 1: the caption tracks listed in the watch page
  async function fromCaptionTracks(videoId) {
    const page = await fetch(`/watch?v=${encodeURIComponent(videoId)}`);
    if (!page.ok) return null;
    const player = extractJsonAfter(await page.text(), "ytInitialPlayerResponse = ");
    const renderer = player && player.captions && player.captions.playerCaptionsTracklistRenderer;
    const tracks = renderer && renderer.captionTracks;
    if (!tracks || !tracks.length) return null;
    return fetchJson3(pickCaptionTrack(tracks).baseUrl);
  }

  // Method 2: reuse the caption request the player itself made (it carries YouTube's own token)
  async function fromPlayerRequest(videoId) {
    if (!performance.getEntriesByType) return null;
    const requests = performance
      .getEntriesByType("resource")
      .filter((entry) => entry.name.includes("/api/timedtext") && entry.name.includes("pot="));
    for (let i = requests.length - 1; i >= 0; i--) {
      const url = new URL(requests[i].name);
      if (url.searchParams.get("v") !== videoId) continue;
      const segments = await fetchJson3(url.toString());
      if (segments) return segments;
    }
    return null;
  }

  // Method 3: open YouTube's own "Show transcript" panel and read what it shows
  const TIME_ONLY = /^(\d{1,2}:)?\d{1,2}:\d{2}$/;
  const TRANSCRIPT_ROW = "ytd-transcript-segment-renderer, transcript-segment-view-model";
  const TRANSCRIPT_BUTTONS = [
    "ytd-video-description-transcript-section-renderer button",
    'button[aria-label="Show transcript"]',
  ];

  function readTranscriptPanel() {
    const segments = [];
    for (const row of document.querySelectorAll(TRANSCRIPT_ROW)) {
      let time = row.querySelector(".segment-timestamp, .ytwTranscriptSegmentViewModelTimestamp");
      let text = row.querySelector(".segment-text, .yt-core-attributed-string");
      let timeText = time && time.textContent.trim();
      let bodyText = text && text.textContent.trim();
      if (!timeText || !bodyText) {
        // Layout changed again: fall back to "first line = time, the rest = text"
        const lines = (row.innerText || row.textContent || "")
          .split("\n").map((l) => l.trim()).filter(Boolean);
        timeText = lines[0];
        bodyText = lines.slice(1).join(" ");
      }
      if (timeText && bodyText && TIME_ONLY.test(timeText)) {
        segments.push({ text: bodyText.replace(/\s+/g, " "), start: parseTime(timeText) });
      }
    }
    return segments;
  }

  function closeTranscriptPanel() {
    const panel = document.querySelector(
      'ytd-engagement-panel-section-list-renderer[target-id="engagement-panel-searchable-transcript"]'
    );
    const close = panel && panel.querySelector("#visibility-button button");
    if (close) close.click();
  }

  async function fromTranscriptPanel(videoId) {
    if (getVideoId() !== videoId) return null;

    let segments = readTranscriptPanel();
    if (segments.length) return segments; // the panel is already open

    const button = TRANSCRIPT_BUTTONS.map((selector) => document.querySelector(selector)).find(Boolean);
    if (!button) return null;
    button.click();
    const first = await waitFor(() => {
      const found = readTranscriptPanel();
      return found.length ? found : null;
    }, 8000);
    await sleep(400); // let the rest of the rows finish loading
    segments = first ? readTranscriptPanel() : null;
    closeTranscriptPanel();
    return segments && segments.length ? segments : null;
  }

  async function fetchTranscriptInBrowser(videoId) {
    const methods = [
      ["caption tracks", fromCaptionTracks],
      ["player request", fromPlayerRequest],
      ["transcript panel", fromTranscriptPanel],
    ];
    for (const [name, method] of methods) {
      try {
        const segments = await method(videoId);
        if (segments && segments.length) {
          log(`transcript read via "${name}" (${segments.length} lines)`);
          return segments;
        }
        log(`"${name}" gave no transcript`);
      } catch (err) {
        log(`"${name}" failed:`, err);
      }
    }
    return null;
  }

  // ---------------------------------------------------------------- preparing the video on the backend
  function ensurePrepared() {
    if (state.prepared) return Promise.resolve();
    if (state.preparing) return state.preparing;

    const videoId = state.videoId;
    const task = (async () => {
      setStatus("Reading the video transcript…");
      const segments = await fetchTranscriptInBrowser(videoId);
      setStatus("Indexing the transcript…");
      await sendToBackground("prepare", { video_id: videoId, segments });
      if (videoId === state.videoId) state.prepared = true;
    })();

    state.preparing = task;
    const clear = () => {
      if (state.preparing === task) state.preparing = null;
    };
    task.then(clear, clear);
    return task;
  }

  async function callVideoApi(type, payload) {
    await ensurePrepared();
    const videoId = state.videoId;
    try {
      return await sendToBackground(type, { video_id: videoId, ...payload });
    } catch (err) {
      // The server restarted and forgot the video: send the transcript again, then retry once
      if (err.message === "video_not_prepared") {
        state.prepared = false;
        await ensurePrepared();
        return sendToBackground(type, { video_id: videoId, ...payload });
      }
      throw err;
    }
  }

  // ---------------------------------------------------------------- actions
  async function runAction(userText, type, payload, toAnswer) {
    if (state.busy || !state.videoId) return;
    const videoId = state.videoId;
    addMessage("user", userText);
    setBusy(true);
    try {
      const data = await callVideoApi(type, payload);
      if (videoId !== state.videoId) return; // the user moved to another video meanwhile
      const { text, sources } = toAnswer(data);
      addMessage("assistant", text, sources);
    } catch (err) {
      if (videoId === state.videoId) addMessage("error", err.message);
    } finally {
      if (videoId === state.videoId) setBusy(false);
    }
  }

  function summarize() {
    runAction("Summarize this video", "summary", {}, (d) => ({ text: d.summary }));
  }

  function ask() {
    const question = ui.input.value.trim();
    if (!question) return;
    ui.input.value = "";
    autoGrow();
    runAction(question, "ask", { question }, (d) => ({ text: d.answer, sources: d.sources }));
  }

  // ---------------------------------------------------------------- rendering (never uses innerHTML for chat text)
  function appendInline(parent, text) {
    // Supports **bold** and [mm:ss] timestamps that jump the video to that moment
    const pattern = /(\*\*[^*]+\*\*|\[\d{1,2}:\d{2}(?::\d{2})?\])/g;
    let last = 0;
    let match;
    while ((match = pattern.exec(text))) {
      if (match.index > last) parent.appendChild(document.createTextNode(text.slice(last, match.index)));
      const token = match[0];
      if (token.startsWith("**")) {
        const strong = document.createElement("strong");
        strong.textContent = token.slice(2, -2);
        parent.appendChild(strong);
      } else {
        parent.appendChild(timeButton(token.slice(1, -1)));
      }
      last = match.index + token.length;
    }
    if (last < text.length) parent.appendChild(document.createTextNode(text.slice(last)));
  }

  function timeButton(label) {
    const button = document.createElement("button");
    button.className = "ts";
    button.textContent = "▶ " + label;
    button.title = "Jump to " + label;
    button.addEventListener("click", () => seekTo(parseTime(label)));
    return button;
  }

  function renderRich(container, text) {
    let list = null;
    for (const raw of text.split("\n")) {
      const line = raw.trimEnd();
      if (!line.trim()) {
        list = null;
        continue;
      }
      const bullet = line.match(/^\s*[-*•]\s+(.*)$/);
      if (bullet) {
        if (!list) {
          list = document.createElement("ul");
          container.appendChild(list);
        }
        const item = document.createElement("li");
        appendInline(item, bullet[1]);
        list.appendChild(item);
      } else {
        list = null;
        const paragraph = document.createElement("p");
        appendInline(paragraph, line.replace(/^#+\s*/, ""));
        container.appendChild(paragraph);
      }
    }
  }

  function addMessage(role, text, sources) {
    const el = document.createElement("div");
    el.className = "msg " + role;
    if (role === "assistant") renderRich(el, text);
    else el.textContent = text;

    if (sources && sources.length) {
      const row = document.createElement("div");
      row.className = "sources";
      const label = document.createElement("span");
      label.textContent = "Sources:";
      row.appendChild(label);
      for (const source of sources) row.appendChild(timeButton(source.timestamp));
      el.appendChild(row);
    }
    ui.messages.appendChild(el);
    ui.messages.scrollTop = ui.messages.scrollHeight;
  }

  function setStatus(text) {
    if (ui.status) ui.status.textContent = text;
  }

  function setBusy(busy) {
    state.busy = busy;
    ui.send.disabled = busy;
    ui.summarize.disabled = busy;
    setStatus(busy ? "Working…" : "");
  }

  function autoGrow() {
    ui.input.style.height = "auto";
    ui.input.style.height = Math.min(ui.input.scrollHeight, 96) + "px";
  }

  function resetChat() {
    if (!ui.messages) return;
    ui.messages.textContent = "";
    setBusy(false);
    addMessage("assistant", "Hi! Click **Summarize**, or ask me anything about this video.");
  }

  // ---------------------------------------------------------------- UI (Shadow DOM keeps YouTube's CSS out)
  const CSS = `
    :host { all: initial; }
    * { box-sizing: border-box; font-family: Roboto, Arial, sans-serif; }
    .fab { position: fixed; right: 20px; bottom: 20px; z-index: 2147483000; border: 0; border-radius: 24px;
      padding: 12px 18px; font-size: 14px; font-weight: 500; color: #fff; background: #cc0000; cursor: pointer;
      box-shadow: 0 4px 14px rgba(0,0,0,.35); }
    .fab:hover { background: #a80000; }
    .panel { position: fixed; right: 20px; bottom: 76px; z-index: 2147483000; width: 380px; max-width: calc(100vw - 40px);
      height: 540px; max-height: calc(100vh - 110px); display: flex; flex-direction: column; overflow: hidden;
      background: #fff; color: #0f0f0f; border: 1px solid #ddd; border-radius: 14px; box-shadow: 0 8px 30px rgba(0,0,0,.35); }
    .panel[hidden] { display: none; }
    .panel.dark { background: #212121; color: #f1f1f1; border-color: #3a3a3a; }
    header { display: flex; align-items: center; justify-content: space-between; padding: 12px 14px;
      font-weight: 600; font-size: 15px; border-bottom: 1px solid rgba(128,128,128,.3); }
    header button { border: 0; background: transparent; color: inherit; font-size: 16px; cursor: pointer; }
    .messages { flex: 1; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 10px; }
    .msg { padding: 9px 12px; border-radius: 12px; font-size: 14px; line-height: 1.45; max-width: 92%; word-wrap: break-word; }
    .msg p { margin: 0 0 6px; } .msg p:last-child { margin-bottom: 0; }
    .msg ul { margin: 4px 0; padding-left: 18px; } .msg li { margin: 3px 0; }
    .msg.user { align-self: flex-end; background: #cc0000; color: #fff; }
    .msg.assistant { align-self: flex-start; background: rgba(128,128,128,.16); }
    .msg.error { align-self: flex-start; background: #fde7e7; color: #8a1111; }
    .panel.dark .msg.error { background: #4a1f1f; color: #ffb4b4; }
    .ts { border: 0; border-radius: 10px; padding: 1px 7px; margin: 0 1px; font-size: 12px; cursor: pointer;
      color: #065fd4; background: rgba(6,95,212,.12); }
    .panel.dark .ts { color: #7db7ff; background: rgba(125,183,255,.15); }
    .sources { margin-top: 8px; display: flex; flex-wrap: wrap; gap: 4px; align-items: center; font-size: 12px; opacity: .85; }
    .status { min-height: 18px; padding: 0 14px; font-size: 12px; opacity: .7; }
    .actions { padding: 0 12px 8px; }
    .actions button { border: 1px solid rgba(128,128,128,.5); background: transparent; color: inherit;
      border-radius: 16px; padding: 5px 12px; font-size: 13px; cursor: pointer; }
    .actions button:hover:not(:disabled) { background: rgba(128,128,128,.18); }
    .composer { display: flex; gap: 8px; align-items: flex-end; padding: 10px 12px; border-top: 1px solid rgba(128,128,128,.3); }
    textarea { flex: 1; resize: none; border: 1px solid rgba(128,128,128,.5); border-radius: 10px; padding: 8px 10px;
      font-size: 14px; background: transparent; color: inherit; max-height: 96px; outline: none; }
    textarea:focus { border-color: #065fd4; }
    .send { border: 0; border-radius: 10px; padding: 9px 14px; font-size: 14px; color: #fff; background: #cc0000; cursor: pointer; }
    button:disabled { opacity: .5; cursor: default; }
  `;

  const TEMPLATE = `
    <style>${CSS}</style>
    <button class="fab" id="fab" title="Ask AI about this video">💬 Ask AI</button>
    <section class="panel" id="panel" hidden>
      <header><span>Video Chat</span><button id="close" aria-label="Close">✕</button></header>
      <div class="messages" id="messages"></div>
      <div class="status" id="status"></div>
      <div class="actions"><button id="summarize">📝 Summarize</button></div>
      <div class="composer">
        <textarea id="input" rows="1" placeholder="Ask about this video…"></textarea>
        <button class="send" id="send">Send</button>
      </div>
    </section>
  `;

  function buildUi() {
    host = document.createElement("div");
    host.id = "ytrag-host";
    const root = host.attachShadow({ mode: "open" });
    root.innerHTML = TEMPLATE; // static template only; chat text is never inserted this way
    const $ = (id) => root.getElementById(id);
    ui = {
      fab: $("fab"), panel: $("panel"), close: $("close"), messages: $("messages"),
      status: $("status"), summarize: $("summarize"), input: $("input"), send: $("send"),
    };

    ui.fab.addEventListener("click", () => togglePanel());
    ui.close.addEventListener("click", () => togglePanel(false));
    ui.summarize.addEventListener("click", summarize);
    ui.send.addEventListener("click", ask);
    ui.input.addEventListener("input", autoGrow);
    ui.input.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        ask();
      }
    });
    // Stop typing from triggering YouTube shortcuts (space = pause, f = fullscreen, ...)
    for (const name of ["keydown", "keyup", "keypress"]) {
      ui.input.addEventListener(name, (event) => event.stopPropagation());
    }

    // A leftover button from a previous version of the extension would be dead: replace it
    const old = document.getElementById("ytrag-host");
    if (old) old.remove();
    document.documentElement.appendChild(host);
  }

  function togglePanel(open) {
    const show = typeof open === "boolean" ? open : ui.panel.hidden;
    ui.panel.hidden = !show;
    ui.panel.classList.toggle("dark", document.documentElement.hasAttribute("dark"));
    if (show) ui.input.focus();
  }

  // ---------------------------------------------------------------- YouTube is a single-page app
  function syncToPage() {
    const videoId = getVideoId();
    host.style.display = videoId ? "" : "none";
    if (videoId !== state.videoId) {
      state.videoId = videoId;
      state.prepared = false;
      state.preparing = null;
      resetChat();
    }
  }

  // The toolbar icon (see background.js) asks the page to open or close the chat panel
  if (chrome.runtime && chrome.runtime.onMessage) {
    chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
      if (!message || message.type !== "toggle-panel") return false;
      if (!state.videoId) {
        sendResponse({ ok: false, reason: "not_watch_page" });
      } else {
        togglePanel();
        sendResponse({ ok: true });
      }
      return false;
    });
  }

  buildUi();
  syncToPage();
  window.addEventListener("yt-navigate-finish", syncToPage);
  window.addEventListener("popstate", syncToPage);
})();
