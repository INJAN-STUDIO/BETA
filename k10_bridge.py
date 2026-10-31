"""
B.E.T.A.'s side of the K-10 Network (see k10_core.py).

  * The AI can only DRAFT mail to ALPHA. request_send() shows you the exact message in the chat and waits; only your
    Accept sends it (decide()). Reject, no answer, or the Stop button = nothing is sent.
  * Mail that arrives from ALPHA is shown to you first (the K-10 mail screen). B.E.T.A. (the AI) only sees it if you
    tap Accept, and then only as a normal message from you that is labelled as mail from ALPHA.
  * A small background check looks for new mail every 45 seconds and calls on_new() so you get an alert.
    (Render's free server sleeps when idle; mail simply waits and is picked up when it wakes. ALPHA pings the server
    after sending to wake it.)
  * K-10 can never hold up the server: k10_link.Link connects in the background with a hard deadline, switches K-10
    off if it doesn't answer, keeps retrying by itself, and status() is instant. See k10_link.py.
"""

import os
import threading
import time
import uuid

import k10_core
import k10_link

APPROVE_TIMEOUT = 150

_lock = threading.Lock()
_drafts = {}
on_new = None                  # app.py sets this: called with a summary dict when new mail arrives


def _on_poll(new, fresh):
    for m in fresh:
        if on_new:
            try:
                on_new(m)
            except Exception as e:
                k10_core.log("beta: new-mail alert failed (%s)." % type(e).__name__)


# Mail that arrived while the server slept is announced if it is under 2 hours old; older mail only shows in the badge.
LINK = k10_link.Link("beta", on_poll=_on_poll, first_poll_window=2 * 3600)


def enabled():
    """K-10 is configured (all three settings present). It may still be reconnecting - see ready() / status()."""
    return LINK.configured()


def ready():
    return LINK.ready()


def status():
    return LINK.status()


def not_ready_message():
    return LINK.not_ready_message()


def kick():
    LINK.kick()


def note_error(exc):
    LINK.report_error(exc)


def note_ok():
    LINK.report_ok()


def mailbox():
    return LINK.mailbox()


def set_mailbox(mb):                       # for tests
    LINK.set_mailbox(mb)


def request_send(to, subject, body, attach_name, attach_text, explanation, emit):
    """Runs on the AI's thread. Returns the text the AI sees as the tool result."""
    if not enabled():
        return "K-10 isn't set up on the server (K10_KEY is missing)."
    if not ready():
        return ("K-10 mail can't be used right now: %s Tell Karachi, and try again later - don't draft the mail again "
                "until he says it is back." % not_ready_message())
    to = str(to or "alpha").strip().lower()
    if to != "alpha":
        return "You can only send K-10 mail to ALPHA."
    subject, body = str(subject or "").strip(), str(body or "").strip()
    if not (subject or body):
        return "The message is empty."
    explanation = str(explanation or "").strip()
    if len(explanation) < 8:
        return ("Karachi must see, in plain words, why you want to send this. Put one or two short sentences in "
                "'explanation' and call k10_send again.")
    attachment = {"name": str(attach_name or "attachment.txt"), "text": str(attach_text)} if attach_text else None
    draft = {"id": uuid.uuid4().hex[:16], "state": "asked", "decided": threading.Event(), "created": time.time()}
    with _lock:
        for k in [k for k, v in _drafts.items() if time.time() - v["created"] > 3600]:
            _drafts.pop(k, None)
        _drafts[draft["id"]] = draft
    emit({"kind": "k10_ask", "id": draft["id"], "to": "ALPHA", "subject": subject, "body": body[:6000],
          "attachment": {"name": attachment["name"], "size": len(attachment["text"].encode("utf-8"))} if attachment else None,
          "explanation": explanation[:400]})
    if not draft["decided"].wait(APPROVE_TIMEOUT):
        draft["state"] = "expired"
        emit({"kind": "k10_result", "id": draft["id"], "status": "expired"})
        return "Karachi didn't answer in time, so the mail was NOT sent."
    if draft["state"] != "approved":
        emit({"kind": "k10_result", "id": draft["id"], "status": "rejected"})
        return "Karachi did not approve this mail, so it was NOT sent. Don't send it again unless he asks."
    try:
        # What is sent is exactly what the card showed: the body may only be cut at 6000 for display, so send the original.
        msg_id = mailbox().send("alpha", subject, body, attachment)
    except k10_core.K10Error as e:
        note_error(e)
        k10_core.log("beta: send failed: %s" % (getattr(e, "detail", "") or e))
        emit({"kind": "k10_result", "id": draft["id"], "status": "failed", "detail": str(e)})
        return "The mail couldn't be sent: %s" % e
    except Exception as e:
        k10_core.log("beta: send failed: %s" % type(e).__name__)
        emit({"kind": "k10_result", "id": draft["id"], "status": "failed", "detail": "network problem"})
        return "The mail couldn't be sent (network problem): %s" % type(e).__name__
    emit({"kind": "k10_result", "id": draft["id"], "status": "sent"})
    return "Sent to ALPHA through K-10 (id %s) after Karachi approved it." % msg_id


def decide(draft_id, approve):
    with _lock:
        d = _drafts.get(str(draft_id))
        if not d or d["state"] != "asked":
            return False
        d["state"] = "approved" if approve else "rejected"
    d["decided"].set()
    return True


def cancel_all():
    with _lock:
        items = list(_drafts.values())
    for d in items:
        if d["state"] == "asked":
            d["state"] = "cancelled"
            d["decided"].set()


def start_poller():
    """Starts K-10 in the background and returns immediately - it never waits for the network. Safe to call twice."""
    LINK.start()
