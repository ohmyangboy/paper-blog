import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from paper_cli import _main, make_parser
from paper_runtime.core import load_config, load_local_config, save_config


class PaperLocalModeTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self.temp_dir, ignore_errors=True))

        # Setup an isolated PAPER_HOME for global config isolation
        self.old_home = os.environ.get("PAPER_HOME")
        self.paper_home = Path(self.temp_dir) / "global_paper_home"
        os.environ["PAPER_HOME"] = str(self.paper_home)

    def tearDown(self):
        if self.old_home is None:
            os.environ.pop("PAPER_HOME", None)
        else:
            os.environ["PAPER_HOME"] = self.old_home

    def test_load_local_config_defaults(self):
        project_dir = Path(self.temp_dir) / "my_project"
        project_dir.mkdir()
        (project_dir / "posts").mkdir()
        (project_dir / "posts" / "hello.md").write_text("# Hello", encoding="utf-8")

        config = load_local_config(project_dir)
        self.assertEqual(config.posts_dir, (project_dir / "posts").resolve())
        self.assertEqual(config.site_dir, project_dir.resolve())
        self.assertEqual(config.output_dir, (project_dir / "out").resolve())
        self.assertEqual(config.config_path, (project_dir / ".paper-config.json").resolve())

    def test_load_local_config_with_existing_paper_config_json(self):
        project_dir = Path(self.temp_dir) / "my_project"
        project_dir.mkdir()
        custom_config = {
            "siteName": "Custom Project Blog",
            "color": "#123456",
            "postsDir": str(project_dir / "my_custom_posts"),
        }
        (project_dir / ".paper-config.json").write_text(
            json.dumps(custom_config), encoding="utf-8"
        )

        config = load_local_config(project_dir)
        self.assertEqual(config.site_name, "Custom Project Blog")
        self.assertEqual(config.color, "#123456")
        self.assertEqual(config.posts_dir, (project_dir / "my_custom_posts").resolve())

    def test_save_config_in_local_mode_does_not_mutate_global(self):
        project_dir = Path(self.temp_dir) / "my_project"
        project_dir.mkdir()
        local_cfg = load_local_config(project_dir)
        save_config(local_cfg, site_name="New Local Title")

        # Check local file was created
        local_file = project_dir / ".paper-config.json"
        self.assertTrue(local_file.exists())
        self.assertIn("New Local Title", local_file.read_text(encoding="utf-8"))

        # Global config should not be created or affected
        global_file = self.paper_home / "config.json"
        self.assertFalse(global_file.exists())

    def test_cli_build_local_mode(self):
        project_dir = Path(self.temp_dir) / "blog_workspace"
        project_dir.mkdir()
        posts_dir = project_dir / "posts"
        posts_dir.mkdir()
        (posts_dir / "test.md").write_text(
            "---\ntitle: 测试文章\ndate: 2026-08-17\npublished: true\n---\n\n正文内容\n",
            encoding="utf-8",
        )

        buf = io.StringIO()
        with redirect_stdout(buf):
            code = _main(["build", "-C", str(project_dir)])
        self.assertEqual(code, 0)
        self.assertTrue((project_dir / "out" / "index.html").exists())
        self.assertTrue((project_dir / "out" / "posts" / "test" / "index.html").exists())

    def test_cli_list_local_mode(self):
        project_dir = Path(self.temp_dir) / "blog_workspace"
        project_dir.mkdir()
        posts_dir = project_dir / "posts"
        posts_dir.mkdir()
        (posts_dir / "article1.md").write_text(
            "---\ntitle: 本地文章一\ndate: 2026-08-17\npublished: true\n---\n\n内容\n",
            encoding="utf-8",
        )

        buf = io.StringIO()
        with redirect_stdout(buf):
            code = _main(["list", "--dir", str(project_dir)])
        self.assertEqual(code, 0)
        output = buf.getvalue()
        self.assertIn("本地文章一", output)

    def test_cli_new_draft_local_mode(self):
        project_dir = Path(self.temp_dir) / "blog_workspace"
        project_dir.mkdir()

        buf = io.StringIO()
        with redirect_stdout(buf):
            code = _main(["new", "Local New Post", "--dir", str(project_dir)])
        self.assertEqual(code, 0)
        self.assertTrue((project_dir / "posts" / "local-new-post.md").exists())

    def test_cli_parser_options_order(self):
        parser = make_parser()
        
        args1 = parser.parse_args(["--local", "serve", "--port", "9000"])
        self.assertTrue(args1.local)
        self.assertEqual(args1.command, "serve")
        self.assertEqual(args1.port, 9000)

        args2 = parser.parse_args(["serve", "-l", "--port", "9001"])
        self.assertTrue(args2.local)
        self.assertEqual(args2.command, "serve")
        self.assertEqual(args2.port, 9001)

        args3 = parser.parse_args(["-C", "/tmp/test", "build"])
        self.assertEqual(args3.dir, "/tmp/test")
        self.assertEqual(args3.command, "build")


if __name__ == "__main__":
    unittest.main()
