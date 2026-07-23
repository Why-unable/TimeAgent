"""Generate Time Agent PWA icons without third-party deps.

Draws a dark rounded tile with a clock face + hands, and writes PNGs used by
the web app manifest. Pure stdlib (zlib + struct) so it runs anywhere Python
3.12 is available.
"""

from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

BG = (15, 23, 42)  # #0f172a (theme-color)
FG = (226, 232, 240)  # slate-200 clock face outline / ticks
ACCENT = (56, 189, 248)  # sky-400 hands
FACE = (30, 41, 59)  # slate-800 inner face

PUBLIC = Path(__file__).resolve().parent.parent / "public"


def _blend(bg: tuple[int, int, int], fg: tuple[int, int, int], a: float) -> tuple[int, int, int]:
    return tuple(round(b + (f - b) * a) for b, f in zip(bg, fg))  # type: ignore[return-value]


def _write_png(path: Path, pixels: list[list[tuple[int, int, int]]]) -> None:
    height = len(pixels)
    width = len(pixels[0])
    raw = bytearray()
    for row in pixels:
        raw.append(0)  # filter type 0
        for r, g, b in row:
            raw += bytes((r, g, b))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )
    path.write_bytes(png)


def render(size: int, *, maskable: bool) -> list[list[tuple[int, int, int]]]:
    # Maskable icons need a safe zone; shrink the tile radius so the clock
    # survives Android's circular/rounded masks.
    corner = size * (0.5 if maskable else 0.22)
    cx = cy = (size - 1) / 2
    face_r = size * (0.30 if maskable else 0.34)
    outer_r = face_r + size * 0.02

    rows: list[list[tuple[int, int, int]]] = []
    for y in range(size):
        row: list[tuple[int, int, int]] = []
        for x in range(size):
            # Rounded-rect background (superellipse-ish via corner circles).
            in_tile = True
            for ox, oy in ((corner, corner), (size - corner, corner), (corner, size - corner), (size - corner, size - corner)):
                if ((x < corner or x > size - corner) and (y < corner or y > size - corner)):
                    if math.hypot(x - ox, y - oy) > corner:
                        in_tile = False
                        break
            if not in_tile:
                row.append((0, 0, 0))  # transparent-ish edge -> use bg; PNG has no alpha here
                # keep it bg so non-maskable also looks clean on dark UIs
                row[-1] = BG
                continue

            d = math.hypot(x - cx, y - cy)
            color = BG
            if d <= face_r:
                color = FACE
            if abs(d - outer_r) <= size * 0.018:
                color = FG

            # tick marks at 12/3/6/9
            for ang in (0, 90, 180, 270):
                tx = cx + math.cos(math.radians(ang)) * face_r * 0.82
                ty = cy + math.sin(math.radians(ang)) * face_r * 0.82
                if math.hypot(x - tx, y - ty) <= size * 0.02:
                    color = FG

            # hands: hour (up) and minute (right-ish)
            def on_hand(angle_deg: float, length: float, thick: float) -> bool:
                a = math.radians(angle_deg)
                hx, hy = math.cos(a), math.sin(a)
                px, py = x - cx, y - cy
                proj = px * hx + py * hy
                if proj < 0 or proj > face_r * length:
                    return False
                perp = abs(px * -hy + py * hx)
                return perp <= size * thick

            if on_hand(-90, 0.6, 0.028) or on_hand(-20, 0.82, 0.022):
                color = ACCENT
            if d <= size * 0.03:
                color = ACCENT

            row.append(color)
        rows.append(row)
    return rows


def main() -> None:
    PUBLIC.mkdir(parents=True, exist_ok=True)
    targets = [
        ("icon-192.png", 192, False),
        ("icon-512.png", 512, False),
        ("icon-maskable-512.png", 512, True),
        ("apple-touch-icon.png", 180, False),
    ]
    for name, size, maskable in targets:
        _write_png(PUBLIC / name, render(size, maskable=maskable))
        print(f"wrote {name} ({size}x{size})")


if __name__ == "__main__":
    main()
