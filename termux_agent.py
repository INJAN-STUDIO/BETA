#!/usr/bin/env python3
"""
B.E.T.A. in Termux - runs the commands you approve in the B.E.T.A. chat, on this phone.

SET UP (once)
  1. In Termux:      pkg install python
  2. Put this file in a folder, e.g.  ~/beta/termux_agent.py
  3. Create the file ~/.beta_termux.json containing (use YOUR values - the same TERM_TOKEN and TERM_SECRET
     you added in Render's Environment settings):
         {"url": "https://YOUR-SITE.onrender.com", "token": "...", "secret": "..."}
     (or set the environment variables BETA_URL, TERM_TOKEN and TERM_SECRET instead)

USE
  Start it when you want B.E.T.A. to be able to use Termux:      python ~/beta/termux_agent.py
  Stop it with Ctrl+C. While it is stopped, B.E.T.A. cannot run anything on your phone.

SAFETY
  * Nothing runs unless YOU tapped Run on that exact command in the B.E.T.A. chat.
  * Each approved command arrives signed by the server; anything unsigned, altered or old is refused here.
  * Commands run inside ~/beta-workspace, with a time limit, and without access to the keyboard.
  * A few obviously destructive commands are refused here even if approved (see BLOCKED below).
  * It checks in every few seconds, which uses a small amount of mobile data while it is running
    (roughly 0.5 MB an hour). Stop it when you don't need it.
"""

import hashlib
import hmac
import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request

WORKDIR = os.path.expanduser("~/beta-workspace")
OUTPUT_MAX = 6000
MAX_AGE_S = 300            # refuse commands signed longer ago than this

# Refused even when approved. A speed bump against the worst typos, not a guarantee - read the command before you tap Run.
BLOCKED = [
    r"^\s*(sudo|su)\b",
    r"\brm\s+(-[a-zA-Z]*\s+)*(/|~|\$HOME|\$PREFIX|\*)\s*$",
    r"\brm\s+-[a-zA-Z]*[rR][a-zA-Z]*\s+(/|~|\$HOME|\$PREFIX)(\s|/?$)",
    r"\bmkfs\b", r"\bdd\s+.*\bof=/dev/",
    r":\(\)\s*\{.*\};\s*:",            # fork bomb
]


def load_config():
    cfg = {}
    path = os.path.expanduser("~/.beta_termux.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception as e:
            sys.exit("Couldn't read %s: %s" % (path, e))
    url = (os.environ.get("BETA_URL") or cfg.get("url") or "").strip().rstrip("/")
    token = (os.environ.get("TERM_TOKEN") or cfg.get("token") or "").strip()
    secret = (os.environ.get("TERM_SECRET") or cfg.get("secret") or "").strip()
    if not (url and token and secret):
        sys.exit("Missing settings: need url, token and secret (see the top of this file).")
    return url, token, secret


URL, TOKEN, SECRET = load_config()


def call(method, path, payload=None, timeout=25):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(URL + path, data=data, method=method, headers={
        "Authorization": "Bearer " + TOKEN, "X-Requested-With": "beta",
        "Content-Type": "application/json", "User-Agent": "beta-termux/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def expected_sig(job):
    msg = ("%s|%s|%s|%s" % (job["id"], job["ts"], job["timeout"], job["command"])).encode("utf-8")
    return hmac.new(SECRET.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def check(job):
    """None if the command may run, otherwise the reason it must not."""
    try:
        if not hmac.compare_digest(str(job.get("sig", "")), expected_sig(job)):
            return "refused: the signature doesn't match (not from your B.E.T.A. server, or altered)"
        if abs(time.time() - int(job["ts"])) > MAX_AGE_S:
            return "refused: this approval is too old"
    except Exception:
        return "refused: malformed command"
    for pattern in BLOCKED:
        if re.search(pattern, job["command"]):
            return "refused: that command is on this phone's block list"
    return None


def run(command, timeout):
    os.makedirs(WORKDIR, exist_ok=True)
    shell = os.environ.get("SHELL") or "sh"
    p = subprocess.Popen([shell, "-c", command], cwd=WORKDIR, stdin=subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        out, _ = p.communicate(timeout=timeout)
        return p.returncode, out.decode("utf-8", "replace")[-OUTPUT_MAX:], False
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except Exception:
            p.kill()
        out, _ = p.communicate()
        return -1, out.decode("utf-8", "replace")[-OUTPUT_MAX:], True


def handle(job):
    print("\n$ " + job["command"])
    why = check(job)
    if why:
        print("  " + why)
        result = {"id": job["id"], "exit_code": -2, "output": why, "timed_out": False}
    else:
        code, out, timed_out = run(job["command"], int(job.get("timeout") or 30))
        print("  exit code %s%s" % (code, " (timed out)" if timed_out else ""))
        result = {"id": job["id"], "exit_code": code, "output": out, "timed_out": timed_out}
    for attempt in range(3):
        try:
            call("POST", "/api/term/result", result)
            return
        except Exception as e:
            print("  couldn't send the result (try %d): %s" % (attempt + 1, e))
            time.sleep(2)


def main():
    print("B.E.T.A. Termux bridge running - connected to %s\nPress Ctrl+C to stop.\n" % URL)
    fails = 0
    while True:
        try:
            job = call("GET", "/api/term/next")
            fails = 0
        except urllib.error.HTTPError as e:
            if e.code == 401:
                sys.exit("The server rejected the token (TERM_TOKEN doesn't match). Check ~/.beta_termux.json.")
            fails += 1
            job = {"idle": True, "poll_in": min(60, 5 * fails)}
        except Exception:
            fails += 1                                   # server asleep or no signal: wait longer each time
            job = {"idle": True, "poll_in": min(60, 5 * fails)}
        if job.get("id"):
            handle(job)
            continue
        time.sleep(max(1, min(60, int(job.get("poll_in", 6)))))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped. B.E.T.A. can no longer run commands on this phone.")
