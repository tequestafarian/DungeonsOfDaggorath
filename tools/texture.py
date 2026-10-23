"""Textured dungeon style for the CoCo 3 mockups.

Builds on render_mock's 'solid' style:
  - walls are coursed stone blocks with black mortar, in perspective
  - the floor is flagstones, the ceiling is near-black stone
  - each block/flagstone takes its own shade from a hash of its maze
    cell, so the texture is fixed to the world, not the screen
  - light falls off continuously with depth (the game's own formula,
    RLIGHT - range, evaluated per block) and is rendered with a 4x4
    ordered dither between neighbouring palette shades

All of it maps to 6809 work the game can afford: filling small quads
with precomputed dither byte patterns, plus mortar lines through the
existing VECTOR routine.
"""
from render_mock import (Frame, W, VIEW_H, CENTER_X, CENTER_Y, NORSCL, rgb2,
                         walk, draw_lines, draw_vert, run_segs, colour_for,
                         draw_status_colour, scaled, LWALL_P, RWALL_P, FWALL_P,
                         LPAS_P, RPAS_P, LDOOR_P, RDOOR_P, FDOOR_P)
import render_mock

# 16-entry palette for this style: darker stone ramp
PAL_T = [
    rgb2(0, 0, 0),   # 0 black
    rgb2(0, 0, 1),   # 1 stone shadow (blue-black)
    rgb2(1, 1, 1),   # 2 stone
    rgb2(1, 1, 2),   # 3 stone lit
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
    rgb2(2, 2, 2),   # 15 stone highlight (near edges)
]

WALL_RAMP = [0, 2, 15]
FLOOR_RAMP = [0, 2]
CEIL_RAMP = [0, 0]          # black; only the beam joints show
WOOD_RAMP = [0, 5, 6]

BAYER = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]


def hash01(*k):
    h = 2166136261
    for v in k:
        h = ((h ^ (v & 0xFFFFFFFF)) * 16777619) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 0x5bd1e995) & 0xFFFFFFFF
    h ^= h >> 15
    return (h & 0xFFFF) / 65536.0


def dither(ramp, tone):
    """Colour function for a tone 0..1 over a ramp, 4x4 ordered dither,
    with a sparse dark speckle for rough stone."""
    tone = max(0.0, min(1.0, tone))
    pos = tone * (len(ramp) - 1)
    lo = int(pos)
    frac = pos - lo
    hi = min(lo + 1, len(ramp) - 1)

    def col(x, y):
        c = hi if BAYER[y & 3][x & 3] < frac * 16 else lo
        if c > 0 and hash01(x, y, 7) < 0.06:
            c -= 1
        return ramp[c]
    return col


def lum_at(light, depth):
    """Continuous form of SETFAX: full at light-7 >= depth, dark 7 later."""
    v = (light - depth) / 7.0
    v = max(0.0, min(1.0, v))
    return v ** 1.6 * 0.85      # pulled down: this is a dungeon


def poly_fn(f, pts, colfn):
    ys = [p[1] for p in pts]
    for y in range(max(0, int(min(ys))), min(VIEW_H - 1, int(max(ys))) + 1):
        yc = y + 0.5
        xs = []
        n = len(pts)
        for i in range(n):
            (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % n]
            if y0 == y1:
                continue
            if min(y0, y1) <= yc < max(y0, y1):
                xs.append(x0 + (yc - y0) * (x1 - x0) / (y1 - y0))
        xs.sort()
        for i in range(0, len(xs) - 1, 2):
            for x in range(max(0, int(round(xs[i]))), min(W - 1, int(round(xs[i + 1])) - 1) + 1):
                f.px[y][x] = colfn(x, y)


def line(f, a, b, c):
    x0, y0, x1, y1 = (int(round(v)) for v in (*a, *b))
    n = max(abs(x1 - x0), abs(y1 - y0), 1)
    for i in range(n + 1):
        x = x0 + (x1 - x0) * i / n
        y = y0 + (y1 - y0) * i / n
        xi, yi = int(round(x)), int(round(y))
        if 0 <= xi < W and 0 <= yi < VIEW_H:
            f.px[yi][xi] = c


# ---- surface parameterisations ----------------------------------------
def lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def persp(near_a, near_b, far_a):
    """Surface running into the screen.  u across near edge a->b,
    t depth 0 (near) .. 1 (far), perspective-correct along t."""
    c = (CENTER_X, CENTER_Y)
    dn = abs(near_a[0] - c[0]) + abs(near_a[1] - c[1])
    df = abs(far_a[0] - c[0]) + abs(far_a[1] - c[1])
    rho = df / dn

    def P(u, t):
        n = lerp(near_a, near_b, u)
        g = 1.0 / ((1 - t) + t / rho)
        return (c[0] + (n[0] - c[0]) * g, c[1] + (n[1] - c[1]) * g)
    return P


def flat(tl, tr, br, bl):
    """Surface facing the viewer: bilinear."""
    def P(u, v):
        return lerp(lerp(tl, tr, u), lerp(bl, br, u), v)
    return P


def sc(pt, rng):
    s = NORSCL[rng] / 128.0
    return (CENTER_X + (pt[0] - CENTER_X) * s, CENTER_Y + (pt[1] - CENTER_Y) * s)


def bricks(f, P, rows, cols, seed, tone_of, ramp, mortar=0, stagger=True,
           along_v=False, depth_of=None):
    """Lay a grid of blocks on surface P(u, v), u/v in 0..1.

    cols run along u, rows along v; odd rows shift half a block.
    tone_of(u_mid, v_mid, h) gives the block's tone.
    """
    for r in range(rows):
        v0, v1 = r / rows, (r + 1) / rows
        off = 0.5 / cols if stagger and r % 2 else 0.0
        for j in range(-1, cols + 1):
            u0 = max(0.0, j / cols + off)
            u1 = min(1.0, (j + 1) / cols + off)
            if u1 <= u0:
                continue
            h = hash01(*seed, r, j)
            tone = tone_of((u0 + u1) / 2, (v0 + v1) / 2, h)
            if along_v:
                quad = [P(v0, u0), P(v0, u1), P(v1, u1), P(v1, u0)]
            else:
                quad = [P(u0, v0), P(u1, v0), P(u1, v1), P(u0, v1)]
            poly_fn(f, quad, dither(ramp, tone))
            size = min(abs(quad[2][1] - quad[0][1]) + abs(quad[2][0] - quad[0][0]),
                       abs(quad[1][0] - quad[0][0]) + abs(quad[3][1] - quad[0][1]))
            if size >= 5 and tone > 0.08:
                line(f, quad[0], quad[1], mortar)
                line(f, quad[0], quad[3], mortar)


def render_textured(rom, scene, status, text):
    f = Frame()
    f.line_pal = [list(PAL_T) for _ in range(len(f.line_pal))]
    calls = walk(rom, scene)
    light = scene.rlight
    for y in range(VIEW_H):
        f.px[y] = [0] * W

    by_range = {}
    for c in calls:
        by_range.setdefault(c["range"], []).append(c)

    for rng in sorted(by_range, reverse=True):
        group = by_range[rng]
        cell = group[0]["cell"]
        nxt = min(rng + 1, 9)

        # floor and ceiling of this cell (flagstones / dark stone)
        fl = persp(sc((27, 136), rng), sc((229, 136), rng), sc((64, 114), rng))
        bricks(f, lambda u, t: fl(u, t), 2, 2, (cell[0], cell[1], 99),
               lambda u, t, h: lum_at(light, rng + t) * (0.35 + 0.45 * h),
               FLOOR_RAMP, along_v=False)
        ce = persp(sc((27, 16), rng), sc((229, 16), rng), sc((64, 38), rng))
        bricks(f, lambda u, t: ce(u, t), 2, 1, (cell[0], cell[1], 98),
               lambda u, t, h: lum_at(light, rng + t) * 0.3,
               CEIL_RAMP, mortar=1)

        b = render_mock.brightness(light, rng)
        for c in group:
            k, side = c["kind"], c.get("side")
            if side not in ("L", "R", "F"):
                continue
            seed = (cell[0], cell[1], ord(side))
            if k == "passage" and side in ("L", "R"):
                # far wall of the side corridor, plus its floor/ceiling wedges
                p = scaled(LPAS_P if side == "L" else RPAS_P, rng)
                tl, tr, br, bl = (sc(q, rng) for q in (LPAS_P if side == "L" else RPAS_P))
                bricks(f, flat(tl, tr, br, bl), 3, 2, seed,
                       lambda u, v, h: lum_at(light, rng + 1) * (0.4 + 0.35 * h),
                       WALL_RAMP)
                ex = 27 if side == "L" else 229
                poly_fn(f, [sc((ex, 136), rng), sc((64 if side == "L" else 192, 114), rng),
                            sc((ex, 114), rng)],
                        dither(FLOOR_RAMP, lum_at(light, rng + 0.5) * 0.6))
            elif k in ("wall", "door"):
                if side == "F":
                    tl, tr, br, bl = (sc(q, rng) for q in FWALL_P)
                    bricks(f, flat(tl, tr, br, bl), 4, 4, seed,
                           lambda u, v, h: lum_at(light, rng + 1) * (0.4 + 0.3 * h),
                           WALL_RAMP)
                else:
                    pts = LWALL_P if side == "L" else RWALL_P
                    near_t, far_t, far_b, near_b = (sc(q, rng) for q in pts)
                    Pw = persp(near_t, near_b, far_t)
                    # u = height (top..bottom), t = depth; blocks run along depth
                    bricks(f, Pw, 4, 3, seed,
                           lambda t, v, h: lum_at(light, rng + t) * (0.35 + 0.35 * h),
                           WALL_RAMP, along_v=True)
                if k == "door":
                    dp = {"F": FDOOR_P, "L": LDOOR_P, "R": RDOOR_P}[side]
                    q = [sc(p, rng) for p in dp]   # bottom-left, top-left, top-right, bottom-right
                    Pd = flat(q[1], q[2], q[3], q[0])
                    bricks(f, Pd, 1, 4, seed + (1,),
                           lambda u, v, h: lum_at(light, rng + 0.8) * (0.75 + 0.35 * h),
                           WOOD_RAMP, stagger=False)
        # outlines: the game's own vectors, dim, on top of the stone
        for c in group:
            lv = lum_at(light, rng + 0.5)
            if c["kind"] in ("wall", "passage"):
                col = 15 if lv > 0.75 else 3 if lv > 0.45 else 2 if lv > 0.25 else 1 if lv > 0.08 else 0
                draw_lines(f, c, col)
            elif c["kind"] == "sdoor":
                draw_lines(f, c, colour_for(c))
            elif c["kind"] == "door":
                runs = c["runs"]
                col = 7 if lv > 0.6 else 6 if lv > 0.3 else 5 if lv > 0.08 else 0
                draw_lines(f, c, col, segs=run_segs(runs[:2]))
            elif c["kind"] == "vert":
                draw_vert(rom, f, c, b)
        for c in group:
            if c["kind"] in ("creature", "object", "peek"):
                draw_lines(f, c, colour_for(c), thick=c["range"] <= 1, halo=True)

    draw_status_colour(rom, f, status, text)
    f.check()
    return f.to_image()
