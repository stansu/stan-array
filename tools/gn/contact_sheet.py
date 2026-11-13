#!/usr/bin/env python3
"""Compose demo/stan_*.png into demo/stan_contact.png (needs Pillow).

    python3 tools/gn/contact_sheet.py
    python3 tools/gn/contact_sheet.py --dir demo --cols 4
"""

import argparse
import os

ORDER = ["fence", "tiles", "hex", "tri", "brick", "lamp", "bracelet", "scatter", "locators"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "demo"))
    ap.add_argument("--cols", type=int, default=3)
    ap.add_argument("--out", default="stan_contact.png")
    args = ap.parse_args()

    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("需要 Pillow：pip install pillow（或直接看 demo/stan_*.png）")
        return 0

    images = []
    for name in ORDER:
        path = os.path.join(args.dir, "stan_%s.png" % name)
        if os.path.exists(path):
            images.append((name, Image.open(path).convert("RGB")))
    if not images:
        print("找不到 demo/stan_*.png")
        return 1

    w, h = images[0][1].size
    cols = max(1, args.cols)
    rows = (len(images) + cols - 1) // cols
    pad = 10
    sheet = Image.new("RGB", (cols * w + (cols + 1) * pad,
                              rows * h + (rows + 1) * pad), (16, 16, 18))
    draw = ImageDraw.Draw(sheet)
    for i, (name, img) in enumerate(images):
        x = pad + (i % cols) * (w + pad)
        y = pad + (i // cols) * (h + pad)
        sheet.paste(img, (x, y))
        draw.rectangle([x + 12, y + 12, x + 160, y + 38], fill=(12, 12, 14))
        draw.text((x + 22, y + 19), name.upper(), fill=(240, 240, 240))

    out = os.path.join(args.dir, args.out)
    sheet.save(out)
    print("CONTACT", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
