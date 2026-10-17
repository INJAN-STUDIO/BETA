"""
Run this ONCE on your laptop to make the two keys B.E.T.A. needs to send notifications:

    pip install cryptography
    python make_vapid_keys.py

It prints two lines. In Render > your service > Environment, add them as:
    VAPID_PUBLIC_KEY   = (the first value)
    VAPID_PRIVATE_KEY  = (the second value)
The private key is a secret: don't put it in the code or in the repo, and don't share it.
(Optional extras: VAPID_SUBJECT = mailto:you@example.com, and PUSH_PREVIEW = on to show the start of the reply
in the notification. Without PUSH_PREVIEW the notification just says "Your reply is ready.")
"""
import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


key = ec.generate_private_key(ec.SECP256R1())
private_raw = key.private_numbers().private_value.to_bytes(32, "big")
public_raw = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)

print("VAPID_PUBLIC_KEY=" + b64(public_raw))
print("VAPID_PRIVATE_KEY=" + b64(private_raw))
