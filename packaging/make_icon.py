"""Uygulama logosundan (static/brand-mark.svg) exe ve kurulum simgesi üretir: akademik-iz.ico ve akademik-iz-128.png.

    python packaging/make_icon.py

SVG, Playwright'ın Chromium'uyla saydam arka planda çizilir (ayrı bir SVG kütüphanesi gerekmez); ICO, Pillow ile
Windows'un kullandığı boyutları içerecek biçimde yazılır.
"""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
SVG = (ROOT / "static" / "brand-mark.svg").read_text(encoding="utf-8")
OUT = Path(__file__).resolve().parent


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 512, "height": 512}, device_scale_factor=1)
        page.set_content(f"<html><body style='margin:0;background:transparent'>"
                         f"<div style='width:512px;height:512px'>{SVG.replace('<svg ', '<svg width=\"512\" height=\"512\" ', 1)}</div></body></html>")
        png = page.screenshot(omit_background=True, clip={"x": 0, "y": 0, "width": 512, "height": 512})
        browser.close()
    image = Image.open(io.BytesIO(png)).convert("RGBA")
    image.save(OUT / "akademik-iz.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    image.resize((128, 128), Image.LANCZOS).save(OUT / "akademik-iz-128.png")
    # Kurulum sihirbazının küçük görseli (55x58 içinde logo, beyaz zemin).
    small = Image.new("RGB", (110, 116), "white")
    small.paste(image.resize((96, 96), Image.LANCZOS), (7, 10), image.resize((96, 96), Image.LANCZOS))
    small.save(OUT / "wizard-small.bmp")
    # Kurulum sihirbazının sol şeridi (164x314): marka mavisi zemin, ortada logo.
    big = Image.new("RGB", (328, 628), (29, 78, 216))
    logo = image.resize((200, 200), Image.LANCZOS)
    big.paste(logo, (64, 180), logo)
    big.save(OUT / "wizard-large.bmp")
    print("simgeler yazildi:", OUT)


if __name__ == "__main__":
    main()
