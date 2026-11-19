"""bake_color.py 的离线冒烟测试：纯红贴图的球体，顶点色应当还原成红色。"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO, "scripts", "bake_color.py")


def make_textured_sphere(path):
    import numpy as np
    import trimesh
    from PIL import Image

    sphere = trimesh.creation.uv_sphere(radius=1.0, count=[24, 24])
    vertices = sphere.vertices
    radius = np.linalg.norm(vertices, axis=1)
    u = np.arctan2(vertices[:, 1], vertices[:, 0]) / (2 * np.pi) + 0.5
    v = np.arcsin(np.clip(vertices[:, 2] / radius, -1, 1)) / np.pi + 0.5
    image = Image.new("RGB", (8, 8), (255, 0, 0))
    material = trimesh.visual.material.SimpleMaterial(image=image)
    sphere.visual = trimesh.visual.TextureVisuals(uv=np.stack([u, v], 1), material=material)
    sphere.export(path, file_type="obj")
    return path


class BakeColorTest(unittest.TestCase):
    def run_script(self, *args):
        proc = subprocess.run(
            [sys.executable, SCRIPT, *args], capture_output=True, text=True, cwd=REPO
        )
        return proc.returncode, proc.stdout, proc.stderr

    def test_solid_color_is_transferred(self):
        try:
            import rtree  # noqa: F401
            import trimesh  # noqa: F401
            from PIL import Image  # noqa: F401
        except ImportError:
            self.skipTest("需要 rtree / trimesh / pillow")

        with tempfile.TemporaryDirectory() as d:
            textured = make_textured_sphere(os.path.join(d, "textured.obj"))
            solid_path = os.path.join(d, "plain.obj")
            import trimesh

            trimesh.creation.uv_sphere(radius=1.0, count=[24, 24]).export(
                solid_path, file_type="obj"
            )

            code, out, err = self.run_script(
                "--solid", solid_path,
                "--textured", textured,
                "--out", os.path.join(d, "color"),
                "--name", "ball",
            )

            self.assertEqual(code, 0, err)
            data = json.loads(out)
            self.assertTrue(data["ok"])
            self.assertTrue(os.path.exists(data["files"]["obj"]))
            self.assertTrue(os.path.exists(data["files"]["glb"]))
            self.assertEqual(data["mean_rgb"], [255, 0, 0])


class SharpenHeadTest(unittest.TestCase):
    """锐化只该动脸，不该把头发压死。"""

    def test_dark_hair_untouched(self):
        try:
            import numpy as np
            import trimesh
        except ImportError:
            self.skipTest("需要 trimesh / numpy")
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "bake_color", os.path.join(REPO, "scripts", "bake_color.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        mesh = trimesh.creation.uv_sphere(radius=1.0, count=[64, 64])
        z = mesh.vertices[:, 2]
        zn = (z - z.min()) / (z.max() - z.min())
        colors = np.full((len(mesh.vertices), 3), 200, dtype=np.uint8)
        colors[zn > 0.92] = 20  # 顶部一片"头发"

        out, touched = mod.sharpen_head(mesh, colors)
        dark = zn > 0.92
        self.assertTrue(np.array_equal(out[dark], colors[dark]), "头发不该被锐化改动")
        self.assertGreater(touched, 0)
        self.assertLessEqual(touched, int((~dark).sum()))


if __name__ == "__main__":
    unittest.main()
