# B.E.T.A. - ALPHA in the cloud, for your phone

Chat page + small server. Open it on your Honor 8X, install it as an app, done.

**What it can do:** web search, photo search (blurred with a reason when sensitive), YouTube
video analysis, read images/text files you attach, long-term memory, voice in/out (your phone's
own), tables/code/markdown, requests-left meter, Gemini with automatic fallback to Groq.

**What it can't do (on purpose):** touch your laptop. No terminal, files, email or clipboard
tools - the server has none of that, and a public endpoint must never offer a shell. Use ALPHA
on the Dell for those.

## Deploy (about 15 minutes)

1. **Supabase** (memory that survives restarts - Render's free disk is wiped on every restart).
   Open your project -> SQL Editor -> run `supabase.sql`. Then Project Settings -> API Keys and
   copy the project URL and the **secret** key (not the publishable/anon one).
2. **GitHub:** put this folder in a **private** repo.
3. **Render:** New -> Blueprint -> choose the repo. Fill in the values it asks for:
   `BETA_PASSWORD` (long!), `GEMINI_API_KEY`, `SERPER_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`,
   optionally `GROQ_API_KEY`. `SECRET_KEY` is generated for you.
4. **Phone (Fennec / Firefox):** open your `https://beta-xxxx.onrender.com` link, log in once, then tap the
   **⋮ menu -> Install**. (When the app qualifies, Firefox shows *Install* in place of *Add to Home
   screen*.) B.E.T.A. gets its own icon and opens full-screen. Chrome-type browsers: menu -> *Install app*.
   Inside B.E.T.A. the **⋯ menu -> Install as an app** shows these steps and checks the usual causes.

## If "Install" doesn't appear in Fennec / Firefox

- Open the site in a **normal tab** (not Private) - private tabs block the offline helper Install needs.
- Open it once, wait ~10 seconds, **reload**, then check the ⋮ menu again (the service worker has to
  register first). B.E.T.A.'s own menu -> *Install as an app* shows whether it's ready.
- It must be the **https** Render address, not an http link.
- In Fennec's settings, make sure site data/cookies aren't set to clear on exit, and that service
  workers aren't disabled by a privacy add-on.
- Some privacy-hardened Firefox builds switch service workers off entirely; there, use
  *Add to Home screen* (a shortcut) instead.

## Things to know

- **Voice input:** Firefox doesn't have speech recognition, so the microphone button is hidden in
  Fennec. Read-aloud (menu -> Read replies aloud) still works. Voice input can be added with a small
  server-side transcriber if you want it.
- **No Google in the app itself:** B.E.T.A.'s page loads no fonts, scripts or trackers from anyone
  else. (The AI behind it is still Gemini, by your choice - set `GEMINI_MODELS`/Groq to change that.)
- **Text size:** menu -> Text size cycles Small / Medium / Large.

- **Free plan sleeps** after ~15 min idle. The first open then shows a "waking up" screen for
  up to a minute, then works normally. The $7 Starter plan removes the sleep.
- **750 free hours/month are shared by all your free Render services.** If your old B.E.T.A.
  service is still running, delete or suspend it (or reuse it) so you don't run out.
- **Daily limits:** Gemini's free Flash models allow few requests per day each (about 20 was
  reported). Real numbers are in AI Studio; set them with `BETA_DAILY_LIMITS`, e.g.
  `{"gemini-3.8-flash": 20, "gemini-3.1-flash-lite": 500}`. Each tool use costs one request.
- **Secrets** live only in Render's environment variables - never in the repo.
- `agent_core.py` here is ALPHA's, with two tiny additions (a tool allowlist). If you change
  ALPHA's agent later, copy the file over again.

- **Model order:** by default B.E.T.A. tries the smartest Gemini Flash first and falls back down the
  list. The big Flash models have small daily allowances (~20 requests), Flash-Lite a big one (~500).
  Set `GEMINI_MODELS` to choose, e.g. `gemini-3.1-flash-lite` (more messages per day, a bit less smart)
  or `gemini-3.8-flash,gemini-3.1-flash-lite`.
- **Icon:** `static/icon-192.png` / `icon-512.png` are square crops of your B logo. The original is small,
  so a larger source image would make a sharper icon.
- **Keep this project in git.** If any tool (or ALPHA) overwrites a file, `git checkout <file>` restores it.

## Run it on your laptop first (optional)

    pip install -r requirements.txt
    export BETA_PASSWORD=test GEMINI_API_KEY=... SERPER_API_KEY=...
    python app.py        # http://localhost:5000   (memory saved in ./data)

## Tests

    python tests/test_server.py && python tests/test_storage.py && python tests/e2e.py
