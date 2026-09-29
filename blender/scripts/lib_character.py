"""Helpers for the character build (scripts/build_character.py).

Conventions match the ship: 1 unit = 1 m, Z up. Characters face -Y, so their left
side is +X. Left bones end in _L and their mirrors in _R. Names use underscores,
never dots, because three.js's GLTFLoader strips dots from node names.
"""
import os
import shutil
import urllib.request
import zipfile

import bpy
import numpy as np
from mathutils import Vector

BUNDLE_URL = ("https://mirror.blender.org/demo/asset-bundles/human-base-meshes/"
              "human-base-meshes-bundle-v1.4.1.zip")
BUNDLE_DIR = "human-base-meshes-bundle-v1.4.1"
BUNDLE_BLEND = BUNDLE_DIR + "/human_base_meshes_bundle.blend"


# ---------------------------------------------------------------------------
# Source asset
# ---------------------------------------------------------------------------
def ensure_bundle(assets_dir):
    """Path to the Human Base Meshes .blend, downloading it (~50 MB) if missing."""
    path = os.path.join(assets_dir, BUNDLE_BLEND)
    if os.path.exists(path):
        return path
    os.makedirs(assets_dir, exist_ok=True)
    zpath = os.path.join(assets_dir, "human-base-meshes.zip")
    print("downloading", BUNDLE_URL)
    with urllib.request.urlopen(BUNDLE_URL) as r, open(zpath, "wb") as f:
        shutil.copyfileobj(r, f)
    with zipfile.ZipFile(zpath) as z:
        z.extractall(assets_dir)
    os.remove(zpath)
    return path


# ---------------------------------------------------------------------------
# numpy <-> mesh
# ---------------------------------------------------------------------------
def get_co(me):
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    return co.reshape(-1, 3)


def set_co(me, co):
    me.vertices.foreach_set("co", np.ascontiguousarray(co, dtype=np.float64).ravel())
    me.update()


def get_normals(me):
    n = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("normal", n)
    return n.reshape(-1, 3)


def smoothstep(e0, e1, x):
    t = np.clip((np.asarray(x, float) - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def seg_dist(p, a, b):
    """Distance from points p (N,3) to segment a-b, and the segment parameter t."""
    a = np.asarray(a, float)
    ab = np.asarray(b, float) - a
    t = np.clip(((p - a) @ ab) / max(ab @ ab, 1e-12), 0.0, 1.0)
    return np.linalg.norm(p - (a + t[:, None] * ab), axis=1), t


# ---------------------------------------------------------------------------
# Vertex groups as a dense matrix
# ---------------------------------------------------------------------------
def read_weights(ob):
    names = [g.name for g in ob.vertex_groups]
    W = np.zeros((len(ob.data.vertices), len(names)))
    for v in ob.data.vertices:
        for g in v.groups:
            W[v.index, g.group] = g.weight
    return names, W


def write_weights(ob, names, W, max_influences=4, eps=1e-3):
    """Replace every vertex group with W (rows are renormalised, top-N kept)."""
    W = W.copy()
    W[W < eps] = 0.0
    if max_influences:
        order = np.argsort(-W, axis=1)
        drop = order[:, max_influences:]
        np.put_along_axis(W, drop, 0.0, axis=1)
    s = W.sum(1, keepdims=True)
    W = np.where(s > 0, W / np.maximum(s, 1e-12), 0.0)
    ob.vertex_groups.clear()
    groups = [ob.vertex_groups.new(name=n) for n in names]
    for j, g in enumerate(groups):
        idx = np.nonzero(W[:, j] > 0)[0]
        for i in idx:
            g.add([int(i)], float(W[i, j]), "REPLACE")
    return W


# ---------------------------------------------------------------------------
# Cross-sections (used to measure joint centres on the source mesh)
# ---------------------------------------------------------------------------
class Sectioner:
    """Plane/mesh intersection contours, grouped into closed loops."""

    def __init__(self, me, co=None):
        self.co = get_co(me) if co is None else co
        ev = np.empty(len(me.edges) * 2, np.int64)
        me.edges.foreach_get("vertices", ev)
        self.ev = ev.reshape(-1, 2)
        le = np.empty(len(me.loops), np.int64)
        me.loops.foreach_get("edge_index", le)
        ls = np.empty(len(me.polygons), np.int64)
        lt = np.empty(len(me.polygons), np.int64)
        me.polygons.foreach_get("loop_start", ls)
        me.polygons.foreach_get("loop_total", lt)
        self.face_edges = [le[s:s + t] for s, t in zip(ls, lt)]
        self.edge_faces = [[] for _ in range(len(me.edges))]
        for f, es in enumerate(self.face_edges):
            for e in es:
                self.edge_faces[e].append(f)

    def contours(self, p, n):
        n = np.asarray(n, float) / np.linalg.norm(n)
        d = (self.co - np.asarray(p, float)) @ n
        a, b = self.ev[:, 0], self.ev[:, 1]
        cross = np.nonzero(d[a] * d[b] < 0)[0]
        if len(cross) == 0:
            return []
        t = d[a[cross]] / (d[a[cross]] - d[b[cross]])
        pts = self.co[a[cross]] + (self.co[b[cross]] - self.co[a[cross]]) * t[:, None]
        idx = {e: i for i, e in enumerate(cross)}
        parent = list(range(len(cross)))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        for i, e in enumerate(cross):
            for f in self.edge_faces[e]:
                for e2 in self.face_edges[f]:
                    j = idx.get(e2)
                    if j is not None and j != i:
                        ri, rj = find(i), find(j)
                        if ri != rj:
                            parent[ri] = rj
        groups = {}
        for i in range(len(cross)):
            groups.setdefault(find(i), []).append(i)
        return [pts[g] for g in groups.values()]

    def trace(self, start, direction, step=0.01, n=60, maxjump=0.05):
        """March section planes along a limb: [(centroid, mean radius)] per step."""
        p = np.asarray(start, float)
        d = np.asarray(direction, float) / np.linalg.norm(direction)
        out = []
        for _ in range(n):
            cs = self.contours(p, d)
            if not cs:
                break
            c = min(cs, key=lambda c: np.linalg.norm(c.mean(0) - p))
            ctr = c.mean(0)
            if len(c) < 4 or np.linalg.norm(ctr - p) > maxjump:
                break
            out.append((ctr, float(np.linalg.norm(c - ctr, axis=1).mean())))
            if len(out) >= 3:
                nd = out[-1][0] - out[-3][0]
                if np.linalg.norm(nd) > 1e-6:
                    d = 0.7 * d + 0.3 * nd / np.linalg.norm(nd)
                    d /= np.linalg.norm(d)
            p = ctr + d * step
        return out


# ---------------------------------------------------------------------------
# Scene helpers
# ---------------------------------------------------------------------------
def collection(name, parent):
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name)
    if c.name not in parent.children:
        parent.children.link(c)
    return c


def link_only(ob, coll):
    for c in list(ob.users_collection):
        c.objects.unlink(ob)
    coll.objects.link(ob)
    return ob


def look_at(ob, target):
    d = Vector(target) - ob.location
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def mirror_name(name):
    if name.endswith("_L"):
        return name[:-2] + "_R"
    if name.endswith("_R"):
        return name[:-2] + "_L"
    return name
