#!/usr/bin/env python3
"""
Builds the "Steam Controller (2026)" overlay model from Valve's official CAD.

Source: https://gitlab.steamos.cloud/SteamHardware/SteamController
        (sc_solid_stl_20260429.stl, CC BY-NC-SA 4.0, (c) Valve Corporation)

Valve publishes the controller as a single fused solid. This script:
  1. splits the surface into patches along sharp creases (the seams between
     every button/stick/trigger and the shell are sharp, fillets are not),
  2. picks out each moving part by its location,
  3. caps the openings left behind so nothing looks hollow when parts move,
  4. decimates, smooth-shades and writes one OBJ per overlay mesh slot plus
     info.txt with pivots, travel, popup poses and trackpad geometry.

Usage:
  pip install numpy scipy trimesh pyfqmr
  python3 convert_valve_cad.py sc_solid_stl_20260429.stl "../../models/Steam Controller (2026)"
"""
import math
import os
import sys

import numpy as np
import trimesh
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

try:
    import pyfqmr
except ImportError:
    pyfqmr = None

S = 0.013                               # overlay units per mm (same scale as the DualSense model)
CENTER = np.array([0.0, -24.0, 49.6])   # CAD point that becomes the overlay origin (≈ centre of mass)
CREASE_DEG = 25.0


def to_overlay(p):
    return (np.asarray(p, float) - CENTER) * S


# ---------------------------------------------------------------------------
# Part identification. Anchors are bbox centres (CAD mm) + approx area (mm²).
# CAD axes already match the overlay: +X right, +Y out of the face, +Z towards
# the player (the top edge is at z = 0).
# ---------------------------------------------------------------------------
ANCHORS = {
    "touchpad.obj":      [(-30.3, -7.7, 61.4, 1231)],
    "touchpad2.obj":     [(30.3, -7.7, 61.4, 1231)],
    "left_trigger.obj":  [(-47.7, -32.0, 6.2, 1013)],
    "right_trigger.obj": [(47.7, -32.0, 6.2, 1013)],
    "left_bumper.obj":   [(-47.7, -14.1, 1.2, 641)],
    "right_bumper.obj":  [(47.7, -14.1, 1.2, 641)],
    "dpad":              [(-49.0, -1.05, 20.0, 454)],
    "left_ring.obj":     [(-23.0, 5.95, 31.5, 403)],
    "right_ring.obj":    [(23.0, 5.95, 31.5, 403)],
    "left_cap.obj":      [(-23.0, 7.45, 31.5, 123)],
    "right_cap.obj":     [(23.0, 7.45, 31.5, 123)],
    "left_stick.obj":    [(-23.0, 2.25, 31.5, 86), (-23.0, 0.4, 31.5, 66)],
    "right_stick.obj":   [(23.0, 2.25, 31.5, 86), (23.0, 0.4, 31.5, 66)],
    "paddle1.obj":       [(42.1, -38.0, 53.6, 306)],   # R4
    "paddle2.obj":       [(-42.1, -38.0, 53.6, 308)],  # L4
    "paddle3.obj":       [(48.65, -45.5, 74.35, 310)], # R5
    "paddle4.obj":       [(-48.65, -45.5, 74.35, 313)],# L5
    "a_button.obj":      [(49.0, -0.8, 29.25, 118)],
    "b_button.obj":      [(58.3, -2.5, 20.0, 123)],
    "x_button.obj":      [(39.75, 0.25, 20.0, 117)],
    "y_button.obj":      [(49.0, -0.95, 10.7, 118)],
    "guide_button.obj":  [(0.0, 0.15, 20.0, 114)],     # Steam button
    "misc.obj":          [(0.0, -6.3, 61.9, 102)],     # QAM (…)
    "back_button.obj":   [(-28.3, -0.25, 8.6, 61)],    # View
    "start_button.obj":  [(28.3, -0.25, 8.6, 61)],     # Menu
}


def segment(mesh):
    adj, ang = mesh.face_adjacency, mesh.face_adjacency_angles
    keep = ang < math.radians(CREASE_DEG)
    n = len(mesh.faces)
    g = coo_matrix((np.ones(keep.sum()), (adj[keep, 0], adj[keep, 1])), shape=(n, n))
    count, labels = connected_components(g, directed=False)
    area = np.bincount(labels, weights=mesh.area_faces, minlength=count)
    c = mesh.triangles_center
    lo = np.full((count, 3), np.inf)
    hi = np.full((count, 3), -np.inf)
    for k in range(3):
        np.minimum.at(lo[:, k], labels, c[:, k])
        np.maximum.at(hi[:, k], labels, c[:, k])
    return labels, area, lo, hi


def assign_parts(mesh):
    labels, area, lo, hi = segment(mesh)
    centre = (lo + hi) / 2
    shell_seg = int(np.argmax(area))
    seg_part = {}
    for part, anchors in ANCHORS.items():
        for (x, y, z, a) in anchors:
            d = np.linalg.norm(centre - np.array([x, y, z]), axis=1)
            ok = (d < 4.0) & (np.abs(area - a) < 0.25 * a)
            ok[shell_seg] = False
            if not ok.any():
                raise RuntimeError(f"could not find segment for {part} near {(x, y, z)}")
            best = np.where(ok)[0][np.argmax(area[ok])]
            seg_part[int(best)] = part
    # merge small leftover patches (engraved labels, lip slivers) into the part
    # whose bounding box encloses them
    part_box = {}
    for s, p in seg_part.items():
        b = part_box.get(p, [np.full(3, np.inf), np.full(3, -np.inf)])
        part_box[p] = [np.minimum(b[0], lo[s]), np.maximum(b[1], hi[s])]
    for s in np.where(area < 40)[0]:
        if s in seg_part or s == shell_seg:
            continue
        best, best_vol = None, np.inf
        for p, (blo, bhi) in part_box.items():
            if np.all(lo[s] >= blo - 0.3) and np.all(hi[s] <= bhi + 0.3):
                vol = np.prod(bhi - blo)
                if vol < best_vol:
                    best, best_vol = p, vol
        if best is not None:
            seg_part[int(s)] = best
    face_part = np.full(len(mesh.faces), None, dtype=object)
    for s, p in seg_part.items():
        face_part[labels == s] = p
    return face_part


# ---------------------------------------------------------------------------
# Mesh helpers
# ---------------------------------------------------------------------------
def boundary_loops(mesh):
    """Ordered vertex loops along open edges."""
    edges = mesh.edges_sorted
    uniq, inv, cnt = np.unique(edges, axis=0, return_inverse=True, return_counts=True)
    open_mask = cnt[inv.ravel()] == 1
    directed = mesh.edges[open_mask]                 # keep face winding direction
    nxt = {}
    for a, b in directed:
        nxt.setdefault(int(a), []).append(int(b))
    loops, seen = [], set()
    for start in list(nxt.keys()):
        if start in seen:
            continue
        loop, v = [], start
        while v not in seen and v in nxt:
            seen.add(v)
            loop.append(v)
            v = nxt[v][0]
        if len(loop) >= 3:
            loops.append(loop)
    return loops


def cap_holes(mesh, outward_hint):
    """Fan-fill every open loop. outward_hint(loop_centre, loop_normal) -> +1/-1."""
    verts = [mesh.vertices]
    faces = [mesh.faces]
    nv = len(mesh.vertices)
    for loop in boundary_loops(mesh):
        pts = mesh.vertices[loop]
        c = pts.mean(0)
        # loop normal (Newell)
        n = np.zeros(3)
        for i in range(len(pts)):
            p, q = pts[i] - c, pts[(i + 1) % len(pts)] - c
            n += np.cross(p, q)
        if np.linalg.norm(n) < 1e-9:
            continue
        n /= np.linalg.norm(n)
        idx = np.array(loop)
        fan = np.stack([np.full(len(idx), nv), idx, np.roll(idx, -1)], 1)
        if outward_hint(c, n) < 0:
            fan = fan[:, ::-1]
        verts.append(c[None])
        faces.append(fan)
        nv += 1
    return trimesh.Trimesh(np.vstack(verts), np.vstack(faces), process=False)


def decimate(mesh, target):
    if pyfqmr is None or len(mesh.faces) <= target:
        return mesh
    s = pyfqmr.Simplify()
    s.setMesh(mesh.vertices.astype(np.float64), mesh.faces.astype(np.int32))
    s.simplify_mesh(target_count=int(target), aggressiveness=6, preserve_border=True, verbose=False)
    v, f, _ = s.getMesh()
    return trimesh.Trimesh(v, f, process=True)


def write_obj(path, mesh, origin_cad, rotate=None):
    """Write mesh (CAD mm) in overlay units relative to origin_cad."""
    m = trimesh.graph.smooth_shade(mesh, angle=math.radians(35.0))
    v = to_overlay(m.vertices) - to_overlay(origin_cad)
    n = m.vertex_normals.copy()
    if rotate is not None:      # express in a local frame (rows = local axes)
        v = v @ rotate.T
        n = n @ rotate.T
    lo, hi = v.min(0), v.max(0)
    span = np.maximum(hi - lo, 1e-9)
    uv = np.stack([(v[:, 0] - lo[0]) / span[0], 1 - (v[:, 2] - lo[2]) / span[2]], 1)
    f = m.faces + 1
    with open(path, "w", newline="\n") as fh:
        fh.write("# Steam Controller (2026) - converted from Valve's CAD (CC BY-NC-SA 4.0)\n")
        fh.write("# by tools/steam_controller_model/convert_valve_cad.py\n")
        fh.write(f"o {os.path.basename(path)[:-4]}\n")
        fh.write("".join(f"v {a:.4f} {b:.4f} {c:.4f}\n" for a, b, c in v))
        fh.write("".join(f"vt {a:.3f} {b:.3f}\n" for a, b in uv))
        fh.write("".join(f"vn {a:.3f} {b:.3f} {c:.3f}\n" for a, b, c in n))
        fh.write("".join(f"f {a}/{a}/{a} {b}/{b}/{b} {c}/{c}/{c}\n" for a, b, c in f))
    print(f"  {os.path.basename(path):20s} {len(v):7d} verts {len(f):7d} tris")


def euler_xyz(R):
    """Angles (a, b, c) with R = Rx(a) @ Ry(b) @ Rz(c) — the order drawMesh applies them."""
    b = math.asin(max(-1.0, min(1.0, R[0, 2])))
    a = math.atan2(-R[1, 2], R[2, 2])
    c = math.atan2(-R[0, 1], R[0, 0])
    return a, b, c


def rot_x(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def rot_y(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def rot_z(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def rotation_to(a, b):
    """Smallest rotation matrix taking unit vector a onto unit vector b."""
    a, b = a / np.linalg.norm(a), b / np.linalg.norm(b)
    v, c = np.cross(a, b), float(a.dot(b))
    if c < -0.999999:
        return rot_x(math.pi)
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx / (1 + c)


def mean_normal(mesh, mask=None):
    n = mesh.face_normals * mesh.area_faces[:, None]
    if mask is not None:
        n = n[mask]
    n = n.sum(0)
    return n / np.linalg.norm(n)


# ---------------------------------------------------------------------------
def main(stl_path, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    print("loading", stl_path)
    mesh = trimesh.load(stl_path, force="mesh", process=True)
    print("  ", len(mesh.faces), "triangles")
    face_part = assign_parts(mesh)

    parts = {}
    for p in sorted(set(x for x in face_part if x is not None)):
        parts[p] = mesh.submesh([np.where(face_part == p)[0]], append=True)

    # split the D-pad cross into four arms
    dpad = parts.pop("dpad")
    dc = dpad.bounds.mean(0)
    tc = dpad.triangles_center - dc
    arm = np.where(np.abs(tc[:, 0]) > np.abs(tc[:, 2]),
                   np.where(tc[:, 0] < 0, "dpad_left.obj", "dpad_right.obj"),
                   np.where(tc[:, 2] < 0, "dpad_up.obj", "dpad_down.obj"))
    for name in ("dpad_up.obj", "dpad_down.obj", "dpad_left.obj", "dpad_right.obj"):
        parts[name] = dpad.submesh([np.where(arm == name)[0]], append=True)

    # cap the parts' open backs (outward = away from the part's own centre)
    uncapped = {name: m.copy() for name, m in parts.items()}
    for name in list(parts):
        if name.endswith("_ring.obj") or name.endswith("_cap.obj"):
            continue   # covered by the neighbouring stick part; a flat fill would z-fight with the concave cap
        pc = parts[name].bounds.mean(0)
        parts[name] = cap_holes(parts[name], lambda c, n, pc=pc: np.sign(n.dot(c - pc)) or 1)

    # shell = everything else; cap where parts were removed (outward = towards the part)
    shell = mesh.submesh([np.where(face_part == None)[0]], append=True)  # noqa: E711
    part_centres = np.array([parts[p].bounds.mean(0) for p in parts])

    def shell_hint(c, n):
        pc = part_centres[np.argmin(np.linalg.norm(part_centres - c, axis=1))]
        return np.sign(n.dot(pc - c)) or 1
    shell = cap_holes(shell, shell_hint)

    # top / bottom shell split along a plane that follows the face slope
    tc = shell.triangles_center
    top_mask = tc[:, 1] > (-8.0 - 0.18 * tc[:, 2])
    top = shell.submesh([np.where(top_mask)[0]], append=True)
    bottom = shell.submesh([np.where(~top_mask)[0]], append=True)

    info = {}

    def entry(name, position=(0, 0, 0), travel=(0, 0, 0), popup_offset=(0, 0, 0), popup_rotation=(0, 0, 0),
              trigger_max=0.0, stick_max=0.0, touch_w=0.0, touch_h=0.0):
        info[name] = [*position, *travel, *popup_offset, *popup_rotation, trigger_max, stick_max, touch_w, touch_h]

    print("writing meshes")
    write_obj(os.path.join(out_dir, "top_shell.obj"), decimate(top, 40000), CENTER)
    write_obj(os.path.join(out_dir, "bottom_shell.obj"), decimate(bottom, 22000), CENTER)
    entry("top_shell.obj")
    entry("bottom_shell.obj")

    # face buttons: static position, travel straight into the face
    for name, depth in (("a_button.obj", 0.8), ("b_button.obj", 0.8), ("x_button.obj", 0.8), ("y_button.obj", 0.8),
                        ("guide_button.obj", 0.6), ("misc.obj", 0.6), ("back_button.obj", 0.5),
                        ("start_button.obj", 0.5), ("dpad_up.obj", 0.6), ("dpad_down.obj", 0.6),
                        ("dpad_left.obj", 0.6), ("dpad_right.obj", 0.6)):
        m = parts[name]
        n = mean_normal(m, m.face_normals[:, 1] > 0.5)
        write_obj(os.path.join(out_dir, name), decimate(m, 2500), CENTER)
        entry(name, travel=tuple(-n * depth * S))

    # thumbsticks: stem/ring/cap share a pivot below the stem
    stick_max = math.radians(20.0)
    for side in ("left", "right"):
        cap = parts[f"{side}_cap.obj"]
        stem = parts[f"{side}_stick.obj"]
        cx, cz = cap.bounds.mean(0)[0], cap.bounds.mean(0)[2]
        pivot = np.array([cx, stem.bounds[0][1] - 5.0, cz])
        for part, tris in (("stick", 2000), ("ring", 4500), ("cap", 2000)):
            write_obj(os.path.join(out_dir, f"{side}_{part}.obj"), decimate(parts[f"{side}_{part}.obj"], tris), pivot)
            entry(f"{side}_{part}.obj", position=tuple(to_overlay(pivot)), stick_max=stick_max)

    # trackpads + touch points (touch points move in the tilted plane of their pad)
    for pad_name, point_name in (("touchpad.obj", "touch_point1.obj"), ("touchpad2.obj", "touch_point2.obj")):
        pad = parts[pad_name]
        up = pad.face_normals[:, 1] > 0.8
        n = mean_normal(pad, up)
        top_pts = pad.triangles_center[up]
        # in-plane axes: u = pad's "right" edge, v = towards the player
        ref = np.array([1.0, 0.0, 0.0])
        u0 = ref - n * ref.dot(n); u0 /= np.linalg.norm(u0)
        v0 = np.cross(u0, n)
        if v0[2] < 0:
            v0 = -v0
        rel0 = top_pts - top_pts.mean(0)
        pu, pv = rel0 @ u0, rel0 @ v0
        best_area, best_t = np.inf, 0.0
        for t in np.radians(np.arange(-45.0, 45.0, 0.1)):   # min-area rectangle
            cu = math.cos(t) * pu + math.sin(t) * pv
            cv = -math.sin(t) * pu + math.cos(t) * pv
            area = np.ptp(cu) * np.ptp(cv)
            if area < best_area:
                best_area, best_t = area, t
        u = math.cos(best_t) * u0 + math.sin(best_t) * v0
        v = np.cross(u, n)
        if v[2] < 0:
            v = -v
        # extents along u / v
        rel = top_pts - top_pts.mean(0)
        w = np.ptp(rel @ u)
        h = np.ptp(rel @ v)
        centre = top_pts.mean(0) + n * 0.15
        surf = top_pts[np.argmin(np.linalg.norm(top_pts - centre, axis=1))]
        centre = centre + n * ((surf - centre).dot(n) + 0.25)
        write_obj(os.path.join(out_dir, pad_name), decimate(pad, 7000), CENTER)
        entry(pad_name, travel=tuple(-n * 0.5 * S))
        # local frame -> world: columns (u, n, v)
        R = np.stack([u, n, v], 1)
        a, b, c = euler_xyz(R)
        assert np.allclose(rot_x(a) @ rot_y(b) @ rot_z(c), R, atol=1e-6)
        disc_r = 3.4
        disc = trimesh.creation.cylinder(radius=disc_r, height=0.35, sections=48)
        disc.apply_transform(trimesh.transformations.rotation_matrix(-math.pi / 2, [1, 0, 0]))  # axis -> +Y
        disc.apply_translation([0, 0.175, 0])
        disc_world = disc.copy()
        disc_world.vertices = disc.vertices @ R.T + centre
        write_obj(os.path.join(out_dir, point_name), disc_world, centre, rotate=R.T)
        entry(point_name, position=tuple(to_overlay(centre)), popup_rotation=(a, b, c),
              touch_w=(w - 2 * disc_r) * S, touch_h=(h - 2 * disc_r) * S)
        print(f"    {pad_name}: {w:.1f} x {h:.1f} mm, tilt {math.degrees(math.acos(n[1])):.1f} deg")

    # shoulder buttons
    for side, sgn in (("left", -1), ("right", 1)):
        bumper = parts[f"{side}_bumper.obj"]
        bc = bumper.bounds.mean(0)
        write_obj(os.path.join(out_dir, f"{side}_bumper.obj"), decimate(bumper, 4000), bc)
        entry(f"{side}_bumper.obj", position=tuple(to_overlay(bc)), travel=(0, -0.6 * S, 0.3 * S),
              popup_offset=(0, 18.0 * S, -4.0 * S))
        trig = parts[f"{side}_trigger.obj"]
        lo, hi = trig.bounds
        hinge = np.array([(lo[0] + hi[0]) / 2, hi[1], 6.0])
        write_obj(os.path.join(out_dir, f"{side}_trigger.obj"), decimate(trig, 5000), hinge)
        entry(f"{side}_trigger.obj", position=tuple(to_overlay(hinge)), trigger_max=math.radians(18.0),
              popup_offset=(0, (2.0 - hinge[1]) * S, (-9.0 - hinge[2]) * S), popup_rotation=(math.pi / 2, 0, 0))

    # grip buttons: travel into the grip, popup = flipped face-up beside the grip
    for name, sgn in (("paddle1.obj", 1), ("paddle2.obj", -1), ("paddle3.obj", 1), ("paddle4.obj", -1)):
        pdl = parts[name]
        pc = pdl.bounds.mean(0)
        n = mean_normal(uncapped[name])     # the capped mesh is closed, its mean normal ~ 0
        write_obj(os.path.join(out_dir, name), decimate(pdl, 2500), pc)
        R = rotation_to(n, np.array([0.0, 1.0, 0.0]))
        a, b, c = euler_xyz(R)
        target = np.array([sgn * 87.0, 4.0, pc[2]])
        entry(name, position=tuple(to_overlay(pc)), travel=tuple(-n * 0.8 * S),
              popup_offset=tuple((target - pc) * S), popup_rotation=(a, b, c))

    order = ["top_shell.obj", "bottom_shell.obj", "extra.obj", "left_trigger.obj", "right_trigger.obj",
             "left_stick.obj", "right_stick.obj", "left_ring.obj", "right_ring.obj", "a_button.obj",
             "b_button.obj", "x_button.obj", "y_button.obj", "back_button.obj", "guide_button.obj",
             "start_button.obj", "left_cap.obj", "right_cap.obj", "left_bumper.obj", "right_bumper.obj",
             "dpad_up.obj", "dpad_down.obj", "dpad_left.obj", "dpad_right.obj", "misc.obj", "paddle1.obj",
             "paddle2.obj", "paddle3.obj", "paddle4.obj", "touchpad.obj", "touch_point1.obj",
             "touch_point2.obj", "touchpad2.obj"]
    with open(os.path.join(out_dir, "info.txt"), "w", newline="\n") as fh:
        for name in order:
            fh.write(name + "\n")
            for val in info.get(name, [0.0] * 16):
                fh.write(("%g" % round(val, 6)) + "\n")
    with open(os.path.join(out_dir, "LICENSE.txt"), "w", newline="\n") as fh:
        fh.write(
            "Steam Controller (2026) model\n"
            "=============================\n\n"
            "Adapted from the official Steam Controller CAD files released by Valve Corporation:\n"
            "https://gitlab.steamos.cloud/SteamHardware/SteamController\n\n"
            "Original material (c) Valve Corporation, licensed under the Creative Commons\n"
            "Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0):\n"
            "https://creativecommons.org/licenses/by-nc-sa/4.0/\n\n"
            "Changes: the single CAD solid was split into separately moving parts (buttons,\n"
            "sticks, trackpads, bumpers, triggers, grip buttons), openings were capped, the\n"
            "mesh was decimated and re-scaled, and overlay metadata (info.txt) was added.\n"
            "This adapted model is likewise licensed under CC BY-NC-SA 4.0. It is not\n"
            "affiliated with or endorsed by Valve. Unlike the rest of this repository\n"
            "(MIT), the files in this folder may not be used commercially.\n")
    print("done:", out_dir)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "Steam Controller (2026)")
