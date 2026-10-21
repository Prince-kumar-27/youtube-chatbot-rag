
// (The content script runs inside youtube.com, where the browser would block calls to localhost.)

// ---- Settings: change these when you deploy the backend ----
const BACKEND_URL = "http://localhost:8000";
const API_TOKEN = "fgjdiadjvnskdjgpwrpaksdjspgjjaskds"; // must match EXTENSION_TOKEN in backend/.env (leave empty if you did not set one)
// If you deploy, also add your backend URL to "host_permissions" in manifest.json.

const ROUTES = {
  prepare: "/videos/prepare",
  summary: "/videos/summary",
  ask: "/videos/ask",
};

async function callBackend(path, body) {
  const headers = { "Content-Type": "application/json" };
  if (API_TOKEN) headers["X-Api-Token"] = API_TOKEN;

  let response;
  try {
    response = await fetch(BACKEND_URL + path, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });
  } catch (err) {
    throw new Error(`Cannot reach the server at ${BACKEND_URL}. Is the backend running?`);
  }

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof data.detail === "string" ? data.detail : "";
    throw new Error(detail || `Server error (${response.status})`);
  }
  return data;
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  const path = ROUTES[message && message.type];
  if (!path) return false;

  const { type, ...body } = message;
  callBackend(path, body)
    .then((data) => sendResponse({ ok: true, data }))
    .catch((err) => sendResponse({ ok: false, error: err.message }));
  return true; // keep the message channel open for the async reply
});

// ---- Toolbar icon: open or close the chat panel on the current YouTube video ----
const DEFAULT_TITLE = "Open video chat (on a YouTube video page)";

function sendToggle(tabId) {
  return new Promise((resolve) => {
    chrome.tabs.sendMessage(tabId, { type: "toggle-panel" }, (response) => {
      resolve(chrome.runtime.lastError ? null : response);
    });
  });
}

async function togglePanelOnTab(tabId) {
  const reply = await sendToggle(tabId);
  if (reply) return reply;
  // No answer: the tab was opened before the extension was loaded. Inject the script now and retry.
  try {
    await chrome.scripting.executeScript({ target: { tabId }, files: ["content.js"] });
  } catch (err) {
    return null; // not a YouTube page (or a page Chrome does not allow extensions on)
  }
  await new Promise((resolve) => setTimeout(resolve, 150));
  return sendToggle(tabId);
}

function flashWarning(tabId) {
  chrome.action.setBadgeBackgroundColor({ color: "#cc0000" });
  chrome.action.setBadgeText({ tabId, text: "!" });
  chrome.action.setTitle({ tabId, title: "Open a YouTube video first, then click this icon" });
  setTimeout(() => {
    chrome.action.setBadgeText({ tabId, text: "" });
    chrome.action.setTitle({ tabId, title: DEFAULT_TITLE });
  }, 3000);
}

chrome.action.onClicked.addListener(async (tab) => {
  const reply = await togglePanelOnTab(tab.id);
  if (!reply || !reply.ok) flashWarning(tab.id);
});
