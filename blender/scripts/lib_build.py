"""bmesh-based mesh builder with trim-sheet UVs and shared material slots.

Every face is tagged with a trim band (a horizontal strip of the shared trim
atlas, textures/trim_*.png) or a special mapping mode. UVs are generated from
those tags in finish(), so geometry code never deals with UVs directly.

Winding rule used by the profile helpers: faces point to the RIGHT of the
direction of travel along a 2D profile (with the profile's first axis to the
right and its second axis up).
"""
import math

import bmesh
import bpy
from mathutils import Matrix, Vector

# ---------------------------------------------------------------------------
# Trim atlas layout (pixels measured from the BOTTOM of a 2048 px image).
# natural_h = how many metres of real surface the band height represents.
# ---------------------------------------------------------------------------
ATLAS = 2048
PAD = 6
BANDS = [
    ("panel_teal", 0, 384, 1.0),
    ("panel_gray", 384, 640, 0.8),
    ("gunmetal", 640, 896, 0.6),
    ("rivets", 896, 1024, 0.1),
    ("seam", 1024, 1088, 0.05),
    ("vent", 1088, 1280, 0.25),
    ("hazard", 1280, 1344, 0.1),
    ("rubber", 1344, 1472, 0.15),
    ("console", 1472, 1728, 0.5),
    ("ribbed", 1728, 1856, 0.2),
    ("steel", 1856, 1984, 0.2),
    ("label", 1984, 2048, 0.08),
]
BAND = {b[0]: i for i, b in enumerate(BANDS)}
CUSTOM = -1   # UVs already written by the builder
FILL = -2     # face fills the full 0-1 UV square (screens, nameplates)
FLOOR = -3    # planar XY mapping for MAT_floor (tiles every builder.floor_tile metres)

MAT_TRIM = "MAT_trim"


def get_material(name):
    m = bpy.data.materials.get(name)
    if m is None:
        m = bpy.data.materials.new(name)
    return m


def _band_id(band):
    if isinstance(band, int):
        return band
    return BAND[band]


class MB:
    """Mesh builder. Geometry is added in the current local frame (self.M)."""

    def __init__(self, floor_tile=1.0):
        self.bm = bmesh.new()
        self.uv = self.bm.loops.layers.uv.new("UVMap")
        self.trim = self.bm.faces.layers.int.new("trim")
        self.mats = []
        self.M = Matrix.Identity(4)
        self._stack = []
        self.floor_tile = floor_tile

    # ------------------------------------------------------------ frames
    def push(self, m):
        self._stack.append(self.M)
        self.M = self.M @ m
        return self

    def pop(self):
        self.M = self._stack.pop()

    class _Ctx:
        def __init__(self, mb, m):
            self.mb, self.m = mb, m

        def __enter__(self):
            self.mb.push(self.m)
            return self.mb

        def __exit__(self, *a):
            self.mb.pop()

    def at(self, loc=(0, 0, 0), rot_z=0.0, rot=None, scale=None):
        m = Matrix.Translation(Vector(loc))
        if rot is not None:
            m = m @ rot.to_matrix().to_4x4() if hasattr(rot, "to_matrix") else m @ rot
        if rot_z:
            m = m @ Matrix.Rotation(rot_z, 4, "Z")
        if scale is not None:
            m = m @ Matrix.Diagonal(Vector((*scale, 1.0)))
        return MB._Ctx(self, m)

    # ------------------------------------------------------------- basics
    def mat(self, name):
        if name not in self.mats:
            self.mats.append(name)
        return self.mats.index(name)

    def v(self, p):
        return self.bm.verts.new(self.M @ Vector(p))

    def face(self, pts=None, band="gunmetal", mat=MAT_TRIM, verts=None, uvs=None, smooth=False):
        vs = verts if verts is not None else [self.v(p) for p in pts]
        f = self.bm.faces.new(vs)
        f.material_index = self.mat(mat)
        f.smooth = smooth
        if uvs is not None:
            for loop, uv in zip(f.loops, uvs):
                loop[self.uv].uv = uv
            f[self.trim] = CUSTOM
        else:
            f[self.trim] = _band_id(band)
        return f

    def _orient_out(self, faces, center_world):
        for f in faces:
            f.normal_update()
            if (f.calc_center_median() - center_world).dot(f.normal) < 0:
                f.normal_flip()

    # ------------------------------------------------------------- primitives
    def box(self, mn, mx, band="gunmetal", mat=MAT_TRIM, skip=(), bands=None):
        x0, y0, z0 = mn
        x1, y1, z1 = mx
        c = [self.v(p) for p in [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
                                 (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]]
        spec = {"-z": (0, 3, 2, 1), "+z": (4, 5, 6, 7), "-y": (0, 1, 5, 4),
                "+x": (1, 2, 6, 5), "+y": (2, 3, 7, 6), "-x": (3, 0, 4, 7)}
        bands = bands or {}
        out = []
        for k, idx in spec.items():
            if k in skip:
                continue
            m = mat
            b = bands.get(k, band)
            if isinstance(b, tuple):
                b, m = b
            out.append(self.face(band=b, mat=m, verts=[c[i] for i in idx]))
        self._orient_out(out, self.M @ ((Vector(mn) + Vector(mx)) / 2))
        return out

    def cbox(self, mn, mx, c=0.02, band="gunmetal", mat=MAT_TRIM, skip=(), bands=None):
        """Box with 45 degree chamfers on every edge (reads as chunky, catches light)."""
        mn, mx = Vector(mn), Vector(mx)
        ctr = (mn + mx) / 2
        h = (mx - mn) / 2
        c = min(c, h.x * 0.49, h.y * 0.49, h.z * 0.49)
        bands = bands or {}
        V = {}
        for sx in (-1, 1):
            for sy in (-1, 1):
                for sz in (-1, 1):
                    V[(sx, sy, sz, 0)] = self.v(ctr + Vector((sx * h.x, sy * (h.y - c), sz * (h.z - c))))
                    V[(sx, sy, sz, 1)] = self.v(ctr + Vector((sx * (h.x - c), sy * h.y, sz * (h.z - c))))
                    V[(sx, sy, sz, 2)] = self.v(ctr + Vector((sx * (h.x - c), sy * (h.y - c), sz * h.z)))
        faces = []
        order = [(-1, -1), (1, -1), (1, 1), (-1, 1)]
        for ax in range(3):
            a, b = [i for i in range(3) if i != ax]
            for s in (-1, 1):
                key = ("+" if s > 0 else "-") + "xyz"[ax]
                if key in skip:
                    continue
                vs = []
                for sa, sb in order:
                    k = [0, 0, 0]
                    k[ax], k[a], k[b] = s, sa, sb
                    vs.append(V[(k[0], k[1], k[2], ax)])
                bb = bands.get(key, band)
                m = mat
                if isinstance(bb, tuple):
                    bb, m = bb
                faces.append(self.face(band=bb, mat=m, verts=vs))
        cb = bands.get("chamfer", band)
        cm = mat
        if isinstance(cb, tuple):
            cb, cm = cb
        # edge chamfers: between face axis a and face axis b, running along axis t
        for a, b in ((0, 1), (0, 2), (1, 2)):
            t = 3 - a - b
            for sa in (-1, 1):
                for sb in (-1, 1):
                    k0 = [0, 0, 0]
                    k1 = [0, 0, 0]
                    k0[a], k0[b], k0[t] = sa, sb, -1
                    k1[a], k1[b], k1[t] = sa, sb, 1
                    vs = [V[(*k0, a)], V[(*k1, a)], V[(*k1, b)], V[(*k0, b)]]
                    faces.append(self.face(band=cb, mat=cm, verts=vs))
        for sx in (-1, 1):
            for sy in (-1, 1):
                for sz in (-1, 1):
                    vs = [V[(sx, sy, sz, 0)], V[(sx, sy, sz, 1)], V[(sx, sy, sz, 2)]]
                    faces.append(self.face(band=cb, mat=cm, verts=vs))
        self._orient_out(faces, self.M @ ctr)
        return faces

    def prism(self, footprint, z0, z1, band="gunmetal", mat=MAT_TRIM, caps=(True, True),
              side_bands=None, cap_band=None, skip_sides=()):
        """Extrude a CCW footprint [(x, y), ...] from z0 to z1. Side i runs from
        footprint[i] to footprint[i + 1]."""
        n = len(footprint)
        bot = [self.v((x, y, z0)) for x, y in footprint]
        top = [self.v((x, y, z1)) for x, y in footprint]
        out = []
        cb = cap_band or band
        if caps[0]:
            out.append(self.face(band=cb, mat=mat, verts=list(reversed(bot))))
        if caps[1]:
            out.append(self.face(band=cb, mat=mat, verts=top))
        for i in range(n):
            if i in skip_sides:
                continue
            j = (i + 1) % n
            b = side_bands[i] if side_bands else band
            out.append(self.face(band=b, mat=mat, verts=[bot[i], bot[j], top[j], top[i]]))
        return out

    @staticmethod
    def flip(faces):
        for f in faces:
            f.normal_flip()
        return faces

    def quad(self, p0, p1, p2, p3, band="gunmetal", mat=MAT_TRIM):
        return self.face([p0, p1, p2, p3], band=band, mat=mat)

    def fill_quad(self, p0, p1, p2, p3, mat):
        """Quad with UVs filling 0-1 (p0 = bottom-left, counter-clockwise when facing it)."""
        return self.face([p0, p1, p2, p3], mat=mat, uvs=[(0, 0), (1, 0), (1, 1), (0, 1)])

    def panel(self, center, right, up, w, h, mat):
        """Flat quad seen by a viewer whose screen-right is `right` and screen-up is
        `up`; the face points at that viewer and UV (0,0) is their bottom-left."""
        c, r, u = Vector(center), Vector(right).normalized(), Vector(up).normalized()
        hw, hh = r * (w / 2), u * (h / 2)
        return self.fill_quad(c - hw - hh, c + hw - hh, c + hw + hh, c - hw + hh, mat)

    def extrude_profile(self, profile, x0, x1, bands, mat=MAT_TRIM, zclip=None, mats=None):
        """Sweep a 2D profile [(y, z), ...] along +X from x0 to x1.

        Faces point to the right of travel along the profile, so a wall profile
        traced from floor to ceiling faces +Y. bands: one band per segment (or one
        for all). zclip=(zlo, zhi) keeps only the part of the profile in that range.
        """
        segs = []
        for i in range(len(profile) - 1):
            (ya, za), (yb, zb) = profile[i], profile[i + 1]
            b = bands[i] if isinstance(bands, (list, tuple)) else bands
            m = mats[i] if mats else mat
            if zclip:
                lo, hi = zclip
                if max(za, zb) <= lo + 1e-6 or min(za, zb) >= hi - 1e-6:
                    continue

                def lerp_at(z):
                    t = (z - za) / (zb - za)
                    return (ya + (yb - ya) * t, z)
                if za != zb:
                    pa = (ya, za) if lo <= za <= hi else lerp_at(min(max(za, lo), hi))
                    pb = (yb, zb) if lo <= zb <= hi else lerp_at(min(max(zb, lo), hi))
                else:
                    pa, pb = (ya, za), (yb, zb)
                segs.append((pa, pb, b, m))
            else:
                segs.append(((ya, za), (yb, zb), b, m))
        out = []
        for (ya, za), (yb, zb), b, m in segs:
            if abs(ya - yb) < 1e-7 and abs(za - zb) < 1e-7:
                continue
            out.append(self.face([(x0, ya, za), (x0, yb, zb), (x1, yb, zb), (x1, ya, za)], band=b, mat=m))
        return out

    def _orient(self, faces, local_dir):
        d = (self.M.to_3x3() @ Vector(local_dir)).normalized()
        for f in faces:
            f.normal_update()
            if f.normal.dot(d) < 0:
                f.normal_flip()

    def ring_rib(self, profile, inset, x0, x1, band="gunmetal", inner_band=None, mat=MAT_TRIM):
        """Structural rib that follows a profile [(y, z), ...], standing proud of it
        by `inset` (toward the profile's face side) and spanning x0..x1."""
        pts = [Vector(p) for p in profile]
        n = len(pts)
        normals = []
        for i in range(n - 1):
            d = (pts[i + 1] - pts[i]).normalized()
            normals.append(Vector((d.y, -d.x)))
        off = []
        for i in range(n):
            if i == 0:
                off.append(pts[i] + normals[0] * inset)
            elif i == n - 1:
                off.append(pts[i] + normals[-1] * inset)
            else:
                m = (normals[i - 1] + normals[i]).normalized()
                off.append(pts[i] + m * (inset / max(m.dot(normals[i]), 0.3)))
        out = self.extrude_profile([(p.x, p.y) for p in off], x0, x1, inner_band or band, mat)
        lo, hi = [], []
        for i in range(n - 1):
            a, b, c, d = pts[i], pts[i + 1], off[i + 1], off[i]
            lo.append(self.face([(x0, a.x, a.y), (x0, b.x, b.y), (x0, c.x, c.y), (x0, d.x, d.y)], band=band, mat=mat))
            hi.append(self.face([(x1, a.x, a.y), (x1, b.x, b.y), (x1, c.x, c.y), (x1, d.x, d.y)], band=band, mat=mat))
        self._orient(lo, (-1, 0, 0))
        self._orient(hi, (1, 0, 0))
        for i, tang in ((0, pts[0] - pts[1]), (n - 1, pts[-1] - pts[-2])):
            a, d = pts[i], off[i]
            f = self.face([(x0, a.x, a.y), (x1, a.x, a.y), (x1, d.x, d.y), (x0, d.x, d.y)], band=band, mat=mat)
            self._orient([f], (0, tang.x, tang.y))
            out.append(f)
        return out + lo + hi

    def tube(self, path, r, segs=8, band="rubber", mat=MAT_TRIM, caps=False, up=(0, 0, 1), smooth=True):
        """Sweep a circle along a polyline path. UV: U along length, V around (band fit)."""
        P = [Vector(p) for p in path]
        _, p0, p1, nat = BANDS[_band_id(band)]
        dens = (p1 - p0) / nat
        rings = []
        dist = 0.0
        side = None
        for i, p in enumerate(P):
            a = (P[i] - P[i - 1]).normalized() if i > 0 else None
            b = (P[i + 1] - P[i]).normalized() if i < len(P) - 1 else None
            t = ((a if a is not None else b) + (b if b is not None else a)).normalized()
            if i > 0:
                dist += (P[i] - P[i - 1]).length
            if side is None:
                ref = Vector(up) if abs(t.dot(Vector(up))) < 0.95 else Vector((1, 0, 0))
                side = t.cross(ref).normalized()
            else:
                side = (side - t * side.dot(t)).normalized()
            upn = side.cross(t).normalized()
            # at a bend the ring sits in the bisector plane: stretch it along the bend
            bend, k = None, 1.0
            if a is not None and b is not None:
                bd = a - b
                bd = bd - t * bd.dot(t)
                if bd.length > 1e-5:
                    bend = bd.normalized()
                    k = 1.0 / max(a.dot(t), 0.35)
            ring = []
            for j in range(segs):
                ang = 2 * math.pi * j / segs
                off = (side * math.cos(ang) + upn * math.sin(ang)) * r
                if bend is not None:
                    off = off + bend * off.dot(bend) * (k - 1.0)
                ring.append(self.v(p + off))
            rings.append((ring, dist, p))
        out = []
        for i in range(len(rings) - 1):
            ra, da, pa = rings[i]
            rb, db, pb = rings[i + 1]
            mid = self.M @ ((pa + pb) / 2)
            for j in range(segs):
                jn = (j + 1) % segs
                va = (p0 + PAD + (p1 - p0 - 2 * PAD) * j / segs) / ATLAS
                vb = (p0 + PAD + (p1 - p0 - 2 * PAD) * (j + 1) / segs) / ATLAS
                ua, ub = da * dens / ATLAS, db * dens / ATLAS
                f = self.face(verts=[ra[j], ra[jn], rb[jn], rb[j]], mat=mat,
                              uvs=[(ua, va), (ua, vb), (ub, vb), (ub, va)], smooth=smooth)
                f.normal_update()
                if (f.calc_center_median() - mid).dot(f.normal) < 0:
                    f.normal_flip()
                out.append(f)
        if caps:
            for idx, tang in ((0, P[0] - P[1]), (len(rings) - 1, P[-1] - P[-2])):
                f = self.face(verts=list(rings[idx][0]), band=band, mat=mat)
                self._orient([f], tang)
                out.append(f)
        return out

    def lathe(self, profile, segs=16, band="steel", mat=MAT_TRIM, a0=0.0, a1=2 * math.pi, smooth=True):
        """Revolve a profile [(r, z), ...] about local Z. Faces point to the right of
        travel in (r, z): trace bottom-centre -> outward -> up -> back to the axis
        for a closed solid."""
        full = abs((a1 - a0) - 2 * math.pi) < 1e-6
        ncol = segs if full else segs + 1
        angles = [a0 + (a1 - a0) * j / segs for j in range(ncol)]
        V, poles = {}, {}
        for j, a in enumerate(angles):
            ca, sa = math.cos(a), math.sin(a)
            for i, (r, z) in enumerate(profile):
                if r < 1e-6:
                    if i not in poles:
                        poles[i] = self.v((0, 0, z))
                    V[(j, i)] = poles[i]
                else:
                    V[(j, i)] = self.v((r * ca, r * sa, z))
        M3 = self.M.to_3x3()
        out = []
        for j in range(segs):
            jn = (j + 1) % ncol
            am = a0 + (a1 - a0) * (j + 0.5) / segs
            radial = Vector((math.cos(am), math.sin(am), 0))
            for i in range(len(profile) - 1):
                vs = []
                for vv in (V[(j, i)], V[(jn, i)], V[(jn, i + 1)], V[(j, i + 1)]):
                    if vv not in vs:
                        vs.append(vv)
                if len(vs) < 3:
                    continue
                (ra, za), (rb, zb) = profile[i], profile[i + 1]
                dr, dz = rb - ra, zb - za
                seg_smooth = smooth and abs(dz) > abs(dr) * 0.3
                b = band[i] if isinstance(band, (list, tuple)) else band
                m = mat[i] if isinstance(mat, (list, tuple)) else mat
                f = self.face(verts=vs, band=b, mat=m, smooth=seg_smooth)
                f.normal_update()
                want = M3 @ (radial * dz + Vector((0, 0, -dr)))
                if f.normal.dot(want) < 0:
                    f.normal_flip()
                out.append(f)
        return out

    def sweep(self, path, profile, bands, mat=MAT_TRIM, caps=True, cap_band="gunmetal"):
        """Sweep a profile [(r, z), ...] along a plan-view polyline [(x, y), ...].
        r is measured along the path's LEFT normal (mitred at the joints). Faces
        point to the right of travel in (r, z), so trace the section CCW."""
        P = [Vector((x, y, 0.0)) for x, y in path]
        n = len(P)
        N = []
        for i in range(n):
            dirs = []
            if i > 0:
                dirs.append((P[i] - P[i - 1]).normalized())
            if i < n - 1:
                dirs.append((P[i + 1] - P[i]).normalized())
            t = sum(dirs, Vector()).normalized()
            nl = Vector((-t.y, t.x, 0.0))
            k = 1.0
            if len(dirs) == 2:
                d0 = dirs[0]
                k = 1.0 / max(nl.dot(Vector((-d0.y, d0.x, 0.0))), 0.3)
            N.append(nl * k)
        rings = [[self.v(P[i] + N[i] * r + Vector((0, 0, z))) for r, z in profile] for i in range(n)]
        M3 = self.M.to_3x3()
        out = []
        for i in range(n - 1):
            sd = (P[i + 1] - P[i]).normalized()
            nl = Vector((-sd.y, sd.x, 0.0))
            for j in range(len(profile) - 1):
                (ra, za), (rb, zb) = profile[j], profile[j + 1]
                b = bands[j] if isinstance(bands, (list, tuple)) else bands
                m = mat[j] if isinstance(mat, (list, tuple)) else mat
                f = self.face(verts=[rings[i][j], rings[i][j + 1], rings[i + 1][j + 1], rings[i + 1][j]], band=b, mat=m)
                f.normal_update()
                want = M3 @ (nl * (zb - za) + Vector((0, 0, -(rb - ra))))
                if f.normal.dot(want) < 0:
                    f.normal_flip()
                out.append(f)
        if caps:
            m0 = mat[0] if isinstance(mat, (list, tuple)) else mat
            for idx, tang in ((0, P[0] - P[1]), (n - 1, P[-1] - P[-2])):
                f = self.face(verts=list(rings[idx]), band=cap_band, mat=m0)
                self._orient([f], tang)
                out.append(f)
        return out

    # --------------------------------------------------------------- output
    def finish(self, name, recalc=False):
        bm = self.bm
        ngons = [f for f in bm.faces if len(f.verts) > 4]
        if ngons:
            bmesh.ops.triangulate(bm, faces=ngons, quad_method="BEAUTY", ngon_method="BEAUTY")
        loose = [v for v in bm.verts if not v.link_faces]
        if loose:
            bmesh.ops.delete(bm, geom=loose, context="VERTS")
        bm.normal_update()
        apply_trim_uvs(bm, self.uv, self.trim, self.floor_tile)
        me = bpy.data.meshes.get(name)
        if me is None:
            me = bpy.data.meshes.new(name)
        else:
            me.clear_geometry()
            me.materials.clear()
        bm.to_mesh(me)
        bm.free()
        for m in self.mats:
            me.materials.append(get_material(m))
        if "trim" in me.attributes:
            me.attributes.remove(me.attributes["trim"])
        me.update()
        return me


def apply_trim_uvs(bm, uvl, triml, floor_tile=1.0):
    up = Vector((0, 0, 1))
    for f in bm.faces:
        t = f[triml]
        if t == CUSTOM:
            continue
        loops = list(f.loops)
        if t == FLOOR:
            for lp in loops:
                co = lp.vert.co
                lp[uvl].uv = (co.x / floor_tile, co.y / floor_tile)
            continue
        n = f.normal
        if n.length < 1e-8:
            for lp in loops:
                lp[uvl].uv = (0.0, 0.0)
            continue
        if abs(n.z) < 0.7:
            T = up.cross(n).normalized()
        else:
            best = None
            for i in range(len(loops)):
                e = loops[i].vert.co - loops[i - 1].vert.co
                if best is None or e.length > best.length:
                    best = e
            T = (best - n * best.dot(n)).normalized()
        B = n.cross(T).normalized()
        pts = [lp.vert.co for lp in loops]
        us = [p.dot(T) for p in pts]
        vs = [p.dot(B) for p in pts]
        w = max(us) - min(us)
        h = max(vs) - min(vs)
        if t == FILL:
            for lp, uu, vv in zip(loops, us, vs):
                lp[uvl].uv = ((uu - min(us)) / max(w, 1e-6), (vv - min(vs)) / max(h, 1e-6))
            continue
        if abs(n.z) < 0.7 and h > 1.5 * w:
            T, B = B, n.cross(B).normalized()
            us = [p.dot(T) for p in pts]
            vs = [p.dot(B) for p in pts]
            w, h = max(us) - min(us), max(vs) - min(vs)
        _, p0, p1, nat = BANDS[t]
        dens = (p1 - p0) / nat
        bp = (p1 - p0) - 2 * PAD
        vmin = min(vs)
        vc = (min(vs) + max(vs)) / 2
        fit = h * dens > bp
        for lp, uu, vv in zip(loops, us, vs):
            U = uu * dens / ATLAS
            if fit:
                V = (p0 + PAD + (vv - vmin) / max(h, 1e-6) * bp) / ATLAS
            else:
                V = ((p0 + p1) / 2 + (vv - vc) * dens) / ATLAS
            lp[uvl].uv = (U, V)


# ---------------------------------------------------------------------------
# Object helpers
# ---------------------------------------------------------------------------
def place(name, mesh, coll, loc=(0, 0, 0), rot_z=0.0, props=None):
    """Create (or reuse) an object using `mesh` - a linked duplicate when the
    mesh is shared."""
    ob = bpy.data.objects.get(name)
    if ob is not None and ob.type != "MESH":
        bpy.data.objects.remove(ob, do_unlink=True)
        ob = None
    if ob is None:
        ob = bpy.data.objects.new(name, mesh)
    else:
        ob.data = mesh
    for c in list(ob.users_collection):
        if c != coll:
            c.objects.unlink(ob)
    if ob.name not in coll.objects:
        coll.objects.link(ob)
    ob.location = loc
    ob.rotation_euler = (0, 0, rot_z)
    ob.scale = (1, 1, 1)
    for k, v in (props or {}).items():
        ob[k] = v
    return ob


def obj(name, mb_or_mesh, coll, loc=(0, 0, 0), rot=(0, 0, 0), props=None, parent=None):
    """Finish a builder (or take a mesh) into an object; replaces an existing
    object of the same name."""
    mesh = mb_or_mesh.finish(name + "_mesh") if isinstance(mb_or_mesh, MB) else mb_or_mesh
    ob = bpy.data.objects.get(name)
    if ob is not None and ob.type != "MESH":
        bpy.data.objects.remove(ob, do_unlink=True)
        ob = None
    if ob is None:
        ob = bpy.data.objects.new(name, mesh)
    else:
        ob.data = mesh
    for c in list(ob.users_collection):
        if c != coll:
            c.objects.unlink(ob)
    if ob.name not in coll.objects:
        coll.objects.link(ob)
    ob.parent = parent
    ob.matrix_parent_inverse.identity()
    ob.location = loc
    ob.rotation_euler = rot
    ob.scale = (1, 1, 1)
    for k, v in (props or {}).items():
        ob[k] = v
    return ob


def edge_frame(a, b):
    """Location + Z rotation for a module whose local X runs from a to b and whose
    local +Y points to the left of the edge (the room interior for CCW outlines)."""
    a, b = Vector(a), Vector(b)
    d = b - a
    return (a.x, a.y, 0.0), math.atan2(d.y, d.x), d.length
