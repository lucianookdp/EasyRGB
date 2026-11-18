"""Gera o ícone (app/icon.ico, docs/icon.png) e a prévia social (docs/social-preview.png).

Rodar:  python tools/make_assets.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app" / "lib"))
from PIL import Image, ImageChops, ImageDraw, ImageFont  # noqa: E402

BG = (24, 24, 27, 255)


def logo(size=256):
    """Três círculos RGB somados (como luz) num quadrado arredondado escuro."""
    s = size * 4  # desenha grande e reduz: bordas suaves
    base = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(base).rounded_rectangle([0, 0, s - 1, s - 1], radius=s // 4, fill=BG)
    light = Image.new("RGB", (s, s), (0, 0, 0))
    r = int(s * 0.19)
    for (cx, cy), color in (((0.50, 0.395), (255, 59, 78)), ((0.39, 0.58), (34, 211, 107)),
                            ((0.61, 0.58), (59, 130, 246))):
        layer = Image.new("RGB", (s, s), (0, 0, 0))
        ImageDraw.Draw(layer).ellipse([cx * s - r, cy * s - r, cx * s + r, cy * s + r], fill=color)
        light = ImageChops.screen(light, layer)
    mask = light.convert("L").point(lambda v: 255 if v > 0 else 0)
    base.paste(light, (0, 0), mask)
    return base.resize((size, size), Image.LANCZOS)


def font(px, bold=False):
    for name in (("segoeuib.ttf" if bold else "segoeui.ttf"), "arial.ttf"):
        try:
            return ImageFont.truetype(name, px)
        except OSError:
            continue
    return ImageFont.load_default()


def social_preview():
    W, H = 1280, 640
    img = Image.new("RGB", (W, H), (9, 9, 11))
    d = ImageDraw.Draw(img)
    for i in range(H):  # leve brilho colorido no fundo
        t = i / H
        d.line([(0, i), (W, i)], fill=(int(9 + 18 * (1 - t)), 9, int(11 + 22 * t)))
    img.paste(logo(120), (80, 90), logo(120))
    d.text((80, 240), "EasyRGB", font=font(84, True), fill=(250, 250, 250))
    d.text((84, 345), "Your PC's RGB, set up by AI.", font=font(34), fill=(212, 212, 216))
    d.text((84, 402), "Open-source RGB controller for Windows", font=font(24), fill=(161, 161, 170))
    d.text((84, 438), "Palettes · effects · music · game mode", font=font(24), fill=(161, 161, 170))
    bar = [(255, 46, 136), (255, 107, 61), (255, 181, 71), (155, 61, 255), (0, 217, 200)]
    for x in range(84, 84 + 480):
        t = (x - 84) / 480 * (len(bar) - 1)
        k = min(int(t), len(bar) - 2)
        c = tuple(int(bar[k][j] + (bar[k + 1][j] - bar[k][j]) * (t - k)) for j in range(3))
        d.line([(x, 510), (x, 520)], fill=c)
    shot = ROOT / "docs" / "screenshot.png"
    if shot.exists():
        s = Image.open(shot).convert("RGB")
        s = s.crop((0, 0, s.width, int(s.width * 0.75)))
        s.thumbnail((500, 400))
        frame = Image.new("RGB", (s.width + 2, s.height + 2), (51, 51, 58))
        frame.paste(s, (1, 1))
        img.paste(frame, (W - frame.width - 60, (H - frame.height) // 2))
    return img


if __name__ == "__main__":
    icon = logo(256)
    icon.save(ROOT / "app" / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    icon.save(ROOT / "docs" / "icon.png")
    social_preview().save(ROOT / "docs" / "social-preview.png", optimize=True)
    print("ok: app/icon.ico, docs/icon.png, docs/social-preview.png")
