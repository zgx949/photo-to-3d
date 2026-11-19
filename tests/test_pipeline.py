"""pipeline.py 串接测试：断网、无 Key、纯离线，只验证各步骤能被正确连起来。"""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO, "scripts", "pipeline.py")
SPEC = importlib.util.spec_from_file_location("pipeline", SCRIPT)
pipeline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pipeline)


class PipelineTest(unittest.TestCase):
    def test_missing_print_dependency_stops_before_generation(self):
        with mock.patch.object(sys, "argv", [SCRIPT, "--image", "https://example.com/a.png"]), \
                mock.patch.object(pipeline, "import_module", side_effect=ImportError("test")), \
                mock.patch.object(pipeline, "run_step") as run_step, \
                redirect_stdout(StringIO()) as stdout, self.assertRaises(SystemExit):
            pipeline.main()
        run_step.assert_not_called()
        self.assertIn("requirements.txt", json.loads(stdout.getvalue())["error"])

    def test_skip_3d_chains_steps(self):
        try:
            import trimesh  # noqa: F401
        except ImportError:
            self.skipTest("需要 trimesh")

        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "cube.obj")
            import trimesh

            trimesh.creation.box(extents=[0.5, 1.0, 0.3]).export(src, file_type="obj")

            proc = subprocess.run(
                [sys.executable, SCRIPT, "--skip-3d", src,
                 "--out", os.path.join(d, "out"), "--name", "cube",
                 "--no-solidify", "--no-color"],
                capture_output=True, text=True, cwd=REPO,
            )

            self.assertEqual(proc.returncode, 0, proc.stderr)
            data = json.loads(proc.stdout.strip().splitlines()[-1])
            self.assertTrue(data["ok"])
            self.assertTrue(os.path.exists(data["files"]["printable_obj"]))
            self.assertTrue(os.path.exists(data["files"]["printable_stl"]))
            self.assertFalse(data["colored"])
            self.assertTrue(data["printable"])
            self.assertEqual(data["boundary_edges"], 0)
            self.assertFalse(data["warnings"])
            self.assertEqual(data["steps"][0]["step"], "print_prep")


if __name__ == "__main__":
    unittest.main()
