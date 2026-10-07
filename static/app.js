'use strict';
/* B.E.T.A. - phone client. Plain JavaScript, no build step, no libraries. */

const $ = (id) => document.getElementById(id);

// ---------------------------------------------------------------------------
// ICONS (inline SVG)
// ---------------------------------------------------------------------------
const ICONS = {
  menu: '<circle cx="5" cy="12" r="1.6"/><circle cx="12" cy="12" r="1.6"/><circle cx="19" cy="12" r="1.6"/>',
  clip: '<path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48"/>',
  send: '<path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/>',
  image: '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.6"/><path d="M21 15l-5-5L5 21"/>',
};
const iconSvg = (name) => `<svg class="ui-icon" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name] || ''}</svg>`;
const setIcon = (el, name) => { el.innerHTML = iconSvg(name); };
document.querySelectorAll('[data-icon]').forEach((el) => setIcon(el, el.dataset.icon));

// ---------------------------------------------------------------------------
// STREAMING & ANIMATION
// ---------------------------------------------------------------------------
async function streamText(element, text) {
  const words = text.split(' ');
  for (const word of words) {
    element.appendChild(document.createTextNode(word + ' '));
    await new Promise(r => setTimeout(r, 30)); // 30ms word delay
  }
}

// ---------------------------------------------------------------------------
// ENTER KEY TO SEND
// ---------------------------------------------------------------------------
$('prompt').addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    handleSend();
  }
});

async function handleSend() {
  const prompt = $('prompt').value.trim();
  if (!prompt) return;
  $('prompt').value = '';
  
  // Thinking Indicator
  const div = document.createElement('div');
  div.className = 'msg assistant thinking';
  div.innerHTML = '<span class="dot"></span><span class="dot"></span><span class="dot"></span>';
  $('chat').appendChild(div);
  $('chat').scrollTop = $('chat').scrollHeight;

  try {
    const res = await api('/api/send', { method: 'POST', body: { text: prompt } });
    const job = res.job;
    // Poll for completion...
    pollJob(job, div);
  } catch (e) {
    div.classList.remove('thinking');
    div.textContent = 'Error: ' + e.message;
  }
}

async function api(path, { method = 'GET', body } = {}) {
  const res = await fetch(path, {
    method,
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'beta' },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error('API failed');
  return await res.json();
}

async function pollJob(job, msgEl) {
  let after = 0;
  while (true) {
    const p = await api(`/api/poll?job=${job}&after=${after}`);
    for (const ev of p.events) {
      if (ev.type === 'reply') {
        msgEl.classList.remove('thinking');
        msgEl.innerHTML = ''; // clear dots
        await streamText(msgEl, ev.text);
      }
    }
    if (p.done) break;
    after = p.next;
    await new Promise(r => setTimeout(r, 500));
  }
}
