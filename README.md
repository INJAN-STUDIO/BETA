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

## What's new in this release (2026.10.14-media)

- **Model order:** `gemini-3.1-flash-lite` first, `gemini-3.5-flash-lite` second, then **Groq** as the backup
  (Groq is still there - it takes over when both Gemini models are used up or overloaded - but it only
  switches on if `GROQ_API_KEY` is set on Render; menu -> *Models in order* now tells you whether it is).
  Change it any time with the `GEMINI_MODELS` setting, e.g. `gemini-3.1-flash-lite,gemini-3.5-flash-lite`.
- **Read-aloud with Brian:** every reply has a **Listen** button, and menu -> *Read replies aloud (Brian)* reads
  new replies automatically. The server makes the speech with Edge TTS (`en-US-BrianNeural`, change with
  `BETA_TTS_VOICE`) after ALPHA's cleaner has removed web addresses, code, tables, markdown symbols and emoji.
  If the voice can't be reached it falls back to the phone's own voice.
- **Image generation (free, private):** ask "draw a ..." and B.E.T.A. creates it with **FLUX.1 [schnell] on
  Cloudflare Workers AI**. Why this one: Cloudflare gives **10,000 free "Neurons" a day** with no card
  (by their price list ~58 Neurons per 1024x1024 picture = **about 170 pictures a day**), and their Workers AI
  documentation states they **don't use your prompts or pictures to train models or improve their services,
  and don't make them available to other customers**. Set it up once (about 5 minutes):
  1. Make a free Cloudflare account (cloudflare.com, no card needed).
  2. Dashboard -> **Workers & Pages -> AI -> Workers AI -> "Use REST API"**. Copy the **Account ID**, then
     **Create a Workers AI API token** and copy it.
  3. On Render add two environment variables: `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN`.
  Pictures are square; 9:16 / 16:9 requests are centre-cropped. When the day's allowance is used up, B.E.T.A.
  says so (it resets at 00:00 UTC, 1 am in Nigeria).
  *Google's Gemini image model (`gemini-2.5-flash-image`) is also supported and gives better quality, but Google
  lists it as not available on the free API tier. If you ever enable billing, put that key in
  `GEMINI_IMAGE_API_KEY`: B.E.T.A. then tries Google first and falls back to Cloudflare. Force one with
  `IMAGE_PROVIDER=cloudflare` or `google`.*
- **YouTube in the chat:** ask "play a video of ..." (or paste a YouTube link) and a card appears; tap Play and it
  plays inside B.E.T.A. Only videos that allow embedding are shown, nothing loads from YouTube until you tap,
  and sensitive searches arrive blurred with a reason, like photos.
  (This needed the page's referrer header relaxed from `no-referrer` - YouTube shows "Error 153" without one.)
- **Updates show up:** see "Updating" below.

## Updating (why a new push might not show, and the fix)

B.E.T.A. keeps a saved copy so it opens even while Render's free server is asleep. Releases now carry a version
number (menu -> bottom of the sheet shows it), pages are fetched from the server first, and a phone that finds
itself on an old copy clears it and reloads by itself. **If a phone is stuck on an old version once, open
`https://YOUR-SITE.onrender.com/reset`** - it wipes the saved copy and loads the newest. (Needed once, for
phones that still have a pre-2026.10.14 copy.)

## Which kind of "install" you get

| Where you install it | What you get |
|---|---|
| **Fennec / Firefox** (⋮ -> Install) | A **home-screen shortcut** with a small Firefox badge. Firefox on Android can't create real apps, so it never appears in the app menu. |
| **Chrome, Edge, Samsung Internet** (menu -> Install app) | A **real app**: it's in the app menu, has its own settings page, no badge. |
| **The Android app in `android/`** (see its README) | A **real app in your app menu** with the B.E.T.A. icon, whatever browser you use. Build it once in Android Studio. |

B.E.T.A. is written to work in both families of browsers (Chromium: Chrome, Edge, Brave, Samsung, Vivaldi...
and Firefox/Gecko: Fennec, Firefox, Mull, IronFox...). Things Firefox doesn't have are detected and skipped, e.g.
voice input (the mic button is hidden). Menu -> *Install as an app* shows what your browser supports.

### Seeing the green Android robot instead of the B.E.T.A. icon?
A home-screen shortcut keeps the icon it was created with. If you installed an earlier version (or the server was
still waking up at that moment), it can end up with the robot. Fix: long-press the shortcut -> remove it, open
B.E.T.A. in Fennec, let it load fully, reload once, then ⋮ -> Install again. The icons are now small and quick to
fetch, so this should stick.

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
- **Themes:** menu -> Theme cycles Logo colours dark (default) / Logo colours light / Classic dark (ALPHA's original) /
  Classic light. Buttons and the text boxes keep ALPHA's blue in every theme. Your choice is remembered.

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

    python tests/test_server.py && python tests/test_storage.py && python tests/test_pwa.py
    python tests/test_compat.py && python tests/test_android.py && python tests/test_media.py && python tests/e2e.py
