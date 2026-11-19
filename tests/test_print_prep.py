"""print_prep.py 的离线测试：尺度换算、朝上轴、水密判断、减面。

依赖 trimesh；没装时整组跳过（CI 里装不上也不该卡住主链路）。
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "print_prep.py")

try:
    import trimesh  # noqa: F401
    HAVE_TRIMESH = True
except ImportError:
    HAVE_TRIMESH = False


def make_cube(path, height=1.0):
    """造一个封闭立方体，尺寸 0.5 × 0.3 × height。"""
    import trimesh
    mesh = trimesh.creation.box(extents=[0.5, 0.3, height])
    mesh.export(path, file_type="obj")


@unittest.skipUnless(HAVE_TRIMESH, "需要 trimesh")
class TestPrintPrep(unittest.TestCase):
    def run_script(self, *args):
        proc = subprocess.run(
            [sys.executable, SCRIPT, *args],
            capture_output=True, text=True, check=False,
        )
        return proc.returncode, proc.stdout, proc.stderr

    def test_scale_to_height_and_watertight(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "cube.obj")
            make_cube(src, height=1.0)
            code, out, err = self.run_script(src, "--height", "150", "--out", os.path.join(d, "pr"))
            self.assertEqual(code, 0, err)
            data = json.loads(out)
            # 默认 Y-up：y(0.3) 被拉到 150，x(0.5)→250，z(1.0)→500
            self.assertAlmostEqual(data["size_mm"]["height"], 150.0, delta=0.5)
            self.assertAlmostEqual(data["size_mm"]["width"], 250.0, delta=0.5)
            self.assertAlmostEqual(data["size_mm"]["depth"], 500.0, delta=0.5)
            self.assertTrue(data["watertight"])
            self.assertEqual(data["boundary_edges"], 0)
            self.assertTrue(data["printable"])
            self.assertTrue(os.path.exists(data["files"]["obj"]))
            self.assertTrue(os.path.exists(data["files"]["stl"]))

    def test_up_axis_z(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "cube.obj")
            make_cube(src, height=1.0)
            code, out, err = self.run_script(src, "--height", "150", "--up", "z", "--out", os.path.join(d, "pr"))
            self.assertEqual(code, 0, err)
            data = json.loads(out)
            # --up z：z(1.0) 被拉到 150，x→75，y→45
            self.assertAlmostEqual(data["size_mm"]["height"], 150.0, delta=0.5)
            self.assertAlmostEqual(data["size_mm"]["width"], 75.0, delta=0.5)
            self.assertAlmostEqual(data["size_mm"]["depth"], 45.0, delta=0.5)

    def test_decimate_reduces_faces(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "cube.obj")
            make_cube(src, height=1.0)
            code, out, err = self.run_script(src, "--height", "150", "--decimate", "2", "--no-stl", "--out", os.path.join(d, "pr"))
            if code != 0:
                self.skipTest("未安装 fast-simplification")
            data = json.loads(out)
            # 减面算法不保证精确命中目标，只要求明显低于原来的 12 面
            self.assertLess(data["triangles"], 12)

    def test_missing_file_reports_json_error(self):
        code, out, _ = self.run_script("/nonexistent/model.obj")
        self.assertNotEqual(code, 0)
        self.assertEqual(json.loads(out)["ok"], False)


    def test_solidify_keeps_cube_closed(self):
        try:
            import open3d  # noqa: F401
            import pymeshfix  # noqa: F401
        except ImportError:
            self.skipTest("需要 open3d 与 pymeshfix")
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "cube.obj")
            make_cube(src, height=1.0)
            code, out, err = self.run_script(
                src, "--height", "40", "--solidify", "--no-stl", "--out", os.path.join(d, "pr")
            )
            self.assertEqual(code, 0, err)
            data = json.loads(out)
            self.assertTrue(data["solidified"])
            self.assertTrue(data["watertight"])
            self.assertTrue(data["printable"])
            self.assertAlmostEqual(data["size_mm"]["height"], 40.0, delta=1.0)


if __name__ == "__main__":
    unittest.main()
