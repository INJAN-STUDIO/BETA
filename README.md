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
4. **Phone:** open your `https://beta-xxxx.onrender.com` link in Chrome, log in, then Chrome menu
   -> **Install app** / **Add to Home screen**.

## Things to know

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

## Run it on your laptop first (optional)

    pip install -r requirements.txt
    export BETA_PASSWORD=test GEMINI_API_KEY=... SERPER_API_KEY=...
    python app.py        # http://localhost:5000   (memory saved in ./data)

## Tests

    python tests/test_server.py && python tests/test_storage.py && python tests/e2e.py
