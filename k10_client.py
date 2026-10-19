#!/usr/bin/env python3
"""
K-10 Network - ALPHA's side (command line + a small library).

Put k10_core.py and this file together on the laptop and set three environment variables (same values as on Render):
    K10_KEY  SUPABASE_URL  SUPABASE_KEY          (and, optionally, BETA_URL=https://your-site.onrender.com to wake B.E.T.A.)

From a terminal (this is YOU typing, so it sends immediately):
    python k10_client.py inbox                       list mail waiting for ALPHA
    python k10_client.py read <id>                   show one message in full
    python k10_client.py accept <id> | reject <id>   mark it
    python k10_client.py sent                        what ALPHA has sent
    python k10_client.py send --subject "Hi" --body "text" [--file notes.md]

From ALPHA's own code (see K10_ALPHA_GUIDE.md for the rules ALPHA's GUI must follow):
    import k10_client; mb = k10_client.mailbox(); mb.inbox(); mb.read(id); k10_client.send(mb, subject, body)
"""

import argparse
import os
import sys
import time
import urllib.request

import k10_core


def mailbox():
    return k10_core.from_env("alpha")


def wake_beta():
    """Render's free server sleeps when idle; a quick visit wakes it so it notices the new mail and alerts you."""
    url = (os.environ.get("BETA_URL") or "").strip().rstrip("/")
    if not url:
        return
    try:
        urllib.request.urlopen(url + "/api/health", timeout=30).read()
    except Exception:
        pass


def send(mb, subject, body, attachment=None):
    msg_id = mb.send("beta", subject, body, attachment)
    wake_beta()
    return msg_id


def _when(ts):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts / 1000))


def main():
    ap = argparse.ArgumentParser(description="K-10 mail for ALPHA")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("inbox"); sub.add_parser("sent")
    for name in ("read", "accept", "reject"):
        sub.add_parser(name).add_argument("id")
    s = sub.add_parser("send"); s.add_argument("--subject", default=""); s.add_argument("--body", default=""); s.add_argument("--file")
    a = ap.parse_args()
    try:
        mb = mailbox()
        if a.cmd in ("inbox", "sent"):
            rows = mb.inbox() if a.cmd == "inbox" else mb.sent()
            for m in rows:
                att = " [file: %s]" % m["attachment"]["name"] if m["attachment"] else ""
                print("%s  %-8s  %s  %s  %s%s" % (m["id"], m["state"], _when(m["ts"]), m["from"], m["subject"] or "(no subject)", att))
            if not rows:
                print("(nothing)")
        elif a.cmd == "read":
            m = mb.read(a.id)
            print("From: %s  To: %s  Sent: %s  Status: %s\nSubject: %s\n\n%s" % (m["from"], m["to"], _when(m["ts"]), m["state"], m["subject"], m["body"]))
            if m["attachment"]:
                print("\n--- attached file: %s ---\n%s" % (m["attachment"]["name"], m["attachment"]["text"]))
        elif a.cmd in ("accept", "reject"):
            mb.set_state(a.id, "accepted" if a.cmd == "accept" else "rejected"); print("Done.")
        elif a.cmd == "send":
            att = None
            if a.file:
                with open(a.file, "r", encoding="utf-8") as f:
                    att = {"name": os.path.basename(a.file), "text": f.read()}
            print("Sent (id %s)." % send(mb, a.subject, a.body, att))
    except k10_core.K10Error as e:
        sys.exit("K-10: %s" % e)


if __name__ == "__main__":
    main()
