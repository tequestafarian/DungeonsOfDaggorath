"""Render Dungeons of Daggorath mockups from the real ROM vector data.

Styles:
  original - 1983 PMODE 4 look (256x192 mono, NTSC artifact colour)
  lines    - CoCo 3 GIME 256x192x16: colour lines, light as brightness
  solid    - CoCo 3 GIME 256x192x16: shaded solid walls, raster-palette
             floor/ceiling, coloured creatures

Every CoCo 3 frame is checked: each scanline uses <= 16 colours, all from
the GIME's 64-colour RGB palette.

usage: python -I tools/render_mock.py [outdir]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image  # noqa: E402
from dodrom import (Rom, Scene, walk, glyph, text_codes, PAS, DOR, SDR, WAL,
                    NORSCL, CENTER_X, CENTER_Y, VIEW_H, brightness)  # noqa: E402

W, H = 256, 192


def rgb2(r, g, b):
    """CoCo 3 palette entry from 2-bit channels (0..3)."""
    return (r * 85, g * 85, b * 85)


# ---- 16-entry GIME palette ---------------------------------------------
PAL = [
    rgb2(0, 0, 0),   # 0 black
    rgb2(0, 0, 1),   # 1 stone dark
    rgb2(1, 1, 2),   # 2 stone mid
    rgb2(2, 2, 3),   # 3 stone light
    rgb2(3, 3, 3),   # 4 white
    rgb2(1, 0, 0),   # 5 wood dark
    rgb2(2, 1, 0),   # 6 wood
    rgb2(3, 2, 0),   # 7 gold
    rgb2(3, 0, 0),   # 8 red
    rgb2(0, 2, 0),   # 9 green
    rgb2(1, 3, 1),   # 10 lime
    rgb2(2, 0, 3),   # 11 violet
    rgb2(0, 3, 3),   # 12 cyan
    rgb2(0, 1, 3),   # 13 blue
    rgb2(3, 1, 0),   # 14 orange
    rgb2(0, 0, 0),   # 15 raster: floor/ceiling, rewritten per scanline
]
RASTER = 15

CREATURE_COLOR = {
    "SPIDER": 8, "VIPER": 10, "SGINT1": 14, "BLOB": 9, "KNIGT1": 13,
    "SGINT2": 6, "SCORP": 7, "KNIGT2": 3, "WRAITH": 11, "BALROG": 8,
    "WIZ0": 12, "WIZ1": 11,
}
OBJECT_COLOR = {"FFLASK": 12, "FRING": 7, "FSCROL": 4, "FSHIEL": 3,
                "FSWORD": 4, "FTORCH": 14}

# brightness level (0 dark .. 6 full) -> palette index
STONE_LINE = [0, 1, 1, 2, 2, 3, 3, 3]
# fills may be a (a, b) pair: a checkerboard dither of two palette entries
STONE_FILL = [0, 0, (0, 1), 1, 1, (1, 2), 2, 2]
STONE_FILL_SIDE = [0, 0, 0, (0, 1), 1, 1, (1, 2), 2]
WOOD_FILL = [0, 0, (0, 5), 5, 5, (5, 6), 6, 6]
WOOD_LINE = [0, 5, 5, 6, 6, 6, 7, 7]
# floor/ceiling colour per brightness for the raster palette entry
CEIL_RGB = [rgb2(0, 0, 0)] * 5 + [rgb2(0, 0, 1)] * 3
FLOOR_RGB = [rgb2(0, 0, 0)] * 3 + [rgb2(0, 0, 1)] * 3 + [rgb2(1, 1, 1)] * 2


class Frame:
    def __init__(self):
        self.px = [[0] * W for _ in range(H)]
        self.line_pal = [list(PAL) for _ in range(H)]

    def plot(self, x, y, c):
        if 0 <= x < W and 0 <= y < H:
            self.px[y][x] = c

    def hspan(self, y, x0, x1, c):
        if not 0 <= y < VIEW_H:
            return
        for x in range(max(0, x0), min(W - 1, x1) + 1):
            self.px[y][x] = c[(x + y) & 1] if isinstance(c, tuple) else c

    def poly(self, pts, c):
        """Scanline polygon fill, clipped to the view."""
        ys = [p[1] for p in pts]
        for y in range(max(0, min(ys)), min(VIEW_H - 1, max(ys)) + 1):
            xs = []
            n = len(pts)
            for i in range(n):
                (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % n]
                if y0 == y1:
                    continue
                if min(y0, y1) <= y < max(y0, y1):
                    xs.append(x0 + (y - y0) * (x1 - x0) / (y1 - y0))
            xs.sort()
            for i in range(0, len(xs) - 1, 2):
                self.hspan(y, int(round(xs[i])), int(round(xs[i + 1])) - 1, c)

    def to_image(self):
        img = Image.new("RGB", (W, H))
        p = img.load()
        for y in range(H):
            pal = self.line_pal[y]
            for x in range(W):
                p[x, y] = pal[self.px[y][x]]
        return img

    def check(self):
        legal = {rgb2(r, g, b) for r in range(4) for g in range(4) for b in range(4)}
        for y in range(H):
            assert len(self.line_pal[y]) == 16
            for c in self.line_pal[y]:
                assert c in legal, (y, c)


def dda(x0, y0, x1, y1, fadeval=0):
    """VECTOR.ASM's DDA: yields the dots the original routine plots."""
    dx, dy = x1 - x0, y1 - y0
    length = max(abs(dx), abs(dy))
    if length == 0 or fadeval < 0:
        return
    xx, yy = x0 + 0.5, y0 + 0.5
    sx, sy = dx / length, dy / length
    cnt = fadeval + 1
    for _ in range(length):
        cnt -= 1
        if cnt == 0:
            cnt = fadeval + 1
            if 0 <= xx < 256 and 0 <= yy < VIEW_H:
                yield int(xx), int(yy)
        xx += sx
        yy += sy


# ---- original style ----------------------------------------------------
def render_original(rom, scene, status, text):
    f = Frame()
    for c in walk(rom, scene):
        for s in c["segs"]:
            for x, y in dda(*s, fadeval=c["fade"]):
                f.plot(x, y, 1)
    draw_status_mono(rom, f, status, text)
    return artifact(f)


def artifact(f):
    """PMODE 4 on NTSC composite: pixel pairs bleed into blue/orange."""
    img = Image.new("RGB", (W, H))
    p = img.load()
    blue, orange, white = (40, 120, 255), (255, 120, 20), (255, 255, 255)
    for y in range(H):
        row = f.px[y]
        for x in range(0, W, 2):
            a, b = row[x], row[x + 1]
            c = white if a and b else orange if a else blue if b else (0, 0, 0)
            p[x, y] = p[x + 1, y] = c
    return img


def draw_text(rom, f, row_y, col, s, fg, bg=None):
    for i, code in enumerate(text_codes(s)):
        x0 = (col + i) * 8
        rows = glyph(rom, code)
        for r in range(8):
            for b in range(8):
                on = r >= 1 and b >= 1 and b <= 5 and (rows[r - 1] >> (5 - b)) & 1 \
                    if r < 8 else False
                if on:
                    f.plot(x0 + b, row_y + r, fg)
                elif bg is not None:
                    f.plot(x0 + b, row_y + r, bg)


def draw_status_mono(rom, f, status, text):
    y = VIEW_H
    for yy in range(y, y + 8):
        for x in range(W):
            f.px[yy][x] = 1
    left, right = status
    draw_text(rom, f, y, 0, left, 0, 1)
    draw_text(rom, f, y, 15, "<>", 0, 1)
    draw_text(rom, f, y, 32 - len(right), right, 0, 1)
    for i, line in enumerate(text[-4:]):
        draw_text(rom, f, y + 8 + i * 8, 0, line, 1)


# ---- CoCo 3 styles -----------------------------------------------------
def colour_for(c):
    b = c["bright"]
    k = c["kind"]
    if k in ("creature", "peek"):
        base = CREATURE_COLOR[c["name"]]
        return base if b >= 4 else STONE_LINE[b + 1] if b else 0
    if k == "object":
        base = OBJECT_COLOR[c["name"]]
        return base if b >= 4 else STONE_LINE[b + 1] if b else 0
    if k == "door":
        return WOOD_LINE[b]
    if k == "sdoor":
        return 11 if b >= 4 else 13 if b else 0
    if k == "vert":
        return WOOD_LINE[b]
    if k == "ceiling":
        return STONE_LINE[max(0, b - 1)]
    return STONE_LINE[b]


def draw_lines(f, c, col, thick=False, halo=False, segs=None):
    if col == 0 and not halo:
        return
    pts = []
    for s in (c["segs"] if segs is None else segs):
        pts.extend(dda(*s))
    if halo:
        for x, y in pts:
            for ox in (-1, 0, 1, 2) if thick else (-1, 0, 1):
                for oy in (-1, 0, 1):
                    if 0 <= y + oy < VIEW_H:
                        f.plot(x + ox, y + oy, 0)
    for x, y in pts:
        f.plot(x, y, col)
        if thick:
            f.plot(x + 1, y, col)


def render_lines(rom, scene, status, text):
    f = Frame()
    for c in walk(rom, scene):
        thick = c["kind"] in ("creature", "object", "peek") and c["range"] <= 1
        draw_lines(f, c, colour_for(c), thick=thick)
    draw_status_colour(rom, f, status, text)
    f.check()
    return f.to_image()


def run_segs(runs):
    return [(a[0], a[1], b[0], b[1]) for r in runs for a, b in zip(r, r[1:])]


def draw_vert(rom, f, c, b):
    """Holes are black pits with a stone rim; ladders are wood."""
    v = int(c["name"])
    hole = rom.addr("HOLEUP" if v in (0, 1) else "HOLEDN")
    _, runs = rom.segments(hole, NORSCL[c["range"]])
    for r in runs:
        if len(r) > 3:
            f.poly(r, 0)
    draw_lines(f, c, STONE_LINE[b], segs=run_segs(runs))
    if v in (1, 3):
        _, lr = rom.segments(rom.addr("LADDER"), NORSCL[c["range"]])
        draw_lines(f, c, WOOD_LINE[b], segs=run_segs(lr))


def scaled(pts, rng):
    s = NORSCL[rng]

    def sc(v, c):
        return c + int((v - c) * s / 128)
    return [(sc(x, CENTER_X), sc(y, CENTER_Y)) for x, y in pts]


# polygon outlines matching VARC.ASM geometry (screen x,y at scale 1:1)
LWALL_P = [(27, 16), (64, 38), (64, 114), (27, 136)]
RWALL_P = [(229, 16), (192, 38), (192, 114), (229, 136)]
FWALL_P = [(64, 38), (192, 38), (192, 114), (64, 114)]
LPAS_P = [(27, 38), (64, 38), (64, 114), (27, 114)]
RPAS_P = [(229, 38), (192, 38), (192, 114), (229, 114)]
LDOOR_P = [(40, 128), (40, 65), (56, 68), (56, 119)]
RDOOR_P = [(216, 128), (216, 65), (200, 68), (200, 119)]
FDOOR_P = [(108, 114), (108, 67), (148, 67), (148, 114)]


def cell_y(rng, edge):
    """Screen y of the floor (edge=136) / ceiling (16) at a range."""
    return CENTER_Y + int((edge - CENTER_Y) * NORSCL[rng] / 128)


def render_solid(rom, scene, status, text):
    f = Frame()
    calls = walk(rom, scene)
    light = scene.rlight

    # floor/ceiling: one raster palette write per scanline, lit by range
    for y in range(VIEW_H):
        f.px[y] = [RASTER] * W
        dist = abs(y + 0.5 - CENTER_Y)
        rng = 9
        for r in range(1, 10):
            if dist >= (136 - CENTER_Y) * NORSCL[r] / 128:
                rng = r - 1 if r > 1 else 0
                break
        b = brightness(light, rng)
        f.line_pal[y][RASTER] = CEIL_RGB[b] if y < CENTER_Y else FLOOR_RGB[b]

    by_range = {}
    for c in calls:
        by_range.setdefault(c["range"], []).append(c)

    for rng in sorted(by_range, reverse=True):
        group = by_range[rng]
        b = brightness(light, rng)
        bnext = brightness(light, rng + 1)
        # 1. architecture fills
        for c in group:
            k, side = c["kind"], c.get("side")
            if k == "passage" and side in ("L", "R"):
                f.poly(scaled(LPAS_P if side == "L" else RPAS_P, rng),
                       STONE_FILL[bnext])
            elif k in ("wall", "door"):
                if side == "F":
                    f.poly(scaled(FWALL_P, rng), STONE_FILL[b])
                else:
                    f.poly(scaled(LWALL_P if side == "L" else RWALL_P, rng),
                           STONE_FILL_SIDE[b])
                if k == "door":
                    dp = {"F": FDOOR_P, "L": LDOOR_P, "R": RDOOR_P}[side]
                    f.poly(scaled(dp, rng), WOOD_FILL[b])
        # 2. architecture outlines on top
        for c in group:
            if c["kind"] in ("wall", "passage", "sdoor"):
                draw_lines(f, c, colour_for(c))
            elif c["kind"] == "door":
                # runs 0-1 are the door and knob; the rest is the wall edge
                runs = c["runs"]
                draw_lines(f, c, WOOD_LINE[b], segs=run_segs(runs[:2]))
                draw_lines(f, c, STONE_LINE[b], segs=run_segs(runs[2:]))
            elif c["kind"] == "vert":
                draw_vert(rom, f, c, b)
        # 3. things in the cell, with a dark halo so they read on stone
        for c in group:
            if c["kind"] in ("creature", "object", "peek"):
                thick = c["range"] <= 1
                draw_lines(f, c, colour_for(c), thick=thick, halo=True)

    draw_status_colour(rom, f, status, text)
    f.check()
    return f.to_image()


def draw_status_colour(rom, f, status, text):
    y = VIEW_H
    for yy in range(y, H):
        f.px[yy] = [0] * W
        f.line_pal[yy] = list(PAL)
    for yy in range(y, y + 8):
        f.px[yy] = [1] * W
        f.line_pal[yy][1] = rgb2(1, 0, 1)      # status bar plum
    left, right = status
    draw_text(rom, f, y, 0, left, 7, 1)
    draw_text(rom, f, y, 15, "<>", 8, 1)
    draw_text(rom, f, y, 32 - len(right), right, 7, 1)
    for i, line in enumerate(text[-4:]):
        draw_text(rom, f, y + 8 + i * 8, 0, line, 12 if line.startswith(".") else 4)


# ---- scenes -------------------------------------------------------------
def corridor(n, sides=None, end=WAL):
    """Straight N-S corridor, player at row n-1 facing north."""
    walls = {}
    for r in range(n):
        walls[(r, 5)] = [PAS, WAL, PAS, WAL]
    walls[(0, 5)][0] = end
    for (r, d), feat in (sides or {}).items():
        walls[(r, 5)][d] = feat
        if feat == PAS:
            nb = (r, 5 + (1 if d == 1 else -1))
            walls[nb] = [WAL, PAS, WAL, PAS]
    return walls


SCENES = [
    dict(name="corridor", title="Pine torch corridor",
         scene=Scene(corridor(8, {(5, 3): PAS, (3, 1): PAS, (2, 3): DOR},
                              end=DOR), 7, 5, 0, rlight=7),
         status=("EMPTY", "PINE TORCH"), text=[".PULL RIGHT TORCH", ".USE RIGHT", "."]),
    dict(name="spider", title="Spider and loot, lunar torch",
         scene=Scene(corridor(6, {(3, 3): DOR, (2, 1): PAS}), 5, 5, 0, rlight=10,
                     mlight=4, creatures={(4, 5): "SPIDER"},
                     objects={(3, 5): ["FSWORD"], (2, 5): ["FFLASK"]}),
         status=("WOODEN SWORD", "LUNAR TORCH"), text=[".MOVE", ".ATTACK LEFT", "."]),
    dict(name="knight", title="Knight with a giant at the side passage",
         scene=Scene(corridor(5, {(3, 3): PAS}), 4, 5, 0, rlight=8, mlight=2,
                     creatures={(2, 5): "KNIGT1", (3, 4): "SGINT2"},
                     objects={(2, 5): ["FSHIEL"]}, vert={(1, 5): 3}),
         status=("IRON SWORD", "PINE TORCH"), text=[".TURN LEFT", ".TURN RIGHT", "."]),
    dict(name="wizard", title="The Wizard in solar light",
         scene=Scene(corridor(6, {(3, 1): SDR, (4, 3): DOR}), 5, 5, 0, rlight=13,
                     mlight=11, creatures={(3, 5): "WIZ1"},
                     objects={(4, 5): ["FRING"]}, vert={(2, 5): 0}),
         status=("ELVISH SWORD", "SOLAR TORCH"), text=[".INCANT ...", ".ATTACK RIGHT", "."]),
    dict(name="wraith", title="Wraith in the dark (magic light only)",
         scene=Scene(corridor(5, {(3, 3): PAS, (2, 1): PAS}), 4, 5, 0, rlight=6,
                     mlight=9, creatures={(2, 5): "WRAITH"}),
         status=("MITHRIL SHIELD", "LUNAR TORCH"), text=[".LOOK", "."]),
]

STYLES = [("original", render_original), ("lines", render_lines),
          ("solid", render_solid)]


def all_styles():
    from texture import render_textured
    return STYLES + [("textured", render_textured)]


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "build", "mock")
    os.makedirs(out, exist_ok=True)
    rom = Rom()
    for sc in SCENES:
        for style, fn in all_styles():
            img = fn(rom, sc["scene"], sc["status"], sc["text"])
            img = img.resize((W * 3, H * 3), Image.NEAREST)
            path = os.path.join(out, f"{sc['name']}_{style}.png")
            img.save(path)
            print(path)


if __name__ == "__main__":
    main()
