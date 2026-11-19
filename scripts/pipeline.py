#!/usr/bin/env python3
"""一条命令跑完整条链路：3D 生成（obj）→ 补实体 → 上色。

默认交付四件：可打印 obj / stl、彩色 obj / glb 预览，外加原始带贴图 obj 作为保底素材。
不复用别人的判断——每一步都调各自脚本，stdout 只输出整条链路的 JSON 汇总。

用法：
    python3 scripts/pipeline.py --image ref.png --out ./out --name 小王
    python3 scripts/pipeline.py --skip-3d ./out/model-cgt-xxx/mesh_textured_pbr.obj --out ./out --name 小王
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ARK = os.path.join(HERE, "ark_3d.py")
PRINT = os.path.join(HERE, "print_prep.py")
COLOR = os.path.join(HERE, "bake_color.py")
PREVIEW = os.path.join(HERE, "make_preview.py")

DEFAULT_HEIGHT_MM = 150.0

# 高精度修复档：头部加密采样 + 更细的泊松 + 保留更多面 + 面部锐化
REFINE = {"samples": 800_000, "depth": 10, "faces": 600_000, "focus_head": 0.22, "sharpen_head": 0.22}
FAST = {"samples": 500_000, "depth": 9, "faces": 250_000, "focus_head": 0.0, "sharpen_head": 0.0}


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def fail(msg: str, code: int = 1) -> None:
    print(json.dumps({"ok": False, "error": msg}, ensure_ascii=False))
    raise SystemExit(code)


def run_step(tag: str, argv: list[str], required: bool = True) -> dict | None:
    """跑一个子脚本，返回它输出的 JSON；子脚本的 stderr 原样转发给用户看进度。"""
    log(f"[pipeline] === {tag} ===")
    proc = subprocess.run([sys.executable, *argv], capture_output=True, text=True)
    if proc.stderr.strip():
        print(proc.stderr.strip(), file=sys.stderr)
    if proc.returncode != 0:
        detail = proc.stdout.strip()[:500] or proc.stderr.strip()[:500]
        if not required:
            log(f"[pipeline] {tag} 跳过：{detail}")
            return None
        fail(f"{tag} 失败：{detail}")
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        fail(f"{tag} 没有返回可解析的 JSON：{proc.stdout.strip()[:400]}")


def main() -> None:
    ap = argparse.ArgumentParser(description="生成 3D → 补实体 → 上色，一条命令跑完")
    ap.add_argument("--image", help="参考图（公网 URL 或本地路径）；用 --skip-3d 时可省略")
    ap.add_argument("--out", default="./out", help="输出根目录")
    ap.add_argument("--name", default=None, help="产物名前缀，默认用 task_id / 文件名")
    ap.add_argument("--height", type=float, default=DEFAULT_HEIGHT_MM, help="成品高度（毫米）")
    ap.add_argument("--level", default="high", choices=["high", "medium", "low"])
    ap.add_argument("--model", default=None, help="默认 doubao-seed3d-2-0-260328")
    ap.add_argument("--skip-3d", metavar="OBJ", default=None,
                    help="跳过 3D 生成，直接把已有带贴图的 obj 跑完后续步骤")
    ap.add_argument("--no-color", action="store_true", help="只补实体，不上色")
    ap.add_argument("--no-preview", action="store_true", help="不生成 3D 查看器与缩略图")
    ap.add_argument("--no-refine", action="store_true",
                    help="跳过本地高精度修复，回到快档（25 万面、脸不再加密）")
    ap.add_argument("--faces", type=int, default=None, help="成品面数上限，默认修复档 60 万")
    ap.add_argument("--no-solidify", action="store_true",
                    help="不补实体，只做尺度与导出（成品会有裂纹，仅用于对照）")
    args = ap.parse_args()

    started = time.time()
    os.makedirs(args.out, exist_ok=True)
    steps: list[dict] = []

    # ---- 1. 3D 生成（obj，打印优先）----
    if args.skip_3d:
        source = os.path.abspath(args.skip_3d)
        if not os.path.exists(source):
            fail(f"--skip-3d 指向的文件不存在：{source}")
        task_id = None
        log(f"[pipeline] 复用已有模型：{source}")
    else:
        if not args.image:
            fail("需要 --image（或用 --skip-3d 复用已有模型）")
        timer = time.time()
        argv = [ARK, "run", "--image", args.image,
                "--out", os.path.join(args.out, "3d"), "--format", "obj", "--level", args.level]
        if args.model:
            argv += ["--model", args.model]
        info = run_step("3D 生成（obj）", argv)
        source = info.get("model_path") or info.get("path")
        task_id = info.get("task_id")
        steps.append({"step": "ark_obj", "task_id": task_id, "seconds": round(time.time() - timer, 1),
                      "bytes": info.get("bytes")})

    name = args.name or (task_id if task_id else os.path.splitext(os.path.basename(source))[0])
    profile = dict(FAST if args.no_refine else REFINE)
    if args.faces:
        profile["faces"] = args.faces

    # ---- 2. 补实体 + 尺度 + Z-up + STL ----
    timer = time.time()
    argv = [PRINT, source, "--height", str(args.height),
            "--out", os.path.join(args.out, "print"), "--name", name]
    if not args.no_solidify:
        argv += ["--solidify", "--samples", str(profile["samples"]),
                 "--depth", str(profile["depth"]), "--decimate", str(profile["faces"])]
        if profile["focus_head"] > 0:
            argv += ["--focus-head", str(profile["focus_head"])]
    prep = run_step("补实体 / 高精度修复", argv)
    steps.append({"step": "print_prep", "seconds": round(time.time() - timer, 1),
                  "mode": "fast" if args.no_refine else "refine",
                  "printable": prep.get("printable"), "triangles": prep.get("triangles"),
                  "watertight": prep.get("watertight"),
                  "boundary_edges": prep.get("boundary_edges"),
                  "solidify": prep.get("solidify")})

    # ---- 3. 上色：贴图搬回实体 ----
    color = None
    if not args.no_color:
        timer = time.time()
        color_argv = [COLOR, "--solid", prep["files"]["obj"], "--textured", source,
                      "--out", os.path.join(args.out, "color"), "--name", name]
        if profile["sharpen_head"] > 0:
            color_argv += ["--sharpen-head", str(profile["sharpen_head"])]
        color = run_step("上色 + 面部锐化", color_argv, required=False)
        if color:
            steps.append({"step": "bake_color", "seconds": round(time.time() - timer, 1),
                          "nearest_mm": color.get("nearest_mm")})

    # ---- 4. 预览：单文件查看器 + 缩略图，交付时直接点开看 ----
    preview = None
    if color and not args.no_preview:
        timer = time.time()
        size = prep.get("size_mm") or {}
        summary = (f"{name}：{size.get('width', 0)}×{size.get('depth', 0)}×{size.get('height', 0)} mm，"
                   f"{prep.get('triangles', 0):,} 面，"
                   f"{'已补成封闭实体，可直接切片打印' if prep.get('printable') else '未判为可打印'}"
                   f"；颜色为贴图烘到顶点色，用于预览与内容素材。")
        preview = run_step("生成 3D 预览", [
            PREVIEW, color["files"]["glb"], "--out", os.path.join(args.out, "preview"),
            "--name", name, "--title", name, "--summary", summary,
        ], required=False)
        if preview:
            steps.append({"step": "make_preview", "seconds": round(time.time() - timer, 1)})

    files = {
        "source_obj": os.path.abspath(source),
        "printable_obj": prep["files"]["obj"],
        "printable_stl": prep["files"]["stl"],
    }
    if color:
        files["colored_obj"] = color["files"]["obj"]
        files["preview_glb"] = color["files"]["glb"]
    if preview:
        files["preview_html"] = preview["files"]["html"]
        if "png" in preview["files"]:
            files["preview_png"] = preview["files"]["png"]

    warnings = list(prep.get("warnings") or [])
    if not args.no_color and not color:
        warnings.append("上色未完成：源文件没有可用贴图（obj 要 mtl + textures 同目录，glb 要内嵌 baseColorTexture）；"
                        "可先按素模交付，再补一张带贴图的 obj 重跑 --skip-3d")
    if args.no_solidify:
        warnings.append("未补实体：壳体开口，切片会留下裂纹，只适合对照")
    if not prep.get("printable") and not args.no_solidify:
        warnings.append("补实体后仍未判为可打印，看 boundary_edges / nonmanifold_edges 定位")

    print(json.dumps({
        "ok": True,
        "task_id": task_id,
        "name": name,
        "files": files,
        "size_mm": prep.get("size_mm"),
        "triangles": prep.get("triangles"),
        "refine": "off" if args.no_refine else {"samples": profile["samples"], "depth": profile["depth"],
                                               "faces": profile["faces"], "focus_head": profile["focus_head"],
                                               "sharpen_head": profile["sharpen_head"]},
        "printable": bool(prep.get("printable")),
        "watertight": prep.get("watertight"),
        "volume_cm3": prep.get("volume_cm3"),
        "colored": bool(color),
        "steps": steps,
        "seconds_total": round(time.time() - started, 1),
        "warnings": warnings,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
