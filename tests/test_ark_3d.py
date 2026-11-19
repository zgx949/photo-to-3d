"""ark_3d.py 的离线单元测试（不需要网络，不产生方舟调用费用）。

运行：python3 -m unittest discover -s tests -v
"""
import base64
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
SCRIPT = os.path.join(ROOT, "scripts", "ark_3d.py")


def load_module():
    spec = importlib.util.spec_from_file_location("ark_3d", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ark = load_module()


def run_cli(argv):
    """执行 CLI，返回 (退出码, stdout)。"""
    buf = io.StringIO()
    with mock.patch.object(sys, "argv", ["ark_3d.py"] + argv), redirect_stdout(buf):
        try:
            ark.main()
            code = 0
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
    return code, buf.getvalue()


class TestPayload(unittest.TestCase):
    def test_build_payload_shape(self):
        p = ark.build_payload("https://example.com/a.png", ark.DEFAULT_MODEL, "glb", "medium")
        self.assertEqual(p["model"], ark.DEFAULT_MODEL)
        self.assertEqual(len(p["content"]), 2)
        self.assertEqual(p["content"][0]["type"], "text")
        self.assertIn("--subdivisionlevel medium", p["content"][0]["text"])
        self.assertIn("--fileformat glb", p["content"][0]["text"])
        self.assertEqual(p["content"][1]["type"], "image_url")
        self.assertEqual(p["content"][1]["image_url"]["url"], "https://example.com/a.png")

    def test_build_payload_params_are_passed_through(self):
        p = ark.build_payload("https://example.com/a.png", ark.DEFAULT_MODEL, "usdz", "low")
        self.assertEqual(p["content"][0]["text"],
                         "--subdivisionlevel low --fileformat usdz")

    def test_text_param_is_not_a_prompt(self):
        # 官方约束：text 只能承载参数，不能描述内容
        p = ark.build_payload("https://example.com/a.png", ark.DEFAULT_MODEL, "obj", "high")
        text = p["content"][0]["text"]
        self.assertEqual(set(text.split()) >= {"--subdivisionlevel", "--fileformat"}, True)


class TestNormalizeImage(unittest.TestCase):
    def test_url_passthrough(self):
        for url in ("http://a.com/x.png", "https://a.com/x.png?q=1"):
            self.assertEqual(ark.normalize_image(url), url)

    def test_data_uri_passthrough(self):
        uri = "data:image/png;base64,AAAA"
        self.assertEqual(ark.normalize_image(uri), uri)

    def test_local_png_to_data_uri(self):
        path = os.path.join(FIXTURES, "tiny.png")
        out = ark.normalize_image(path)
        self.assertTrue(out.startswith("data:image/png;base64,"))
        payload = out.split(",", 1)[1]
        self.assertEqual(base64.b64decode(payload)[:4], b"\x89PNG")

    def test_ext_mapping_jpeg(self):
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"\xff\xd8\xff\xe0")
            path = f.name
        try:
            out = ark.normalize_image(path)
            self.assertTrue(out.startswith("data:image/jpeg;base64,"))
        finally:
            os.unlink(path)

    def test_unsupported_ext_rejected(self):
        with tempfile.NamedTemporaryFile(suffix=".heic", delete=False) as f:
            f.write(b"x")
            path = f.name
        try:
            code, out = run_cli(["create", "--image", path, "--dry-run"])
            self.assertEqual(code, 1)
            self.assertIn("图片格式不支持", json.loads(out)["error"])
        finally:
            os.unlink(path)

    def test_missing_file_rejected(self):
        code, out = run_cli(["create", "--image", "/tmp/definitely-not-here.png", "--dry-run"])
        self.assertEqual(code, 1)
        self.assertIn("找不到图片文件", json.loads(out)["error"])

    def test_oversize_rejected(self):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"x" * (ark.MAX_IMAGE_BYTES + 1))
            path = f.name
        try:
            code, out = run_cli(["create", "--image", path, "--dry-run"])
            self.assertEqual(code, 1)
            self.assertIn("30 MB", json.loads(out)["error"])
        finally:
            os.unlink(path)


class TestKeyResolution(unittest.TestCase):
    def test_arg_wins(self):
        key, src = ark.find_key("sk-arg")
        self.assertEqual((key, src), ("sk-arg", "arg"))

    def test_env_over_file(self):
        fake_key_file = tempfile.NamedTemporaryFile(delete=False)
        fake_key_file.write(b"sk-file\n")
        fake_key_file.close()
        try:
            with mock.patch.object(ark, "KEY_FILE", fake_key_file.name), \
                    mock.patch.dict(os.environ, {"ARK_API_KEY": "sk-env"}):
                self.assertEqual(ark.find_key(), ("sk-env", "env"))
                with mock.patch.dict(os.environ, {"ARK_API_KEY": ""}, clear=False):
                    self.assertEqual(ark.find_key(), ("sk-file", "file"))
        finally:
            os.unlink(fake_key_file.name)

    def test_none(self):
        with mock.patch.object(ark, "KEY_FILE", "/tmp/no-such-key-file"), \
                mock.patch.dict(os.environ, {"ARK_API_KEY": ""}, clear=False):
            self.assertEqual(ark.find_key(), (None, "none"))

    def test_load_key_fails_without_key(self):
        with mock.patch.object(ark, "KEY_FILE", "/tmp/no-such-key-file"), \
                mock.patch.dict(os.environ, {"ARK_API_KEY": ""}, clear=False), \
                redirect_stdout(io.StringIO()) as out:
            with self.assertRaises(SystemExit):
                ark.load_key()
        self.assertIn("缺少方舟 API Key", json.loads(out.getvalue())["error"])


class TestDoctor(unittest.TestCase):
    def test_doctor_without_key_reports_none(self):
        with mock.patch.object(ark, "KEY_FILE", "/tmp/no-such-key-file"), \
                mock.patch.dict(os.environ, {"ARK_API_KEY": ""}, clear=False):
            code, out = run_cli(["doctor"])
        self.assertEqual(code, 0)
        report = json.loads(out)
        self.assertFalse(report["ok"])
        self.assertEqual(report["key_source"], "none")


class TestHelpers(unittest.TestCase):
    def test_file_url_of_variants(self):
        self.assertEqual(ark.file_url_of({"content": {"file_url": "u"}}), "u")
        self.assertEqual(ark.file_url_of({"content": {"url": "u2"}}), "u2")
        self.assertEqual(ark.file_url_of({}), "")

    def test_guess_ext_prefers_filename(self):
        self.assertEqual(ark.guess_ext("a.obj", "https://x/b.glb"), ".obj")

    def test_guess_ext_from_url_with_query(self):
        self.assertEqual(ark.guess_ext("", "https://x/b.usdz?sign=1&t=2"), ".usdz")

    def test_guess_ext_defaults_to_glb(self):
        self.assertEqual(ark.guess_ext("", ""), ".glb")
        self.assertEqual(ark.guess_ext("a.bin", "https://x/b.bin"), ".glb")


class TestBundle(unittest.TestCase):
    """方舟实际返回的是 zip 包（内含 pbr/*.glb），需要按文件头识别并解包。"""

    def test_sniff_ext_detects_zip(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "model.glb")
            with open(p, "wb") as f:
                f.write(b"PK\x03\x04rest")
            self.assertEqual(ark.sniff_ext(p), ".zip")

    def test_sniff_ext_detects_gltf(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "model.glb")
            with open(p, "wb") as f:
                f.write(b"glTF\x02\x00\x00\x00")
            self.assertEqual(ark.sniff_ext(p), ".glb")

    def test_sniff_ext_unknown(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "model.bin")
            with open(p, "wb") as f:
                f.write(b"\x00\x01\x02\x03")
            self.assertIsNone(ark.sniff_ext(p))

    def test_extract_model_bundle_picks_glb(self):
        import zipfile
        with tempfile.TemporaryDirectory() as d:
            zpath = os.path.join(d, "model-cgt-test.zip")
            payload = b"glTF\x02\x00\x00\x00payload"
            with zipfile.ZipFile(zpath, "w") as z:
                z.writestr("pbr/mesh_textured_pbr.glb", payload)
                z.writestr("README.txt", b"ignore me")
            out_dir = os.path.join(d, "out")
            os.makedirs(out_dir)
            target = ark.extract_model_bundle(zpath, out_dir, "cgt-test")
            self.assertEqual(target, os.path.join(out_dir, "model-cgt-test.glb"))
            with open(target, "rb") as f:
                self.assertEqual(f.read(), payload)

    def test_extract_model_bundle_picks_obj_and_mtl(self):
        import zipfile
        with tempfile.TemporaryDirectory() as d:
            zpath = os.path.join(d, "model-cgt-obj.zip")
            with zipfile.ZipFile(zpath, "w") as z:
                z.writestr("pbr/mesh_textured_pbr.obj", b"v 0 0 0\n")
                z.writestr("pbr/mesh_textured_pbr.mtl", b"newmtl m\n")
                z.writestr("pbr/textures/diffuse.png", b"PNG")
            out_dir = os.path.join(d, "out")
            os.makedirs(out_dir)
            target = ark.extract_model_bundle(zpath, out_dir, "cgt-obj")
            self.assertEqual(target, os.path.join(out_dir, "model-cgt-obj", "mesh_textured_pbr.obj"))
            # mtl 与贴图必须一起带出来，否则 obj 的材质引用会断
            self.assertTrue(os.path.exists(os.path.join(out_dir, "model-cgt-obj", "mesh_textured_pbr.mtl")))
            self.assertTrue(os.path.exists(os.path.join(out_dir, "model-cgt-obj", "textures", "diffuse.png")))

    def test_extract_model_bundle_prefers_glb_over_obj(self):
        import zipfile
        with tempfile.TemporaryDirectory() as d:
            zpath = os.path.join(d, "model-cgt-mixed.zip")
            with zipfile.ZipFile(zpath, "w") as z:
                z.writestr("pbr/model.obj", b"v 0 0 0\n")
                z.writestr("pbr/model.glb", b"glTF\x02\x00\x00\x00")
            out_dir = os.path.join(d, "out")
            os.makedirs(out_dir)
            target = ark.extract_model_bundle(zpath, out_dir, "cgt-mixed")
            self.assertTrue(target.endswith(".glb"))

    def test_extract_model_bundle_without_model(self):
        import zipfile
        with tempfile.TemporaryDirectory() as d:
            zpath = os.path.join(d, "model-cgt-test.zip")
            with zipfile.ZipFile(zpath, "w") as z:
                z.writestr("README.txt", b"no model here")
            out_dir = os.path.join(d, "out")
            os.makedirs(out_dir)
            self.assertIsNone(ark.extract_model_bundle(zpath, out_dir, "cgt-test"))


class TestCliSurface(unittest.TestCase):
    def test_version_flag(self):
        code, out = run_cli(["--version"])
        self.assertEqual(code, 0)
        self.assertIn(ark.__version__, out)

    def test_help_does_not_need_key(self):
        code, _ = run_cli(["--help"])
        self.assertEqual(code, 0)

    def test_dry_run_needs_no_key(self):
        code, out = run_cli(["create", "--image", "https://example.com/a.png", "--dry-run"])
        self.assertEqual(code, 0)
        report = json.loads(out)
        self.assertTrue(report["dry_run"])
        self.assertEqual(report["request"]["model"], ark.DEFAULT_MODEL)

    def test_dry_run_masks_base64(self):
        code, out = run_cli(["create", "--image",
                             os.path.join(FIXTURES, "tiny.png"), "--dry-run"])
        self.assertEqual(code, 0)
        url = json.loads(out)["request"]["content"][1]["image_url"]["url"]
        self.assertTrue(url.endswith("(base64 已省略)"))


if __name__ == "__main__":
    unittest.main()
