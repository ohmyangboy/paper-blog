import json
import os
import tempfile
import unittest
from pathlib import Path

from paper_runtime.core import (
    GitRemoteInfo,
    PaperConfig,
    _base_path,
    _github_url,
    _site_root,
    build_site,
    discover_posts,
    normalize_git_remote,
    parse_frontmatter,
    render_markdown,
)


class PaperCoreTests(unittest.TestCase):
    def test_frontmatter_without_published_is_a_draft(self):
        metadata, body = parse_frontmatter("---\ntitle: Private note\n---\n\nsecret")
        self.assertEqual(metadata["title"], "Private note")
        self.assertFalse(metadata["published"])
        self.assertEqual(body, "secret")

    def test_markdown_profile_supports_gfm_and_escapes_raw_html(self):
        rendered = render_markdown("- [x] shipped\n\n| A | B |\n| - | - |\n| 1 | 2 |\n\n<script>alert(1)</script>\n\n~~old~~")
        self.assertIn('type="checkbox"', rendered)
        self.assertIn("<table>", rendered)
        self.assertIn("<s>old</s>", rendered)
        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)

    def test_markdown_single_newline_renders_as_line_break(self):
        rendered = render_markdown("第一行\n第二行\n第三行")
        self.assertIn("<br>", rendered)
        self.assertEqual(rendered.count("<br>"), 2)
        self.assertIn("第一行<br>", rendered)

    def test_markdown_blank_line_still_starts_a_paragraph(self):
        rendered = render_markdown("第一段\n\n第二段")
        self.assertNotIn("<br>", rendered)
        self.assertIn("<p>第一段</p>", rendered)
        self.assertIn("<p>第二段</p>", rendered)

    def test_markdown_preserves_at_most_two_source_blank_lines_as_visible_space(self):
        source = "# 标题\n\n第一段\n\n\n\n第二段"
        rendered = render_markdown(source)
        self.assertEqual(rendered.count('class="markdown-blank-line"'), 3)

    def test_markdown_images_avoid_hotlink_referrer_and_rewrite_local_assets(self):
        remote = render_markdown("![avatar](https://cdn.example.test/avatar.png)")
        local = render_markdown("![cover](assets/cover.png)", asset_base="/blog/assets/")
        self.assertIn('referrerpolicy="no-referrer"', remote)
        self.assertIn('loading="lazy"', remote)
        self.assertIn('src="/blog/assets/cover.png"', local)

    def test_markdown_imports_relative_local_image_into_assets(self):
        with tempfile.TemporaryDirectory() as root:
            posts = Path(root)
            (posts / "photos").mkdir()
            (posts / "photos" / "a.png").write_bytes(b"\x89PNG fake")
            rendered = render_markdown("![x](photos/a.png)", posts_dir=posts)
            self.assertIn('src="/assets/a.png"', rendered)
            self.assertTrue((posts / "assets" / "a.png").exists())

    def test_markdown_imports_obsidian_image_embed_with_spaces(self):
        with tempfile.TemporaryDirectory() as root:
            posts = Path(root)
            image_name = "Pasted image 20260813131935.png"
            (posts / image_name).write_bytes(b"\x89PNG obsidian")
            rendered = render_markdown(f"![[{image_name}]]", posts_dir=posts)
            self.assertIn('<img src="/assets/Pasted image 20260813131935.png"', rendered)
            self.assertNotIn("![[", rendered)
            self.assertTrue((posts / "assets" / image_name).exists())

    def test_markdown_supports_obsidian_image_alias_and_dimensions(self):
        with tempfile.TemporaryDirectory() as root:
            posts = Path(root)
            (posts / "photo.png").write_bytes(b"\x89PNG dimensions")
            alias = render_markdown("![[photo.png|产品截图]]", posts_dir=posts)
            width = render_markdown("![[photo.png|300]]", posts_dir=posts)
            dimensions = render_markdown("![[photo.png|300x200]]", posts_dir=posts)
            self.assertIn('alt="产品截图"', alias)
            self.assertIn('width="300"', width)
            self.assertNotIn('height=', width)
            self.assertIn('width="300"', dimensions)
            self.assertIn('height="200"', dimensions)

    def test_markdown_shows_placeholder_for_missing_obsidian_image(self):
        with tempfile.TemporaryDirectory() as root:
            rendered = render_markdown("前文\n\n![[missing image.png]]\n\n后文", posts_dir=Path(root))
            self.assertIn('class="missing-image"', rendered)
            self.assertIn("图片未找到：missing image.png", rendered)
            self.assertIn("前文", rendered)
            self.assertIn("后文", rendered)

    def test_markdown_rejects_ambiguous_obsidian_image_name(self):
        with tempfile.TemporaryDirectory() as root:
            posts = Path(root)
            (posts / "a").mkdir()
            (posts / "b").mkdir()
            (posts / "a" / "same.png").write_bytes(b"A")
            (posts / "b" / "same.png").write_bytes(b"B")
            with self.assertRaisesRegex(ValueError, "图片名称不唯一"):
                render_markdown("![[same.png]]", posts_dir=posts)

    def test_markdown_keeps_obsidian_note_and_code_embeds_as_text(self):
        rendered = render_markdown(
            "![[另一篇笔记]]\n\n`![[inline.png]]`\n\n```md\n![[block.png]]\n```"
        )
        self.assertIn("![[另一篇笔记]]", rendered)
        self.assertIn("<code>![[inline.png]]</code>", rendered)
        self.assertIn("![[block.png]]", rendered)
        self.assertNotIn("<img", rendered)

    def test_markdown_obsidian_explicit_path_wins_over_duplicate_filename(self):
        with tempfile.TemporaryDirectory() as root:
            posts = Path(root)
            (posts / "a").mkdir()
            (posts / "b").mkdir()
            (posts / "a" / "same.png").write_bytes(b"A")
            (posts / "b" / "same.png").write_bytes(b"B")
            rendered = render_markdown("![[a/same.png]]", posts_dir=posts)
            self.assertIn('src="/assets/same.png"', rendered)
            self.assertEqual((posts / "assets" / "same.png").read_bytes(), b"A")

    def test_markdown_imports_standard_image_with_spaces(self):
        with tempfile.TemporaryDirectory() as root:
            posts = Path(root)
            image_name = "Pasted image 20260813131935.png"
            (posts / image_name).write_bytes(b"\x89PNG commonmark")
            rendered = render_markdown(f"![截图](<{image_name}>)", posts_dir=posts)
            self.assertIn(f'src="/assets/{image_name}"', rendered)
            self.assertTrue((posts / "assets" / image_name).exists())

    def test_markdown_finds_unique_obsidian_attachment_in_nested_posts_folder(self):
        with tempfile.TemporaryDirectory() as root:
            posts = Path(root)
            attachments = posts / "attachments"
            attachments.mkdir()
            image_name = "Pasted image 20260813131935.png"
            (attachments / image_name).write_bytes(b"\x89PNG vault")
            rendered = render_markdown(f"![[{image_name}]]", posts_dir=posts)
            self.assertIn(f'src="/assets/{image_name}"', rendered)
            self.assertTrue((posts / "assets" / image_name).exists())

    def test_markdown_imports_absolute_local_image_into_assets(self):
        with tempfile.TemporaryDirectory() as root:
            posts = Path(root) / "posts"
            posts.mkdir()
            outside = Path(root) / "b.png"
            outside.write_bytes(b"\x89PNG abs")
            rendered = render_markdown(f"![x]({outside})", posts_dir=posts)
            self.assertIn('src="/assets/b.png"', rendered)
            self.assertTrue((posts / "assets" / "b.png").exists())

    def test_markdown_import_dedups_same_name_different_content(self):
        with tempfile.TemporaryDirectory() as root:
            posts = Path(root)
            (posts / "a").mkdir()
            (posts / "b").mkdir()
            (posts / "a" / "same.png").write_bytes(b"AAA")
            (posts / "b" / "same.png").write_bytes(b"BBB")
            first = render_markdown("![x](a/same.png)", posts_dir=posts)
            second = render_markdown("![x](b/same.png)", posts_dir=posts)
            names = sorted(path.name for path in (posts / "assets").iterdir())
            self.assertEqual(len(names), 2)
            self.assertIn("same.png", names)
            self.assertTrue(any(name.startswith("same-") for name in names))
            self.assertIn('src="/assets/same.png"', first)
            self.assertIn('src="/assets/same-', second)

    def test_markdown_leaves_remote_data_missing_and_direct_assets_untouched(self):
        with tempfile.TemporaryDirectory() as root:
            posts = Path(root)
            source = (
                "![web](https://e.test/x.png)\n\n"
                "![data](data:image/png;base64,AAAA)\n\n"
                "![missing](../nope.png)\n\n"
                "![dir](assets/cover.png)"
            )
            rendered = render_markdown(source, posts_dir=posts)
            self.assertIn('src="https://e.test/x.png"', rendered)
            self.assertIn('src="data:image/png;base64,AAAA"', rendered)
            self.assertIn('src="../nope.png"', rendered)
            self.assertIn('src="/assets/cover.png"', rendered)
            self.assertFalse((posts / "assets").exists())

    def test_markdown_rejects_symlinked_image_import(self):
        with tempfile.TemporaryDirectory() as root:
            posts = Path(root)
            outside = Path(root) / "secret.png"
            outside.write_bytes(b"secret")
            (posts / "leak.png").symlink_to(outside)
            rendered = render_markdown("![x](leak.png)", posts_dir=posts)
            self.assertIn('src="leak.png"', rendered)
            self.assertFalse((posts / "assets").exists())

    def test_discovery_defaults_to_draft_and_ignores_nested_markdown(self):
        with tempfile.TemporaryDirectory() as root:
            posts_dir = Path(root)
            (posts_dir / "private.md").write_text("# private", encoding="utf-8")
            (posts_dir / "nested").mkdir()
            (posts_dir / "nested" / "hidden.md").write_text("# hidden", encoding="utf-8")
            posts = discover_posts(posts_dir)
            self.assertEqual([post.slug for post in posts], ["private"])
            self.assertFalse(posts[0].published)

    def test_discovery_sorts_by_file_modification_time_not_frontmatter_date(self):
        with tempfile.TemporaryDirectory() as root:
            posts_dir = Path(root)
            older = posts_dir / "older.md"
            newer = posts_dir / "newer.md"
            older.write_text("---\ntitle: Older\ndate: 2099-01-01\n---\n", encoding="utf-8")
            newer.write_text("---\ntitle: Newer\ndate: 2000-01-01\n---\n", encoding="utf-8")
            os.utime(older, (100, 100))
            os.utime(newer, (200, 200))
            posts = discover_posts(posts_dir)
            self.assertEqual([post.slug for post in posts], ["newer", "older"])
            self.assertGreater(posts[0].modified_time, posts[1].modified_time)

    def test_discovery_rejects_slug_collisions(self):
        with tempfile.TemporaryDirectory() as root:
            posts_dir = Path(root)
            (posts_dir / "hello world.md").write_text("# one", encoding="utf-8")
            (posts_dir / "hello-world.md").write_text("# two", encoding="utf-8")
            with self.assertRaises(ValueError):
                discover_posts(posts_dir)

    def test_build_site_outputs_published_posts_rss_sitemap_and_assets(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            posts_dir = root_path / "posts"
            site_dir = root_path / "site"
            posts_dir.mkdir()
            (posts_dir / "index.md").write_text("# Home\n\nWelcome", encoding="utf-8")
            (posts_dir / "public.md").write_text("---\ntitle: Public\npublished: true\n---\n\nHello", encoding="utf-8")
            (posts_dir / "private.md").write_text("---\ntitle: Private\n---\n\nSecret", encoding="utf-8")
            (posts_dir / "assets").mkdir()
            (posts_dir / "assets" / "a.txt").write_text("asset", encoding="utf-8")
            output = build_site(PaperConfig(posts_dir=posts_dir, site_dir=site_dir, site_url="https://example.test"))
            self.assertTrue((output / "index.html").exists())
            self.assertIn("Public", (output / "index.html").read_text(encoding="utf-8"))
            self.assertTrue((output / "posts" / "public" / "index.html").exists())
            self.assertFalse((output / "posts" / "private" / "index.html").exists())
            self.assertTrue((output / "assets" / "a.txt").exists())
            self.assertIn("Public", (output / "rss.xml").read_text(encoding="utf-8"))
            self.assertIn("public", (output / "sitemap.xml").read_text(encoding="utf-8"))

    def test_build_site_publishes_obsidian_embedded_image(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            posts = root_path / "posts"
            posts.mkdir()
            image_name = "Pasted image.png"
            (posts / image_name).write_bytes(b"\x89PNG site")
            (posts / "article.md").write_text(
                f"---\ntitle: Article\npublished: true\n---\n\n![[{image_name}|320]]",
                encoding="utf-8",
            )
            output = build_site(PaperConfig(posts_dir=posts, site_dir=root_path / "site"))
            article = (output / "posts" / "article" / "index.html").read_text(encoding="utf-8")
            self.assertIn('src="/assets/Pasted image.png"', article)
            self.assertIn('width="320"', article)
            self.assertEqual((output / "assets" / image_name).read_bytes(), b"\x89PNG site")

    def test_site_url_base_path_is_not_repeated_in_feeds(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            posts_dir = root_path / "posts"
            posts_dir.mkdir()
            (posts_dir / "hello.md").write_text(
                "---\ntitle: Hello\npublished: true\n---\n\nBody", encoding="utf-8"
            )
            output = build_site(
                PaperConfig(
                    posts_dir=posts_dir,
                    site_dir=root_path / "site",
                    site_url="https://alice.github.io/blog",
                )
            )
            rss = (output / "rss.xml").read_text(encoding="utf-8")
            sitemap = (output / "sitemap.xml").read_text(encoding="utf-8")
            self.assertIn("https://alice.github.io/blog/posts/hello/", rss)
            self.assertNotIn("/blog/blog/", rss)
            self.assertIn("https://alice.github.io/blog/", sitemap)

    def test_build_restores_legacy_footer_and_can_inject_live_reload(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            posts_dir = root_path / "posts"
            posts_dir.mkdir()
            output = build_site(
                PaperConfig(posts_dir=posts_dir, site_dir=root_path / "site"),
                live_reload=True,
            )
            home = (output / "index.html").read_text(encoding="utf-8")
            self.assertIn('class="footer-brand"', home)
            self.assertIn('font-family: Georgia, Cambria, Baskerville', home)
            self.assertIn('rel="icon"', home)
            self.assertIn('data:image/svg+xml', home)
            self.assertIn('/.paper-revision', home)

    def test_build_rejects_symlinked_assets(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            posts_dir = root_path / "posts"
            site_dir = root_path / "site"
            posts_dir.mkdir()
            assets = posts_dir / "assets"
            assets.mkdir()
            outside = root_path / "outside.txt"
            outside.write_text("private", encoding="utf-8")
            (assets / "leak.txt").symlink_to(outside)
            with self.assertRaises(ValueError):
                build_site(PaperConfig(posts_dir=posts_dir, site_dir=site_dir))

    def test_corrupt_config_is_an_explicit_error(self):
        from paper_runtime.core import ConfigError, load_config

        with tempfile.TemporaryDirectory() as root:
            old_home = os.environ.get("PAPER_HOME")
            os.environ["PAPER_HOME"] = str(Path(root) / ".paper")
            try:
                config_file = Path(os.environ["PAPER_HOME"]) / "config.json"
                config_file.parent.mkdir(parents=True)
                config_file.write_text("{broken", encoding="utf-8")
                with self.assertRaises(ConfigError):
                    load_config()
            finally:
                if old_home is None:
                    os.environ.pop("PAPER_HOME", None)
                else:
                    os.environ["PAPER_HOME"] = old_home


class TestNormalizeGitRemote(unittest.TestCase):
    VALID = [
        # (input, ssh_url, owner, repo, is_user_pages, pages_url)
        ("git@github.com:o/r.git", "git@github.com:o/r.git", "o", "r", False, "https://o.github.io/r"),
        ("git@github.com:o/r", "git@github.com:o/r.git", "o", "r", False, "https://o.github.io/r"),
        ("ssh://git@github.com/o/r", "git@github.com:o/r.git", "o", "r", False, "https://o.github.io/r"),
        ("https://github.com/o/r", "git@github.com:o/r.git", "o", "r", False, "https://o.github.io/r"),
        ("https://github.com/o/r.git", "git@github.com:o/r.git", "o", "r", False, "https://o.github.io/r"),
        ("http://github.com/o/r", "git@github.com:o/r.git", "o", "r", False, "https://o.github.io/r"),
        ("github.com/o/r", "git@github.com:o/r.git", "o", "r", False, "https://o.github.io/r"),
        ("o/r", "git@github.com:o/r.git", "o", "r", False, "https://o.github.io/r"),
        ("o/r.git", "git@github.com:o/r.git", "o", "r", False, "https://o.github.io/r"),
        ("o/r/", "git@github.com:o/r.git", "o", "r", False, "https://o.github.io/r"),
        (
            "git@github.com:owner/owner.github.io.git",
            "git@github.com:owner/owner.github.io.git",
            "owner",
            "owner.github.io",
            True,
            "https://owner.github.io",
        ),
        (
            "Owner/Owner.github.io",
            "git@github.com:Owner/Owner.github.io.git",
            "Owner",
            "Owner.github.io",
            True,
            "https://Owner.github.io",
        ),
        (
            "OctoCat/Hello-World",
            "git@github.com:OctoCat/Hello-World.git",
            "OctoCat",
            "Hello-World",
            False,
            "https://OctoCat.github.io/Hello-World",
        ),
    ]

    INVALID = [
        "",
        "   ",
        "foo",
        "github.com/o/r/x",
        "www.github.com/o/r",
        "git@gitlab.com:o/r",
        "https://gitlab.com/o/r",
        "git://github.com/o/r",
        "https://github.com/",
        "git@github.com:",
        "o /r",
        "o/r tree",
        "git@github.com:o/r/tree/main",
        "https://github.com/o/r?foo=bar",
        "https://github.com/o/r#frag",
        "git@github.com:o/r?token=abc",
        "github.com/o/r?token=abc",
    ]

    def test_valid_forms_normalize_to_canonical_ssh(self):
        for raw, ssh_url, owner, repo, is_user_pages, pages_url in self.VALID:
            with self.subTest(raw=raw):
                info = normalize_git_remote(raw)
                self.assertIsInstance(info, GitRemoteInfo)
                self.assertEqual(info.ssh_url, ssh_url)
                self.assertEqual(info.owner, owner)
                self.assertEqual(info.repo, repo)
                self.assertEqual(info.is_user_pages, is_user_pages)
                self.assertEqual(info.pages_url, pages_url)

    def test_invalid_inputs_are_rejected(self):
        for raw in self.INVALID:
            with self.subTest(raw=raw):
                self.assertIsNone(normalize_git_remote(raw))


class TestGitRemoteUrlDerivation(unittest.TestCase):
    def test_equivalent_remote_forms_derive_identical_urls(self):
        configs = [
            PaperConfig(posts_dir=Path("p"), site_dir=Path("s"), git_remote="git@github.com:o/r.git"),
            PaperConfig(posts_dir=Path("p"), site_dir=Path("s"), git_remote="o/r"),
            PaperConfig(posts_dir=Path("p"), site_dir=Path("s"), git_remote="https://github.com/o/r"),
        ]
        for cfg in configs:
            with self.subTest(git_remote=cfg.git_remote):
                self.assertEqual(_base_path(cfg), "/r")
                self.assertEqual(_site_root(cfg), "https://o.github.io/r")
                self.assertEqual(_github_url(cfg), "https://github.com/o/r")

    def test_user_pages_have_no_base_path(self):
        cfg = PaperConfig(
            posts_dir=Path("p"), site_dir=Path("s"), git_remote="git@github.com:o/o.github.io.git"
        )
        self.assertEqual(_base_path(cfg), "")
        self.assertEqual(_site_root(cfg), "https://o.github.io")
        self.assertEqual(_github_url(cfg), "https://github.com/o/o.github.io")

    def test_site_url_takes_precedence_over_derivation(self):
        cfg = PaperConfig(
            posts_dir=Path("p"),
            site_dir=Path("s"),
            git_remote="git@github.com:o/r.git",
            site_url="https://example.test/blog",
        )
        self.assertEqual(_base_path(cfg), "/blog")
        self.assertEqual(_site_root(cfg), "https://example.test/blog")

    def test_malformed_remote_falls_back_safely(self):
        cfg = PaperConfig(posts_dir=Path("p"), site_dir=Path("s"), git_remote="git@gitlab.com:o/r")
        self.assertEqual(_base_path(cfg), "")
        self.assertEqual(_site_root(cfg), "")
        self.assertEqual(_github_url(cfg), "https://github.com")

    def test_pages_settings_url_derived_from_remote(self):
        info = normalize_git_remote("git@github.com:o/r.git")
        self.assertEqual(info.pages_settings_url, "https://github.com/o/r/settings/pages")
        user = normalize_git_remote("git@github.com:o/o.github.io.git")
        self.assertEqual(user.pages_settings_url, "https://github.com/o/o.github.io/settings/pages")


if __name__ == "__main__":
    unittest.main()
