#!/usr/bin/env python3
"""火山方舟 3D 生成任务 CLI（仅标准库，无第三方依赖）。

子命令：
  create   提交图生 3D 任务，返回 task_id
  status   查询任务状态，成功后返回 file_url
  run      create + 轮询 + 下载到本地，一步完成
  download 按 file_url 下载产物
  doctor   自检 Key 是否可用（不产生费用）

API Key 查找顺序：--key > 环境变量 ARK_API_KEY > 本 Skill 目录下的 .ark_key 文件。
所有结果以 JSON 打印到 stdout；过程日志打到 stderr。
"""
import argparse
import base64
import json
import os
import re
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import PurePosixPath

__version__ = "0.2.9"

BASE = "https://ark.cn-beijing.volces.com/api/v3"
TASKS = BASE + "/contents/generations/tasks"
DEFAULT_MODEL = "doubao-seed3d-2-0-260328"
KEY_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".ark_key"
)
IMG_EXTS = {".jpg": "jpeg", ".jpeg": "jpeg", ".png": "png", ".webp": "webp",
            ".bmp": "bmp", ".tif": "tiff", ".tiff": "tiff", ".gif": "gif"}
MODEL_EXTS = (".glb", ".gltf", ".obj", ".usd", ".usdz", ".stl", ".fbx")
MAX_IMAGE_BYTES = 30 * 1024 * 1024


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def fail(msg, code=1):
    print(json.dumps({"error": msg}, ensure_ascii=False))
    sys.exit(code)


def find_key(explicit=None):
    """返回 (key, source)：source 为 arg / env / file / none。"""
    for name, cand in (("arg", explicit), ("env", os.getenv("ARK_API_KEY"))):
        if cand and cand.strip():
            return cand.strip(), name
    if os.path.isfile(KEY_FILE):
        with open(KEY_FILE, encoding="utf-8") as f:
            content = f.read().strip()
        if content:
            return content, "file"
    return None, "none"


def load_key(explicit=None):
    key, _ = find_key(explicit)
    if not key:
        fail(f"缺少方舟 API Key：请写入 {KEY_FILE}，或设置环境变量 ARK_API_KEY，或传 --key。")
    return key


def http_json(method, url, key, payload=None, timeout=60):
    data = None
    headers = {"Authorization": "Bearer " + key}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "ignore")
            return resp.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = {"raw": body[:2000]}
        return e.code, parsed
    except urllib.error.URLError as e:
        fail(f"网络请求失败：{e.reason}（检查代理或网络出口）")


def normalize_image(image):
    """返回 Ark 可用的 image_url 值：公网 URL 或 data:<fmt>;base64,<data>。"""
    if image.lower().startswith(("http://", "https://")):
        return image
    if image.startswith("data:"):
        return image
    path = os.path.expanduser(image)
    if not os.path.isfile(path):
        fail(f"找不到图片文件，也不是 URL：{image}")
    ext = os.path.splitext(path)[1].lower()
    if ext not in IMG_EXTS:
        fail(f"图片格式不支持：{ext}（仅支持 jpeg/png/webp/bmp/tiff/gif）")
    size = os.path.getsize(path)
    if size > MAX_IMAGE_BYTES:
        fail("图片 %.1f MB 超过 30 MB 上限，请先压缩或改用公网 URL（先上传取 URL）。"
             % (size / 1024 / 1024))
    with open(path, "rb") as f:
        raw = f.read()
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:image/{IMG_EXTS[ext]};base64,{b64}"


def build_payload(image, model, fmt, level):
    return {
        "model": model,
        "content": [
            {"type": "text", "text": f"--subdivisionlevel {level} --fileformat {fmt}"},
            {"type": "image_url", "image_url": {"url": normalize_image(image)}},
        ],
    }


def create_task(payload, key, dry_run=False):
    if dry_run:
        shown = json.loads(json.dumps(payload))
        url = shown["content"][1]["image_url"]["url"]
        if url.startswith("data:"):
            shown["content"][1]["image_url"]["url"] = url[:60] + "...(base64 已省略)"
        print(json.dumps({"dry_run": True, "request": shown}, ensure_ascii=False, indent=2))
        return None
    for attempt in range(3):
        code, resp = http_json("POST", TASKS, key, payload)
        if code == 200:
            log("任务已创建：{}".format(resp.get("id")))
            return resp.get("id")
        if code == 429:
            wait = 20 * (attempt + 1)
            log(f"触发限流（429），{wait} 秒后重试（{attempt + 1}/3）")
            time.sleep(wait)
            continue
        if code in (401, 403):
            fail(f"鉴权失败（{code}）：API Key 无效，或账号未开通 3D 生成模型。"
                 f"{json.dumps(resp, ensure_ascii=False)[:500]}", 2)
        fail(f"创建任务失败（HTTP {code}）：{json.dumps(resp, ensure_ascii=False)[:800]}")
    fail("连续限流，任务未创建。请稍后再试。")


def get_task(task_id, key):
    return http_json("GET", TASKS + "/" + task_id, key)


def poll_task(task_id, key, interval, timeout):
    started = time.time()
    while True:
        code, resp = get_task(task_id, key)
        if code != 200:
            fail(f"查询任务失败（HTTP {code}）：{json.dumps(resp, ensure_ascii=False)[:800]}")
        status = resp.get("status")
        if status == "succeeded":
            return resp
        if status == "failed":
            fail(f"任务失败：{json.dumps(resp.get('error', resp), ensure_ascii=False)[:800]}")
        if status == "cancelled":
            fail(f"任务已取消：task_id={task_id}")
        if time.time() - started > timeout:
            fail(f"等待超时（{timeout} 秒仍为 {status}），task_id={task_id} "
                 f"仍可稍后用 status 子命令查询。")
        log(f"状态：{status}，{interval} 秒后再查…")
        time.sleep(interval)


def file_url_of(task):
    content = task.get("content") or {}
    return content.get("file_url") or content.get("url") or ""


def guess_ext(filename, file_url):
    """从 Content-Disposition 文件名或 URL 推断产物后缀，兜底 glb。"""
    for cand in (os.path.splitext(filename or "")[1],
                 os.path.splitext((file_url or "").split("?")[0])[1]):
        if cand and cand.lower() in MODEL_EXTS:
            return cand.lower()
    return ".glb"


def sniff_ext(path):
    """按文件头判断真实格式：PK=zip 包（方舟常见）、glTF=裸模型、其它返回 None。"""
    with open(path, "rb") as f:
        head = f.read(4)
    if head[:2] == b"PK":
        return ".zip"
    if head[:4] == b"glTF":
        return ".glb"
    return None


def extract_model_bundle(zip_path, out_dir, task_id, preferred_format=None):
    """从方舟的 zip 产物中取出模型文件，返回其本地路径。

    glb 直接取出；obj 会把同目录的 mtl 与贴图一起带出来，否则贴图引用会断。
    """
    with zipfile.ZipFile(zip_path) as z:
        names = {}
        for info in z.infolist():
            path = PurePosixPath(info.filename)
            if info.is_dir() or path.is_absolute() or ".." in path.parts:
                continue
            if "\\" in info.filename or ":" in info.filename:
                continue
            names[path] = info
        members = [path for path in names if path.suffix.lower() in MODEL_EXTS]
        if not members:
            return None

        preferred_ext = f".{preferred_format}"
        member = min(members, key=lambda p: (p.suffix.lower() != preferred_ext,
                                              MODEL_EXTS.index(p.suffix.lower())))
        ext = member.suffix.lower()

        if ext == ".obj":
            dest_root = os.path.join(out_dir, f"model-{task_id}")
            for path, info in names.items():
                if not path.is_relative_to(member.parent):
                    continue
                rel = path.relative_to(member.parent)
                dst = os.path.join(dest_root, *rel.parts)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with z.open(info) as src, open(dst, "wb") as fp:
                    shutil.copyfileobj(src, fp)
            target = os.path.join(dest_root, member.name)
        else:
            target = os.path.join(out_dir, f"model-{task_id}{ext}")
            with z.open(names[member]) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)

    log(f"已从压缩包解出模型：{member} -> {target}")
    return target


def download(file_url, out_dir, task_id, preferred_format=None):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", task_id):
        fail("task_id 只能包含字母、数字、连字符和下划线")
    os.makedirs(out_dir, exist_ok=True)
    req = urllib.request.Request(file_url)
    temp_path = None
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            cd = resp.headers.get("Content-Disposition", "")
            name = ""
            if "filename=" in cd:
                name = cd.split("filename=")[-1].strip('"; ')
            ext = guess_ext(name, file_url)
            with tempfile.NamedTemporaryFile(dir=out_dir, delete=False) as f:
                temp_path = f.name
                shutil.copyfileobj(resp, f, length=1 << 20)

        # 方舟的下载名可能是 .glb，实际返回内容则是 zip 包。
        ext = sniff_ext(temp_path) or ext
        path = os.path.join(out_dir, f"model-{task_id}{ext}")
        os.replace(temp_path, path)
        temp_path = None
    except urllib.error.URLError as e:
        fail(f"下载失败：{e.reason}（产物链接 24 小时有效，过期需重新生成）")
    finally:
        if temp_path:
            os.unlink(temp_path)

    model_path = path
    if path.lower().endswith(".zip"):
        try:
            model_path = extract_model_bundle(path, out_dir, task_id, preferred_format) or path
        except zipfile.BadZipFile:
            fail(f"下载的产物不是有效的 ZIP 文件：{path}")

    return {"path": path, "model_path": model_path, "bytes": os.path.getsize(path)}


def main():
    if "--version" in sys.argv[1:]:
        print(f"ark_3d {__version__}")
        return
    ap = argparse.ArgumentParser(description="火山方舟 3D 生成任务")
    ap.add_argument("--key", help="Ark API Key（默认读 ARK_API_KEY 或 .ark_key）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("create", help="提交图生 3D 任务")
    p.add_argument("--image", required=True, help="公网图片 URL 或本地图片路径")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--format", default="obj", choices=["obj", "glb", "usd", "usdz"],
                   help="默认 obj（保留 mtl 与贴图，打印链路直接可用）；glb 仅特殊场景才用")
    p.add_argument("--level", default="high", choices=["high", "medium", "low"],
                   help="默认 high（100 万面）；medium=50 万、low=10 万")
    p.add_argument("--dry-run", action="store_true", help="只打印请求体，不真实调用")

    p = sub.add_parser("status", help="查询单个任务")
    p.add_argument("--task-id", required=True)

    p = sub.add_parser("run", help="创建 + 轮询 + 下载")
    p.add_argument("--image", required=True)
    p.add_argument("--out", required=True, help="产物保存目录")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--format", default="obj", choices=["obj", "glb", "usd", "usdz"],
                   help="默认 obj（保留 mtl 与贴图，打印链路直接可用）；glb 仅特殊场景才用")
    p.add_argument("--level", default="high", choices=["high", "medium", "low"],
                   help="默认 high（100 万面）；medium=50 万、low=10 万")
    p.add_argument("--poll-interval", type=int, default=15)
    p.add_argument("--timeout", type=int, default=1500)

    p = sub.add_parser("download", help="按 file_url 下载")
    p.add_argument("--file-url", required=True)
    p.add_argument("--task-id", required=True)
    p.add_argument("--out", required=True)

    sub.add_parser("doctor", help="自检：Key 是否已配置、是否被服务端接受（不产生费用）")

    args = ap.parse_args()
    if args.cmd == "download":
        info = download(args.file_url, args.out, args.task_id)
        print(json.dumps(info, ensure_ascii=False))
        return

    if args.cmd == "doctor":
        key, source = find_key(args.key)
        if not key:
            print(json.dumps({"ok": False, "key_source": "none", "http": None,
                              "hint": "请先设置环境变量 ARK_API_KEY，"
                                      f"或在本机写入 {KEY_FILE} 后重新自检。"}, ensure_ascii=False))
            sys.exit(0)
        code, _ = http_json("GET", TASKS + "?page_size=1", key)
        if code == 401:
            hint = "方舟未接受 API Key，请在本机检查凭据配置"
        elif code == 403:
            hint = "方舟拒绝访问任务列表，请检查账号权限"
        elif code == 200:
            hint = "任务列表访问成功，请另行在方舟控制台确认 Seed3D 模型已开通"
        else:
            hint = f"任务列表返回 HTTP {code}，无法验证凭据"
        print(json.dumps({"ok": code == 200, "key_source": source, "http": code,
                          "auth": "passed" if code == 200 else "unclear",
                          "hint": hint}, ensure_ascii=False))
    elif args.cmd == "create":
        key = None if args.dry_run else load_key(args.key)
        task_id = create_task(build_payload(args.image, args.model, args.format, args.level),
                              key, args.dry_run)
        if task_id:
            print(json.dumps({"task_id": task_id, "model": args.model}, ensure_ascii=False))
    elif args.cmd == "status":
        key = load_key(args.key)
        code, resp = get_task(args.task_id, key)
        if code != 200:
            fail(f"查询失败（HTTP {code}）：{json.dumps(resp, ensure_ascii=False)[:800]}")
        print(json.dumps({"task_id": args.task_id, "status": resp.get("status"),
                          "file_url": file_url_of(resp),
                          "error": resp.get("error")}, ensure_ascii=False))
    elif args.cmd == "run":
        key = load_key(args.key)
        task_id = create_task(build_payload(args.image, args.model, args.format, args.level),
                              key)
        task = poll_task(task_id, key, args.poll_interval, args.timeout)
        url = file_url_of(task)
        if not url:
            fail(f"任务成功但未返回 file_url：{json.dumps(task, ensure_ascii=False)[:800]}")
        info = download(url, args.out, task_id, args.format)
        print(json.dumps({"task_id": task_id, "status": "succeeded", "file_url": url,
                          "path": info["path"], "model_path": info["model_path"],
                          "bytes": info["bytes"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
