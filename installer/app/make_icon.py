"""Draw Penwise's icons: the app's, installer/app/Penwise.icns (a white pen nib on a blue rounded
square, on the grid of macOS app icons), and the menu bar's, the same nib alone
(src/penwise/hammerspoon/Penwise.spoon/menubar.png). The app's square stays within the shape macOS
26 gives every icon, with no shadow of its own: an icon with anything outside it is shrunk onto a
gray tile. Run it again only to change them:

    uv run --no-project --with pillow python installer/app/make_icon.py
"""

import io
import math
import struct
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

ROOT = Path(__file__).resolve().parent.parent.parent
SIZE = 1024
SCALE = 4  # drawn larger, then made smaller by averaging: smooth edges, nothing past them
TOP, BOTTOM = (91, 155, 255), (37, 82, 201)
# Every size macOS looks for in an app's icon, as `iconutil` writes them: PNG images.
ICNS_SIZES = [
    (b"icp4", 16),
    (b"icp5", 32),
    (b"icp6", 64),
    (b"ic07", 128),
    (b"ic08", 256),
    (b"ic09", 512),
    (b"ic10", 1024),  # 512 points on a Retina screen
    (b"ic11", 32),
    (b"ic12", 64),
    (b"ic13", 256),
    (b"ic14", 512),
]


def curve(start, control, end, steps=48):
    """Points along a quadratic Bézier curve."""
    return [
        tuple((1 - t) ** 2 * a + 2 * (1 - t) * t * b + t**2 * c for a, b, c in zip(start, control, end, strict=True))
        for t in (i / steps for i in range(steps + 1))
    ]


def nib(draw, center, unit, angle, slit=0.06, hole=0.12):
    """The nib, its tip down at `angle` degrees, `unit` pixels per half its height. `slit` and
    `hole`: their sizes, larger when the nib is drawn small."""
    turn = math.radians(angle)

    def place(points):
        return [
            (
                center[0] + unit * (x * math.cos(turn) - y * math.sin(turn)),
                center[1] + unit * (x * math.sin(turn) + y * math.cos(turn)),
            )
            for x, y in points
        ]

    right = curve((0.5, -0.1), (0.47, 0.55), (0, 1.0))
    left = [(-x, y) for x, y in reversed(right)]
    body = [(-0.42, -0.56), (0.42, -0.56), *right, *left]
    draw.polygon(place(body), fill=255)
    collar = [(-0.42, -1.0), (0.42, -1.0), (0.42, -0.68), (-0.42, -0.68)]
    draw.polygon(place(collar), fill=255)
    draw.line(place([(0, -0.1), (0, 1.05)]), fill=0, width=round(unit * slit))
    middle = place([(0, -0.12)])[0]
    radius = unit * hole
    draw.ellipse([middle[0] - radius, middle[1] - radius, middle[0] + radius, middle[1] + radius], fill=0)


def squircle(size: float, inset: float, radius: float, smoothing: float = 0.6, steps: int = 48) -> list:
    """The rounded square of macOS icons, `inset` from the edges: corners that ease out of the
    straight edges ("corner smoothing" 60%, as figma-squircle draws them), not plain arcs."""
    arc = 90 * (1 - smoothing)  # degrees of plain arc left in the middle of each corner
    arc_length = math.sin(math.radians(arc / 2)) * radius * math.sqrt(2)
    alpha = (90 - arc) / 2
    c = radius * math.tan(math.radians(alpha / 2)) * math.cos(math.radians(45 * smoothing))
    d = c * math.tan(math.radians(45 * smoothing))
    span = (1 + smoothing) * radius  # how far along each edge the corner reaches
    b = (span - arc_length - c - d) / 3
    a = 2 * b

    def cubic(p0, p1, p2, p3):
        return [
            tuple(
                (1 - u) ** 3 * w + 3 * (1 - u) ** 2 * u * x + 3 * (1 - u) * u**2 * y + u**3 * z
                for w, x, y, z in zip(p0, p1, p2, p3, strict=True)
            )
            for u in (i / steps for i in range(1, steps + 1))
        ]

    # The top right corner, in from the right and down from the top.
    start = (span, 0.0)
    eased_in = (span - a - b - c, d)
    corner = [start, *cubic(start, (span - a, 0.0), (span - a - b, 0.0), eased_in)]
    centre = (radius, radius)
    for i in range(1, steps + 1):
        angle = math.radians(-90 + alpha + arc * i / steps)  # clockwise, round the plain arc
        corner.append((centre[0] - radius * math.cos(angle), centre[1] + radius * math.sin(angle)))
    eased_out = corner[-1]
    end = (0.0, span)
    corner += cubic(eased_out, (eased_out[0] - d, eased_out[1] + c), (eased_out[0] - d, eased_out[1] + b + c), end)
    low, high = inset, size - inset
    return [
        *((high - x, low + y) for x, y in corner),  # top right
        *((high - y, high - x) for x, y in corner),  # bottom right
        *((low + x, high - y) for x, y in corner),  # bottom left
        *((low + y, low + x) for x, y in corner),  # top left
    ]


def icon() -> Image.Image:
    big = SIZE * SCALE
    # Apple's grid: an 824-point square, 100 points in, its corners 185.4 points round; 2 points
    # smaller all round, to stay inside the shape macOS gives icons.
    inset, radius = 102 * SCALE, 184.5 * SCALE
    square = Image.new("L", (big, big), 0)
    ImageDraw.Draw(square).polygon(squircle(big, inset, radius), fill=255)

    gradient = Image.new("RGB", (1, big))
    for y in range(big):
        t = min(max((y - inset) / (big - 2 * inset), 0), 1)
        gradient.putpixel((0, y), tuple(round(a + (b - a) * t) for a, b in zip(TOP, BOTTOM, strict=True)))
    gradient = gradient.resize((big, big))

    glyph = Image.new("L", (big, big), 0)
    nib(ImageDraw.Draw(glyph), (big * 0.477, big * 0.523), big * 0.25, 45)  # optically centred

    out = Image.new("RGBA", (big, big), (0, 0, 0, 0))  # no shadow: macOS draws its own
    out.paste(gradient, (0, 0), square)
    out.paste((255, 255, 255), (0, 0), ImageChops.multiply(glyph, square))
    return out.resize((SIZE, SIZE), Image.BOX)


def icns(image: Image.Image) -> bytes:
    """An .icns file with every size, and its table of contents first, as `iconutil` makes it."""
    entries = []
    for kind, size in ICNS_SIZES:
        png = io.BytesIO()
        image.resize((size, size), Image.BOX).save(png, "PNG", optimize=True)
        entries.append(kind + struct.pack(">I", len(png.getvalue()) + 8) + png.getvalue())
    toc = b"".join(entry[:8] for entry in entries)
    body = b"TOC " + struct.pack(">I", len(toc) + 8) + toc + b"".join(entries)
    return b"icns" + struct.pack(">I", len(body) + 8) + body


def menubar(points=18) -> Image.Image:
    """The nib alone, black on clear: a template image, which macOS draws in the menu bar's own
    colour. `points` high, drawn for Retina screens."""
    size, big = points * 2, points * 2 * 16
    glyph = Image.new("L", (big, big), 0)
    nib(ImageDraw.Draw(glyph), (big * 0.47, big * 0.53), big * 0.39, 45, slit=0.11, hole=0.16)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.putalpha(glyph.resize((size, size), Image.BOX))
    return out


if __name__ == "__main__":
    app = Path(__file__).with_name("Penwise.icns")
    app.write_bytes(icns(icon()))
    bar = ROOT / "src" / "penwise" / "hammerspoon" / "Penwise.spoon" / "menubar.png"
    menubar().save(bar, optimize=True)
    print(app, bar, sep="\n")
