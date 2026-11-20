"""Gera o ícone (app/icon.ico, app/icon.png, docs/icon.png) e a prévia social (docs/social-preview.png).

Ícone: brilho de 4 pontas vazado, com o colorido RGB em volta (gradiente cônico) e uma bola colorida no meio.
Rodar:  python tools/make_assets.py
"""
import colorsys
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app" / "lib"))
sys.path.insert(0, str(ROOT / "app" / "lib" / f"py{sys.version_info[0]}{sys.version_info[1]}"))
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont  # noqa: E402

BG = (17, 17, 20, 255)
_cache = {}


def _conic(s, start=0.62):
    """Gradiente de matiz em volta do centro (o colorido RGB do ícone)."""
    key = (s, start)
    if key not in _cache:
        im = Image.new("RGB", (s, s))
        px, c = im.load(), s / 2
        for y in range(s):
            for x in range(s):
                h = (math.atan2(y - c, x - c) / (2 * math.pi) + start) % 1.0
                r, g, b = colorsys.hsv_to_rgb(h, 1, 1)
                px[x, y] = (int(r * 255), int(g * 255), int(b * 255))
        _cache[key] = im
    return _cache[key]


def _sparkle(s, cx, cy, R, pinch=0.08):
    """Estrela de 4 pontas com lados curvos."""
    pts, outer = [], [(cx, cy - R), (cx + R, cy), (cx, cy + R), (cx - R, cy)]
    for i in range(4):
        a, b = outer[i], outer[(i + 1) % 4]
        ctrl = (cx + (a[0] + b[0] - 2 * cx) * pinch, cy + (a[1] + b[1] - 2 * cy) * pinch)
        for k in range(48):
            t = k / 48
            pts.append(((1 - t) ** 2 * a[0] + 2 * (1 - t) * t * ctrl[0] + t ** 2 * b[0],
                        (1 - t) ** 2 * a[1] + 2 * (1 - t) * t * ctrl[1] + t ** 2 * b[1]))
    m = Image.new("L", (s, s), 0)
    ImageDraw.Draw(m).polygon(pts, fill=255)
    return m


def tray_logo(size=64):
    """Versão da bandeja: mesmo desenho, mas contorno grosso, ocupando o quadrado e sem brilho difuso,
    para continuar nítido em 16-32 px (o Windows desenha os ícones da bandeja bem pequenos)."""
    s = 512
    cx = cy = s / 2
    R, w = s * 0.5, s * 0.13
    outline = ImageChops.subtract(_sparkle(s, cx, cy, R, pinch=0.22), _sparkle(s, cx, cy, R - w * 1.9, pinch=0.22))
    ball = Image.new("L", (s, s), 0)
    r = s * 0.11
    ImageDraw.Draw(ball).ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)
    out = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    out.paste(_conic(s), (0, 0), ImageChops.lighter(outline, ball))
    return out.resize((size, size), Image.LANCZOS)


def logo(size=256, background=True):
    s = 512
    cx, cy, R, w = s * 0.5, s * 0.5, s * 0.36, s * 0.05
    outline = ImageChops.subtract(_sparkle(s, cx, cy, R), _sparkle(s, cx, cy, R - w * 1.9))
    ball = Image.new("L", (s, s), 0)
    r = s * 0.062
    ImageDraw.Draw(ball).ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)
    art = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    art.paste(_conic(s), (0, 0), ImageChops.lighter(outline, ball))
    out = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    if background:
        ImageDraw.Draw(out).rounded_rectangle([0, 0, s - 1, s - 1], radius=s // 4, fill=BG)
    glow = art.filter(ImageFilter.GaussianBlur(26))
    out.alpha_composite(Image.blend(Image.new("RGBA", (s, s), (0, 0, 0, 0)), glow, 0.85))
    out.alpha_composite(art)
    if background:   # o brilho não passa da borda do quadrado
        sq = Image.new("L", (s, s), 0)
        ImageDraw.Draw(sq).rounded_rectangle([0, 0, s - 1, s - 1], radius=s // 4, fill=255)
        out.putalpha(ImageChops.multiply(out.split()[3], sq))
    return out.resize((size, size), Image.LANCZOS)


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
    mark = tray_logo(120)
    img.paste(mark, (80, 90), mark)
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
    # O mesmo desenho em todo lugar: brilho de traço grosso, sem fundo (nítido do favicon ao atalho).
    icon = tray_logo(256)
    icon.save(ROOT / "app" / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    icon.save(ROOT / "app" / "icon.png")     # favicon e logo do topo da página
    tray_logo(64).save(ROOT / "app" / "tray.png")   # bandeja
    icon.save(ROOT / "docs" / "icon.png")    # logo do README
    social_preview().save(ROOT / "docs" / "social-preview.png", optimize=True)
    print("ok: app/icon.ico, app/icon.png, docs/icon.png, docs/social-preview.png")
