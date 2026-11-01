# B.E.T.A. 4.0 - accounts for friends, plus ideas 1 and 2 (replace these files in your Render repo, push)

app.py  accounts.py (new)  userctx.py (new)  agent_core.py  beta_agent.py  k10_bridge.py  k10_core.py  k10_link.py
static/app.js  static/index.html  static/style.css  static/themes.css       tools/vivid_colors.py (optional)

## What your friends get
- Open the link, tap "Have an invite code?", enter the code you gave them + their name + a password. A short interview (3 questions)
  shapes their B.E.T.A.; its first message is written from their answers. Passwords are stored only as salted hashes.
- Their own chat history, memory, long-term memory, settings, theme (new accounts start on the logo colours) and notification
  subscription. Nothing is shared between accounts.
- A daily allowance of messages (default 50, change per friend). "Use my own free key" (menu) lifts it: they paste a Google AI
  Studio key, it is checked with Google, stored encrypted, and used only for their messages.
- Notifications through the browser (Web Push). ntfy stays yours. Export my data / Delete my account in their menu.
- Not offered to friends: Termux and K-10 mail (they are tied to your phone and desktop), the admin screen, ntfy.

## What you get
- Your login is unchanged (BETA_PASSWORD). Your data stays exactly where it is (no prefix). Menu > "Friends and invites": allowance
  -/+ per friend, pause/resume, remove, create one-time invite codes (14 days) with a copy button.
- A paused or removed account is logged out at once.

## Ideas 1 and 2
- A rate-limit wait now counts down live (20, 19, 18 ... resuming) instead of sitting on one number.
- The Enter key makes a new line; messages are sent with the send button only.

## Also in this release: everything from the earlier updates
K-10 that can't hold up boot, Groq model chain, bigger pastes and screenshots, date/time-aware search, the ntfy fix, vivid colours
(themes.css AND style.css now).

## Settings (all optional, Render environment)
BETA_OWNER_NAME (default Karachi), BETA_FRIEND_DAILY_LIMIT (default 50), plus the earlier ones. Saving a friend's key needs SECRET_KEY
(you already have it) and the 'cryptography' package (already needed for K-10).

## Good to know
- One chat is answered at a time across everyone (image/video/Termux helpers hold per-job state). A second person's message waits
  its turn and is told "you're next".
- Friends on the shared key share one Gemini quota; the allowance keeps that fair.
- I couldn't see storage.py, so accounts use only store.get(key, default) / store.set(key, value). Long-term memory
  (personal_brain.brain_manager.load_db / save_db) is redirected per account at start-up; if that module is shaped differently, friends
  would share the owner's long-term memory - check Menu > Long-term memory as a friend.
