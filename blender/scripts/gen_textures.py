"""Procedurally generate every texture the ship uses (no external assets).

Writes PNGs into //textures/:
  trim_basecolor.png / trim_orm.png / trim_normal.png   2048^2 trim atlas (bands in lib_build.BANDS)
  floor_basecolor.png / floor_orm.png / floor_normal.png 1024^2 tileable diamond plate (1 m per tile)
  display_readouts.png                                   512^2 emissive readouts for small displays
  screen_placeholder.png                                 512^2 CRT placeholder for MAT_screen
ORM packing follows glTF: R = occlusion (unused, 1), G = roughness, B = metallic.
Normal maps are OpenGL style (+Y up), as glTF expects.
Deterministic: every generator uses a fixed seed.
"""
import numpy as np

import bpy

import lib_build as B

TEX_DIR = bpy.path.abspath("//textures")


# ---------------------------------------------------------------------------
# noise helpers (row 0 = bottom of the image; everything tiles in X)
# ---------------------------------------------------------------------------
def _sm(t):
    return t * t * (3 - 2 * t)


def vnoise(h, w, cx, cy, rng, wrap_y=False):
    cx = max(1, int(cx))
    cy = max(1, int(cy))
    gy = cy if wrap_y else cy + 1
    grid = rng.random((gy, cx)).astype(np.float32)
    ys = (np.arange(h) + 0.5) / h * cy
    xs = (np.arange(w) + 0.5) / w * cx
    y0 = np.floor(ys).astype(int)
    x0 = np.floor(xs).astype(int)
    fy = _sm(ys - y0)[:, None]
    fx = _sm(xs - x0)[None, :]
    y1 = (y0 + 1) % gy if wrap_y else np.minimum(y0 + 1, gy - 1)
    y0 = y0 % gy
    x1 = (x0 + 1) % cx
    x0 = x0 % cx
    a = grid[y0][:, x0]
    b = grid[y0][:, x1]
    c = grid[y1][:, x0]
    d = grid[y1][:, x1]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def fbm(h, w, cx, rng, octaves=5, aspect=1.0, wrap_y=False, gain=0.5):
    """Fractal noise with roughly square features (aspect > 1 stretches them vertically)."""
    out = np.zeros((h, w), np.float32)
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        cxx = cx * (2 ** o)
        cyy = max(1, round(cxx * h / w / aspect))
        out += amp * vnoise(h, w, cxx, cyy, rng, wrap_y)
        tot += amp
        amp *= gain
    return out / tot


def scratches(h, w, n, rng, length=(20, 160), angle=0.25, width=1):
    m = np.zeros((h, w), np.float32)
    for _ in range(n):
        x0, y0 = rng.random() * w, rng.random() * h
        ang = rng.normal(0, angle) + (np.pi if rng.random() < 0.5 else 0)
        ln = rng.uniform(*length)
        t = np.arange(0, ln, 0.5)
        xs = (x0 + np.cos(ang) * t).astype(int) % w
        ys = (y0 + np.sin(ang) * t).astype(int)
        ok = (ys >= 0) & (ys < h)
        fade = np.sin(np.linspace(0, np.pi, len(t)))[ok]
        for dw in range(width):
            np.maximum.at(m, (np.clip(ys[ok] + dw, 0, h - 1), xs[ok]), fade * rng.uniform(0.5, 1.0))
    return m


def blur_x(a, r):
    out = a.copy()
    for k in range(1, r + 1):
        out += np.roll(a, k, 1) + np.roll(a, -k, 1)
    return out / (2 * r + 1)


def blur(a, r, wrap_y=False):
    out = blur_x(a, r)
    acc = out.copy()
    for k in range(1, r + 1):
        if wrap_y:
            acc += np.roll(out, k, 0) + np.roll(out, -k, 0)
        else:
            up = np.concatenate([out[k:], np.repeat(out[-1:], k, 0)])
            dn = np.concatenate([np.repeat(out[:1], k, 0), out[:-k]])
            acc += up + dn
    return acc / (2 * r + 1)


def normal_from_height(hgt, strength, wrap_y=False):
    dx = (np.roll(hgt, -1, 1) - np.roll(hgt, 1, 1)) * 0.5
    if wrap_y:
        dy = (np.roll(hgt, -1, 0) - np.roll(hgt, 1, 0)) * 0.5
    else:
        dy = np.zeros_like(hgt)
        dy[1:-1] = (hgt[2:] - hgt[:-2]) * 0.5
    nx, ny, nz = -dx * strength, -dy * strength, np.ones_like(hgt)
    ln = np.sqrt(nx * nx + ny * ny + nz * nz)
    return np.stack([nx / ln * 0.5 + 0.5, ny / ln * 0.5 + 0.5, nz / ln * 0.5 + 0.5], -1)


def col(c):
    return np.array(c, np.float32)[None, None, :]


def mix(a, b, t):
    t = t[..., None] if t.ndim == 2 else t
    return a * (1 - t) + b * t


def edge_dist(h, w):
    r = np.arange(h, dtype=np.float32)
    e = np.minimum(r, h - 1 - r)
    return np.repeat(e[:, None], w, 1)


def rivet_row(h, w, y, spacing, r, x_off=0):
    hgt = np.zeros((h, w), np.float32)
    yy = np.arange(h)[:, None].astype(np.float32)
    xx = np.arange(w)[None, :].astype(np.float32)
    dxs = ((xx - x_off) % spacing) - spacing / 2
    d = np.sqrt(dxs ** 2 + (yy - y) ** 2)
    dome = np.clip(1 - (d / r) ** 2, 0, 1)
    return np.sqrt(dome)


# ---------------------------------------------------------------------------
# band generators -> rgb (h, w, 3), rough (h, w), metal (h, w), height (h, w)
# ---------------------------------------------------------------------------
W = B.ATLAS
STEEL = (0.52, 0.53, 0.54)


def painted(h, rng, base, var=0.06, grime=0.35, edge_wear=True, rivets=True, drips=True, wear=1.0):
    w = W
    mott = fbm(h, w, 6, rng, 5) - 0.5
    rgb = col(base) * (1 + mott[..., None] * var * 2)
    hgt = np.zeros((h, w), np.float32)
    rough = 0.6 + mott * 0.15
    metal = np.zeros((h, w), np.float32)
    e = edge_dist(h, w)
    # grime: heavier toward the bottom of the panel, vertical streaks from the top
    yb = np.linspace(1, 0, h, dtype=np.float32)[:, None]
    streak = vnoise(h, w, 260, 2, rng) * vnoise(h, w, 90, 3, rng)
    g = np.clip((yb ** 3) * 0.9 + (fbm(h, w, 10, rng, 4) - 0.45) * 0.8, 0, 1) * grime
    if drips:
        topfade = np.clip(np.linspace(0, 1, h, dtype=np.float32)[:, None] * 1.4 - 0.2, 0, 1)
        g = g + np.clip(streak - 0.35, 0, 1) * 0.9 * topfade * grime
    g = np.clip(g, 0, 0.85)
    rgb = mix(rgb, col((0.07, 0.065, 0.055)), g * 0.8)
    rough = rough + g * 0.25
    # edge bevel (panel edges) + chipped paint
    bev = np.clip(1 - e / 5.0, 0, 1)
    hgt -= bev * 1.2
    if edge_wear:
        chipn = fbm(h, w, 28, rng, 5) * 0.7 + fbm(h, w, 180, rng, 2) * 0.3
        thr = 0.60 + np.clip(e / 7.0, 0, 1) * 0.5
        chip = np.clip((chipn - thr) * 14, 0, 1)
        spots = np.clip((fbm(h, w, 90, rng, 3) - 0.80) * 8, 0, 1) * 0.5
        chip = np.clip(chip + spots, 0, 1) * wear
        rgb = mix(rgb, col(STEEL) * (0.55 + 0.25 * fbm(h, w, 200, rng, 2)[..., None]), chip * 0.85)
        rough = mix(rough[..., None], np.full((h, w, 1), 0.38, np.float32), chip)[..., 0]
        metal = np.maximum(metal, chip)
        hgt -= chip * 0.6
    sc = scratches(h, w, int(W * h / 14000) + 6, rng)
    rgb = mix(rgb, col(STEEL), sc * 0.35)
    metal = np.maximum(metal, sc * 0.6)
    rough -= sc * 0.2
    if rivets and h >= 128:
        for yy in (9.0, h - 10.0):
            rv = rivet_row(h, w, yy, 64, 3.2)
            hgt += rv * 2.5
            rgb = mix(rgb, col(base) * 0.85, np.clip(rv * 2, 0, 1))
    return rgb, np.clip(rough, 0.05, 1), np.clip(metal, 0, 1), hgt


def band_panel_teal(h, rng):
    return painted(h, rng, (0.27, 0.39, 0.37), var=0.07, grime=0.45)


def band_panel_gray(h, rng):
    return painted(h, rng, (0.40, 0.44, 0.40), var=0.06, grime=0.5)


def band_gunmetal(h, rng):
    rgb, rough, metal, hgt = painted(h, rng, (0.15, 0.16, 0.17), var=0.1, grime=0.3, rivets=False, wear=0.6)
    brush = blur_x(rng.random((h, W)).astype(np.float32), 12) - 0.5
    rgb = rgb * (1 + brush[..., None] * 0.25)
    rough = rough - 0.08 + brush * 0.1
    return rgb, rough, metal, hgt


def band_rivets(h, rng):
    rgb, rough, metal, hgt = painted(h, rng, (0.17, 0.18, 0.18), var=0.1, grime=0.35, rivets=False, wear=0.5)
    rv = rivet_row(h, W, h / 2, 64, h * 0.16)
    hgt += rv * 4
    rgb = mix(rgb, col((0.36, 0.37, 0.37)), np.clip(rv * 1.5, 0, 1) * 0.7)
    metal = np.maximum(metal, np.clip(rv * 2, 0, 1) * 0.8)
    ring = np.clip((rivet_row(h, W, h / 2, 64, h * 0.26) > 0.01) * 1.0 - (rv > 0.01) * 1.0, 0, 1)
    rgb = mix(rgb, col((0.05, 0.05, 0.05)), ring * 0.5)
    return rgb, rough, metal, hgt


def band_seam(h, rng):
    rgb, rough, metal, hgt = painted(h, rng, (0.16, 0.17, 0.18), var=0.08, grime=0.3, rivets=False, drips=False)
    y = np.abs(np.arange(h, dtype=np.float32) - h / 2)[:, None]
    groove = np.clip(1 - y / 5.0, 0, 1)
    hgt -= np.repeat(groove, W, 1) * 3
    rgb = mix(rgb, col((0.03, 0.03, 0.03)), np.repeat(np.clip(1 - y / 2.5, 0, 1), W, 1) * 0.9)
    return rgb, rough, metal, hgt


def band_vent(h, rng):
    w = W
    rows = np.arange(h, dtype=np.float32)[:, None]
    border = 14
    inner = (rows >= border) & (rows < h - border)
    period = 22
    ph = ((rows - border) % period) / period
    slat = (ph < 0.62) & inner
    # slats are angled: a height ramp inside each slat
    hgt = np.where(slat, ph / 0.62 * 3.0, np.where(inner, -2.0, 1.5)).astype(np.float32)
    hgt = np.repeat(hgt, w, 1)
    base = np.where(np.repeat(slat, w, 1)[..., None], col((0.2, 0.21, 0.22)),
                    np.where(np.repeat(inner, w, 1)[..., None], col((0.015, 0.015, 0.015)), col((0.16, 0.17, 0.18))))
    shade = np.repeat(np.where(slat, 0.75 + ph * 0.5, 1.0), w, 1)
    rgb = base * shade[..., None]
    dust = np.clip(fbm(h, w, 20, rng, 4) - 0.4, 0, 1) * 1.2
    rgb = mix(rgb, col((0.1, 0.09, 0.075)), dust * 0.6)
    rough = np.full((h, w), 0.55, np.float32) + dust * 0.3
    metal = np.repeat(np.where(slat, 0.6, 0.0), w, 1).astype(np.float32)
    # bolts in the frame
    for yy in (border / 2, h - border / 2):
        rv = rivet_row(h, w, yy, 128, 3.5, 64)
        hgt += rv * 2
        rgb = mix(rgb, col((0.35, 0.35, 0.36)), np.clip(rv * 2, 0, 1) * 0.6)
    return rgb, rough, metal, hgt


def band_hazard(h, rng):
    w = W
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    stripe = ((xx + yy) % 64) < 32
    rgb = np.where(stripe[..., None], col((0.80, 0.52, 0.10)), col((0.035, 0.035, 0.03)))
    rough = np.where(stripe, 0.55, 0.6).astype(np.float32)
    metal = np.zeros((h, w), np.float32)
    hgt = np.zeros((h, w), np.float32)
    e = edge_dist(h, w)
    wear = np.clip((fbm(h, w, 60, rng, 4) - (0.45 + np.clip(e / 20, 0, 1) * 0.25)) * 9, 0, 1)
    rgb = mix(rgb, col(STEEL) * 0.8, wear)
    metal = np.maximum(metal, wear)
    g = np.clip(fbm(h, w, 12, rng, 4) - 0.35, 0, 1) * 1.3
    rgb = mix(rgb, col((0.06, 0.05, 0.04)), g * 0.6)
    rough += g * 0.2
    hgt -= wear * 0.8
    edge = e < 3
    rgb = np.where(edge[..., None], col((0.03, 0.03, 0.03)), rgb)
    return rgb, rough, metal, hgt


def band_rubber(h, rng):
    w = W
    n = fbm(h, w, 30, rng, 4)
    xx = np.arange(w, dtype=np.float32)[None, :]
    ribs = (np.sin(xx / 16 * 2 * np.pi) * 0.5 + 0.5) ** 4
    rgb = col((0.045, 0.045, 0.048)) * (0.8 + 0.4 * n[..., None])
    rgb = rgb * (1 + ribs[..., None] * 0.3)
    rough = 0.82 + (n - 0.5) * 0.1
    metal = np.zeros((h, w), np.float32)
    hgt = np.repeat(ribs, h, 0) * 1.5 + n * 0.5
    return rgb, rough, metal, hgt


def band_console(h, rng):
    w = W
    n = fbm(h, w, 12, rng, 5)
    rgb = col((0.50, 0.52, 0.47)) * (0.94 + 0.12 * n[..., None])
    rough = 0.48 + (n - 0.5) * 0.1
    metal = np.zeros((h, w), np.float32)
    hgt = (fbm(h, w, 400, rng, 2) - 0.5) * 0.3
    # finger grime blotches and a dirty lower edge
    g = np.clip(fbm(h, w, 25, rng, 4) - 0.58, 0, 1) * 2.0
    yb = np.linspace(1, 0, h, dtype=np.float32)[:, None] ** 4
    g = np.clip(g + yb * 0.5, 0, 1)
    rgb = mix(rgb, col((0.18, 0.17, 0.14)), g * 0.55)
    rough += g * 0.15
    # printed legends: small dark rectangles scattered in rows
    for _ in range(18):
        x = rng.integers(0, w)
        y = rng.integers(24, h - 24)
        for k in range(rng.integers(1, 4)):
            lw = rng.integers(14, 40)
            xs = np.arange(x, x + lw) % w
            rgb[y - k * 7:y - k * 7 + 3, xs] = rgb[y - k * 7:y - k * 7 + 3, xs] * 0.55
    e = edge_dist(h, w)
    sm = np.clip(1 - e / 3, 0, 1)
    hgt -= sm * 1.5
    rgb = mix(rgb, col((0.08, 0.08, 0.07)), sm * 0.7)
    return rgb, rough, metal, hgt


def band_ribbed(h, rng):
    w = W
    xx = np.arange(w, dtype=np.float32)[None, :]
    rib = np.sin(xx / 14 * 2 * np.pi) * 0.5 + 0.5
    n = fbm(h, w, 20, rng, 4)
    rgb = col((0.30, 0.33, 0.31)) * (0.75 + 0.35 * rib[..., None]) * (0.9 + 0.2 * n[..., None])
    g = np.clip(fbm(h, w, 8, rng, 4) - 0.45, 0, 1) * 1.5
    rgb = mix(rgb, col((0.08, 0.07, 0.06)), g * 0.6)
    rough = 0.5 + g * 0.3 + (1 - rib) * 0.1
    metal = np.full((h, w), 0.0, np.float32)
    hgt = np.repeat(rib, h, 0) * 3
    return rgb, rough, metal, hgt


def band_steel(h, rng):
    w = W
    brush = blur_x(rng.random((h, w)).astype(np.float32), 20)
    n = fbm(h, w, 8, rng, 4)
    rgb = col(STEEL) * (0.8 + 0.4 * (brush[..., None] - 0.5) + 0.15 * (n[..., None] - 0.5))
    sc = scratches(h, w, 60, rng)
    rgb = mix(rgb, col((0.75, 0.76, 0.77)), sc * 0.5)
    g = np.clip(fbm(h, w, 14, rng, 4) - 0.55, 0, 1) * 2
    rgb = mix(rgb, col((0.12, 0.11, 0.09)), g * 0.5)
    rough = 0.32 + (brush - 0.5) * 0.2 + g * 0.3
    metal = np.full((h, w), 1.0, np.float32)
    hgt = sc * -0.5
    return rgb, rough, metal, hgt


GLYPHS = None


def _glyph_bank(rng, n=40):
    """Random 3x5 block glyphs: stencil-like marks that read as text without being text."""
    bank = []
    for _ in range(n):
        g = rng.random((5, 3)) < 0.55
        g[:, 1] |= rng.random(5) < 0.3
        bank.append(g)
    return bank


def draw_glyph_line(img, x, y, count, scale, bank, rng, color, w):
    cx = x
    for i in range(count):
        if rng.random() < 0.18:
            cx += 2 * scale
            continue
        g = bank[rng.integers(0, len(bank))]
        for gy in range(5):
            for gx in range(3):
                if g[4 - gy, gx]:
                    xs = np.arange(cx + gx * scale, cx + (gx + 1) * scale) % w
                    img[y + gy * scale:y + (gy + 1) * scale, xs] = color
        cx += 4 * scale
    return cx


def band_label(h, rng):
    w = W
    bank = _glyph_bank(rng)
    rgb = np.repeat(np.repeat(col((0.10, 0.11, 0.11)), h, 0), w, 1).copy()
    n = fbm(h, w, 20, rng, 4)
    rgb *= (0.8 + 0.4 * n[..., None])
    marks = np.zeros((h, w, 3), np.float32)
    x = 16
    while x < w - 200:
        c = (0.82, 0.78, 0.68) if rng.random() < 0.8 else (0.85, 0.55, 0.12)
        x = draw_glyph_line(marks, x, h // 2 - 12, rng.integers(3, 8), 5, bank, rng, c, w)
        x += rng.integers(40, 120)
    m = marks.sum(-1) > 0
    wear = fbm(h, w, 90, rng, 3) > 0.62
    m = m & ~wear
    rgb = np.where(m[..., None], marks, rgb)
    e = edge_dist(h, w)
    rgb = np.where((e < 4)[..., None], col((0.55, 0.56, 0.55)), rgb)
    rough = np.full((h, w), 0.5, np.float32)
    metal = np.where(e < 4, 1.0, 0.0).astype(np.float32)
    hgt = np.clip(1 - e / 4, 0, 1) * 1.0
    return rgb, rough, metal, hgt


BAND_FUNCS = {
    "panel_teal": band_panel_teal, "panel_gray": band_panel_gray, "gunmetal": band_gunmetal,
    "rivets": band_rivets, "seam": band_seam, "vent": band_vent, "hazard": band_hazard,
    "rubber": band_rubber, "console": band_console, "ribbed": band_ribbed, "steel": band_steel,
    "label": band_label,
}


# ---------------------------------------------------------------------------
# floor: 1 m diamond plate tile with a plate seam around the border
# ---------------------------------------------------------------------------
def floor_maps(size, rng):
    s = size
    yy, xx = np.mgrid[0:s, 0:s].astype(np.float32)
    cell = s / 16
    # staggered, elongated diamonds alternating direction
    cx = xx / cell
    cy = yy / cell
    ix, iy = np.floor(cx), np.floor(cy)
    fx, fy = cx - ix - 0.5, cy - iy - 0.5
    flip = ((ix + iy) % 2) == 0
    a = np.where(flip, fx + fy, fx - fy) / 1.414
    b = np.where(flip, fx - fy, fx + fy) / 1.414
    d = np.abs(a) / 0.36 + np.abs(b) / 0.1
    bump = np.clip(1 - d, 0, 1) ** 0.6
    hgt = bump * 3.0
    n = fbm(s, s, 4, rng, 5, wrap_y=True)
    rgb = col((0.20, 0.21, 0.21)) * (0.85 + 0.3 * n[..., None])
    rgb = mix(rgb, col((0.42, 0.43, 0.43)), bump * 0.55)     # worn shiny tops
    rough = 0.55 - bump * 0.2 + (n - 0.5) * 0.1
    # mostly diffuse (worn painted deck, shiny only on the worn tread tops): baked
    # lightmaps only light the diffuse part of a material in three.js
    metal = 0.15 + bump * 0.35
    # grime in the recesses + oil blotches + scuffs
    g = np.clip(fbm(s, s, 6, rng, 5, wrap_y=True) - 0.45, 0, 1) * 1.8 * (1 - bump)
    rgb = mix(rgb, col((0.05, 0.045, 0.04)), g * 0.7)
    rough += g * 0.25
    metal -= g * 0.5
    oil = np.clip(fbm(s, s, 3, rng, 4, wrap_y=True) - 0.6, 0, 1) * 2.5
    rgb = mix(rgb, col((0.03, 0.03, 0.03)), oil * 0.5)
    rough -= oil * 0.15
    sc = scratches(s, s, 70, rng, (30, 220), angle=1.2)
    rgb = mix(rgb, col((0.5, 0.5, 0.5)), sc * 0.35)
    # plate seam on the tile border + bolts at the corners
    e = np.minimum(np.minimum(xx, s - 1 - xx), np.minimum(yy, s - 1 - yy))
    seam = np.clip(1 - e / 4, 0, 1)
    hgt -= seam * 4
    rgb = mix(rgb, col((0.02, 0.02, 0.02)), seam * 0.9)
    for bx, by in ((22, 22), (s - 22, 22), (22, s - 22), (s - 22, s - 22), (s / 2, 22), (s / 2, s - 22),
                   (22, s / 2), (s - 22, s / 2)):
        dd = np.sqrt((xx - bx) ** 2 + (yy - by) ** 2)
        bolt = np.sqrt(np.clip(1 - (dd / 9) ** 2, 0, 1))
        hgt += bolt * 4
        rgb = mix(rgb, col((0.38, 0.38, 0.38)), np.clip(bolt * 3, 0, 1))
    return rgb, np.clip(rough, 0.05, 1), np.clip(metal, 0, 1), hgt


# ---------------------------------------------------------------------------
# emissive displays
# ---------------------------------------------------------------------------
AMBER = (1.0, 0.62, 0.18)


def crt_base(s, rng, tint=(0.02, 0.05, 0.04)):
    yy, xx = np.mgrid[0:s, 0:s].astype(np.float32)
    u, v = xx / s - 0.5, yy / s - 0.5
    vign = np.clip(1 - (u * u + v * v) * 2.2, 0, 1)
    scan = 0.82 + 0.18 * (np.sin(yy * np.pi / 2) ** 2)
    rgb = col(tint) * (0.5 + 0.8 * vign[..., None]) * scan[..., None]
    return rgb, vign, scan


def display_readouts(s, rng):
    bank = _glyph_bank(rng)
    rgb, vign, scan = crt_base(s, rng)
    layer = np.zeros((s, s, 3), np.float32)
    amber = np.array(AMBER, np.float32)
    # header bar
    layer[s - 60:s - 40, 30:s - 30] = amber * 0.9
    y = s - 90
    while y > s * 0.45:
        draw_glyph_line(layer, 34, y, rng.integers(8, 20), 3, bank, rng, amber, s)
        y -= 24
    # bar graph
    for i in range(10):
        hgt = int(rng.uniform(0.15, 0.9) * s * 0.3)
        x0 = 40 + i * 42
        layer[40:40 + hgt, x0:x0 + 26] = amber * (0.55 if i % 3 else 0.9)
    layer[34:37, 30:s - 30] = amber * 0.6
    # status squares
    for i in range(4):
        layer[s - 30:s - 18, s - 40 - i * 22:s - 28 - i * 22] = amber * (1.0 if i % 2 else 0.35)
    glow = blur(layer.sum(-1) / 3, 3, True)
    out = rgb + layer * scan[..., None] * (0.35 + 0.65 * vign[..., None]) + glow[..., None] * amber * 0.25
    return np.clip(out, 0, 1)


def screen_placeholder(s, rng):
    bank = _glyph_bank(rng)
    rgb, vign, scan = crt_base(s, rng, (0.015, 0.04, 0.035))
    layer = np.zeros((s, s, 3), np.float32)
    amber = np.array(AMBER, np.float32)
    g = 32
    yy, xx = np.mgrid[0:s, 0:s]
    grid = ((xx % g) == 0) | ((yy % g) == 0)
    layer[grid] = amber * 0.12
    # frame + centre crosshair box, "awaiting signal" glyph line
    layer[16:20, 16:s - 16] = amber * 0.5
    layer[s - 20:s - 16, 16:s - 16] = amber * 0.5
    layer[16:s - 16, 16:20] = amber * 0.5
    layer[16:s - 16, s - 20:s - 16] = amber * 0.5
    c = s // 2
    layer[c - 40:c + 40, c - 1:c + 1] = amber * 0.6
    layer[c - 1:c + 1, c - 40:c + 40] = amber * 0.6
    draw_glyph_line(layer, c - 70, c - 90, 7, 4, bank, rng, amber, s)
    glow = blur(layer.sum(-1) / 3, 3, True)
    out = rgb + layer * scan[..., None] + glow[..., None] * amber * 0.3
    return np.clip(out, 0, 1)


def nameplate(w, h, rng):
    """Brushed plate with a dark border and placeholder glyph blocks (the game
    swaps in a per-pod name texture)."""
    bank = _glyph_bank(rng)
    brush = blur_x(rng.random((h, w)).astype(np.float32), 16)
    rgb = np.repeat(np.repeat(col((0.62, 0.62, 0.6)), h, 0), w, 1) * (0.85 + 0.3 * (brush[..., None] - 0.5))
    e = edge_dist(h, w)
    ex = np.minimum(np.arange(w), w - 1 - np.arange(w))[None, :].astype(np.float32)
    e = np.minimum(e, ex)
    rgb = np.where((e < 6)[..., None], col((0.1, 0.1, 0.1)), rgb)
    marks = np.zeros((h, w, 3), np.float32)
    x = draw_glyph_line(marks, 40, h // 2 - 20, 4, 8, bank, rng, (0.08, 0.08, 0.08), w)
    marks[h // 2 - 2:h // 2 + 2, x + 20:w - 60] = 0.08
    m = marks.sum(-1) > 0
    rgb = np.where(m[..., None], marks, rgb)
    for bx in (18, w - 18):
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        d = np.sqrt((xx - bx) ** 2 + (yy - h / 2) ** 2)
        rgb = np.where((d < 6)[..., None], col((0.3, 0.3, 0.3)), rgb)
    return rgb


# ---------------------------------------------------------------------------
# image IO
# ---------------------------------------------------------------------------
def save_png(name, rgb, colorspace="sRGB"):
    h, w = rgb.shape[:2]
    img = bpy.data.images.get(name)
    if img is not None and (img.size[0] != w or img.size[1] != h):
        bpy.data.images.remove(img)
        img = None
    if img is None:
        img = bpy.data.images.new(name, w, h, alpha=False)
    img.colorspace_settings.name = colorspace
    rgba = np.concatenate([np.clip(rgb, 0, 1), np.ones((h, w, 1), np.float32)], -1).astype(np.float32)
    img.pixels.foreach_set(rgba.ravel())
    path = f"{TEX_DIR}/{name}"
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    img.filepath = "//textures/" + name
    img.reload()
    return path


def build():
    written = []
    # trim atlas
    rgb = np.zeros((W, W, 3), np.float32)
    rough = np.zeros((W, W), np.float32)
    metal = np.zeros((W, W), np.float32)
    nrm = np.zeros((W, W, 3), np.float32)
    for i, (name, p0, p1, nat) in enumerate(B.BANDS):
        rng = np.random.default_rng(1000 + i)
        c, r, m, hgt = BAND_FUNCS[name](p1 - p0, rng)
        rgb[p0:p1] = c
        rough[p0:p1] = r
        metal[p0:p1] = m
        nrm[p0:p1] = normal_from_height(hgt, 0.9)
    orm = np.stack([np.ones_like(rough), np.clip(rough, 0.05, 1), np.clip(metal, 0, 1)], -1)
    written.append(save_png("trim_basecolor.png", rgb))
    written.append(save_png("trim_orm.png", orm, "Non-Color"))
    written.append(save_png("trim_normal.png", nrm, "Non-Color"))

    rng = np.random.default_rng(7)
    c, r, m, hgt = floor_maps(1024, rng)
    written.append(save_png("floor_basecolor.png", c))
    written.append(save_png("floor_orm.png", np.stack([np.ones_like(r), r, m], -1), "Non-Color"))
    written.append(save_png("floor_normal.png", normal_from_height(hgt, 0.8, wrap_y=True), "Non-Color"))

    written.append(save_png("display_readouts.png", display_readouts(512, np.random.default_rng(11))))
    written.append(save_png("screen_placeholder.png", screen_placeholder(512, np.random.default_rng(12))))
    written.append(save_png("nameplate_placeholder.png", nameplate(512, 96, np.random.default_rng(13))))
    return {"written": written}
