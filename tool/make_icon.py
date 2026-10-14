"""Draw the app icon (an open book under one lit point; same geometry as ScripturesMark in lib/app/brand.dart) and write
every size the platforms need.

  .venv\\Scripts\\python.exe -I tool/make_icon.py

Outputs: assets/icons/app-icon-1024.png, assets/icons/scriptures-mark.svg, windows/runner/resources/app_icon.ico,
Android launcher icons. Brand grammar: structure in one ink colour, exactly one pink accent.
"""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
SS = 4  # supersampling for clean edges
NAVY, PINK, WHITE = (14, 24, 62, 255), (240, 109, 174, 255), (255, 255, 255, 255)

# the mark on a 100-unit grid: (kind, points, stroke width)
def geometry():
    segs = []
    for m in (-1, 1):
        x = lambda v: 50 + m * v  # noqa: E731
        page = [(50, 40), (x(36), 31), (x(36), 76), (50, 85), (50, 40)]
        segs.append((page, 3.6))
        for i in range(3):
            y = 46 + i * 10
            segs.append(([(x(28), y), (x(8), y + 4.5)], 2.4))
    segs.append(([(50, 24), (50, 40)], 2.4))
    return segs


def draw(size, inset=0.0):
    """Navy rounded tile, white structure, one pink dot. [inset] shrinks the mark (launcher safe zone)."""
    n = size * SS
    img = Image.new('RGBA', (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([n * 0.04, n * 0.04, n * 0.96, n * 0.96], radius=n * 0.2, fill=NAVY)
    scale = n * (0.62 - inset) / 100.0
    ox = (n - 100 * scale) / 2
    oy = (n - 100 * scale) / 2 + n * 0.01
    P = lambda x, y: (ox + x * scale, oy + y * scale)  # noqa: E731
    for pts, w in geometry():
        px = [P(*p) for p in pts]
        r = w * scale / 2
        d.line(px, fill=WHITE, width=max(1, int(w * scale)), joint='curve')
        for x, y in px:
            d.ellipse([x - r, y - r, x + r, y + r], fill=WHITE)
    cx, cy = P(50, 17)
    r = 7 * scale
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=PINK)
    return img.resize((size, size), Image.LANCZOS)


def svg():
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" fill="none" stroke="#0e183e" stroke-linecap="round" stroke-linejoin="round">']
    for pts, w in geometry():
        d = 'M' + ' L'.join(f'{x:g} {y:g}' for x, y in pts)
        parts.append(f'<path d="{d}" stroke-width="{w}"/>')
    parts.append('<circle cx="50" cy="17" r="7" fill="#d3167b" stroke="none"/></svg>')
    return '\n'.join(parts)


def main():
    out = ROOT / 'assets' / 'icons'
    out.mkdir(parents=True, exist_ok=True)
    draw(1024).save(out / 'app-icon-1024.png')
    (out / 'scriptures-mark.svg').write_text(svg(), 'utf-8')
    sizes = [16, 24, 32, 48, 64, 128, 256]
    ico = ROOT / 'windows' / 'runner' / 'resources' / 'app_icon.ico'
    draw(256).save(ico, format='ICO', sizes=[(s, s) for s in sizes])
    res = ROOT / 'android' / 'app' / 'src' / 'main' / 'res'
    for folder, px in {'mdpi': 48, 'hdpi': 72, 'xhdpi': 96, 'xxhdpi': 144, 'xxxhdpi': 192}.items():
        target = res / f'mipmap-{folder}' / 'ic_launcher.png'
        if target.parent.exists():
            draw(px).save(target)
    print('icon written:', ico, ico.stat().st_size, 'bytes')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
