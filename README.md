# B.E.T.A. + ALPHA update (K-10 reliability, paste, Groq models)

Release number is now 2.9 in beta-cloud/app.py (phones refresh themselves when it changes).

## beta-cloud/  -> your Render repo (replace these files; static/app.js goes in static/)
app.py  agent_core.py  beta_agent.py  k10_bridge.py  k10_core.py  k10_link.py  static/app.js

### 1. K-10 can no longer hold up boot
Background connection with an 8 s deadline; it switches itself off if it doesn't answer, keeps retrying (10 s ... every 5 min),
and switches back on by itself. Named errors, a log at /api/k10/log (open while logged in), POST /api/k10/retry.
Optional setting: K10_BOOT_TIMEOUT. More detail in alpha-web/README_K10.md.

### 2. Large text and screenshots
- Long text used to be cut silently at 10,000 characters. Now the AI reads up to 60,000 characters (12,000 while on Groq, whose
  free tier allows far less per minute) and is told - and so are you - when something was cut.
  Optional settings: ATTACH_TEXT_CHARS, ATTACH_TEXT_CHARS_GROQ.
- Pictures are kept at up to 2048 px (was 1280, which halved phone screenshots and blurred small text); transparent PNGs get a
  white background instead of turning black; the result always stays under the server limit.
- Chat history shows "(attached text)" for old long pastes instead of printing the whole text again on reload.
- Old long pastes are shortened in what is sent to the model (stored history is untouched), so one big paste can't weigh down
  every later message.
- The clipboard button now falls back from read() to readText() instead of giving up, says exactly what happened, and Ctrl+V
  anywhere on the page (desktop) works.
- The small "Paste" bubble on Firefox is Firefox's own privacy rule - a web page cannot remove it.

### 3. More free Groq models
Chain (tried in order; each model has its own limits, and one that hits its limit or has been retired is skipped until it recovers):
  openai/gpt-oss-120b -> openai/gpt-oss-20b -> llama-3.3-70b-versatile -> llama-3.1-8b-instant
Picker-only (preview): qwen/qwen3.6-27b.  Menu > Model now shows "Groq - automatic order" and each Groq model by name.
Change the lists without editing code: GROQ_MODELS and GROQ_EXTRA_MODELS (comma separated) in Render's environment.
Check what your account really gets at console.groq.com/settings/limits - Groq changes its free models from time to time.

## alpha-web/  -> your laptop
Same as the last zip except the K-10 files. Setup steps are in alpha-web/README_K10.md.
