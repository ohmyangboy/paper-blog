import contextlib
import io
import os
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from unittest import mock
from urllib.parse import unquote, urlparse

from PIL import Image

from paper_cli import cmd_config, main
from paper_runtime.core import PaperConfig, build_site, load_config, load_local_config, save_config
from paper_runtime.social import CARD_SIZE, page_description


class Head(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.meta = {}
        self.canonical = ""
        self.feed(source.split("</head>", 1)[0])

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta":
            self.meta[attrs.get("property") or attrs.get("name")] = attrs.get("content")
        elif tag == "link" and attrs.get("rel") == "canonical":
            self.canonical = attrs["href"]


class PaperSocialTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="paper-social-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.posts = self.root / "posts"
        self.posts.mkdir()
        self.config = PaperConfig(
            posts_dir=self.posts, site_dir=self.root / "site", site_name="我的博客",
            git_remote="git@github.com:writer/blog.git", compress=False,
        )
        self.environment = mock.patch.dict(os.environ, {
            "PAPER_HOME": str(self.root / ".paper"), "PAPER_LANG": "zh_CN", "PAPER_NO_AUTO_UPDATE": "1",
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def post(self, name="hello", *, metadata="", content="这是一篇文章。", published=True):
        source = self.posts / f"{name}.md"
        source.write_text(
            f'---\ntitle: 分享与写作\ndate: 2026-09-30\npublished: {str(published).lower()}\n{metadata}---\n\n{content}',
            encoding="utf-8",
        )
        return source

    def image(self, path):
        target = self.posts / path
        target.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (1200, 630), "#d97757").save(target)
        return target

    def head(self, output, path="index.html"):
        return Head((output / path).read_text(encoding="utf-8"))

    def test_default_cards_and_metadata_are_static_and_use_pages_urls(self):
        self.post(metadata="description: 专门用于分享的摘要。\n")
        output = build_site(self.config)
        home = self.head(output)
        article = self.head(output, "posts/hello/index.html")
        self.assertEqual(home.meta["og:site_name"], "我的博客")
        self.assertEqual(home.meta["og:type"], "website")
        self.assertEqual(home.canonical, "https://writer.github.io/blog/")
        self.assertEqual(article.meta["og:type"], "article")
        self.assertEqual(article.meta["og:title"], "分享与写作")
        self.assertEqual(article.meta["description"], "专门用于分享的摘要。")
        self.assertEqual(article.meta["og:description"], article.meta["twitter:description"])
        self.assertEqual(article.meta["og:url"], "https://writer.github.io/blog/posts/hello/")
        self.assertEqual(article.meta["twitter:card"], "summary_large_image")
        self.assertEqual(article.meta["og:image:width"], "1200")
        self.assertEqual(article.meta["og:image:height"], "630")
        self.assertEqual(article.meta["og:image"], article.meta["twitter:image"])
        self.assertNotEqual(article.meta["og:image"], home.meta["og:image"])
        for head in (home, article):
            relative = urlparse(head.meta["og:image"]).path.removeprefix("/blog/")
            with Image.open(output / relative) as image:
                self.assertEqual(image.size, CARD_SIZE)
                self.assertEqual(image.format, "PNG")
                self.assertEqual(image.mode, "RGB")
        self.assertEqual(len(list((output / "assets/og").glob("*.png"))), 2)

    def test_card_urls_are_stable_and_change_when_site_name_or_content_changes(self):
        source = self.post()
        first = self.head(build_site(self.config), "posts/hello/index.html").meta["og:image"]
        self.assertEqual(first, self.head(build_site(self.config), "posts/hello/index.html").meta["og:image"])
        source.write_text(source.read_text().replace("这是一篇文章。", "这是更新后的文字。"))
        second = self.head(build_site(self.config), "posts/hello/index.html").meta["og:image"]
        self.assertNotEqual(first, second)
        self.config.site_name = "新的站点名称"
        output = build_site(self.config)
        self.assertNotEqual(second, self.head(output, "posts/hello/index.html").meta["og:image"])
        self.assertEqual(len(list((output / "assets/og").glob("*.png"))), 2)

    def test_page_image_overrides_site_image_and_og_only_assets_are_copied(self):
        site = self.image("assets/site.png")
        cover = self.image("assets/中文封面.png")
        self.image("assets/unused.png")
        self.config.og_image = "assets/site.png"
        self.post(metadata="og_image: assets/中文封面.png\n")
        self.post("other")
        output = build_site(self.config)
        self.assertEqual(self.head(output).meta["og:image"], "https://writer.github.io/blog/assets/site.png")
        article = self.head(output, "posts/hello/index.html")
        self.assertEqual(unquote(article.meta["og:image"]), "https://writer.github.io/blog/assets/中文封面.png")
        self.assertEqual(self.head(output, "posts/other/index.html").meta["og:image"], self.head(output).meta["og:image"])
        self.assertEqual((output / "assets/site.png").read_bytes(), site.read_bytes())
        self.assertEqual((output / "assets/中文封面.png").read_bytes(), cover.read_bytes())
        self.assertFalse((output / "assets/unused.png").exists())
        self.assertFalse((output / "assets/og").exists())

    def test_home_frontmatter_remote_image_and_escaped_metadata(self):
        remote = "https://cdn.example.test/card?width=1200&height=630"
        self.config.site_name = 'My "Blog" & <Notes>'
        self.config.site_url = "https://example.test/journal"
        (self.posts / "index.md").write_text(f"---\ndescription: A & B\nog_image: {remote}\n---\nHome")
        output = build_site(self.config)
        head = self.head(output)
        self.assertEqual(head.meta["og:title"], self.config.site_name)
        self.assertEqual(head.meta["og:description"], "A & B")
        self.assertEqual(head.meta["og:image"], remote)
        self.assertEqual(head.canonical, "https://example.test/journal/")
        source = (output / "index.html").read_text()
        self.assertIn('content="My &quot;Blog&quot; &amp; &lt;Notes&gt;"', source)
        self.assertNotIn("og:image:width", source)

    def test_draft_images_are_excluded_from_production_and_preview_is_noindex(self):
        self.image("assets/private.png")
        self.post("secret", metadata="og_image: assets/private.png\n", published=False)
        output = build_site(self.config)
        self.assertFalse((output / "assets/private.png").exists())
        self.assertFalse((output / "posts/secret").exists())
        output = build_site(self.config, include_drafts=True)
        self.assertTrue((output / "assets/private.png").exists())
        self.assertEqual(self.head(output, "posts/secret/index.html").meta["robots"], "noindex, nofollow")
        self.assertNotIn("secret", (output / "rss.xml").read_text())
        self.assertNotIn("secret", (output / "sitemap.xml").read_text())
        build_site(self.config)
        self.assertFalse((output / "assets/private.png").exists())

    def test_invalid_image_preserves_the_previous_build(self):
        output = build_site(self.config)
        previous = (output / "index.html").read_bytes()
        external = self.root / "external.png"
        Image.new("RGB", (10, 10)).save(external)
        (self.posts / "linked.png").symlink_to(external)
        for value in ("missing.png", "../external.png", "linked.png", "data:image/png;base64,abc", "javascript:alert(1)"):
            with self.subTest(value=value):
                self.config.og_image = value
                with self.assertRaises(ValueError):
                    build_site(self.config)
                self.assertEqual((output / "index.html").read_bytes(), previous)

    def test_long_titles_render_with_custom_domains_and_local_preview(self):
        self.post(metadata="", content="简介。")
        source = self.posts / "hello.md"
        source.write_text(source.read_text().replace("分享与写作", "很长的中文标题与 English title " * 20))
        self.config.site_url = "https://example.test/journal/"
        output = build_site(self.config)
        head = self.head(output, "posts/hello/index.html")
        self.assertTrue(head.meta["og:image"].startswith("https://example.test/journal/assets/og/"))
        self.assertNotIn("/journal/journal/", head.meta["og:image"])
        self.config.site_url = ""
        self.config.git_remote = ""
        head = self.head(build_site(self.config))
        self.assertTrue(head.meta["og:image"].startswith("/assets/og/"))
        self.assertEqual(head.canonical, "/")

    def test_description_extracts_plain_text_and_excludes_code(self):
        self.assertEqual(page_description('<p>Hello <em>world</em> &amp; 朋友</p><pre>secret</pre><p>Next</p>'), "Hello world & 朋友 Next")
        self.assertEqual(page_description("<p>Body</p>", "Explicit summary"), "Explicit summary")
        self.assertEqual(len(page_description("<p>" + "字" * 200 + "</p>")), 180)

    def test_cli_name_and_image_settings_persist_globally_and_locally(self):
        global_config = save_config(self.config)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["config", "name", "新站点"]), 0)
            self.assertEqual(main(["config", "og-image", "https://example.test/share.png"]), 0)
        self.assertEqual(load_config().site_name, "新站点")
        self.assertEqual(load_config().og_image, "https://example.test/share.png")
        global_bytes = global_config.config_path.read_bytes()
        project = self.root / "project"
        project.mkdir()
        (project / "posts/assets").mkdir(parents=True)
        local = load_local_config(project)
        save_config(local)
        Image.new("RGB", (1200, 630)).save(project / "posts/assets/local.png")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["-C", str(project), "config", "name", "局部博客"]), 0)
            self.assertEqual(main(["-C", str(project), "config", "og-image", "assets/local.png"]), 0)
        self.assertEqual(load_local_config(project).site_name, "局部博客")
        self.assertEqual(load_local_config(project).og_image, "assets/local.png")
        self.assertEqual(global_config.config_path.read_bytes(), global_bytes)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["-C", str(project), "config", "og-image", "auto"]), 0)
        self.assertEqual(load_local_config(project).og_image, "")

    def test_cli_invalid_values_and_cancel_leave_config_unchanged(self):
        config = save_config(self.config)
        previous = config.config_path.read_bytes()
        with contextlib.redirect_stderr(io.StringIO()):
            for value in ("", "  ", "two\nlines"):
                self.assertEqual(main(["config", "name", value]), 1)
            self.assertEqual(main(["config", "og-image", "missing.png"]), 1)
        with mock.patch("paper_cli._prompt", return_value=None):
            self.assertEqual(cmd_config(config_cmd="name"), 0)
            self.assertEqual(cmd_config(config_cmd="og-image"), 0)
        self.assertEqual(config.config_path.read_bytes(), previous)

    def test_config_menu_exposes_both_settings(self):
        save_config(self.config)
        with mock.patch("sys.stdin.isatty", return_value=True), mock.patch(
            "paper_cli._terminal_menu", side_effect=["name", "og-image", "back"]
        ) as menu, mock.patch("paper_cli._prompt", side_effect=["菜单中的站点", "auto"]), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cmd_config(), 0)
        options = {entry[0] for entry in menu.call_args_list[0].args[1]}
        self.assertTrue({"name", "og-image"}.issubset(options))
        self.assertEqual(load_config().site_name, "菜单中的站点")


if __name__ == "__main__":
    unittest.main()
