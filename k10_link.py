"""
K-10's connection supervisor - shared by B.E.T.A. (k10_bridge.py) and ALPHA (k10_alpha_bridge.py).

The problem it solves: a slow or broken K-10 (wrong key, Supabase paused, no network) must NEVER hold up the program.
  * Starting it never blocks: everything happens on a background thread, and the first check has a hard deadline
    (K10_BOOT_TIMEOUT, default 8 s). If K-10 doesn't answer in time it is simply marked "unavailable" and the
    program carries on booting normally.
  * It then keeps trying in the background - after 10 s, 20 s, 40 s ... up to every 5 minutes, for ever - and switches
    itself back on as soon as the mailbox answers. Nothing needs a restart.
  * While it is on, it checks for mail every 45 s. Three failed checks in a row switch it back to "unavailable" and the
    retry loop takes over again.
  * status() is instant (it only reads what the background thread last learned), so a web page or window can ask
    "how is K-10?" at any moment without ever waiting for the network.
Every state change is logged once, with the reason in plain words (see k10_core.log), never with a secret.
"""

import os
import threading
import time

import k10_core

BACKOFF = (10, 20, 40, 80, 160, 300)       # seconds between retries while unavailable; the last value repeats
POLL_SECONDS = 45
FAILS_BEFORE_UNAVAILABLE = 3
PURGE_EVERY = 6 * 3600


def _float_env(name, default):
    try:
        return max(2.0, float(os.environ.get(name, default)))
    except (TypeError, ValueError):
        return float(default)


def run_with_deadline(fn, seconds):
    """Runs fn() on a helper thread. Returns (finished, result_or_exception). A DNS lookup or socket that hangs can't
    hold the caller past `seconds`: the helper is a daemon thread and is simply left behind."""
    box = {}
    done = threading.Event()

    def work():
        try:
            box["value"] = fn()
        except BaseException as e:                  # noqa - handed back to the caller
            box["error"] = e
        finally:
            done.set()

    threading.Thread(target=work, daemon=True).start()
    if not done.wait(seconds):
        return False, None
    return True, box.get("error") if "error" in box else box.get("value")


class Link:
    def __init__(self, me, on_poll=None, mailbox_factory=None, first_poll_window=None):
        """on_poll(new_messages, fresh_messages): called after every successful check of the inbox.
        first_poll_window: None = the first check announces nothing; or seconds - mail newer than that is 'fresh' too."""
        self.me = me
        self.on_poll = on_poll
        self._factory = mailbox_factory or (lambda: k10_core.from_env(me, timeout=_float_env("K10_BOOT_TIMEOUT", 8)))
        self.first_poll_window = first_poll_window
        self.boot_timeout = _float_env("K10_BOOT_TIMEOUT", 8)
        self.poll_seconds = POLL_SECONDS
        self._lock = threading.Lock()
        self._kick = threading.Event()
        self._started = False
        self._mb = None
        self._seen = set()
        self._first_poll = True
        self._purge_at = 0.0
        self._poll_fails = 0
        self._logged_reason = None
        self.state = "off"           # off | connecting | ready | unavailable
        self.kind = None
        self.message = None
        self.attempts = 0
        self.unread = None
        self.warning = None
        self.last_ok = None
        self.next_retry = None
        if hasattr(os, "register_at_fork"):
            os.register_at_fork(after_in_child=self._after_fork)

    def _after_fork(self):
        """gunicorn may load the app in its master process and then fork the worker that answers requests. A fork copies
        this object but NOT its background thread, so the worker would show whatever state the master had at that
        moment (usually 'connecting') for ever, with nobody updating it. So the worker starts its own connection."""
        was_started = self._started
        self._lock = threading.Lock()          # a lock the master's thread held at fork time would stay locked for ever
        self._kick = threading.Event()
        self._started, self._mb, self._poll_fails = False, None, 0
        self.state, self.kind, self.message, self.next_retry = "off", None, None, None
        if was_started:
            self.start()

    # -- what the rest of the program asks ---------------------------------
    @staticmethod
    def configured():
        return all((os.environ.get(n) or "").strip() for n in ("K10_KEY", "SUPABASE_URL", "SUPABASE_KEY"))

    def ready(self):
        return self.state == "ready"

    def status(self):
        """Instant. Safe to call from any request."""
        with self._lock:
            retry_in = max(0, int(self.next_retry - time.time())) if (self.state == "unavailable" and self.next_retry) else None
            return {"configured": self.configured(), "state": self.state, "ready": self.state == "ready", "kind": self.kind,
                    "message": self.message, "attempts": self.attempts, "retry_in": retry_in, "unread": self.unread,
                    "warning": self.warning,
                    "last_ok_ago": int(time.time() - self.last_ok) if self.last_ok else None}

    def not_ready_message(self):
        st = self.status()
        if not st["configured"]:
            return "K-10 isn't set up (K10_KEY, SUPABASE_URL and SUPABASE_KEY are needed)."
        base = st["message"] or "K-10 is still connecting."
        if st["state"] == "unavailable":
            return "%s K-10 is switched off for now and keeps retrying by itself (next try in about %ds)." % (base, st["retry_in"] or 0)
        return base

    def mailbox(self):
        with self._lock:
            if self._mb is None:
                self._mb = self._factory()
            return self._mb

    def set_mailbox(self, mb):                       # for tests
        with self._lock:
            self._mb = mb

    def kick(self):
        """Try again right now instead of waiting for the next scheduled retry."""
        self._kick.set()

    def report_error(self, exc):
        """A real action (reading, sending) failed. Keeps the status honest and starts reconnecting."""
        if isinstance(exc, k10_core.K10Unavailable) and exc.kind not in ("config",):
            self._go_unavailable(exc, from_action=True)

    def report_ok(self):
        with self._lock:
            self.last_ok = time.time()

    # -- the background thread ---------------------------------------------
    def start(self):
        """Never blocks. Safe to call more than once."""
        with self._lock:
            if self._started:
                return
            self._started = True
        if not self.configured():
            k10_core.log("%s: not configured - mail line stays off (needs K10_KEY, SUPABASE_URL, SUPABASE_KEY)." % self.me)
            return
        with self._lock:
            self.state, self.message = "connecting", "K-10 is connecting…"
        k10_core.log("%s: connecting in the background (gives up on the first try after %.0fs; boot is not held up)." % (self.me, self.boot_timeout))
        threading.Thread(target=self._loop, daemon=True, name="k10-link").start()

    def _sleep(self, seconds):
        self._kick.wait(seconds)
        self._kick.clear()

    def _loop(self):
        attempt_no = 0
        while True:
            try:
                if self.state != "ready":
                    attempt_no += 1
                    err = self._attempt()
                    if err is None:
                        self._go_ready(attempt_no)
                        attempt_no = 0
                    else:
                        wait = BACKOFF[min(attempt_no - 1, len(BACKOFF) - 1)]
                        self._go_unavailable(err, retry_in=wait)
                        self._sleep(wait)
                        continue
                self._poll_once()
            except Exception as e:                    # the supervisor itself must never die
                k10_core.log("%s: supervisor hiccup (%s) - carrying on." % (self.me, type(e).__name__))
            self._sleep(self.poll_seconds if self.state == "ready" else BACKOFF[0])

    def _attempt(self):
        """One connection check with a hard deadline. Returns None if all is well, else a K10Unavailable."""
        with self._lock:
            self.attempts += 1
            if self.state != "ready":
                self.state = "connecting"
        finished, result = run_with_deadline(lambda: k10_core.diagnose(timeout=self.boot_timeout), self.boot_timeout + 2)
        if not finished:
            return k10_core.K10Unavailable("timeout", "K-10 didn't answer within %.0f seconds." % self.boot_timeout, "deadline passed")
        if isinstance(result, BaseException):
            return k10_core.classify_error(result)
        if not result["ok"]:
            if result.get("detail"):
                k10_core.log("%s: check failed at '%s': %s" % (self.me, result["step"], result["detail"]))
            return k10_core.K10Unavailable(result["kind"], result["message"], result.get("detail", ""))
        try:
            self.mailbox()
        except k10_core.K10Error as e:
            return e if isinstance(e, k10_core.K10Unavailable) else k10_core.K10Unavailable("key", str(e))
        return None

    def _poll_once(self):
        window = self.first_poll_window
        try:
            finished, result = run_with_deadline(lambda: self.mailbox().inbox(limit=30), self.boot_timeout + 10)
            if not finished:
                raise k10_core.K10Unavailable("timeout", "Checking for mail took too long.", "deadline passed")
            if isinstance(result, BaseException):
                raise result
        except Exception as e:
            self._poll_fails += 1
            err = k10_core.classify_error(e)
            k10_core.log("%s: mail check failed (%d/%d): %s" % (self.me, self._poll_fails, FAILS_BEFORE_UNAVAILABLE, err.detail or err))
            if self._poll_fails >= FAILS_BEFORE_UNAVAILABLE:
                self._go_unavailable(err, retry_in=BACKOFF[0])
            return
        self._poll_fails = 0
        with self._lock:
            self.last_ok = time.time()
        msgs = result
        new = [m for m in msgs if m.get("state") == "new"]
        unreadable = [m for m in msgs if m.get("state") == "unreadable"]
        fresh = [m for m in new if m["id"] not in self._seen]
        if self._first_poll:
            cutoff = int((time.time() - window) * 1000) if window else None
            fresh = [m for m in fresh if cutoff is not None and m.get("ts", 0) >= cutoff]
            self._first_poll = False
        self._seen.update(m["id"] for m in new)
        with self._lock:
            self.unread = len(new)
            warn = ("%d message(s) couldn't be opened. K10_KEY is probably different on ALPHA and B.E.T.A. - "
                    "set the same value on both." % len(unreadable)) if unreadable else None
            changed = warn != self.warning
            self.warning = warn
        if changed and warn:
            k10_core.log("%s: %s" % (self.me, warn))
        if self.on_poll:
            try:
                self.on_poll(new, fresh)
            except Exception as e:
                k10_core.log("%s: new-mail notification failed (%s)." % (self.me, type(e).__name__))
        if time.time() > self._purge_at:
            self._purge_at = time.time() + PURGE_EVERY
            try:
                self.mailbox().purge_old()
            except Exception:
                pass

    # -- state changes (each logged once) -----------------------------------
    def _go_ready(self, tries=1):
        with self._lock:
            self.state, self.kind, self.message, self.next_retry = "ready", None, None, None
            self.last_ok, self._poll_fails, self._logged_reason = time.time(), 0, None
        k10_core.log("%s: mail line is ON%s." % (self.me, "" if tries <= 1 else " (connected after %d tries)" % tries))

    def _go_unavailable(self, err, retry_in=None, from_action=False):
        with self._lock:
            self.state, self.kind, self.message = "unavailable", err.kind, str(err)
            self.next_retry = time.time() + (retry_in if retry_in is not None else BACKOFF[0])
            changed = self._logged_reason != str(err)
            self._logged_reason = str(err)
        if changed or self.attempts % 10 == 0:
            k10_core.log("%s: mail line is OFF [%s] %s Retrying %s." % (
                self.me, err.kind, err, ("in %ds" % retry_in) if retry_in else "shortly"))
        if from_action:
            self.kick()
