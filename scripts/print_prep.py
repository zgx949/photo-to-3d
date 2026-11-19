#!/usr/bin/env python3
"""把图生 3D 的开口壳整理成可打印件：补实体、校尺度、转 Z-up、导 STL。

用法：
    python3 scripts/print_prep.py model.obj --height 150 --out ./print --solidify

三条能力：
  1. 尺度：按朝上轴把最大尺寸缩到 --height 毫米
  2. 补实体（--solidify）：泊松重建 + 局部拓扑修复，把开口壳变成封闭实体
  3. 朝向：STL 统一转成 Z-up（切片软件默认 Z 是竖直方向），并落地到 z=0

依赖：trimesh；--solidify 另需 open3d、pymeshfix；--decimate 另需 fast-simplification。
stdout 只输出 JSON，日志走 stderr。
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from typing import Any

DEFAULT_HEIGHT_MM = 150.0
DEFAULT_SOLID_FACES = 250_000
HEAVY_TRIANGLES = 600_000


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def fail(msg: str, code: int = 1) -> None:
    print(json.dumps({"ok": False, "error": msg}, ensure_ascii=False))
    raise SystemExit(code)


def load_mesh(path: str):
    try:
        import trimesh
    except ImportError:
        fail('缺少 trimesh，请先 pip install trimesh（要补实体再加 open3d、pymeshfix）')

    if not os.path.exists(path):
        fail(f"文件不存在：{path}")

    log(f"[print] 读取 {path}")
    kwargs: dict[str, Any] = {"process": False}
    if path.lower().endswith((".glb", ".gltf")):
        kwargs["force"] = "mesh"
    scene = trimesh.load(path, **kwargs)
    if isinstance(scene, trimesh.Scene):
        meshes = [g for g in scene.geometry.values() if isinstance(g, trimesh.Trimesh)]
        if not meshes:
            fail("文件里没有可用的网格")
        return trimesh.util.concatenate(meshes)
    return scene


def edge_stats(mesh) -> tuple[int, int]:
    """返回 (边界边, 非流形边)。边界边=只被 1 个面引用；非流形边=>2 个面引用。"""
    import numpy as np

    if len(mesh.edges_sorted) == 0:
        return 0, 0
    _, counts = np.unique(mesh.edges_sorted, axis=0, return_counts=True)
    return int((counts == 1).sum()), int((counts > 2).sum())


def clean(mesh) -> list[str]:
    """去退化面、合并顶点、补洞、统一法线。返回做过的处理步骤。"""
    import trimesh

    steps: list[str] = []
    if len(mesh.faces) == 0:
        return steps

    keep = mesh.nondegenerate_faces()
    if not keep.all():
        mesh.update_faces(keep)
        steps.append("remove_degenerate_faces")

    before = len(mesh.vertices)
    mesh.merge_vertices()
    if len(mesh.vertices) != before:
        steps.append("merge_vertices")

    if not mesh.is_watertight:
        trimesh.repair.fill_holes(mesh)
        steps.append("fill_holes")

    trimesh.repair.fix_normals(mesh)
    steps.append("fix_normals")
    return steps


def solidify(mesh, samples: int, depth: int, target_faces: int,
             focus_head: float = 0.0, axis: int = 1) -> tuple[Any, dict[str, Any]]:
    """泊松重建把开口壳补成封闭实体，再用 pymeshfix 收拾残余的非流形边。

    为什么是泊松：图生 3D 的产物是一层皮，边界能到几万条；先用有向点云重建成接近闭合的
    曲面（泊松天然输出封闭面），再把剩下的几条坏边修掉，比直接补洞稳得多。
    """
    try:
        import numpy as np
        import open3d as o3d
        import pymeshfix
        import trimesh
    except ImportError as exc:
        fail(f"补实体需要 open3d 与 pymeshfix（{exc}）。可先只做尺度与诊断，去掉 --solidify")

    before_boundary, before_nonmanifold = edge_stats(mesh)
    points, face_index = trimesh.sample.sample_surface(mesh, samples)
    point_normals = mesh.face_normals[face_index]

    # 高精度修复：头部区域加密采样。脸在整张图上占得少，均匀采样会把五官抹平，
    # 只把上半身的采样密度翻倍，脸和头发才能留住细节，代价是多花一点重建时间。
    head_extra = 0
    if focus_head > 0:
        coords = mesh.vertices[:, axis]
        thresh = coords.max() - focus_head * (coords.max() - coords.min())
        centroids = mesh.vertices[mesh.faces].mean(axis=1)[:, axis]
        head_faces = mesh.faces[centroids >= thresh]
        if len(head_faces):
            head_mesh = trimesh.Trimesh(vertices=mesh.vertices, faces=head_faces, process=False)
            extra_pts, extra_idx = trimesh.sample.sample_surface(head_mesh, int(samples * 0.6))
            points = np.vstack([points, extra_pts])
            point_normals = np.vstack([point_normals, head_mesh.face_normals[extra_idx]])
            head_extra = len(extra_pts)
            log(f"[print] 头部加密：额外 {head_extra:,} 个采样点（{len(points) / samples:.1f}× 密度）")

    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points.astype(np.float64))
    pcd.normals = o3d.utility.Vector3dVector(point_normals.astype(np.float64))

    log(f"[print] 泊松重建：{len(points):,} 点，depth={depth}")
    # Open3D 的并行泊松重建有概率在原生层中止进程。
    # https://github.com/isl-org/Open3D/issues/2027
    recon, _ = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
        pcd, depth=depth, scale=1.1, n_threads=1
    )
    if target_faces > 0 and len(recon.triangles) > target_faces:
        recon = recon.simplify_quadric_decimation(target_number_of_triangles=target_faces)

    solid = trimesh.Trimesh(
        vertices=np.asarray(recon.vertices), faces=np.asarray(recon.triangles), process=True
    )

    # 泊松偶尔留几条非流形边，pymeshfix 处理这种小缺陷很快；开口壳那种大面积缺洞它会卡死
    fixer = pymeshfix.MeshFix(solid.vertices, solid.faces)
    fixer.repair(joincomp=True, remove_smallest_components=False)
    solid = trimesh.Trimesh(vertices=fixer.points, faces=fixer.faces, process=True)
    trimesh.repair.fix_normals(solid)

    return solid, {
        "method": "poisson+pymeshfix",
        "samples": samples,
        "depth": depth,
        "focus_head": focus_head,
        "head_extra_points": head_extra,
        "before": {"boundary_edges": before_boundary, "nonmanifold_edges": before_nonmanifold},
    }


def rotate_to_z_up(mesh, up: str = "y") -> Any:
    """把输入模型的朝上轴转到 Z，并落到 z=0。"""
    import numpy as np
    import trimesh

    if up == "x":
        mesh.apply_transform(trimesh.transformations.rotation_matrix(-np.pi / 2, [0, 1, 0]))
    elif up == "y":
        mesh.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
    mesh.apply_translation([0, 0, -float(mesh.bounds[0][2])])
    return mesh


def main() -> None:
    ap = argparse.ArgumentParser(description="把模型整理成可打印件（尺度 / 补实体 / Z-up / STL）")
    ap.add_argument("model", help="输入模型路径（.obj / .glb / .gltf / .stl）")
    ap.add_argument("--height", type=float, default=DEFAULT_HEIGHT_MM,
                    help=f"目标成品高度（毫米），默认 {DEFAULT_HEIGHT_MM:.0f}")
    ap.add_argument("--up", choices=["x", "y", "z"], default="y",
                    help="模型的朝上轴，默认 y（glTF / 方舟产物是 Y-up）")
    ap.add_argument("--out", default="./print", help="输出目录，默认 ./print")
    ap.add_argument("--name", default=None, help="输出文件名（不含扩展名）")
    ap.add_argument("--keep-source-units", action="store_true", help="不缩放，只检查与导出")
    ap.add_argument("--solidify", action="store_true",
                    help="补成封闭实体（泊松重建），打印前建议开")
    ap.add_argument("--samples", type=int, default=500_000, help="补实体时的采样点数")
    ap.add_argument("--depth", type=int, default=9, help="泊松重建深度，越大越细也越慢")
    ap.add_argument("--decimate", type=int, default=0,
                    help=f"减面到指定面数（0 = 不减；补实体时默认 {DEFAULT_SOLID_FACES:,}）")
    ap.add_argument("--focus-head", type=float, default=0.0,
                    help="头部加密采样的比例（0 关闭，0.2 表示顶部 20%% 高度内取样密度提高）")
    ap.add_argument("--no-stl", action="store_true", help="只导出 obj")
    args = ap.parse_args()

    if not args.keep_source_units and (not math.isfinite(args.height) or args.height <= 0):
        fail("--height 必须是大于 0 的有限数值")
    mesh = load_mesh(args.model)
    if len(mesh.faces) == 0:
        fail("模型里没有三角面")

    axis = {"x": 0, "y": 1, "z": 2}[args.up]
    source_height = float(mesh.extents[axis])
    if source_height <= 0:
        fail("模型沿朝上轴的尺寸为 0，无法确定尺度")

    steps = clean(mesh)
    solidify_info = None

    if args.solidify:
        target_faces = args.decimate or DEFAULT_SOLID_FACES
        mesh, solidify_info = solidify(mesh, args.samples, args.depth, target_faces,
                                       args.focus_head, axis)
        steps.append("solidify_poisson")
    elif args.decimate > 0:
        if args.decimate >= len(mesh.faces):
            fail(f"减面目标 {args.decimate:,} 不小于当前面数 {len(mesh.faces):,}")
        try:
            mesh = mesh.simplify_quadric_decimation(face_count=args.decimate)
        except ImportError:
            fail("减面需要 fast-simplification，请先 pip install fast-simplification")
        steps.append(f"decimate_to_{args.decimate}")

    if args.keep_source_units:
        scale = 1.0
    else:
        scale = args.height / float(mesh.extents[axis])
        mesh.apply_scale(scale)

    rotated = args.up != "z"
    mesh = rotate_to_z_up(mesh, args.up)

    ext = [float(v) for v in mesh.extents]
    height_mm = ext[2]
    width_mm, depth_mm = ext[0], ext[1]
    triangles = len(mesh.faces)

    boundary_edges, nonmanifold_edges = edge_stats(mesh)
    watertight = bool(mesh.is_watertight)

    volume_cm3 = None
    if watertight and mesh.volume > 0:
        bbox_cm3 = float(mesh.bounding_box.volume) / 1000.0
        # 体积不该超过包围盒；超了多半是法线/拓扑有问题，不给错误数字
        if mesh.volume / 1000.0 <= bbox_cm3 * 1.02:
            volume_cm3 = round(float(mesh.volume) / 1000.0, 2)

    warnings: list[str] = []
    if not watertight:
        warnings.append(
            "图生 3D 的产物是开口壳体（不是封闭实体）。下次可加 --solidify 用泊松重建补成实体；"
            "或先试 Bambu Studio / PrusaSlicer / Cura 的自动修复，仍不行再用 Blender "
            "Remesh(Voxel 0.3 mm) → Smooth → Decimate"
        )
    if boundary_edges:
        warnings.append(f"{boundary_edges:,} 条开放边（壳体缺口，模型上表现为裂纹）")
    if nonmanifold_edges:
        warnings.append(f"{nonmanifold_edges:,} 条非流形边（被 3 个以上面共用，切片可能算错内外）")
    if triangles > HEAVY_TRIANGLES:
        warnings.append(f"三角面 {triangles:,} 偏多，切片会明显变慢，建议 --decimate 250000")
    if height_mm < 20:
        warnings.append("成品高度不足 20 mm，手指、五官这类细节打不出来")

    name = args.name or os.path.splitext(os.path.basename(args.model))[0]
    os.makedirs(args.out, exist_ok=True)

    obj_path = os.path.join(args.out, f"{name}-{height_mm:.0f}mm.obj")
    mesh.export(obj_path, file_type="obj")

    stl_path = None
    if not args.no_stl:
        stl_path = os.path.join(args.out, f"{name}-{height_mm:.0f}mm.stl")
        mesh.export(stl_path, file_type="stl")

    print(json.dumps({
        "ok": True,
        "source": os.path.abspath(args.model),
        "solidified": bool(solidify_info),
        "solidify": solidify_info,
        "triangles": triangles,
        "scale_applied": round(scale, 6),
        "up": "z",
        "rotated_to_z_up": rotated,
        "size_mm": {"width": round(width_mm, 2), "depth": round(depth_mm, 2),
                    "height": round(height_mm, 2)},
        "watertight": watertight,
        "boundary_edges": boundary_edges,
        "nonmanifold_edges": nonmanifold_edges,
        "volume_cm3": volume_cm3,
        "cleaned": steps,
        "printable": bool(watertight and boundary_edges == 0 and nonmanifold_edges == 0
                          and height_mm >= 20),
        "warnings": warnings,
        "files": {"obj": os.path.abspath(obj_path),
                  "stl": os.path.abspath(stl_path) if stl_path else None},
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
