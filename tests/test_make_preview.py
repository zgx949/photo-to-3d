"""make_preview 的离线用例：只验证模板填充与内联，不跑截图。"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO, "scripts", "make_preview.py")


class MakePreviewTest(unittest.TestCase):
    def test_inline_glb(self):
        try:
            import trimesh
        except ImportError:
            self.skipTest("需要 trimesh")

        with tempfile.TemporaryDirectory() as d:
            glb = os.path.join(d, "m.glb")
            trimesh.creation.box(extents=[1, 1, 1]).export(glb, file_type="glb")
            proc = subprocess.run(
                [sys.executable, SCRIPT, glb, "--out", os.path.join(d, "p"),
                 "--name", "样件", "--no-png"],
                capture_output=True, text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            data = json.loads(proc.stdout.strip().splitlines()[-1])
            with open(data["files"]["html"], encoding="utf-8") as f:
                html = f.read()
            self.assertIn("样件", html)
            self.assertNotIn("__GLB_B64__", html)
            self.assertNotIn("__BLURB__", html)


if __name__ == "__main__":
    unittest.main()
