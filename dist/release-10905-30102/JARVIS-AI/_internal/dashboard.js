"use strict";

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const main = $("#mainContent");
let homeMarkup = main.innerHTML;
let chatMarkup = $("#chatTemplate").innerHTML.trim();
const storageKeys = { notes: "jarvis.preview.notes", reminders: "jarvis.preview.reminders", settings: "jarvis.preview.settings" };
let toastTimer;
let coreFrame = 0;
let barTimer = 0;

function updateClock() {
  const clock = $("#clock");
  if (clock) clock.textContent = new Intl.DateTimeFormat(undefined, {
    hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: true,
  }).format(new Date());
}

function showToast(message) {
  const toast = $("#toast");
  if (!toast) return;
  toast.textContent = message;
  toast.classList.add("visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("visible"), 3000);
}

function readLocal(key, fallback = []) {
  try {
    const value = JSON.parse(localStorage.getItem(key) || "null");
    return Array.isArray(fallback) ? (Array.isArray(value) ? value : fallback) : (value && typeof value === "object" ? value : fallback);
  } catch { return fallback; }
}

function writeLocal(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); return true; }
  catch { showToast("Browser storage is unavailable or full; nothing was saved."); return false; }
}

function escapeHTML(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[character]);
}

function pageFrame(title, subtitle, content, label = "JARVIS WORKSPACE") {
  return `<section class="tool-view panel"><div class="tool-view-head"><div><span class="tool-eyebrow">${label}</span><h1>${title}</h1><p>${subtitle}</p></div><span class="preview-chip"><i></i> BROWSER PREVIEW</span></div>${content}</section>`;
}

function noteMarkup() {
  const notes = readLocal(storageKeys.notes);
  if (!notes.length) return `<div class="empty-state"><span>▧</span><strong>No saved notes yet</strong><small>Add a note below. It stays in this browser on this device.</small></div>`;
  return `<div class="saved-list">${notes.slice().reverse().map((note) => `<article class="saved-item"><div><strong>${escapeHTML(note.title)}</strong><small>${escapeHTML(note.created)}</small><p>${escapeHTML(note.body)}</p></div><button class="icon-action danger-action" data-delete-note="${escapeHTML(note.id)}" aria-label="Delete note">×</button></article>`).join("")}</div>`;
}

function reminderMarkup() {
  const reminders = readLocal(storageKeys.reminders).slice().sort((a, b) => a.due.localeCompare(b.due));
  if (!reminders.length) return `<div class="empty-state"><span>◷</span><strong>No saved reminders</strong><small>Create one below; it stays in this browser only.</small></div>`;
  return `<div class="saved-list">${reminders.map((item) => `<article class="saved-item reminder-item ${item.done ? "is-done" : ""}"><div><strong>${escapeHTML(item.title)}</strong><small>${escapeHTML(new Date(item.due).toLocaleString())}</small></div>${item.done ? `<span class="done-label">DONE</span>` : `<button class="small-button" data-complete-reminder="${escapeHTML(item.id)}">Complete</button>`}</article>`).join("")}</div>`;
}

function calculatorMarkup() {
  return `<div class="tool-card calculator-card"><div class="tool-card-heading"><span class="heading-icon">▦</span><div><h2>Calculator</h2><p>Basic arithmetic · no expression code is executed</p></div></div><input id="calcDisplay" class="calc-display" type="text" inputmode="decimal" value="0" aria-label="Calculator expression"><div class="calc-grid">${["C", "(", ")", "÷", "7", "8", "9", "×", "4", "5", "6", "−", "1", "2", "3", "+", "0", ".", "⌫", "="].map((key) => `<button class="calc-key ${["÷", "×", "−", "+", "="].includes(key) ? "calc-operator" : ""} ${key === "=" ? "calc-equals" : ""}" data-calc="${key}">${key}</button>`).join("")}</div><div class="tool-hint">Type an expression or use the buttons. Supports parentheses.</div></div>`;
}

function paintMarkup() {
  return `<div class="tool-card"><div class="tool-card-heading"><span class="heading-icon">◉</span><div><h2>Paint Pad</h2><p>Draw directly on this canvas; drawings are temporary.</p></div><button class="small-button" data-clear-paint>Clear canvas</button></div><div class="paint-controls"><label>Ink color <input id="paintColor" type="color" value="#61caff"></label><label>Brush size <input id="paintSize" type="range" min="1" max="28" value="5"></label></div><canvas id="paintCanvas" class="paint-canvas" aria-label="Drawing canvas"></canvas></div>`;
}

function folderMarkup() {
  return `<div class="tool-card"><div class="tool-card-heading"><span class="heading-icon">▱</span><div><h2>Choose local files</h2><p>Your browser only exposes files you select.</p></div></div><label class="file-picker">Select files<input id="localFiles" type="file" multiple></label><label class="file-picker secondary-picker">Select a folder<input id="localFolder" type="file" webkitdirectory multiple></label><div id="fileSelection" class="file-selection">Nothing selected.</div><div class="tool-hint">The preview can list selected filenames; it cannot launch Explorer or read unselected folders.</div></div>`;
}

function appsMarkup(tool = "") {
  let detail = "<p class='tool-hint'>Choose a browser-side tool below. Opening Windows applications requires the Python desktop bridge.</p>";
  if (tool === "calculator") detail = calculatorMarkup();
  if (tool === "paint") detail = paintMarkup();
  if (tool === "folder") detail = folderMarkup();
  return pageFrame("Applications & Tools", "Browser tools work here; Windows app launching needs the desktop bridge.", `${detail}<div class="tool-launch-grid"><button class="tool-launch" data-open-tool="notepad"><span>▧</span><strong>Notepad</strong><small>Save browser-local notes</small></button><button class="tool-launch" data-open-tool="calculator"><span>▦</span><strong>Calculator</strong><small>Basic arithmetic pad</small></button><button class="tool-launch" data-open-tool="paint"><span>◉</span><strong>Paint</strong><small>Temporary drawing canvas</small></button><button class="tool-launch" data-open-tool="folder"><span>▱</span><strong>Open Folder</strong><small>Select local files</small></button><button class="tool-launch" data-open-tool="browser"><span>◎</span><strong>Browser</strong><small>Enter a website address</small></button></div>${tool === "browser" ? `<form id="websiteForm" class="inline-form"><label for="websiteAddress">Website address</label><div class="form-line"><input id="websiteAddress" type="url" placeholder="https://example.com" required><button class="primary-button">Open website</button></div></form>` : ""}`);
}

function renderPage(view, option = "") {
  const visibleChat = $(".chat-panel", main);
  if (visibleChat) chatMarkup = visibleChat.outerHTML;
  if (coreFrame) cancelAnimationFrame(coreFrame);
  clearInterval(barTimer);
  $$(".nav-item").forEach((button) => button.classList.toggle("active", button.dataset.view === view));
  main.classList.toggle("page-mode", view !== "Home");
  main.classList.toggle("chat-mode", view === "AI Chat");
  document.body.classList.toggle("chat-open", view === "AI Chat");
  if (view === "Home") {
    main.innerHTML = homeMarkup;
    setupBars("#footerWave", 74, 3, 19);
    setupBars("#signalBox", 29, 3, 28);
    setupCore();
    return;
  }
  if (view === "AI Chat") {
    main.innerHTML = chatMarkup;
    requestAnimationFrame(() => {
      const history = $("#chatHistory");
      if (history) history.scrollTop = history.scrollHeight;
    });
  } else if (view === "Voice Control") {
    main.innerHTML = pageFrame("Voice Control", "Voice capture is deliberately unavailable in this standalone preview.", `<div class="notice-card"><span>♩</span><div><strong>Microphone is not connected</strong><p>This page does not request microphone permission or upload audio. Offline speech recognition has not been implemented in the Python app.</p></div></div><button class="secondary-button" data-route="AI Chat">Continue with text chat</button>`);
  } else if (view === "Applications") {
    main.innerHTML = appsMarkup(option);
  } else if (view === "Web & Search") {
    main.innerHTML = pageFrame("Web & Search", "Search the web or open a site when you submit a query.", `<form id="searchForm" class="inline-form"><label for="webQuery">Search query</label><div class="form-line"><input id="webQuery" type="search" placeholder="Search the web…" required><button class="primary-button">Search web ↗</button></div><small>Submitting opens Google in a new tab and shares the query with Google.</small></form><form id="websiteForm" class="inline-form"><label for="websiteAddress">Open website</label><div class="form-line"><input id="websiteAddress" type="url" placeholder="https://example.com" required><button class="secondary-button">Open ↗</button></div></form><div class="notice-card subtle"><span>◎</span><div><strong>External search is user-triggered</strong><p>Nothing is sent until you press Search web.</p></div></div>`);
  } else if (view === "Notes & Memory") {
    main.innerHTML = pageFrame("Notes & Memory", "Your notes are stored in this browser's local storage only.", `<div class="two-column-tools"><form id="noteForm" class="tool-card"><div class="tool-card-heading"><span class="heading-icon">▧</span><div><h2>New note</h2><p>Save a note on this device.</p></div></div><label class="field-label" for="noteTitle">Title</label><input class="text-field" id="noteTitle" maxlength="100" placeholder="Note title" required><label class="field-label" for="noteBody">Note</label><textarea class="text-field text-area" id="noteBody" maxlength="4000" placeholder="Write your note…" required></textarea><button class="primary-button">Save note</button></form><div class="tool-card"><div class="tool-card-heading"><span class="heading-icon">▤</span><div><h2>Saved notes</h2><p id="noteCount">${readLocal(storageKeys.notes).length} notes in this browser</p></div></div><div id="noteList">${noteMarkup()}</div></div></div>`);
  } else if (view === "Reminders") {
    main.innerHTML = pageFrame("Reminders", "Reminders are stored locally in this browser; no notifications are sent.", `<div class="two-column-tools"><form id="reminderForm" class="tool-card"><div class="tool-card-heading"><span class="heading-icon">◷</span><div><h2>New reminder</h2><p>Add a local reminder entry.</p></div></div><label class="field-label" for="reminderTitle">Reminder</label><input class="text-field" id="reminderTitle" maxlength="120" placeholder="What should you remember?" required><label class="field-label" for="reminderDue">Date and time</label><input class="text-field" id="reminderDue" type="datetime-local" required><button class="primary-button">Save reminder</button></form><div class="tool-card"><div class="tool-card-heading"><span class="heading-icon">◷</span><div><h2>Saved reminders</h2><p>Complete an item when it is done.</p></div></div><div id="reminderList">${reminderMarkup()}</div></div></div>`);
  } else if (view === "My AI Model") {
    main.innerHTML = pageFrame("My AI Model", "Model details are informational; this HTML page is not connected to the Python checkpoint.", `<div class="model-summary-grid"><article class="stat-tile"><small>MODEL</small><strong>JARVIS Byte-Bigram</strong></article><article class="stat-tile"><small>PARAMETERS</small><strong>8,580</strong></article><article class="stat-tile"><small>VOCABULARY</small><strong>260 byte tokens</strong></article><article class="stat-tile"><small>CONTEXT</small><strong>1 previous byte</strong></article></div><div class="notice-card"><span>◈</span><div><strong>Training and generation run in the desktop Python app</strong><p>This browser preview cannot inspect your checkpoint or start a training job. Use the Python app's My AI Model page for real training metrics and generated output.</p></div></div><button class="secondary-button" data-toast="Run the Python desktop app to train or test the local model.">Model bridge status: disconnected</button>`);
  } else if (view === "System Monitor") {
    const cores = navigator.hardwareConcurrency ? `${navigator.hardwareConcurrency} logical threads reported by browser` : "Unavailable";
    const memory = navigator.deviceMemory ? `About ${navigator.deviceMemory} GiB reported by browser` : "Not exposed by browser";
    main.innerHTML = pageFrame("System Monitor", "These are browser-reported device hints, not live operating-system telemetry.", `<div class="model-summary-grid"><article class="stat-tile"><small>PLATFORM</small><strong>${escapeHTML(navigator.userAgentData?.platform || navigator.platform || "Browser")}</strong></article><article class="stat-tile"><small>CPU HINT</small><strong>${escapeHTML(cores)}</strong></article><article class="stat-tile"><small>MEMORY HINT</small><strong>${escapeHTML(memory)}</strong></article><article class="stat-tile"><small>LIVE METRICS</small><strong>Python bridge disconnected</strong></article></div><div class="notice-card subtle"><span>⌁</span><div><strong>No fabricated CPU or RAM percentages</strong><p>The browser does not provide reliable live CPU load, storage usage, or battery values to this page.</p></div></div>`);
  } else if (view === "Settings") {
    const settings = readLocal(storageKeys.settings, {});
    main.innerHTML = pageFrame("Settings", "These preview preferences are stored locally in this browser.", `<div class="tool-card settings-card"><label class="setting-row"><span><strong>Reduce motion</strong><small>Limit the animated core and decorative movement.</small></span><input id="reduceMotion" type="checkbox" ${settings.reduceMotion ? "checked" : ""}></label><div class="setting-row"><span><strong>Theme</strong><small>Current interface palette.</small></span><b class="setting-value">Dark blue</b></div><div class="setting-row"><span><strong>Python desktop bridge</strong><small>Model, OS actions, and voice are not connected here.</small></span><b class="muted-state">Offline</b></div><button class="secondary-button" data-clear-browser-data>Clear preview notes and reminders</button></div>`);
    document.body.classList.toggle("reduce-motion", Boolean(settings.reduceMotion));
  } else {
    main.innerHTML = pageFrame("JARVIS Workspace", `${escapeHTML(view)} preview`, `<div class="notice-card"><span>◈</span><div><strong>${escapeHTML(view)}</strong><p>This page is ready for a local backend connection.</p></div></div>`);
  }
  if (option === "notepad") {
    const title = $("#noteTitle");
    if (title) title.focus();
  }
  if (option === "search") $("#webQuery")?.focus();
  if (option === "folder") $("#localFolder")?.click();
  if (option === "browser") $("#websiteAddress")?.focus();
  if (option === "calculator") $("#calcDisplay")?.focus();
  if (view === "Applications" && option === "paint") setupPaint();
}

function appendMessage(role, text) {
  const history = $("#chatHistory");
  if (!history) return;
  const article = document.createElement("article");
  article.className = `message ${role === "user" ? "user-message" : "assistant-message"}`;
  const avatar = document.createElement("div");
  avatar.className = `avatar ${role === "user" ? "user-avatar" : "jarvis-avatar"}`;
  avatar.textContent = role === "user" ? "U" : "J";
  const wrap = document.createElement("div");
  wrap.className = "bubble-wrap";
  const meta = document.createElement("div");
  meta.className = "message-meta";
  meta.append(document.createTextNode(role === "user" ? "YOU" : "JARVIS UI"));
  const time = document.createElement("time");
  time.textContent = new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit" }).format(new Date());
  meta.append(time);
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;
  wrap.append(meta, bubble);
  article.append(avatar, wrap);
  history.append(article);
  requestAnimationFrame(() => history.scrollTo({ top: history.scrollHeight, behavior: "smooth" }));
}

function evaluateArithmetic(expression) {
  const source = String(expression).replace(/[×x]/gi, "*").replace(/[÷]/g, "/").replace(/[−]/g, "-").replace(/\s+/g, "");
  if (!source || source.length > 100 || !/^[\d.+*/()\-]+$/.test(source)) throw new Error("Enter a basic arithmetic expression.");
  const tokens = source.match(/\d*\.?\d+|[()+*/-]/g) || [];
  if (tokens.join("") !== source) throw new Error("Invalid arithmetic expression.");
  let position = 0;
  function factor() {
    if (tokens[position] === "+" || tokens[position] === "-") {
      const sign = tokens[position++] === "-" ? -1 : 1;
      return sign * factor();
    }
    if (tokens[position] === "(") {
      position += 1;
      const value = expressionValue();
      if (tokens[position++] !== ")") throw new Error("Missing closing parenthesis.");
      return value;
    }
    const token = tokens[position++];
    if (token === undefined || !/^\d*\.?\d+$/.test(token)) throw new Error("Expected a number.");
    return Number(token);
  }
  function term() {
    let value = factor();
    while (tokens[position] === "*" || tokens[position] === "/") {
      const operator = tokens[position++];
      const next = factor();
      if (operator === "/" && next === 0) throw new Error("Cannot divide by zero.");
      value = operator === "*" ? value * next : value / next;
    }
    return value;
  }
  function expressionValue() {
    let value = term();
    while (tokens[position] === "+" || tokens[position] === "-") {
      const operator = tokens[position++];
      const next = term();
      value = operator === "+" ? value + next : value - next;
    }
    return value;
  }
  const result = expressionValue();
  if (position !== tokens.length || !Number.isFinite(result)) throw new Error("Invalid or out-of-range calculation.");
  return Number(result.toPrecision(12)).toString();
}

function localChatReply(message) {
  const text = message.trim();
  const lowered = text.toLocaleLowerCase();
  if (/\b(time|clock)\b|समय/.test(lowered)) return `Your local time is ${new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(new Date())}.`;
  if (/\b(date|today|day)\b|तारीख|आज/.test(lowered)) return `Today is ${new Intl.DateTimeFormat(undefined, { dateStyle: "full" }).format(new Date())}.`;
  const calc = text.match(/(?:calculate|compute|what is|solve)\s+(.+)$/i) || text.match(/^\s*[\d(].*[+*/×÷−-].*$/);
  if (calc) {
    try { return `Result: ${evaluateArithmetic(calc[1] || text)}`; }
    catch (error) { return error.message; }
  }
  const notes = readLocal(storageKeys.notes);
  if (/\b(note|notes|memory)\b|नोट/.test(lowered)) return notes.length ? `You have ${notes.length} browser-local note${notes.length === 1 ? "" : "s"}. Open Notes & Memory to view them.` : "There are no saved browser-local notes yet. Open Notes & Memory to add one.";
  if (/\b(hello|hi|hey|namaste)\b|नमस्ते/i.test(text)) return "Namaste! I can tell the time or date, calculate basic arithmetic, and find your browser-local notes. The trained Python model is not connected to this page.";
  return "This preview can answer time/date and basic calculation requests and check local notes. For model-generated answers, connect the Python local-model backend; it is not connected here.";
}

function setupBars(selector, count, min, max) {
  const host = $(selector);
  if (!host) return;
  const fragment = document.createDocumentFragment();
  for (let index = 0; index < count; index += 1) {
    const bar = document.createElement("i");
    bar.style.height = `${min + Math.random() * (max - min)}px`;
    fragment.append(bar);
  }
  host.append(fragment);
  if (!document.body.classList.contains("reduce-motion")) {
    barTimer = setInterval(() => $$("i", host).forEach((bar) => { bar.style.height = `${min + Math.random() * (max - min)}px`; }), 180);
  }
}

function setupPaint() {
  const canvas = $("#paintCanvas");
  if (!canvas) return;
  const context = canvas.getContext("2d");
  const ratio = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = Math.round(rect.width * ratio);
  canvas.height = Math.round(360 * ratio);
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  context.fillStyle = "#081a34";
  context.fillRect(0, 0, rect.width, 360);
  let drawing = false;
  const point = (event) => {
    const rect = canvas.getBoundingClientRect();
    return [event.clientX - rect.left, event.clientY - rect.top];
  };
  canvas.addEventListener("pointerdown", (event) => { drawing = true; canvas.setPointerCapture(event.pointerId); const [x, y] = point(event); context.beginPath(); context.moveTo(x, y); });
  canvas.addEventListener("pointermove", (event) => {
    if (!drawing) return;
    const [x, y] = point(event);
    context.strokeStyle = $("#paintColor").value;
    context.lineWidth = Number($("#paintSize").value);
    context.lineCap = "round";
    context.lineJoin = "round";
    context.lineTo(x, y);
    context.stroke();
  });
  canvas.addEventListener("pointerup", () => { drawing = false; });
  canvas.addEventListener("pointercancel", () => { drawing = false; });
  $("[data-clear-paint]").addEventListener("click", () => { context.fillStyle = "#081a34"; context.fillRect(0, 0, canvas.width, canvas.height); });
}

function openTool(name) {
  if (name === "notepad") return renderPage("Notes & Memory", name);
  if (name === "calculator") return renderPage("Applications", name);
  if (name === "paint") return renderPage("Applications", name);
  if (name === "folder") return renderPage("Applications", name);
  if (name === "browser") return renderPage("Applications", name);
}

function setupControls() {
  $$(".nav-item").forEach((button) => button.addEventListener("click", () => renderPage(button.dataset.view)));
  $$("[data-action]").forEach((button) => button.addEventListener("click", () => {
    const action = button.dataset.action;
    const route = { Notepad: ["Notes & Memory", "notepad"], "Create Note": ["Notes & Memory", "notepad"], Calculator: ["Applications", "calculator"], Paint: ["Applications", "paint"], Browser: ["Applications", "browser"], "Web Search": ["Web & Search", "search"], "Open Folder": ["Applications", "folder"], "System Info": ["System Monitor", ""], "More Tools": ["Applications", ""] }[action];
    if (route) renderPage(route[0], route[1]);
  }));
  $(".view-all")?.addEventListener("click", () => renderPage("Reminders"));
  $("#mainContent").addEventListener("click", (event) => {
    if (event.target.closest("#micButton")) return showToast("Microphone input is not connected in this browser preview.");
    const route = event.target.closest("[data-route]");
    if (route) return renderPage(route.dataset.route);
    const suggestion = event.target.closest(".suggestion");
    if (suggestion) { const input = $("#chatInput"); if (input) { input.value = suggestion.dataset.prompt; input.focus(); } return; }
    const tool = event.target.closest("[data-open-tool]");
    if (tool) return openTool(tool.dataset.openTool);
    const removeNote = event.target.closest("[data-delete-note]");
    if (removeNote) {
      const notes = readLocal(storageKeys.notes).filter((note) => note.id !== removeNote.dataset.deleteNote);
      if (writeLocal(storageKeys.notes, notes)) renderPage("Notes & Memory");
      return;
    }
    const complete = event.target.closest("[data-complete-reminder]");
    if (complete) {
      const reminders = readLocal(storageKeys.reminders).map((item) => item.id === complete.dataset.completeReminder ? { ...item, done: true } : item);
      if (writeLocal(storageKeys.reminders, reminders)) renderPage("Reminders");
      return;
    }
    const calc = event.target.closest("[data-calc]");
    if (calc) {
      const display = $("#calcDisplay");
      const key = calc.dataset.calc;
      if (key === "C") display.value = "0";
      else if (key === "⌫") display.value = display.value.slice(0, -1) || "0";
      else if (key === "=") { try { display.value = evaluateArithmetic(display.value); } catch (error) { showToast(error.message); } }
      else display.value = display.value === "0" && /\d/.test(key) ? key : display.value + key;
      return;
    }
    if (event.target.closest("[data-clear-browser-data]")) {
      if (window.confirm("Clear notes, reminders, and saved preview preferences from this browser?")) {
        Object.values(storageKeys).forEach((key) => localStorage.removeItem(key));
        renderPage("Settings");
        showToast("Browser preview data cleared.");
      }
    }
  });
  document.addEventListener("click", (event) => {
    const toastButton = event.target.closest("[data-toast]");
    if (toastButton) showToast(toastButton.dataset.toast);
  });

  main.addEventListener("submit", (event) => {
    event.preventDefault();
    const form = event.target;
    if (form.id === "chatForm") {
      const input = $("#chatInput", form);
      const value = input.value.trim();
      if (!value) return;
      appendMessage("user", value);
      appendMessage("assistant", localChatReply(value));
      input.value = "";
    } else if (form.id === "noteForm") {
      const notes = readLocal(storageKeys.notes);
      notes.push({ id: crypto.randomUUID ? crypto.randomUUID() : String(Date.now()), title: $("#noteTitle").value.trim(), body: $("#noteBody").value.trim(), created: new Date().toLocaleString() });
      if (writeLocal(storageKeys.notes, notes)) renderPage("Notes & Memory");
    } else if (form.id === "reminderForm") {
      const reminders = readLocal(storageKeys.reminders);
      reminders.push({ id: crypto.randomUUID ? crypto.randomUUID() : String(Date.now()), title: $("#reminderTitle").value.trim(), due: new Date($("#reminderDue").value).toISOString(), done: false });
      if (writeLocal(storageKeys.reminders, reminders)) renderPage("Reminders");
    } else if (form.id === "searchForm") {
      const query = $("#webQuery").value.trim();
      if (query) {
        const opened = window.open(`https://www.google.com/search?q=${encodeURIComponent(query)}`, "_blank");
        if (opened) opened.opener = null;
        if (!opened) showToast("Popup blocked. Allow a new tab to open your search.");
      }
    } else if (form.id === "websiteForm") {
      const url = new URL($("#websiteAddress").value);
      if (!["http:", "https:"].includes(url.protocol)) return showToast("Only HTTP or HTTPS websites can be opened.");
      const opened = window.open(url.href, "_blank");
      if (opened) opened.opener = null;
      if (!opened) showToast("Popup blocked. Allow a new tab to open this site.");
    }
  });

  main.addEventListener("input", (event) => {
    if (event.target.id === "localFiles" || event.target.id === "localFolder") {
      const files = [...event.target.files];
      $("#fileSelection").textContent = files.length ? `${files.length} item(s): ${files.slice(0, 8).map((file) => file.webkitRelativePath || file.name).join(", ")}${files.length > 8 ? ", …" : ""}` : "Nothing selected.";
    }
    if (event.target.id === "reduceMotion") {
      const settings = readLocal(storageKeys.settings, {});
      settings.reduceMotion = event.target.checked;
      writeLocal(storageKeys.settings, settings);
      document.body.classList.toggle("reduce-motion", event.target.checked);
    }
  });
  main.addEventListener("keydown", (event) => {
    if (event.target.id === "calcDisplay" && event.key === "Enter") {
      event.preventDefault();
      try { event.target.value = evaluateArithmetic(event.target.value); } catch (error) { showToast(error.message); }
    }
  });
  main.addEventListener("input", (event) => {
    if (event.target.id === "calcDisplay") event.target.value = event.target.value.replace(/[^\d.+*/()\-×÷−]/g, "");
  });
  $("#voiceOrb").addEventListener("click", () => renderPage("Voice Control"));
  $("#fullscreen").addEventListener("click", async () => {
    try { if (!document.fullscreenElement) await document.documentElement.requestFullscreen(); else await document.exitFullscreen(); }
    catch { showToast("Fullscreen is unavailable in this browser window."); }
  });
}

function setupCore() {
  const canvas = $("#coreCanvas");
  if (!canvas) return;
  const context = canvas.getContext("2d");
  const reduce = () => document.body.classList.contains("reduce-motion") || window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let width = 0, height = 0, frame = 0;
  const stars = Array.from({ length: 72 }, () => ({ angle: Math.random() * Math.PI * 2, distance: 0.2 + Math.random() * 0.85, speed: (Math.random() * 0.002 + 0.0004) * (Math.random() < 0.5 ? -1 : 1), size: 0.6 + Math.random() * 1.4 }));
  function resize() {
    const box = canvas.getBoundingClientRect();
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    width = box.width; height = box.height;
    canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio);
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
  }
  function draw() {
    frame += 1; context.clearRect(0, 0, width, height);
    const cx = width / 2, cy = height * 0.47, radius = Math.min(width * 0.20, height * 0.34, 128);
    const glow = context.createRadialGradient(cx, cy, 2, cx, cy, radius * 1.8);
    glow.addColorStop(0, "#2c9dff35"); glow.addColorStop(0.42, "#1269c51b"); glow.addColorStop(1, "#071a3600");
    context.fillStyle = glow; context.fillRect(cx - radius * 2, cy - radius * 2, radius * 4, radius * 4);
    context.save(); context.translate(cx, cy); context.rotate(-0.12);
    for (let ring = 0; ring < 3; ring += 1) {
      context.beginPath(); context.ellipse(0, 0, radius * (1.22 + ring * 0.18), radius * (0.25 + ring * 0.07), 0, 0, Math.PI * 2);
      context.strokeStyle = ring === 1 ? "#55c5ff77" : "#398cf04d"; context.lineWidth = ring === 1 ? 1.3 : 0.8;
      context.setLineDash(ring === 2 ? [4, 8] : []); context.stroke();
    }
    context.setLineDash([]); context.restore();
    const globe = context.createRadialGradient(cx - radius * 0.34, cy - radius * 0.4, radius * 0.03, cx, cy, radius);
    globe.addColorStop(0, "#91e0ff"); globe.addColorStop(0.22, "#278fe7"); globe.addColorStop(0.66, "#10498f"); globe.addColorStop(1, "#071b3d");
    context.beginPath(); context.arc(cx, cy, radius, 0, Math.PI * 2); context.fillStyle = globe; context.shadowBlur = 34; context.shadowColor = "#258dffb8"; context.fill(); context.shadowBlur = 0;
    context.save(); context.beginPath(); context.arc(cx, cy, radius - 1, 0, Math.PI * 2); context.clip(); context.strokeStyle = "#82d8ff38"; context.lineWidth = 0.7;
    for (let line = -3; line <= 3; line += 1) { const y = line * radius * 0.23; const half = Math.sqrt(Math.max(0, radius * radius - y * y)); context.beginPath(); context.ellipse(cx, cy + y, half * 0.84, Math.max(2, radius * (0.14 - Math.abs(line) * 0.009)), 0, 0, Math.PI * 2); context.stroke(); }
    for (let line = 0; line < 5; line += 1) { context.beginPath(); context.ellipse(cx, cy, radius * (0.22 + line * 0.16), radius, 0, 0, Math.PI * 2); context.stroke(); }
    context.restore();
    stars.forEach((star) => { if (!reduce()) star.angle += star.speed; const x = cx + Math.cos(star.angle) * radius * star.distance * 1.8; const y = cy + Math.sin(star.angle) * radius * star.distance * 0.72; context.beginPath(); context.arc(x, y, star.size, 0, Math.PI * 2); context.fillStyle = star.distance > 0.75 ? "#bdeaff" : "#63b8ff99"; context.fill(); });
    context.fillStyle = "#e5f6ff"; context.textAlign = "center"; context.textBaseline = "middle"; context.font = `700 ${Math.max(17, radius * 0.31)}px Segoe UI, sans-serif`; context.shadowBlur = 15; context.shadowColor = "#80d6ff"; context.fillText("JARVIS", cx, cy + 1); context.shadowBlur = 0;
    const platformY = height * 0.82;
    for (let ring = 0; ring < 4; ring += 1) { context.beginPath(); context.ellipse(cx, platformY, radius * (1.12 - ring * 0.15), 8 + ring * 3, 0, 0, Math.PI * 2); context.strokeStyle = ring === 0 ? "#75d9ffb5" : `rgba(53, 151, 255, ${0.45 - ring * 0.08})`; context.lineWidth = ring === 0 ? 1.8 : 1; context.stroke(); }
    const beamAlpha = 0.15 + Math.sin(frame * 0.035) * 0.07; context.beginPath(); context.moveTo(cx, cy - radius * 1.32); context.lineTo(cx, platformY + 13); context.strokeStyle = `rgba(87, 197, 255, ${beamAlpha})`; context.stroke();
    if (!reduce()) coreFrame = requestAnimationFrame(draw);
  }
  resize(); window.addEventListener("resize", resize, { passive: true }); draw();
}

updateClock();
setInterval(updateClock, 1000);
setupControls();
setupBars("#footerWave", 74, 3, 19);
setupBars("#signalBox", 29, 3, 28);
setupCore();
