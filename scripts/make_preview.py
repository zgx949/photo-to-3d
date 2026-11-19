#!/usr/bin/env python3
"""把 glb 包成单文件 3D 查看器，顺手渲染一张缩略图。

产物：
    <out>/<name>-预览.html   glb 以 base64 内联，浏览器联网载入 Three.js 后可旋转和缩放
    <out>/<name>-预览.png    有 chromium + playwright 时才有，给聊天窗口先看一眼

没有 playwright 不影响 html 产出。
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import sys
from html import escape
from pathlib import Path

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(HERE, "assets", "viewer.template.html")


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def fail(msg: str) -> None:
    print(json.dumps({"ok": False, "error": msg}, ensure_ascii=False))
    raise SystemExit(1)


DEFAULT_BLURB = ("由一张照片生成的卡通参考图转成网格。角色做了手办化处理，比例与细节有取舍，"
                 "不是对真人的精确还原；面部与原片一致的部分取决于提示词里写死的身份特征。")


def build_html(glb_path: str, title: str, out_html: str, blurb: str = DEFAULT_BLURB) -> int:
    if not os.path.exists(TEMPLATE):
        fail(f"找不到查看器模板：{TEMPLATE}")
    template = Path(TEMPLATE).read_text(encoding="utf-8")
    b64 = base64.b64encode(Path(glb_path).read_bytes()).decode("ascii")
    values = {"__GLB_B64__": b64, "__TITLE__": escape(title), "__BLURB__": escape(blurb)}
    html = re.sub(r"__GLB_B64__|__TITLE__|__BLURB__", lambda match: values[match[0]], template)
    Path(out_html).write_text(html, encoding="utf-8")
    return len(b64)


def render_png(html_path: str, out_png: str) -> bool:
    """用无头 chromium 截一张图；环境不具备就安静跳过。"""
    try:
        from playwright.sync_api import Error, sync_playwright
    except ImportError:
        log("[preview] 没有 Playwright，跳过缩略图")
        return False

    proxy = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")
    try:
        with sync_playwright() as p:
            args = ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
            proxy_config = {"server": proxy} if proxy else None
            try:
                browser = p.chromium.launch(args=args, proxy=proxy_config)
            except Error:
                chromium = shutil.which("chromium") or shutil.which("chromium-browser")
                if not chromium:
                    raise
                browser = p.chromium.launch(executable_path=chromium, args=args, proxy=proxy_config)
            try:
                page = browser.new_page(viewport={"width": 1100, "height": 1200}, device_scale_factor=1)
                page.goto(Path(html_path).resolve().as_uri())
                page.locator("#veil.gone").wait_for(state="attached", timeout=20_000)
                page.screenshot(path=out_png)
            finally:
                browser.close()
        return os.path.exists(out_png)
    except Exception as exc:  # noqa: BLE001 截图失败不该拖垮主流程
        log(f"[preview] 缩略图失败：{exc}")
        return False


def main() -> None:
    ap = argparse.ArgumentParser(description="glb → 单文件 3D 查看器（+ 可选缩略图）")
    ap.add_argument("glb", help="彩色 glb 路径")
    ap.add_argument("--out", default="./preview", help="输出目录")
    ap.add_argument("--name", default=None, help="产物名前缀，默认取 glb 文件名")
    ap.add_argument("--title", default=None, help="查看器里显示的名字")
    ap.add_argument("--blurb", default=None, help="页首一段说明，默认用通用文案")
    ap.add_argument("--summary", default=None, help="覆盖说明的实况摘要（尺寸、面数、可否打印）")
    ap.add_argument("--no-png", action="store_true", help="只出 html，不尝试缩略图")
    args = ap.parse_args()

    if not os.path.exists(args.glb):
        fail(f"文件不存在：{args.glb}")
    os.makedirs(args.out, exist_ok=True)
    name = args.name or os.path.splitext(os.path.basename(args.glb))[0]
    title = args.title or name

    html_path = os.path.join(args.out, f"{name}-预览.html")
    blurb = args.blurb or DEFAULT_BLURB
    if args.summary:  # 带上尺寸/面数等实况，比通用文案信息量高
        blurb = args.summary
    b64_len = build_html(args.glb, title, html_path, blurb)
    log(f"[preview] 已内联 glb（base64 {b64_len / 1024 / 1024:.1f} MB）→ {html_path}")

    png_path = None
    if not args.no_png:
        candidate = os.path.join(args.out, f"{name}-预览.png")
        if render_png(html_path, candidate):
            png_path = candidate

    print(json.dumps({
        "ok": True,
        "files": {"html": os.path.abspath(html_path),
                  **({"png": os.path.abspath(png_path)} if png_path else {})},
        "html_mb": round(os.path.getsize(html_path) / 1024 / 1024, 2),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
