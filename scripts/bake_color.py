#!/usr/bin/env python3
"""把原始带贴图模型的颜色搬到重建后的实体网格上，输出彩色 obj / glb。

背景：补实体（泊松重建）只重建几何，UV 与贴图会丢，成品是素模。本脚本按「最近点 → 重心坐标
→ UV → 采样贴图」把颜色取回来，写成顶点色；再做一遍邻域去斑，去掉错配产生的零星色点。

用法：
    python3 scripts/bake_color.py \
        --solid  print-solid/手办-150mm.obj \
        --textured extracted/pbr/mesh_textured_pbr.obj \
        --out ./color --name 手办

依赖：trimesh、rtree 与 scipy（最近点查询）、numpy、pillow。
stdout 只输出 JSON。
"""

from __future__ import annotations

import argparse
import json
import os
import sys


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def fail(msg: str, code: int = 1) -> None:
    print(json.dumps({"ok": False, "error": msg}, ensure_ascii=False))
    raise SystemExit(code)


def load_textured(path: str):
    """返回 (网格, 贴图)。obj 从 mtl 取 image；glb 走 PBR 的 baseColorTexture。"""
    import trimesh

    if not os.path.exists(path):
        fail(f"文件不存在：{path}")
    mesh = trimesh.load(path, force="mesh", process=False)
    if getattr(mesh.visual, "uv", None) is None:
        fail("这个模型没有 UV，不能从贴图取色；请用带贴图的 obj 或 glb")

    material = getattr(mesh.visual, "material", None)
    image = getattr(material, "image", None) if material is not None else None
    if image is None and material is not None:
        image = getattr(material, "baseColorTexture", None)  # glb 的 PBR 贴图
    if image is None:
        fail("找不到贴图：obj 需要 mtl 与 textures/ 同目录，glb 需要内嵌 baseColorTexture")
    return mesh, image


def align(textured, solid, solid_up: str) -> float:
    """把带贴图的壳搬进实体所在的坐标系：按高度缩放 → 转正 → 平移到底面/居中。"""
    import numpy as np
    import trimesh

    axis = {"x": 0, "y": 1, "z": 2}[solid_up]
    src = float(textured.extents[1])  # 方舟产物 Y-up
    if src <= 0 or solid.extents[axis] <= 0:
        fail("模型沿朝上轴的尺寸为 0，无法对齐贴图")
    scale = float(solid.extents[axis]) / src
    textured.apply_scale(scale)

    if solid_up == "x":
        textured.apply_transform(trimesh.transformations.rotation_matrix(-np.pi / 2, [0, 0, 1]))
    elif solid_up == "z":
        textured.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))

    target_min = np.asarray(solid.bounds[0], dtype=float)
    current_min = np.asarray(textured.bounds[0], dtype=float)
    shift = target_min - current_min
    # 只在“贴地”和“水平居中”两个方向上对位，避免把模型沿厚度方向强推
    center_delta = np.asarray(solid.centroid, dtype=float) - np.asarray(textured.centroid, dtype=float)
    shift[axis] = target_min[axis] - current_min[axis]
    for i in range(3):
        if i != axis:
            shift[i] = center_delta[i]
    textured.apply_translation(shift)
    return scale


def sample_colors(solid, textured, image):
    import numpy as np
    import trimesh

    log("[color] 查询最近点")
    closest, distance, tri_id = trimesh.proximity.closest_point(textured, solid.vertices)

    tri = textured.faces[tri_id]
    a, b, c = textured.vertices[tri[:, 0]], textured.vertices[tri[:, 1]], textured.vertices[tri[:, 2]]
    v0, v1, v2 = b - a, c - a, closest - a
    d00 = (v0 * v0).sum(1)
    d01 = (v0 * v1).sum(1)
    d11 = (v1 * v1).sum(1)
    d20 = (v2 * v0).sum(1)
    d21 = (v2 * v1).sum(1)
    den = d00 * d11 - d01 * d01
    den[den == 0] = 1e-12
    bv = (d11 * d20 - d01 * d21) / den
    bw = (d00 * d21 - d01 * d20) / den
    bu = 1.0 - bv - bw

    weights = np.stack([bu, bv, bw], 1)[:, :, None]
    uv = (textured.visual.uv[tri] * weights).sum(1)

    image = np.asarray(image.convert("RGB"))
    height, width = image.shape[:2]
    px = np.clip((uv[:, 0] * width).astype(int), 0, width - 1)
    py = np.clip(((1.0 - uv[:, 1]) * height).astype(int), 0, height - 1)
    return image[py, px].astype(np.uint8), distance


def despeckle(mesh, colors, threshold: int = 45, rounds: int = 2):
    """顶点色去斑：与邻域中位色差太大就替换掉。头发、皮肤上的零星黑点来自最近点错配。"""
    import numpy as np

    edges = mesh.edges_unique
    n = len(mesh.vertices)
    neighbors: list[list[int]] = [[] for _ in range(n)]
    for i, j in edges:
        neighbors[i].append(j)
        neighbors[j].append(i)

    colors = colors.astype(np.int16)
    for _ in range(rounds):
        changed = 0
        new = colors.copy()
        for i, nb in enumerate(neighbors):
            if not nb:
                continue
            med = np.median(colors[nb], axis=0)
            if np.abs(colors[i] - med).max() > threshold:
                new[i] = med.astype(np.int16)
                changed += 1
        colors = new
        log(f"[color] 去斑：修正 {changed:,} 个顶点")
    return np.clip(colors, 0, 255).astype(np.uint8)


def sharpen_head(mesh, colors, ratio: float = 0.22, strength: float = 1.15,
                 band=(0.70, 0.92), luma_min: float = 95.0, axis: int = 2):
    """只在脸部那一圈做反锐化：提眼眉、唇线与鼻影，不碰头发和身体。

    头顶是最暗的一片头发，整段锐化会把它压成死黑；所以用高度带
    band=(下界, 上界) 框住脸，再用亮度下限把头发、深色边缘剔掉。
    """
    import numpy as np

    height = mesh.vertices[:, axis]
    normalized = (height - height.min()) / max(height.max() - height.min(), 1e-9)
    lo, hi = band[0], band[1]
    # 没显式给 band 时，按 ratio 从顶部往下算一段
    if ratio > 0 and band == (0.70, 0.92):
        hi = 1.0
        lo = max(0.0, 1.0 - ratio)
    idx = np.where((normalized >= lo) & (normalized <= hi))[0]
    if not len(idx):
        return colors.astype(np.uint8), 0
    luma = colors[idx].astype(np.float32) @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    idx = idx[luma >= luma_min]

    base = colors.astype(np.float32)
    edges = mesh.edges_unique
    acc = np.zeros_like(base)
    cnt = np.zeros(len(base), dtype=np.float32)
    np.add.at(acc, edges[:, 0], base[edges[:, 1]])
    np.add.at(acc, edges[:, 1], base[edges[:, 0]])
    np.add.at(cnt, edges[:, 0], 1)
    np.add.at(cnt, edges[:, 1], 1)
    cnt[cnt == 0] = 1
    blur = acc / cnt[:, None]

    sharp = blur[idx] + strength * (base[idx] - blur[idx])
    out = base.copy()
    out[idx] = np.clip(sharp, 0, 255)
    return out.astype(np.uint8), int(len(idx))


def main() -> None:
    ap = argparse.ArgumentParser(description="把贴图颜色搬到重建后的网格，输出彩色 obj / glb")
    ap.add_argument("--solid", required=True, help="补实体后的模型（.obj / .stl / .glb）")
    ap.add_argument("--textured", required=True, help="原始带贴图模型（方舟 obj 包里的 mesh_textured_pbr.obj）")
    ap.add_argument("--out", default="./color", help="输出目录")
    ap.add_argument("--name", default=None, help="输出文件名（不含扩展名）")
    ap.add_argument("--solid-up", choices=["x", "y", "z"], default="z",
                    help="实体模型的朝上轴，print_prep 输出的是 z")
    ap.add_argument("--no-despeckle", action="store_true", help="不做邻域去斑")
    ap.add_argument("--sharpen-head", type=float, default=0.0,
                    help="头部顶点色反锐化比例（0 关闭，0.22 表示顶部 22%% 高度）；用于高精度修复")
    ap.add_argument("--sharpen-strength", type=float, default=1.25, help="锐化强度，1.0 起")
    args = ap.parse_args()

    try:
        import numpy as np
        import rtree  # noqa: F401  trimesh 最近点查询依赖
        import scipy  # noqa: F401  trimesh 最近点查询依赖
        import trimesh
        from PIL import Image  # noqa: F401  trimesh 贴图依赖
    except ImportError as exc:
        fail(f"无法加载上色依赖（{exc}）。请运行 python -m pip install -r requirements.txt。")

    solid = trimesh.load(args.solid, force="mesh", process=False)
    if len(solid.faces) == 0:
        fail("实体模型里没有三角面")
    textured, texture_image = load_textured(args.textured)
    if getattr(solid.visual, "uv", None) is not None:
        log("[color] 实体自带 UV，仍然按最近点重投颜色，结果以本脚本为准")

    scale = align(textured, solid, args.solid_up)
    colors, distance = sample_colors(solid, textured, texture_image)
    log(f"[color] 最近点距离：平均 {distance.mean():.2f} mm，最大 {distance.max():.2f} mm")

    if not args.no_despeckle:
        colors = despeckle(solid, colors)
    else:
        colors = colors.astype(np.uint8)

    sharpened = 0
    if args.sharpen_head > 0:
        colors, sharpened = sharpen_head(solid, colors, args.sharpen_head, args.sharpen_strength,
                                         axis={"x": 0, "y": 1, "z": 2}[args.solid_up])
        log(f"[color] 头部锐化：{sharpened:,} 个顶点")

    solid.visual = trimesh.visual.ColorVisuals(
        vertex_colors=np.hstack([colors, np.full((len(colors), 1), 255, dtype=np.uint8)])
    )

    name = args.name or os.path.splitext(os.path.basename(args.solid))[0]
    os.makedirs(args.out, exist_ok=True)

    obj_path = os.path.join(args.out, f"{name}-彩色.obj")
    solid.export(obj_path, file_type="obj")

    # 预览用 glb 转回 Y-up，浏览器 / Blender / 手机都能直接正着看
    preview = solid.copy()
    if args.solid_up == "x":
        preview.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [0, 0, 1]))
    elif args.solid_up == "z":
        preview.apply_transform(trimesh.transformations.rotation_matrix(-np.pi / 2, [1, 0, 0]))
    if args.solid_up != "y":
        preview.apply_translation([0, -float(preview.bounds[0][1]), 0])
    glb_path = os.path.join(args.out, f"{name}-彩色.glb")
    preview.export(glb_path, file_type="glb")

    print(json.dumps({
        "ok": True,
        "solid": os.path.abspath(args.solid),
        "textured": os.path.abspath(args.textured),
        "scale_applied": round(scale, 6),
        "vertices": int(len(solid.vertices)),
        "triangles": int(len(solid.faces)),
        "nearest_mm": {"mean": round(float(distance.mean()), 3),
                       "max": round(float(distance.max()), 3)},
        "despeckled": not args.no_despeckle,
        "head_sharpened_vertices": sharpened,
        "mean_rgb": [int(v) for v in colors.mean(0).round(0)],
        "files": {"obj": os.path.abspath(obj_path), "glb": os.path.abspath(glb_path)},
        "note": "顶点色在切片软件里支持不一致；打印上色仍建议分件换色或后期手涂",
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
