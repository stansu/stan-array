#!/usr/bin/env python3
"""Compose demo/stan_*.png into demo/stan_contact.png (needs Pillow).

    python3 tools/gn/contact_sheet.py
    python3 tools/gn/contact_sheet.py --dir demo --cols 4
    python3 tools/gn/contact_sheet.py --prefix box_ --out box_contact.png
"""

import argparse
import os

ORDER = ["fence", "tiles", "hex", "tri", "brick", "patterns", "chevron", "lamp", "bracelet", "scatter", "locators"]
BOX_ORDER = ["solid", "hollow", "plug", "scatter", "corner"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "demo"))
    ap.add_argument("--cols", type=int, default=3)
    ap.add_argument("--out", default="stan_contact.png")
    ap.add_argument("--prefix", default="stan_",
                    help="PNG prefix: stan_ (Stan Array) or box_ (Stan Box)")
    args = ap.parse_args()

    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("需要 Pillow：pip install pillow（或直接看 demo/*.png）")
        return 0

    order = BOX_ORDER if args.prefix == "box_" else ORDER
    images = []
    for name in order:
        path = os.path.join(args.dir, args.prefix + name + ".png")
        if os.path.exists(path):
            images.append((name, Image.open(path).convert("RGB")))
    if not images:
        print("找不到 demo/%s*.png" % args.prefix)
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
