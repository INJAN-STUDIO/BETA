"""
Run this ONCE (on any computer with Python + Pillow) to find out which FLUX.2 request shape Cloudflare accepts.
It sends 5 small test requests and prints OK or the exact error for each. Each one costs only a few Neurons.

  export CLOUDFLARE_ACCOUNT_ID=...   export CLOUDFLARE_API_TOKEN=...
  python flux2_test.py                 # tests flux-2-klein-4b (the default)
  python flux2_test.py @cf/black-forest-labs/flux-2-dev     # or name another model
  python flux2_test.py klein-4b some_reference.jpg          # optional: use your own picture (any size, gets shrunk)

Put it in the same folder as image_gen.py and image_search.py.
"""
import io
import os
import sys

import image_gen as ig


def make_ref(path=None):
    from PIL import Image, ImageDraw
    if path:
        im = Image.open(path).convert("RGB")
    else:
        im = Image.new("RGB", (400, 300), (30, 30, 60))
        d = ImageDraw.Draw(im)
        d.ellipse((120, 60, 280, 220), fill=(220, 60, 60))
    im.thumbnail((480, 480))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=85)
    return out.getvalue()


def main():
    acct, tok = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip(), os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    if not acct or not tok:
        sys.exit("Set CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN first.")
    model = ig.CF_REF_MODEL
    path = None
    for a in sys.argv[1:]:
        if a.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            path = a
        elif a.startswith("@cf/"):
            model = a
        else:
            model = "@cf/black-forest-labs/flux-2-" + a
    img = make_ref(path)
    url = "%s/%s/ai/run/%s" % (ig.CF_ROOT, acct, model)
    one = {"input_image_0": ("r0.jpg", "image/jpeg", img)}
    three = {"input_image_%d" % i: ("r%d.jpg" % i, "image/jpeg", img) for i in range(3)}
    p = "a red sun over a dark sea, simple illustration"
    tests = [
        ("A  prompt only", {"prompt": p}, {}),
        ("B  prompt + 1 picture", {"prompt": p}, one),
        ("C  prompt + 3 pictures", {"prompt": p}, three),
        ("D  3 pictures + width/height 768x1360", {"prompt": p, "width": 768, "height": 1360}, three),
        ("E  3 pictures + width/height + steps=20", {"prompt": p, "width": 768, "height": 1360, "steps": 20}, three),
    ]
    print("Model:", model, "| reference picture: %d bytes" % len(img))
    for name, fields, files in tests:
        try:
            data = ig._flux2_request(url, tok, fields, files, 120)
            ok = bool((data.get("result") or {}).get("image"))
            print("%-45s %s" % (name, "OK" if ok else "answered but no picture"))
        except ig.ImageGenError as e:
            print("%-45s FAILED: %s" % (name, e.user_message))


if __name__ == "__main__":
    main()
