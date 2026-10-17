'use strict';
/* B.E.T.A. - phone client. Plain JavaScript, no build step, no libraries. */

const $ = (id) => document.getElementById(id);

// The release number comes from this script's own address (?v=2.0, filled in by the server from APP_VERSION in app.py),
// so there is nothing to keep in step by hand. If the server reports a different one, this copy of the app is out of
// date and refreshes itself (see waitForServer).
const CLIENT_VERSION = (() => {
  try { return new URL(document.currentScript.src).searchParams.get('v') || '0'; } catch (e) { return '0'; }
})();
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ---------------------------------------------------------------------------
// Icons (inline SVG - no emoji fonts, no downloads)
// ---------------------------------------------------------------------------
const ICONS = {
  menu: '<circle cx="5" cy="12" r="1.6"/><circle cx="12" cy="12" r="1.6"/><circle cx="19" cy="12" r="1.6"/>',
  clip: '<path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48"/>',
  mic: '<path d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z"/><path d="M19 10v2a7 7 0 01-14 0v-2M12 19v4M8 23h8"/>',
  send: '<path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/>',
  stop: '<rect x="6" y="6" width="12" height="12" rx="2"/>',
  speaker: '<path d="M11 5L6 9H2v6h4l5 4V5z"/><path d="M15.5 8.5a5 5 0 010 7M18.5 5.5a9 9 0 010 13"/>',
  'speaker-off': '<path d="M11 5L6 9H2v6h4l5 4V5z"/><path d="M22 9l-6 6M16 9l6 6"/>',
  bookmark: '<path d="M19 21l-7-5-7 5V5a2 2 0 012-2h10a2 2 0 012 2z"/>',
  trash: '<path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6M10 11v6M14 11v6"/>',
  logout: '<path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9"/>',
  copy: '<rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/>',
  check: '<path d="M20 6L9 17l-5-5"/>',
  alert: '<path d="M12 9v4M12 17h.01"/><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>',
  'eye-off': '<path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19m-6.72-1.07a3 3 0 11-4.24-4.24"/><path d="M1 1l22 22"/>',
  external: '<path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6M15 3h6v6M10 14L21 3"/>',
  x: '<path d="M18 6L6 18M6 6l12 12"/>',
  download: '<path d="M12 3v12M7 10l5 5 5-5M5 21h14"/>',
  text: '<path d="M4 7V5h16v2M9 19h6M12 5v14"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  moon: '<path d="M21 12.8A9 9 0 1111.2 3a7 7 0 009.8 9.8z"/>',
  palette: '<circle cx="13.5" cy="6.5" r="1"/><circle cx="17.5" cy="10.5" r="1"/><circle cx="8.5" cy="7.5" r="1"/><circle cx="6.5" cy="12.5" r="1"/><path d="M12 2a10 10 0 100 20c1.1 0 2-.9 2-2 0-.5-.2-1-.5-1.3-.3-.4-.5-.8-.5-1.3 0-1.1.9-2 2-2h2.4A4.7 4.7 0 0022 10.7C22 5.9 17.5 2 12 2z"/>',
  loader: '<path d="M21 12a9 9 0 11-6.2-8.56"/>',
  'play-fill': '<path d="M8 5v14l11-7z" fill="currentColor" stroke="none"/>',
  'arrow-down': '<path d="M12 5v14M19 12l-7 7-7-7"/>',
  bell: '<path d="M18 8a6 6 0 00-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.73 21a2 2 0 01-3.46 0"/>',
  'bell-off': '<path d="M13.73 21a2 2 0 01-3.46 0M18.63 13A17.9 17.9 0 0118 8M6.26 6.26A5.86 5.86 0 006 8c0 7-3 9-3 9h14M18 8a6 6 0 00-9.33-5M1 1l22 22"/>',
  image: '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.6"/><path d="M21 15l-5-5L5 21"/>',
};
const iconSvg = (name) =>
  `<svg class="ui-icon" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name] || ''}</svg>`;
const setIcon = (el, name) => { el.innerHTML = iconSvg(name); };
document.querySelectorAll('[data-icon]').forEach((el) => setIcon(el, el.dataset.icon));

// ---------------------------------------------------------------------------
// Small helpers: API, toast, clipboard
// ---------------------------------------------------------------------------
async function api(path, { method = 'GET', body } = {}) {
  const res = await fetch(path, {
    method,
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'beta' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let data = null;
  try { data = await res.json(); } catch (e) { /* non-JSON error page */ }
  if (res.status === 401 && path !== '/api/login') showLogin();
  if (!res.ok) {
    const err = new Error((data && data.error) || `Request failed (${res.status})`);
    err.status = res.status;
    throw err;
  }
  return data;
}

let toastTimer = null;
function toast(msg, failed) {
  const t = $('toast');
  t.textContent = msg;
  t.classList.toggle('failed', !!failed);
  t.classList.remove('hidden');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.add('hidden'), 1500);
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch (e) {
    try {                                   // fallback for pages without clipboard permission
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand('copy');
      ta.remove();
      return ok;
    } catch (e2) { return false; }
  }
}

// Every button reacts when pressed: a ripple spreads from the touch point and the phone gives a
// tiny buzz. (CSS also squashes the button a little while it's held down.)
const reducedMotion = () => window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
document.addEventListener('pointerdown', (e) => {
  const btn = e.target.closest && e.target.closest('button');
  if (!btn || btn.disabled) return;
  if (navigator.vibrate) { try { navigator.vibrate(8); } catch (err) { /* not allowed */ } }
  if (reducedMotion()) return;
  const r = btn.getBoundingClientRect(), d = Math.max(r.width, r.height) * 2;
  const s = document.createElement('span');
  s.className = 'ripple';
  s.style.width = s.style.height = d + 'px';
  s.style.left = (e.clientX - r.left - d / 2) + 'px';
  s.style.top = (e.clientY - r.top - d / 2) + 'px';
  btn.appendChild(s);
  s.addEventListener('animationend', () => s.remove());
}, true);

// tap inline code / URLs / link labels to copy
document.addEventListener('click', async (e) => {
  const el = e.target.closest('.md-copy');
  if (!el || !el.dataset.copy) return;
  if (String(window.getSelection()).length > 0) return;
  toast((await copyText(el.dataset.copy)) ? 'Copied' : "Couldn't copy", false);
});

// ---------------------------------------------------------------------------
// Markdown -> DOM (headings, bold/italic, lists, tables, code, links). Built from
// DOM nodes only - never innerHTML - so model output can't inject markup.
// ---------------------------------------------------------------------------
const INLINE_RE = new RegExp(
  '(\\*\\*\\*[^*\\n]+?\\*\\*\\*' +
  '|\\*\\*(?:[^*\\n]|\\*(?!\\*))+?\\*\\*' +
  '|`[^`\\n]+`' +
  '|\\[[^\\]\\n]+\\]\\([^)\\n]*\\)' +
  '|https?:\\/\\/[^\\s<>"\'`]+' +
  '|\\*[^*\\s][^*\\n]*?\\*)', 'g');

function appendInline(parent, text) {
  text = text.replace(/<br\s*\/?>/gi, '\n');
  const re = new RegExp(INLINE_RE.source, 'g');
  let last = 0, m;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parent.appendChild(document.createTextNode(text.slice(last, m.index)));
    const tok = m[0];
    if (tok.startsWith('***')) {
      const s = document.createElement('strong'), em = document.createElement('em');
      em.textContent = tok.slice(3, -3); s.appendChild(em); parent.appendChild(s);
    } else if (tok.startsWith('**')) {
      const s = document.createElement('strong'); appendInline(s, tok.slice(2, -2)); parent.appendChild(s);
    } else if (tok.startsWith('`')) {
      const c = document.createElement('code');
      c.className = 'md-copy'; c.textContent = tok.slice(1, -1); c.dataset.copy = tok.slice(1, -1);
      parent.appendChild(c);
    } else if (tok.startsWith('[')) {
      const lm = /^\[([^\]]+)\]\(([^)]*)\)$/.exec(tok);
      const span = document.createElement('span');
      span.className = 'md-link';
      if (lm[2]) { span.classList.add('md-copy'); span.dataset.copy = lm[2]; }
      appendInline(span, lm[1]); parent.appendChild(span);
    } else if (tok.startsWith('http')) {
      const url = tok.replace(/[.,;:!?)\]]+$/, '');
      re.lastIndex = m.index + url.length;
      const span = document.createElement('span');
      span.className = 'md-url md-copy'; span.textContent = url; span.dataset.copy = url;
      parent.appendChild(span);
      last = re.lastIndex;
      continue;
    } else {
      const em = document.createElement('em'); appendInline(em, tok.slice(1, -1)); parent.appendChild(em);
    }
    last = re.lastIndex;
  }
  if (last < text.length) parent.appendChild(document.createTextNode(text.slice(last)));
}

const MD = {
  heading: /^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$/,
  hr: /^\s{0,3}([-*_])(?:\s*\1){2,}\s*$/,
  ul: /^(\s*)[*+-]\s+(.*)$/,
  ol: /^(\s*)(\d+)[.)]\s+(.*)$/,
  quote: /^\s{0,3}>\s?(.*)$/,
};

function renderProse(text) {
  const root = document.createElement('div');
  root.className = 'md';
  const lines = text.split('\n');
  let para = [], lists = [];
  const flush = () => {
    if (!para.length) return;
    const p = document.createElement('p'); appendInline(p, para.join('\n')); root.appendChild(p); para = [];
  };
  const isList = (l) => MD.ul.test(l) || MD.ol.test(l);
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.trim() === '') {
      flush();
      if (lists.length) {
        let j = i + 1;
        while (j < lines.length && lines[j].trim() === '') j++;
        if (!(j < lines.length && isList(lines[j]))) lists = [];
      }
      i++; continue;
    }
    let m = MD.heading.exec(line);
    if (m) { flush(); lists = []; const h = document.createElement('h' + m[1].length); appendInline(h, m[2]); root.appendChild(h); i++; continue; }
    if (MD.hr.test(line)) { flush(); lists = []; root.appendChild(document.createElement('hr')); i++; continue; }
    if ((m = MD.quote.exec(line))) {
      flush(); lists = [];
      const q = [];
      while (i < lines.length && (m = MD.quote.exec(lines[i]))) { q.push(m[1]); i++; }
      const bq = document.createElement('blockquote'); appendInline(bq, q.join('\n')); root.appendChild(bq);
      continue;
    }
    let li = MD.ul.exec(line), type = 'ul', indent, content, start = 1;
    if (li) { indent = li[1].replace(/\t/g, '    ').length; content = li[2]; }
    else if ((li = MD.ol.exec(line))) { type = 'ol'; indent = li[1].replace(/\t/g, '    ').length; content = li[3]; start = parseInt(li[2], 10); }
    if (li) {
      flush();
      while (lists.length && indent < lists[lists.length - 1].indent) lists.pop();
      let top = lists[lists.length - 1];
      const make = () => {
        const el = document.createElement(type);
        if (type === 'ol' && start !== 1) el.start = start;
        const parent = lists.length && lists[lists.length - 1].lastLi ? lists[lists.length - 1].lastLi : root;
        parent.appendChild(el);
        return { indent, type, el, lastLi: null };
      };
      if (!top || indent > top.indent) { top = make(); lists.push(top); }
      else if (top.type !== type) { lists.pop(); top = make(); lists.push(top); }
      const liEl = document.createElement('li'); appendInline(liEl, content); top.el.appendChild(liEl); top.lastLi = liEl;
      i++; continue;
    }
    if (lists.length && /^\s+\S/.test(line) && !para.length) { appendInline(lists[lists.length - 1].lastLi, '\n' + line.trim()); i++; continue; }
    lists = []; para.push(line); i++;
  }
  flush();
  return root;
}

function splitCells(line) {
  const s = line.trim(), cells = [];
  let cur = '';
  for (let i = 0; i < s.length; i++) {
    const ch = s[i];
    if (ch === '\\' && s[i + 1] === '|') { cur += '|'; i++; }
    else if (ch === '|') { cells.push(cur); cur = ''; }
    else cur += ch;
  }
  cells.push(cur);
  if (s.startsWith('|')) cells.shift();
  if (s.endsWith('|') && !s.endsWith('\\|')) cells.pop();
  return cells.map((c) => c.trim());
}
const isSeparator = (l) => l.includes('|') && splitCells(l).every((c) => /^:?-+:?$/.test(c));

// text -> [{type:'text'|'code'|'table', ...}]
function parseSegments(text) {
  const segs = [];
  const fence = /```(?:([^\s`]+)[ \t]*\n|\n?)([\s\S]*?)```/g;
  let last = 0, m;
  while ((m = fence.exec(text)) !== null) {
    if (m.index > last) segs.push({ type: 'text', content: text.slice(last, m.index) });
    segs.push({ type: 'code', lang: m[1] || '', content: m[2].replace(/\n$/, '') });
    last = fence.lastIndex;
  }
  if (last < text.length) segs.push({ type: 'text', content: text.slice(last) });
  return segs.flatMap((s) => (s.type === 'text' ? splitTables(s.content) : [s]));
}

function splitTables(text) {
  const lines = text.split('\n'), out = [];
  let buf = [], found = false;
  const flush = () => { if (buf.length) { out.push({ type: 'text', content: buf.join('\n') }); buf = []; } };
  let i = 0;
  while (i < lines.length) {
    if (lines[i].includes('|') && i + 1 < lines.length && isSeparator(lines[i + 1])) {
      const header = splitCells(lines[i]), sep = splitCells(lines[i + 1]);
      if (header.length === sep.length) {
        const align = sep.map((c) => (c.startsWith(':') && c.endsWith(':') ? 'center' : c.endsWith(':') ? 'right' : 'left'));
        const rows = [];
        let j = i + 2;
        while (j < lines.length && lines[j].trim() !== '' && lines[j].includes('|')) { rows.push(splitCells(lines[j])); j++; }
        flush(); out.push({ type: 'table', header, align, rows }); found = true; i = j; continue;
      }
    }
    buf.push(lines[i]); i++;
  }
  flush();
  if (!found) return [{ type: 'text', content: text }];
  return out
    .map((s, k) => {
      if (s.type !== 'text') return s;
      let c = s.content;
      if (out[k + 1] && out[k + 1].type === 'table') c = c.replace(/\n+$/, '');
      if (out[k - 1] && out[k - 1].type === 'table') c = c.replace(/^\n+/, '');
      return { type: 'text', content: c };
    })
    .filter((s) => s.type !== 'text' || s.content.trim() !== '');
}

function copyButton(getText) {
  const btn = document.createElement('button');
  btn.className = 'copy-btn';
  const show = (state) => {
    btn.innerHTML = iconSvg(state === 'done' ? 'check' : 'copy') + (state === 'done' ? 'Copied' : 'Copy');
    btn.classList.toggle('done', state === 'done');
  };
  show('copy');
  btn.addEventListener('click', async () => {
    const ok = await copyText(getText());
    if (ok) { show('done'); setTimeout(() => show('copy'), 1500); } else toast("Couldn't copy", true);
  });
  return btn;
}

function blockShell(label, copyFn) {
  const wrap = document.createElement('div'); wrap.className = 'block';
  const head = document.createElement('div'); head.className = 'block-head';
  const l = document.createElement('span'); l.textContent = label; head.appendChild(l);
  head.appendChild(copyButton(copyFn));
  wrap.appendChild(head);
  return wrap;
}

function buildCode(seg) {
  const wrap = blockShell(seg.lang || 'code', () => seg.content);
  const pre = document.createElement('pre'); pre.textContent = seg.content;
  wrap.appendChild(pre);
  return wrap;
}

function buildTable(seg) {
  const cols = seg.header.length;
  const tsv = () => [seg.header, ...seg.rows.map((r) => Array.from({ length: cols }, (_, k) => r[k] || ''))]
    .map((r) => r.map((c) => c.replace(/\s+/g, ' ')).join('\t')).join('\n');
  const wrap = blockShell('table', tsv);
  const scroll = document.createElement('div'); scroll.className = 'table-scroll';
  const table = document.createElement('table');
  const thead = document.createElement('thead'), hr = document.createElement('tr');
  seg.header.forEach((t, k) => { const th = document.createElement('th'); th.style.textAlign = seg.align[k]; appendInline(th, t); hr.appendChild(th); });
  thead.appendChild(hr); table.appendChild(thead);
  const tbody = document.createElement('tbody');
  seg.rows.forEach((row) => {
    const tr = document.createElement('tr');
    for (let k = 0; k < cols; k++) { const td = document.createElement('td'); td.style.textAlign = seg.align[k]; appendInline(td, row[k] || ''); tr.appendChild(td); }
    tbody.appendChild(tr);
  });
  table.appendChild(tbody); scroll.appendChild(table); wrap.appendChild(scroll);
  return wrap;
}

function renderRich(text) {
  const box = document.createElement('div');
  parseSegments(text).forEach((seg) => {
    if (seg.type === 'code') box.appendChild(buildCode(seg));
    else if (seg.type === 'table') box.appendChild(buildTable(seg));
    else box.appendChild(renderProse(seg.content));
  });
  return box;
}

// ---------------------------------------------------------------------------
// Chat view + scroll rules
// ---------------------------------------------------------------------------
const chat = $('chat');
let stick = true, lastTop = 0;

function scrollDown(force) {
  if (force) stick = true;
  if (stick) chat.scrollTop = chat.scrollHeight;
}
// Any upward scroll stops auto-follow; it resumes at the very bottom or via "Latest".
chat.addEventListener('scroll', () => {
  const dist = chat.scrollHeight - chat.scrollTop - chat.clientHeight;
  if (chat.scrollTop < lastTop - 1) stick = false;
  else if (dist <= 2) stick = true;
  lastTop = chat.scrollTop;
  $('jump').classList.toggle('hidden', stick);
});
$('jump').addEventListener('click', () => { scrollDown(true); $('jump').classList.add('hidden'); });

function addEl(el) {
  chat.appendChild(el);
  while (chat.children.length > 80) chat.removeChild(chat.firstChild);   // keep the page light
  scrollDown();
}

// Replies "stream" in word by word, like ALPHA. Paragraphs, list items and headings stay
// hidden until the typing reaches them; code blocks and tables pop in whole. The pace
// adapts so even a long answer finishes in about 6 seconds. Tap a reply to show it all
// at once (sending a new message does the same).
const typers = new Set();
const TYPE_BLOCKS = new Set(['P', 'LI', 'UL', 'OL', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'BLOCKQUOTE', 'HR']);

function collectTyping(node, queue) {
  Array.from(node.childNodes).forEach((ch) => {
    if (ch.nodeType === 3) {
      const chunks = ch.nodeValue.match(/\S+\s*|\s+/g) || [];
      ch.nodeValue = '';
      chunks.forEach((chunk) => queue.push({ node: ch, chunk }));
    } else if (ch.nodeType === 1) {
      if (ch.classList.contains('block')) { ch.style.display = 'none'; queue.push({ reveal: ch }); }
      else {
        if (TYPE_BLOCKS.has(ch.tagName)) { ch.style.display = 'none'; queue.push({ reveal: ch }); }
        collectTyping(ch, queue);
      }
    }
  });
}

function finishTyping(t) {
  if (!typers.has(t)) return;
  clearTimeout(t.timer);
  for (; t.i < t.queue.length; t.i++) {
    const item = t.queue[t.i];
    if (item.reveal) item.reveal.style.display = '';
    else item.node.nodeValue += item.chunk;
  }
  typers.delete(t);
  if (t.onDone) t.onDone();
  scrollDown();
}
function finishAllTyping() { Array.from(typers).forEach(finishTyping); }

function startTyping(el, root, onDone) {
  const queue = [];
  collectTyping(root, queue);
  const words = queue.filter((q) => q.chunk && /\S/.test(q.chunk)).length;
  const perTick = Math.max(1, Math.ceil(words / 220));
  const t = { queue, i: 0, timer: null, onDone };
  typers.add(t);
  el.addEventListener('click', () => finishTyping(t));
  const tick = () => {
    let typed = 0;
    while (t.i < queue.length && typed < perTick) {
      const item = queue[t.i++];
      if (item.reveal) item.reveal.style.display = '';
      else { item.node.nodeValue += item.chunk; if (/\S/.test(item.chunk)) typed++; }
    }
    scrollDown();
    if (t.i < queue.length) t.timer = setTimeout(tick, 28); else { typers.delete(t); if (t.onDone) t.onDone(); }
  };
  return { t, tick };
}

function addMessage(role, text, animate) {
  const el = document.createElement('div');
  el.className = 'msg ' + (role === 'user' ? 'user' : role === 'error' ? 'ai error' : 'ai');
  let typing = null;
  if (role === 'user') el.textContent = text;
  else if (role === 'error') el.textContent = text;
  else {
    const rich = renderRich(text);
    el.appendChild(rich);
    const bar = document.createElement('div');       // "Listen": reads this reply aloud (Edge voice, Brian)
    bar.className = 'msg-actions';
    const lb = document.createElement('button');
    lb.className = 'listen-btn';
    lb.setAttribute('aria-label', 'Read this reply aloud');
    setListenState(lb, 'idle');
    lb.addEventListener('click', () => {
      if (lb.classList.contains('loading') || lb.classList.contains('playing')) stopSpeaking();
      else speak(text, lb);
    });
    bar.appendChild(lb);
    el.appendChild(bar);
    if (animate) {
      bar.style.display = 'none';                    // shows up once the reply has finished typing
      typing = startTyping(el, rich, () => { bar.style.display = ''; });
    }
  }
  if (role === 'user') { stick = true; }
  addEl(el);
  if (typing) typing.tick();
  return el;
}

// "B.E.T.A. is thinking" bubble - shown from the moment you send until the first sign of progress
let thinkingEl = null;
function showThinking() {
  if (thinkingEl) return;
  thinkingEl = document.createElement('div');
  thinkingEl.className = 'msg ai thinking';
  thinkingEl.innerHTML = '<span class="dots"><i></i><i></i><i></i></span>';
  addEl(thinkingEl);
}
function hideThinking() {
  if (thinkingEl) { thinkingEl.remove(); thinkingEl = null; }
}

function addNotice(text) {
  const el = document.createElement('div');
  el.className = 'msg notice';
  el.textContent = text;
  addEl(el);
}

// ---------------------------------------------------------------------------
// Photo galleries (blurred, with a reason, when the search looks sensitive)
// ---------------------------------------------------------------------------
function openGeneratedInLightbox(tile) {
  const img = $('lb-img'), status = $('lb-status'), lb = $('lightbox');
  img.src = tile.thumb;
  $('lb-title').textContent = tile.title || 'Generated image';
  $('lb-source').textContent = (tile.source || 'Generated image') + (tile.width && tile.height ? ` · ${tile.width}×${tile.height}` : '');
  $('lb-open').style.display = 'none';
  $('lb-save').style.display = '';
  $('lb-save').onclick = () => { window.location.href = '/api/generated/' + tile.gen_id + '?download=1'; };   // downloads as a file
  status.textContent = 'Loading full size…'; status.style.display = '';
  lb.classList.remove('hidden'); lb.dataset.cur = 'gen' + tile.gen_id;
  const full = new Image();
  full.onload = () => { if (lb.dataset.cur === 'gen' + tile.gen_id) { img.src = full.src; status.style.display = 'none'; } };
  full.onerror = () => { if (lb.dataset.cur === 'gen' + tile.gen_id) status.textContent = "Showing the preview - the full image isn't available any more."; };
  full.src = '/api/generated/' + tile.gen_id;
}

function openLightbox(tile) {
  if (tile.gen_id) return openGeneratedInLightbox(tile);
  $('lb-save').style.display = 'none';
  const img = $('lb-img'), status = $('lb-status');
  img.src = tile.thumb;
  $('lb-title').textContent = tile.title || 'Untitled image';
  $('lb-source').textContent = (tile.source || 'Unknown source') + (tile.width && tile.height ? ` · ${tile.width}×${tile.height}` : '');
  $('lb-open').style.display = tile.page_url ? '' : 'none';
  $('lb-open').onclick = () => { if (/^https?:\/\//.test(tile.page_url)) window.open(tile.page_url, '_blank', 'noopener,noreferrer'); };
  status.textContent = 'Loading full size…';
  status.style.display = '';
  $('lightbox').classList.remove('hidden');
  const token = tile.full_url;
  $('lightbox').dataset.cur = token;
  api('/api/full_image', { method: 'POST', body: { url: tile.full_url } })
    .then((r) => {
      if ($('lightbox').dataset.cur !== token) return;
      if (r && r.data) { img.src = r.data; status.style.display = 'none'; }
      else status.textContent = "Showing the preview - full size couldn't load.";
    })
    .catch(() => { if ($('lightbox').dataset.cur === token) status.textContent = "Showing the preview - full size couldn't load."; });
}
$('lb-close').addEventListener('click', () => $('lightbox').classList.add('hidden'));

function addGallery(p) {
  if (!p || !p.images || !p.images.length) return;
  const blurred = !!p.blurred, reason = p.reason || 'may contain disturbing content';
  const card = document.createElement('div');
  card.className = 'msg ai gallery';

  const head = document.createElement('div'); head.className = 'gallery-head';
  const title = document.createElement('span'); title.textContent = `Photos · "${p.query || ''}"`; head.appendChild(title);
  card.appendChild(head);

  let banner = null;
  const grid = document.createElement('div'); grid.className = 'grid';
  if (blurred) {
    const all = document.createElement('button'); all.className = 'reveal-all'; all.textContent = 'Reveal all';
    all.addEventListener('click', () => { grid.querySelectorAll('.tile.blurred').forEach((t) => t.classList.remove('blurred')); all.remove(); if (banner) banner.remove(); });
    head.appendChild(all);
    banner = document.createElement('div'); banner.className = 'banner';
    banner.innerHTML = iconSvg('eye-off');
    const bt = document.createElement('span'); bt.textContent = `Blurred - ${reason}. You choose whether to look.`; banner.appendChild(bt);
    card.appendChild(banner);
  }

  p.images.forEach((t) => {
    const tile = document.createElement('button');
    tile.className = 'tile' + (blurred ? ' blurred' : '');
    const img = document.createElement('img'); img.src = t.thumb; img.alt = t.title || ''; img.draggable = false;
    tile.appendChild(img);
    if (blurred) {
      const veil = document.createElement('div'); veil.className = 'veil';
      veil.innerHTML = iconSvg('eye-off');
      const r = document.createElement('div'); r.className = 'veil-reason'; r.textContent = reason; veil.appendChild(r);
      const h = document.createElement('div'); h.className = 'veil-hint'; h.textContent = 'Tap to reveal'; veil.appendChild(h);
      tile.appendChild(veil);
    }
    const cap = document.createElement('div'); cap.className = 'caption'; cap.textContent = t.source || ''; tile.appendChild(cap);
    tile.addEventListener('click', () => {
      if (tile.classList.contains('blurred')) tile.classList.remove('blurred');   // first tap reveals,
      else openLightbox(t);                                                       // second tap opens
    });
    grid.appendChild(tile);
  });
  card.appendChild(grid);
  const note = document.createElement('div'); note.className = 'gallery-note';
  note.textContent = 'Photos from web results - check each source. A photo may be from a different date or event.';
  card.appendChild(note);
  addEl(card);
}

// ---------------------------------------------------------------------------
// Usage meter
// ---------------------------------------------------------------------------
// ---------------------------------------------------------------------------
// YouTube videos that play INSIDE the chat, and generated images.
// A video card shows a thumbnail the server already fetched, so nothing is loaded from YouTube until you
// tap Play - then the player comes from youtube-nocookie.com (YouTube's privacy-friendly embed).
// Videos that could be upsetting arrive blurred with a reason, exactly like photos.
// ---------------------------------------------------------------------------
const YT_ID = /^[A-Za-z0-9_-]{11}$/;

// A separate function so it is easy to swap out (the preview page replaces it with a mock player).
function createVideoPlayer(id) {
  const f = document.createElement('iframe');
  f.src = 'https://www.youtube-nocookie.com/embed/' + id + '?autoplay=1&playsinline=1&rel=0&modestbranding=1';
  f.title = 'YouTube video player';
  f.setAttribute('allow', 'autoplay; encrypted-media; picture-in-picture; fullscreen');
  f.setAttribute('allowfullscreen', '');
  f.setAttribute('referrerpolicy', 'strict-origin-when-cross-origin');   // YouTube refuses to play without a referrer (Error 153)
  return f;
}

function stopAllVideos() {
  document.querySelectorAll('.video-stage.playing').forEach((stage) => {
    const f = stage.querySelector('iframe, .mock-player');
    if (f) f.remove();
    stage.classList.remove('playing');
  });
}

function playVideo(stage, v) {
  if (!YT_ID.test(v.video_id)) return;
  stopSpeaking();                              // don't talk over the video
  stopAllVideos();                             // one at a time
  stage.classList.add('playing');
  stage.appendChild(createVideoPlayer(v.video_id));
}

function addVideos(p) {
  if (!p || !p.videos || !p.videos.length) return;
  const blurred = !!p.blurred, reason = p.reason || 'may contain disturbing content';
  const card = document.createElement('div');
  card.className = 'msg ai gallery video-card';
  const head = document.createElement('div'); head.className = 'gallery-head';
  const title = document.createElement('span'); title.textContent = `Videos · "${p.query || ''}"`; head.appendChild(title);
  card.appendChild(head);
  let banner = null;
  const list = document.createElement('div');
  if (blurred) {
    const all = document.createElement('button'); all.className = 'reveal-all'; all.textContent = 'Reveal all';
    all.addEventListener('click', () => { list.querySelectorAll('.video.blurred').forEach((x) => x.classList.remove('blurred')); all.remove(); if (banner) banner.remove(); });
    head.appendChild(all);
    banner = document.createElement('div'); banner.className = 'banner'; banner.innerHTML = iconSvg('eye-off');
    const bt = document.createElement('span'); bt.textContent = `Blurred - ${reason}. You choose whether to look.`; banner.appendChild(bt);
    card.appendChild(banner);
  }
  p.videos.forEach((v) => {
    if (!YT_ID.test(v.video_id || '')) return;
    const box = document.createElement('div'); box.className = 'video' + (blurred ? ' blurred' : '');
    const stage = document.createElement('div'); stage.className = 'video-stage';
    if (v.thumb) { const img = document.createElement('img'); img.src = v.thumb; img.alt = v.title || ''; img.draggable = false; stage.appendChild(img); }
    const play = document.createElement('button'); play.className = 'video-play'; play.setAttribute('aria-label', 'Play ' + (v.title || 'video')); setIcon(play, 'play-fill');
    stage.appendChild(play);
    if (v.duration) { const d = document.createElement('span'); d.className = 'video-dur'; d.textContent = v.duration; stage.appendChild(d); }
    if (blurred) {
      const veil = document.createElement('div'); veil.className = 'video-veil'; veil.innerHTML = iconSvg('eye-off');
      const r = document.createElement('div'); r.className = 'veil-reason'; r.textContent = reason; veil.appendChild(r);
      const h = document.createElement('div'); h.className = 'veil-hint'; h.textContent = 'Tap to reveal'; veil.appendChild(h);
      stage.appendChild(veil);
    }
    stage.addEventListener('click', (e) => {
      if (stage.classList.contains('playing')) return;
      if (box.classList.contains('blurred')) { box.classList.remove('blurred'); return; }   // first tap reveals, second plays
      playVideo(stage, v);
    });
    box.appendChild(stage);
    const meta = document.createElement('div'); meta.className = 'video-meta';
    const t = document.createElement('div'); t.className = 'video-title'; t.textContent = v.title || 'YouTube video'; meta.appendChild(t);
    const sub = document.createElement('div'); sub.className = 'video-sub'; sub.textContent = v.channel || ''; meta.appendChild(sub);
    const open = document.createElement('button'); open.className = 'video-link'; open.innerHTML = iconSvg('external') + 'Open on YouTube';
    open.addEventListener('click', () => { if (/^https:\/\/www\.youtube\.com\/watch\?v=[A-Za-z0-9_-]{11}$/.test(v.url || '')) window.open(v.url, '_blank', 'noopener,noreferrer'); });
    meta.appendChild(open);
    box.appendChild(meta);
    list.appendChild(box);
  });
  card.appendChild(list);
  addEl(card);
}

function addGenerated(p) {
  if (!p || !p.images || !p.images.length) return;
  const card = document.createElement('div');
  card.className = 'msg ai gallery gen-card';
  const head = document.createElement('div'); head.className = 'gallery-head';
  const title = document.createElement('span'); title.textContent = 'Created image'; head.appendChild(title);
  card.appendChild(head);
  p.images.forEach((t) => {
    const tile = document.createElement('button'); tile.className = 'gen-tile'; tile.setAttribute('aria-label', 'Open the image');
    const img = document.createElement('img'); img.src = t.thumb; img.alt = t.title || 'Generated image'; img.draggable = false;
    tile.appendChild(img);
    tile.addEventListener('click', () => openLightbox(t));
    card.appendChild(tile);
    const actions = document.createElement('div'); actions.className = 'gen-actions';
    const open = document.createElement('button'); open.className = 'reveal-all'; open.textContent = 'Open'; open.addEventListener('click', () => openLightbox(t));
    const save = document.createElement('button'); save.className = 'reveal-all'; save.textContent = 'Save';
    save.addEventListener('click', () => { window.location.href = '/api/generated/' + t.gen_id + '?download=1'; });
    actions.appendChild(open); actions.appendChild(save); card.appendChild(actions);
  });
  const note = document.createElement('div'); note.className = 'gallery-note';
  note.textContent = 'Made by an AI image model from your description. Only the most recent images are kept on the server, so save the ones you like.';
  card.appendChild(note);
  addEl(card);
}

function updateUsage(s) {
  if (!s || !s.models || !s.models.length) return;
  // The model order, spelled out in the menu - including whether the Groq backup is switched on.
  if (s.groq !== undefined) {
    const short = (m) => m.replace(/^gemini-/, '').replace(/^openai\//, '');
    const gem = s.models.filter((m) => m.provider !== 'groq').map((m) => short(m.model));
    $('m-models').textContent = 'Models in order: ' + gem.join(' → ') + ' → ' +
      (s.groq ? 'Groq (' + short(s.groq_model || 'groq') + ') ready' : 'Groq: not switched on (no GROQ_API_KEY on the server)');
  }
  const e = s.models.find((m) => m.model === s.active) || s.models[0];
  const name = e.model.replace(/^gemini-/, '').replace(/^openai\//, '');
  $('usage-label').textContent = e.limit == null ? `${name} · ${e.used} used` : `${name} · ${e.remaining}/${e.limit} left`;
  const pct = e.limit ? Math.max(0, Math.min(100, (e.remaining / e.limit) * 100)) : 100;
  $('usage-fill').style.width = pct + '%';
  $('usage-fill').classList.toggle('low', pct <= 20);
  const secs = s.resets_in || 0, h = Math.floor(secs / 3600), m = Math.floor((secs % 3600) / 60);
  $('usage-reset').textContent = secs ? `resets ${h ? h + 'h ' : ''}${m}m` : '';
}

// ---------------------------------------------------------------------------
// Voice (the phone's own speech recognition + speech synthesis)
// ---------------------------------------------------------------------------
const store = {
  get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* private mode */ } },
};
let voiceOn = store.get('beta_voice') === '1';

function speakable(text) {
  return text
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/^\s*\|.*\|\s*$/gm, ' ')
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/https?:\/\/\S+/g, ' ')
    .replace(/[`*#>_]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 900);
}
// ---------------------------------------------------------------------------
// Read aloud: the SERVER makes the speech with Microsoft Edge's neural voice (Brian) - the same engine
// ALPHA uses - after cleaning the text (no web addresses, code, tables or symbols). It arrives as an MP3
// and plays through one <audio> element. The phone's own speech engine is only a last resort if the
// server's voice can't be reached.
// ---------------------------------------------------------------------------
const ttsAudio = new Audio();
const SILENT_WAV = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAESsAABErAAABAAgAZGF0YQAAAAA=';
let ttsToken = 0, ttsAbort = null, ttsUrl = null, ttsBtn = null, audioPrimed = false;

// Browsers only allow sound after you've touched the page. The first tap "unlocks" the audio element
// (with a silent clip), so a reply can be read aloud later without another tap.
function primeAudio() {
  if (audioPrimed) return;
  audioPrimed = true;
  try {
    ttsAudio.src = SILENT_WAV;
    const p = ttsAudio.play();
    if (p && p.catch) p.catch(() => { audioPrimed = false; });
  } catch (e) { audioPrimed = false; }
}
document.addEventListener('pointerdown', primeAudio, true);

function setListenState(btn, state) {
  if (!btn) return;
  btn.classList.toggle('loading', state === 'loading');
  btn.classList.toggle('playing', state === 'playing');
  const icon = state === 'loading' ? 'loader' : state === 'playing' ? 'stop' : 'speaker';
  const label = state === 'loading' ? 'Loading…' : state === 'playing' ? 'Stop' : 'Listen';
  btn.innerHTML = iconSvg(icon) + label;
}

function stopSpeaking() {
  ttsToken++;
  if (ttsAbort) { try { ttsAbort.abort(); } catch (e) { /* already done */ } ttsAbort = null; }
  try { ttsAudio.pause(); } catch (e) { /* nothing playing */ }
  if (window.speechSynthesis) { try { speechSynthesis.cancel(); } catch (e) { /* ignore */ } }
  if (ttsBtn) { setListenState(ttsBtn, 'idle'); ttsBtn = null; }
}

async function speak(text, btn) {
  stopSpeaking();
  const mine = ++ttsToken;
  ttsBtn = btn || null;
  setListenState(btn, 'loading');
  const ctrl = new AbortController();
  ttsAbort = ctrl;
  try {
    const res = await fetch('/api/tts', {
      method: 'POST', credentials: 'same-origin', signal: ctrl.signal,
      headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'beta' },
      body: JSON.stringify({ text }),
    });
    if (!res.ok) {
      let msg = "The voice isn't available right now.";
      try { msg = (await res.json()).error || msg; } catch (e) { /* not JSON */ }
      const err = new Error(msg); err.fromServer = true; throw err;
    }
    const blob = await res.blob();
    if (mine !== ttsToken) return;
    if (ttsUrl) URL.revokeObjectURL(ttsUrl);
    ttsUrl = URL.createObjectURL(blob);
    ttsAudio.onended = () => { if (mine === ttsToken) { setListenState(btn, 'idle'); ttsBtn = null; } };
    ttsAudio.src = ttsUrl;
    await ttsAudio.play();
    if (mine === ttsToken) setListenState(btn, 'playing');
  } catch (e) {
    if (e.name === 'AbortError' || mine !== ttsToken) return;
    setListenState(btn, 'idle'); ttsBtn = null;
    const fallback = window.speechSynthesis ? speakable(text) : '';
    if (fallback) {                                       // last resort: the phone's own voice
      try { speechSynthesis.cancel(); speechSynthesis.speak(new SpeechSynthesisUtterance(fallback)); toast("Using the phone's own voice"); return; } catch (err) { /* fall through */ }
    }
    toast(e.fromServer ? e.message : "Couldn't play the voice - check your connection", true);
  }
}

function refreshVoiceMenu() {
  setIcon($('m-voice-icon'), voiceOn ? 'speaker' : 'speaker-off');
  $('m-voice-text').textContent = 'Read replies aloud (Brian): ' + (voiceOn ? 'on' : 'off');
}

const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let recog = null, listening = false;
if (Recognition) {
  $('mic-btn').classList.remove('hidden');
  $('mic-btn').addEventListener('click', () => {
    if (listening) { recog.stop(); return; }
    recog = new Recognition();
    recog.lang = navigator.language || 'en-US';
    recog.interimResults = true;
    recog.onstart = () => { listening = true; $('mic-btn').classList.add('active'); };
    recog.onend = () => { listening = false; $('mic-btn').classList.remove('active'); };
    recog.onerror = () => { listening = false; $('mic-btn').classList.remove('active'); };
    recog.onresult = (ev) => {
      let text = '', final = false;
      for (let i = 0; i < ev.results.length; i++) { text += ev.results[i][0].transcript; if (ev.results[i].isFinal) final = true; }
      $('input').value = text; autosize();
      if (final) send();
    };
    try { recog.start(); } catch (e) { /* already started */ }
  });
}

// ---------------------------------------------------------------------------
// Composer: text, attachments, send / stop
// ---------------------------------------------------------------------------
let attachments = [];   // {name, data(base64)}
let busy = false, currentJob = null, stoppedJob = null;

function autosize() {
  const t = $('input');
  t.style.height = 'auto';
  t.style.height = Math.min(t.scrollHeight, 120) + 'px';
}
$('input').addEventListener('input', autosize);
// Enter sends; Shift+Enter makes a new line. Phone keyboards often don't report a normal
// Enter keydown, so the "insertLineBreak" input event is caught too.
let shiftDown = false;
$('input').addEventListener('keydown', (e) => {
  shiftDown = e.shiftKey;
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); }
});
$('input').addEventListener('keyup', (e) => { shiftDown = e.shiftKey; });
$('input').addEventListener('beforeinput', (e) => {
  if ((e.inputType === 'insertLineBreak' || e.inputType === 'insertParagraph') && !shiftDown) { e.preventDefault(); send(); }
});

function renderChips() {
  const row = $('attach-row');
  row.innerHTML = '';
  row.classList.toggle('hidden', attachments.length === 0);
  attachments.forEach((a, i) => {
    const chip = document.createElement('span'); chip.className = 'chip';
    const n = document.createElement('span'); n.className = 'name'; n.textContent = a.name; chip.appendChild(n);
    const x = document.createElement('button'); x.textContent = '×'; x.setAttribute('aria-label', 'Remove');
    x.addEventListener('click', () => { attachments.splice(i, 1); renderChips(); });
    chip.appendChild(x); row.appendChild(chip);
  });
}

// Phone photos are 3-6 MB; shrink to ~1280px JPEG first so uploads are quick on mobile data.
function loadBitmap(file) {
  const viaImage = () => new Promise((resolve, reject) => {          // fallback for browsers without createImageBitmap
    const reader = new FileReader();                                  // (a data: URL, so the strict security policy needs no blob: exception)
    reader.onload = () => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = () => reject(new Error('unreadable image'));
      img.src = reader.result;
    };
    reader.onerror = () => reject(new Error('unreadable image'));
    reader.readAsDataURL(file);
  });
  if (!window.createImageBitmap) return viaImage();
  return createImageBitmap(file).catch(viaImage);
}
async function shrinkImage(file) {
  const bmp = await loadBitmap(file);
  const bw = bmp.naturalWidth || bmp.width, bh = bmp.naturalHeight || bmp.height;
  const scale = Math.min(1, 1280 / Math.max(bw, bh));
  const c = document.createElement('canvas');
  c.width = Math.round(bw * scale); c.height = Math.round(bh * scale);
  c.getContext('2d').drawImage(bmp, 0, 0, c.width, c.height);
  return c.toDataURL('image/jpeg', 0.82).split(',')[1];
}
const fileToBase64 = (file) => new Promise((resolve, reject) => {
  const r = new FileReader();
  r.onload = () => resolve(String(r.result).split(',')[1]);
  r.onerror = reject;
  r.readAsDataURL(file);
});

$('attach-btn').addEventListener('click', () => $('file-input').click());
$('file-input').addEventListener('change', async (e) => {
  for (const file of Array.from(e.target.files)) {
    if (attachments.length >= 4) { toast('Up to 4 files at a time', true); break; }
    try {
      if (file.type.startsWith('image/')) attachments.push({ name: file.name.replace(/\.[^.]+$/, '') + '.jpg', data: await shrinkImage(file) });
      else if (file.size > 3 * 1024 * 1024) toast(`${file.name} is over 3 MB`, true);
      else attachments.push({ name: file.name, data: await fileToBase64(file) });
    } catch (err) { toast(`Couldn't read ${file.name}`, true); }
  }
  e.target.value = '';
  renderChips();
});

function setBusy(on) {
  busy = on;
  const btn = $('send-btn');
  btn.classList.toggle('stop', on);
  setIcon(btn, on ? 'stop' : 'send');
  btn.setAttribute('aria-label', on ? 'Stop' : 'Send');
  $('state-label').textContent = on ? 'thinking…' : 'ready';
  document.querySelector('.brand .blob').classList.toggle('thinking', on);
  if (!on) { $('activity').classList.add('hidden'); hideThinking(); }
}

async function send() {
  if (busy) return;
  const text = $('input').value.trim();
  if (!text) return;
  const files = attachments.slice();
  finishAllTyping();                                  // show any reply that's still typing, in full
  stopSpeaking();
  const bubble = addMessage('user', text);
  if (files.length) {
    const note = document.createElement('span'); note.className = 'attach-note';
    note.textContent = files.map((f) => f.name).join(', ');
    bubble.appendChild(note);
  }
  $('input').value = ''; autosize();
  attachments = []; renderChips();
  const sb = $('send-btn'); sb.classList.remove('pulse'); void sb.offsetWidth; sb.classList.add('pulse');
  setBusy(true);
  showThinking();
  try {
    const { job } = await api('/api/send', { method: 'POST', body: { text, files } });
    currentJob = job;
    sessionStorage.setItem('beta_job', job);
    await pollJob(job);
  } catch (err) {
    addMessage('error', err.message);
  } finally {
    setBusy(false);
  }
}

function handleEvent(ev) {
  hideThinking();
  if (ev.type === 'activity') { $('activity-text').textContent = ev.text; $('activity').classList.remove('hidden'); }
  else if (ev.type === 'images') {
    const p = ev.payload || {};
    if (p.kind === 'videos') addVideos(p);
    else if (p.kind === 'generated') addGenerated(p);
    else addGallery(p);
  }
  else if (ev.type === 'reply') {
    $('activity').classList.add('hidden');
    const bubble = addMessage('ai', ev.text, true);
    if (voiceOn) speak(ev.text, bubble.querySelector('.listen-btn'));
  }
  else if (ev.type === 'error') addMessage('error', ev.text);
  else if (ev.type === 'notice') addNotice(ev.text);
}

async function pollJob(job) {
  let after = 0;
  for (;;) {
    if (stoppedJob === job) return;
    let p;
    try {
      p = await api(`/api/poll?job=${job}&after=${after}&h=${document.hidden ? 1 : 0}`);
    } catch (err) {
      if (err.status === 404 || err.status === 401) return;    // job gone (server restarted) or logged out
      await sleep(2000); continue;                              // flaky connection - just try again
    }
    after = p.next;
    updateUsage(p.usage);
    let finished = false;
    p.events.forEach((ev) => { handleEvent(ev); if (ev.type === 'reply' || ev.type === 'error') finished = true; });
    if (p.done || finished) break;     // a reply or error is always the last event - don't wait for another poll
    await sleep(document.hidden ? 3000 : 800);
  }
  sessionStorage.removeItem('beta_job');
}

$('send-btn').addEventListener('click', async () => {
  if (!busy) return send();
  stoppedJob = currentJob;
  try { await api('/api/cancel', { method: 'POST', body: { job: currentJob } }); } catch (e) { /* ignore */ }
  sessionStorage.removeItem('beta_job');
  addNotice('Stopped.');
  setBusy(false);
});

// ---------------------------------------------------------------------------
// Menu + memory panel
// ---------------------------------------------------------------------------
const show = (id) => $(id).classList.remove('hidden');
const hide = (id) => $(id).classList.add('hidden');
$('menu-btn').addEventListener('click', () => { refreshVoiceMenu(); refreshNotifyMenu(); show('menu'); });
$('menu-close').addEventListener('click', () => hide('menu'));
$('menu').addEventListener('click', (e) => { if (e.target === $('menu')) hide('menu'); });
$('memory').addEventListener('click', (e) => { if (e.target === $('memory')) hide('memory'); });
$('memory-close').addEventListener('click', () => hide('memory'));
$('lightbox').addEventListener('click', (e) => { if (e.target === $('lightbox')) hide('lightbox'); });

// ---- text size (Small / Medium / Large) ----
const TEXT_SIZES = [['Small', 0.9], ['Medium', 1], ['Large', 1.18]];
let sizeIdx = Math.min(2, Math.max(0, parseInt(store.get('beta_size') || '1', 10) || 1));
function applyTextSize() {
  document.documentElement.style.setProperty('--ts', TEXT_SIZES[sizeIdx][1]);
  $('m-size-text').textContent = 'Text size: ' + TEXT_SIZES[sizeIdx][0];
}
$('m-size').addEventListener('click', () => { sizeIdx = (sizeIdx + 1) % TEXT_SIZES.length; store.set('beta_size', String(sizeIdx)); applyTextSize(); });
applyTextSize();

// ---- theme: logo colours (dark / light) or classic (ALPHA's original dark / light) ----
const THEMES = [
  { id: 'icon-dark', name: 'Logo colours · Dark', bar: '#051a22', icon: 'palette' },
  { id: 'icon-light', name: 'Logo colours · Light', bar: '#e8f5f8', icon: 'palette' },
  { id: 'dark', name: 'Classic dark (ALPHA)', bar: '#05060a', icon: 'moon' },
  { id: 'light', name: 'Classic light', bar: '#f2f6fb', icon: 'sun' },
];
let themeIdx = Math.max(0, THEMES.findIndex((t) => t.id === store.get('beta_theme')));   // default: logo colours, dark
function applyTheme() {
  const t = THEMES[themeIdx];
  document.documentElement.setAttribute('data-theme', t.id);
  const meta = document.querySelector('meta[name="theme-color"]'); if (meta) meta.setAttribute('content', t.bar);
  $('m-theme-text').textContent = 'Theme: ' + t.name;
  setIcon($('m-theme-icon'), t.icon);
}
$('m-theme').addEventListener('click', () => {
  themeIdx = (themeIdx + 1) % THEMES.length;
  store.set('beta_theme', THEMES[themeIdx].id);
  const root = document.documentElement;
  root.classList.add('theme-anim'); setTimeout(() => root.classList.remove('theme-anim'), 450);   // smooth cross-fade
  applyTheme();
});
applyTheme();

// ---- install as an app ----
// Chrome-type browsers fire "beforeinstallprompt" and we can open their install dialog. Firefox and
// Fennec never do, so there the sheet just says exactly what to tap - and checks the things that
// make Firefox hide the Install item (no service worker, private tab, not https).
let installEvent = null;
const isStandalone = () => (window.matchMedia && matchMedia('(display-mode: standalone)').matches) || navigator.standalone === true;
window.addEventListener('beforeinstallprompt', (e) => { e.preventDefault(); installEvent = e; });
window.addEventListener('appinstalled', () => { installEvent = null; toast('B.E.T.A. installed'); $('m-install').classList.add('hidden'); });
if (isStandalone()) $('m-install').classList.add('hidden');

function step(n, text) {
  const row = document.createElement('div'); row.className = 'step';
  const num = document.createElement('span'); num.className = 'num'; num.textContent = n;
  const t = document.createElement('span'); t.textContent = text;
  row.appendChild(num); row.appendChild(t);
  return row;
}
async function showInstallHelp() {
  const body = $('install-body');
  body.innerHTML = '';
  const firefox = /Firefox|Fennec/i.test(navigator.userAgent);
  const p = document.createElement('p');
  p.textContent = firefox ? 'In Fennec / Firefox:' : 'In your browser:';
  body.appendChild(p);
  body.appendChild(step(1, 'Tap the \u22EE menu (top right of the browser).'));
  body.appendChild(step(2, firefox ? "Tap Install. (It appears in place of \"Add to Home screen\" when the app qualifies.)" : 'Tap Install app, or Add to Home screen.'));
  body.appendChild(step(3, 'Confirm. B.E.T.A. gets its own icon and opens full-screen.'));
  let reg = null;
  try { reg = 'serviceWorker' in navigator ? await navigator.serviceWorker.getRegistration() : null; } catch (e) { /* blocked */ }
  const lines = [];
  const missing = [];
  if (!window.visualViewport) missing.push('keyboard fitting');
  if (!navigator.clipboard) missing.push('clipboard (fallback used)');
  if (!window.speechSynthesis) missing.push('read-aloud');
  if (!(window.SpeechRecognition || window.webkitSpeechRecognition)) missing.push('voice input');
  if (!window.createImageBitmap) missing.push('fast photo shrinking (fallback used)');
  lines.push(missing.length ? 'Not available in this browser: ' + missing.join(', ') : 'Browser features: everything B.E.T.A. uses is available');
  lines.push(window.isSecureContext ? 'Secure connection (https): yes' : 'Secure connection (https): NO - installing needs https');
  lines.push('serviceWorker' in navigator ? 'Offline helper: ' + (reg ? 'ready' : 'not registered yet - reload once, wait a few seconds, then try the menu again') : 'Offline helper: BLOCKED by this browser (a Private tab or strict privacy setting) - Install will not appear until it is allowed');
  lines.push('Currently installed: ' + (isStandalone() ? 'yes' : 'no'));
  const status = document.createElement('div'); status.className = 'status'; status.textContent = lines.join('\n'); status.style.whiteSpace = 'pre-line';
  body.appendChild(status);
  show('install');
}
$('m-install').addEventListener('click', async () => {
  hide('menu');
  if (installEvent) {                       // Chrome-type browsers: open the real install dialog
    installEvent.prompt();
    try { await installEvent.userChoice; } catch (e) { /* dismissed */ }
    installEvent = null;
    return;
  }
  showInstallHelp();
});
$('install-close').addEventListener('click', () => hide('install'));
$('install').addEventListener('click', (e) => { if (e.target === $('install')) hide('install'); });

$('m-voice').addEventListener('click', () => {
  voiceOn = !voiceOn; store.set('beta_voice', voiceOn ? '1' : '0');
  if (!voiceOn) stopSpeaking();
  refreshVoiceMenu();
});

// ---- notifications: "your reply is ready", even after you have left the app (Web Push) ----
const pushSupported = 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
const urlB64ToBytes = (s) => {
  const raw = atob((s + '='.repeat((4 - (s.length % 4)) % 4)).replace(/-/g, '+').replace(/_/g, '/'));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
};
async function getPushSub() {
  try { const reg = await navigator.serviceWorker.ready; return await reg.pushManager.getSubscription(); } catch (e) { return null; }
}
let notifyMode = 'webpush';          // 'ntfy' when the server is set up to send through the ntfy app
let ntfyOn = false;
async function refreshNotifyMenu() {
  let info = null;
  try { info = await api('/api/notify/info'); } catch (e) { /* offline: fall back to browser push */ }
  if (info && info.ntfy) {
    notifyMode = 'ntfy'; ntfyOn = !!info.ntfy_on;
    $('m-notify').classList.remove('hidden');
    setIcon($('m-notify-icon'), ntfyOn ? 'bell' : 'bell-off');
    $('m-notify-text').textContent = 'Notify me when a reply is ready (ntfy): ' + (ntfyOn ? 'on' : 'off');
    return;
  }
  notifyMode = 'webpush';
  if (!pushSupported) { $('m-notify').classList.add('hidden'); return; }
  $('m-notify').classList.remove('hidden');
  const on = Notification.permission === 'granted' && !!(await getPushSub());
  setIcon($('m-notify-icon'), on ? 'bell' : 'bell-off');
  $('m-notify-text').textContent = 'Notify me when a reply is ready: ' + (on ? 'on' : 'off');
}
async function enablePush() {
  const { key } = await api('/api/push/key');
  if (!key) throw new Error('The server has no notification keys yet (VAPID keys missing on Render).');
  const reg = await navigator.serviceWorker.ready;
  const old = await reg.pushManager.getSubscription();
  if (old) { try { await old.unsubscribe(); } catch (e) { /* start clean in case the server key changed */ } }
  const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlB64ToBytes(key) });
  await api('/api/push/subscribe', { method: 'POST', body: { subscription: sub.toJSON() } });
  api('/api/push/test', { method: 'POST', body: {} }).catch(() => {});    // a test notification, so you can see it works
  toast('Notifications on');
}
async function disablePush(sub) {
  try { await api('/api/push/unsubscribe', { method: 'POST', body: { endpoint: sub.endpoint } }); } catch (e) { /* ignore */ }
  try { await sub.unsubscribe(); } catch (e) { /* ignore */ }
  toast('Notifications off');
}
// Opened the app with notifications already on: make sure the server still has this phone saved.
async function syncPushSub() {
  if (!pushSupported || Notification.permission !== 'granted') return;
  const sub = await getPushSub();
  if (sub) api('/api/push/subscribe', { method: 'POST', body: { subscription: sub.toJSON() } }).catch(() => {});
}
$('m-notify').addEventListener('click', async () => {
  if (notifyMode === 'ntfy') {                 // the server sends through the ntfy app; this just switches it on or off
    try {
      await api('/api/notify/ntfy', { method: 'POST', body: { on: !ntfyOn } });
      toast(!ntfyOn ? 'Notifications on - they arrive in the ntfy app' : 'Notifications off');
    } catch (e) { toast(e.message || 'Could not change notifications.', true); }
    refreshNotifyMenu();
    return;
  }
  let perm = Notification.permission;
  if (perm === 'default') { try { perm = await Notification.requestPermission(); } catch (e) { /* ignore */ } }   // must come straight from the tap
  try {
    const sub = await getPushSub();
    if (sub) await disablePush(sub);
    else if (perm === 'granted') await enablePush();
    else toast('Notifications are blocked for B.E.T.A. - allow them in Firefox: tap the lock icon in the address bar > Permissions.', true);
  } catch (e) {
    const m = String((e && e.message) || e || '');
    toast(/push (service|subscription)/i.test(m)
      ? "This browser has no push service (common on Fennec). Use the ntfy option instead: set NTFY_TOPIC on the server."
      : (m || 'Could not change notifications.'), true);
  }
  refreshNotifyMenu();
});

$('m-clear').addEventListener('click', async () => {
  if (!confirm('Clear this conversation? Long-term memory is kept.')) return;
  try { await api('/api/clear', { method: 'POST' }); chat.innerHTML = ''; hide('menu'); toast('Conversation cleared'); }
  catch (e) { toast(e.message, true); }
});

$('m-logout').addEventListener('click', async () => {
  try { await api('/api/logout', { method: 'POST' }); } catch (e) { /* ignore */ }
  location.reload();
});

async function loadMemory() {
  const list = $('memory-list');
  list.innerHTML = '<div class="empty">Loading…</div>';
  try {
    const { entries } = await api('/api/memory');
    list.innerHTML = '';
    if (!entries.length) { list.innerHTML = '<div class="empty">Nothing saved yet. Ask B.E.T.A. to remember something.</div>'; return; }
    entries.forEach((en) => {
      const row = document.createElement('div'); row.className = 'mem-entry';
      const box = document.createElement('div'); box.className = 'mem-text';
      box.textContent = en.text;
      if (en.meta) { const meta = document.createElement('span'); meta.className = 'mem-meta'; meta.textContent = en.meta; box.appendChild(meta); }
      const del = document.createElement('button'); del.className = 'mem-del'; setIcon(del, 'trash'); del.setAttribute('aria-label', 'Delete');
      del.addEventListener('click', async () => {
        if (!confirm('Delete this memory?')) return;
        try { await api('/api/memory/delete', { method: 'POST', body: { id: en.id } }); loadMemory(); } catch (e) { toast(e.message, true); }
      });
      row.appendChild(box); row.appendChild(del); list.appendChild(row);
    });
  } catch (e) { list.innerHTML = ''; const d = document.createElement('div'); d.className = 'empty'; d.textContent = e.message; list.appendChild(d); }
}
$('m-memory').addEventListener('click', () => { hide('menu'); show('memory'); loadMemory(); });

// ---------------------------------------------------------------------------
// Boot: wake the server -> check login -> load the conversation
// ---------------------------------------------------------------------------
// Fade one screen out as the next fades in (wake -> login -> app).
function showOnly(id) {
  ['wake', 'login', 'app'].forEach((s) => {
    const el = $(s);
    if (s === id) { el.classList.remove('hidden', 'leaving'); }
    else if (!el.classList.contains('hidden')) {
      el.classList.add('leaving');
      setTimeout(() => { el.classList.add('hidden'); el.classList.remove('leaving'); }, 280);
    }
  });
}
function showLogin() { showOnly('login'); setTimeout(() => $('password').focus(), 350); }

// The server says which release it is running. If this page is an older copy (kept by the offline cache), clear
// the cache and reload - once - so you're never stuck on an old version.
async function checkVersion(info) {
  if (!info || !info.version) return;
  $('m-version').textContent = 'Version ' + info.version + (info.commit ? ' · build ' + info.commit : '');
  if (info.version === CLIENT_VERSION) return;
  if (sessionStorage.getItem('beta_refreshed_for') === info.version) return;      // already tried: don't loop
  sessionStorage.setItem('beta_refreshed_for', info.version);
  $('wake-text').textContent = 'Updating to the latest version…';
  location.replace('/reset');
}

async function waitForServer() {
  // A sleeping Render server doesn't refuse the request - it just leaves it hanging for up to a minute.
  // So the explanation is shown on a timer (after 3 seconds), not after a failed attempt.
  const explain = setTimeout(() => {
    $('wake-text').textContent = 'Waking B.E.T.A. up… the free server sleeps when idle, this can take up to a minute.';
  }, 3000);
  for (;;) {
    try {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), 20000);
      const res = await fetch('/api/health', { cache: 'no-store', signal: ctrl.signal });
      clearTimeout(t);
      if (res.ok) {
        clearTimeout(explain);
        let info = null;
        try { info = await res.json(); } catch (e) { /* older server */ }
        await checkVersion(info);
        return;
      }
    } catch (e) { /* not up yet */ }
    await sleep(1500);
  }
}

// The "unlock" effect: the form drops away, the logo winds up and bursts, and the chat opens as a
// circle that grows out of the logo. Used from the login screen (and the wake screen when you're
// already logged in). Skipped for people who've asked their phone to reduce motion.
async function openChatWithEffect(fromId) {
  const from = $(fromId), logo = from && from.querySelector('.logo-wrap'), card = from && from.querySelector('.screen-card');
  if (!logo || reducedMotion()) { showOnly('app'); return; }
  const r = logo.getBoundingClientRect(), app = $('app'), pr = app.parentNode.getBoundingClientRect();
  const cx = r.left + r.width / 2 - pr.left, cy = r.top + r.height / 2 - pr.top;   // relative to the app's container
  card.classList.add('unlocking');
  await sleep(420);                                    // wind-up: the form fades, the logo squashes
  app.style.setProperty('--cx', cx + 'px'); app.style.setProperty('--cy', cy + 'px');
  const ring = document.createElement('div');
  ring.className = 'portal-ring'; ring.style.setProperty('--cx', cx + 'px'); ring.style.setProperty('--cy', cy + 'px');
  app.parentNode.appendChild(ring);
  app.classList.remove('hidden', 'leaving'); app.classList.add('reveal');
  await sleep(1000);
  app.classList.remove('reveal'); ring.remove();
  from.classList.add('hidden'); card.classList.remove('unlocking');
}

async function startApp(fromId) {
  const statePromise = api('/api/state').then((s) => ({ s }), (e) => ({ e }));   // load the chat while the effect plays
  if (fromId) await openChatWithEffect(fromId); else showOnly('app');
  const got = await statePromise;
  if (got.e) { addMessage('error', got.e.message); return; }
  const st = got.s;
  chat.innerHTML = '';
  if (st.setup_error) addMessage('error', st.setup_error);
  else if (!st.history.length) addMessage('ai', "Hi Karachi, I'm **B.E.T.A.** I can search the web, find photos, watch YouTube videos, read what you attach, and remember things for you. What do you need?");
  st.history.forEach((m) => addMessage(m.role === 'user' ? 'user' : 'ai', m.text));
  updateUsage(st.usage);
  scrollDown(true);
  syncPushSub();
  if (st.active_job) {            // a reply was still being worked on when the page reloaded
    currentJob = st.active_job;
    setBusy(true);
    await pollJob(st.active_job);
    setBusy(false);
  }
}

async function doLogin() {
  const pw = $('password').value;
  if (!pw) return;
  $('login-error').textContent = '';
  const btn = $('login-btn');
  btn.disabled = true; btn.classList.add('loading'); btn.textContent = 'Unlocking…';
  try {
    await api('/api/login', { method: 'POST', body: { password: pw } });
    $('password').value = '';
    startApp('login');
  } catch (e) {
    $('login-error').textContent = e.message;
    const card = document.querySelector('#login .screen-card');
    card.classList.remove('shake'); void card.offsetWidth; card.classList.add('shake');   // shake on a wrong password
  } finally { btn.disabled = false; btn.classList.remove('loading'); btn.textContent = 'Unlock'; }
}
$('login-btn').addEventListener('click', doLogin);
$('password').addEventListener('keydown', (e) => { if (e.key === 'Enter') doLogin(); });

// Keep the whole app - and above all the text box - inside the part of the screen you can see. The
// on-screen keyboard covers the bottom of the page; Firefox/Fennec don't resize the page for it, so we
// read the visible area from the VisualViewport API and size the app to match (CSS: --app-h / --app-top).
(function fitToVisibleArea() {
  const root = document.documentElement, vv = window.visualViewport;
  let raf = 0, fullH = 0, lastW = 0;
  const apply = () => {
    raf = 0;
    const w = window.innerWidth;
    if (w !== lastW) { fullH = 0; lastW = w; }                       // rotated: forget the old full height
    const h = vv ? vv.height : window.innerHeight, top = vv ? vv.offsetTop : 0;
    fullH = Math.max(fullH, h + top);                               // tallest area seen = the screen with no keyboard
    root.style.setProperty('--app-h', Math.round(h) + 'px');
    root.style.setProperty('--app-top', Math.round(top) + 'px');
    root.classList.toggle('kb', h < fullH - 120);                   // 120px+ missing = keyboard is up (not just the URL bar)
    scrollDown();                                                    // keep the newest message in view while it opens
  };
  const schedule = () => { if (!raf) raf = requestAnimationFrame(apply); };
  if (vv) { vv.addEventListener('resize', schedule); vv.addEventListener('scroll', schedule); }
  window.addEventListener('resize', schedule);
  window.addEventListener('orientationchange', schedule);
  ['input', 'password'].forEach((id) => {                            // keyboards animate open over ~half a second
    $(id).addEventListener('focus', () => { [0, 120, 350, 700].forEach((ms) => setTimeout(schedule, ms)); });
    $(id).addEventListener('blur', () => { [0, 200, 500].forEach((ms) => setTimeout(schedule, ms)); });
  });
  apply();
})();

document.addEventListener('visibilitychange', () => { if (!document.hidden) scrollDown(); });

(async function boot() {
  if ('serviceWorker' in navigator) {
    const hadController = !!navigator.serviceWorker.controller;
    let reloading = false;
    // A new release's service worker has taken over: reload once so the new files show right away.
    navigator.serviceWorker.addEventListener('controllerchange', () => { if (hadController && !reloading) { reloading = true; location.reload(); } });
    navigator.serviceWorker.register('/sw.js?v=' + CLIENT_VERSION).catch(() => {});
  }
  await waitForServer();
  try {
    const me = await api('/api/me');
    if (!me.configured) { $('wake-text').textContent = 'Server is missing BETA_PASSWORD.'; return; }
    if (me.authed) startApp('wake'); else showLogin();
  } catch (e) { showLogin(); }
})();
