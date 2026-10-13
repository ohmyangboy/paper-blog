"""Translated homepage creation, static output, and browser negotiation regressions."""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

import paper_cli
from paper_runtime.core import PaperConfig, build_site, create_homepage, discover_homepages, discover_posts, parse_frontmatter
from paper_runtime.homepages import HomepageLink, homepage_language_bootstrap, normalize_homepage_language
from paper_runtime.i18n import override_language


class HomepageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="paper-homepage-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.posts = self.root / "posts"
        self.posts.mkdir()
        self.config = PaperConfig(posts_dir=self.posts, site_dir=self.root / "site",
                                  site_name="我的博客", language="zh_CN", site_url="https://example.test/blog", compress=False)

    def write(self, name: str, content: str) -> Path:
        path = self.posts / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_language_tags_are_canonical_and_cannot_escape_output(self):
        for source, expected in [(" en ", "en"), ("EN_us", "en-US"), ("zh_hant_tw", "zh-Hant-TW"),
                                 ("pt-br", "pt-BR"), ("es-419", "es-419"), ("de-CH-1901", "de-CH-1901")]:
            with self.subTest(source=source):
                self.assertEqual(normalize_homepage_language(source), expected)
        for value in ["", "auto", "../en", "en/../../assets", "en<script>", "en--US", "english", True]:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    normalize_homepage_language(value)
        self.assertEqual(parse_frontmatter("---\ni18n: no\n---\nHei")[0]["i18n"], "no")

    def test_creation_copies_metadata_and_body_and_preserves_default(self):
        source = "---\n# Keep this comment\n  i18n: zh-CN\ntitle: 我的首页\ndescription: 简介\nog_image: assets/home.png\ncustom: value\n---\n\n# 首页\n\n正文\n"
        index = self.write("index.md", source)
        created = create_homepage(self.config, "EN_us")
        self.assertEqual(created.name, "index.en-US.md")
        metadata, body = parse_frontmatter(created.read_text(encoding="utf-8"))
        self.assertEqual(metadata["i18n"], "en-US")
        self.assertEqual(metadata["custom"], "value")
        self.assertEqual(metadata["og_image"], "assets/home.png")
        self.assertEqual(body, "# 首页\n\n正文")
        self.assertIn("# Keep this comment", created.read_text(encoding="utf-8"))
        self.assertEqual(index.read_text(encoding="utf-8"), source)

    def test_creation_uses_plain_or_missing_homepage_and_refuses_overwrites(self):
        self.write("index.md", "# Hello\n\nWorld\n")
        created = create_homepage(self.config, "en")
        self.assertEqual(parse_frontmatter(created.read_text(encoding="utf-8"))[1], "# Hello\n\nWorld")
        with self.assertRaises(ValueError):
            create_homepage(self.config, "EN")
        original = self.write("index.fr.md", "An existing article without i18n")
        with self.assertRaises(ValueError):
            create_homepage(self.config, "fr")
        self.assertEqual(original.read_text(encoding="utf-8"), "An existing article without i18n")
        (self.posts / "index.md").unlink()
        self.assertTrue(create_homepage(self.config, "ja").exists())

    def test_homepage_variants_are_not_articles_or_drafts(self):
        self.write("english-home.md", "---\ni18n: en\npublished: false\n---\n# Welcome")
        self.write("index.ja.md", "---\ni18n: ja\n---\n# ようこそ")
        self.write("article.md", "---\npublished: true\n---\nArticle")
        self.assertEqual([post.slug for post in discover_posts(self.posts)], ["article"])
        variants = discover_homepages(self.posts)
        self.assertEqual({post.i18n for post in variants}, {"en", "ja"})
        self.assertTrue(all(post.published for post in variants))
        items = paper_cli._list_items(self.config)
        self.assertEqual(items[0].slug, "__home__")
        self.assertEqual({item.i18n for item in items[1:3]}, {"en", "ja"})
        self.assertEqual(items[3].slug, "article")

    def test_static_variants_have_correct_links_metadata_assets_and_sitemap(self):
        self.write("index.md", "---\ni18n: zh-CN\n---\n# 默认首页")
        self.write("welcome.md", "---\ni18n: en\ntitle: Welcome\ndescription: English description\n---\n# Welcome\n\n![Only here](assets/english.png)")
        self.write("index.ar.md", "---\ni18n: ar\n---\n# مرحبا")
        self.write("article.md", "---\npublished: true\n---\nArticle body")
        assets = self.posts / "assets"
        assets.mkdir()
        (assets / "english.png").write_bytes(b"only-used-by-english")
        with mock.patch.dict("os.environ", {"PAPER_LANG": "zh_CN"}):
            output = build_site(self.config, live_reload=True)
        root = (output / "index.html").read_text(encoding="utf-8")
        english = (output / "en" / "index.html").read_text(encoding="utf-8")
        arabic = (output / "ar" / "index.html").read_text(encoding="utf-8")
        article = (output / "posts" / "article" / "index.html").read_text(encoding="utf-8")
        self.assertIn('<html lang="en">', english)
        self.assertIn('<title>Welcome | 我的博客</title>', english)
        self.assertIn('property="og:locale" content="en_US"', english)
        self.assertIn('property="og:description" content="English description"', english)
        self.assertIn('rel="canonical" href="https://example.test/blog/en/"', english)
        self.assertIn('rel="alternate" hreflang="x-default" href="https://example.test/blog/"', root)
        self.assertIn('rel="alternate" hreflang="en" href="https://example.test/blog/en/"', root)
        self.assertIn('rel="alternate" hreflang="zh-CN"', root)
        self.assertIn('href="/blog/?lang=default"', english)
        self.assertIn('href="/blog/en/" data-paper-language="en"', article)
        self.assertIn('data-paper-language="en" lang="en" hreflang="en" aria-current="page"', english)
        self.assertIn('"auto": true', root)
        self.assertIn('"auto": false', english)
        self.assertIn('"auto": false', article)
        self.assertLess(root.index("location.replace"), root.index("</head>"))
        self.assertIn('<html lang="ar" dir="rtl">', arabic)
        self.assertIn("/.paper-revision", english)
        self.assertTrue((output / "assets" / "english.png").exists())
        self.assertFalse((output / "posts" / "welcome").exists())
        feed = ET.fromstring((output / "rss.xml").read_text(encoding="utf-8"))
        self.assertEqual(len(feed.findall("channel/item")), 1)
        sitemap = ET.fromstring((output / "sitemap.xml").read_text(encoding="utf-8"))
        urls = [node.text for node in sitemap.iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
        self.assertIn("https://example.test/blog/en/", urls)
        self.assertIn("https://example.test/blog/ar/", urls)

    def test_default_only_site_does_not_add_language_controls_or_redirects(self):
        self.write("index.md", "# Original homepage")
        output = build_site(self.config)
        root = (output / "index.html").read_text(encoding="utf-8")
        self.assertIn("Original homepage", root)
        self.assertNotIn('class="footer-language"', root)
        self.assertNotIn("location.replace", root)

    def test_invalid_or_duplicate_tags_leave_previous_build_intact(self):
        self.write("index.md", "# Original homepage")
        self.write("english.md", "---\ni18n: en-US\n---\nEnglish")
        output = build_site(self.config)
        previous = (output / "index.html").read_bytes()
        duplicate = self.write("duplicate.md", "---\ni18n: EN_us\n---\nDuplicate")
        with self.assertRaises(ValueError):
            build_site(self.config)
        self.assertEqual((output / "index.html").read_bytes(), previous)
        duplicate.write_text("---\ni18n: ../en\n---\nInvalid", encoding="utf-8")
        with self.assertRaises(ValueError):
            build_site(self.config)
        self.assertEqual((output / "index.html").read_bytes(), previous)

    def test_default_language_cannot_be_created_twice(self):
        self.write("index.md", "---\ni18n: en\n---\nHome")
        with self.assertRaises(ValueError):
            create_homepage(self.config, "en")
        self.write("other.md", "---\ni18n: en\n---\nOther")
        with self.assertRaises(ValueError):
            build_site(self.config)

    def test_homepage_console_creates_and_edits_language_versions(self):
        self.write("index.md", "# 首页")
        with contextlib.redirect_stdout(io.StringIO()), mock.patch("paper_cli._require_linked", return_value=self.config), \
             mock.patch("sys.stdin.isatty", return_value=True), mock.patch("sys.stdout.isatty", return_value=True), \
             mock.patch("paper_cli._terminal_menu", side_effect=["__home__", "i18n", "en", "__home__:en", "edit", "back"]) as menu, \
             mock.patch("paper_cli._open_editor") as editor, mock.patch("paper_cli._pause"), override_language("zh_CN"):
            self.assertEqual(paper_cli.cmd_list(), 0)
        path = self.posts / "index.en.md"
        self.assertTrue(path.exists())
        self.assertEqual(editor.call_args_list, [mock.call(path, self.config), mock.call(path, self.config)])
        home_options = menu.call_args_list[1].args[1]
        self.assertIn(("i18n", "新增多语言页面", "选择语言，创建对应的首页版本"), home_options)
        translated_options = menu.call_args_list[4].args[1]
        self.assertEqual([option[0] for option in translated_options], ["edit", "back"])

    def test_config_home_menu_exposes_language_creation(self):
        with mock.patch("paper_cli._terminal_menu", side_effect=["i18n", "back"]) as menu, \
             mock.patch("paper_cli._add_homepage") as create, override_language("zh_CN"):
            self.assertEqual(paper_cli.cmd_brand_config(self.config), 0)
        self.assertIn(("i18n", "新增多语言页面", "选择语言，创建对应的首页版本"), menu.call_args_list[0].args[1])
        create.assert_called_once_with(self.config)

    def test_language_menu_excludes_existing_versions_and_can_cancel(self):
        self.write("index.md", "---\ni18n: zh-CN\n---\n# 首页")
        self.write("custom.md", "---\ni18n: en\n---\n# English")
        with mock.patch("paper_cli._terminal_menu", return_value=None) as menu, mock.patch("paper_cli._open_editor") as editor:
            paper_cli._add_homepage(self.config)
        codes = [option[0] for option in menu.call_args.args[1]]
        self.assertNotIn("en", codes)
        self.assertNotIn("zh-CN", codes)
        self.assertIn("ja", codes)
        editor.assert_not_called()
        self.assertEqual(len(list(self.posts.glob("*.md"))), 2)


@unittest.skipUnless(shutil.which("node"), "Browser negotiation checks use optional Node.js, not the Paper runtime")
class HomepageBrowserNegotiationTests(unittest.TestCase):
    def negotiate(self, languages: list[str], *, choices: tuple[str, ...] = ("en", "fr", "zh-CN", "zh-TW"),
                  preferred: str | None = None, auto: bool = True, query: str = "", storage_blocked: bool = False,
                  default_language: str = "", intl: bool = True) -> dict:
        links = [HomepageLink("default", default_language, "/blog/", "Default")]
        links += [HomepageLink(code, code, f"/blog/{code}/", code) for code in choices]
        script = homepage_language_bootstrap(links, base_path="/blog", auto=auto)[8:-9]
        harness = """
const vm = require('node:vm');
const input = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const storage = input.preferred ? {'paper-language:/blog': input.preferred} : {};
const url = new URL('https://example.test/blog/' + input.query);
let redirect = null;
const context = {
  window: {}, URL, URLSearchParams, Intl: input.intl ? Intl : {},
  navigator: {languages: input.languages, language: input.languages[0]},
  location: {href: url.href, search: url.search, hash: url.hash, replace: value => redirect = value},
  localStorage: {
    getItem: key => {if (input.storage_blocked) throw new Error('Blocked'); return storage[key] || null},
    setItem: (key, value) => {if (input.storage_blocked) throw new Error('Blocked'); storage[key] = value}
  }
};
vm.runInNewContext(input.script, context);
process.stdout.write(JSON.stringify({redirect, storage}));
"""
        result = subprocess.run([shutil.which("node"), "-e", harness], input=json.dumps({
            "script": script, "languages": languages, "preferred": preferred, "query": query,
            "storage_blocked": storage_blocked, "intl": intl,
        }), capture_output=True, text=True, check=True)
        return json.loads(result.stdout)

    def test_browser_preferences_regions_and_scripts(self):
        cases = [(["en-US"], "en"), (["de-DE", "fr-CA", "en"], "fr"), (["zh-HK"], "zh-TW"),
                 (["zh-Hans-SG"], "zh-CN"), (["zh-Hant-TW"], "zh-TW"), (["ja-JP"], None)]
        for languages, choice in cases:
            with self.subTest(languages=languages):
                expected = f"https://example.test/blog/{choice}/" if choice else None
                self.assertEqual(self.negotiate(languages)["redirect"], expected)
        self.assertIsNone(self.negotiate(["zh-CN"], choices=("en", "zh-TW"))["redirect"])
        self.assertEqual(self.negotiate(["en-AU"], choices=("en-US", "en-GB"))["redirect"], "https://example.test/blog/en-US/")
        self.assertEqual(self.negotiate(["en-GB"], choices=("en-US", "en-GB"))["redirect"], "https://example.test/blog/en-GB/")

    def test_manual_choice_and_explicit_language_urls_win(self):
        self.assertEqual(self.negotiate(["en-US"], preferred="fr")["redirect"], "https://example.test/blog/fr/")
        self.assertIsNone(self.negotiate(["en-US"], preferred="default")["redirect"])
        self.assertIsNone(self.negotiate(["en-US"], preferred="fr", auto=False)["redirect"])
        self.assertEqual(self.negotiate(["en-US"], preferred="removed")["redirect"], "https://example.test/blog/en/")
        result = self.negotiate(["en-US"], preferred="fr", query="?lang=default")
        self.assertIsNone(result["redirect"])
        self.assertEqual(result["storage"]["paper-language:/blog"], "default")

    def test_default_declaration_participates_in_ordered_preferences(self):
        self.assertIsNone(self.negotiate(["zh-CN", "en"], choices=("en", "fr"), default_language="zh-CN")["redirect"])
        self.assertEqual(self.negotiate(["en-US", "zh-CN"], choices=("en", "fr"), default_language="zh-CN")["redirect"], "https://example.test/blog/en/")

    def test_blocked_storage_default_link_and_tracking_parameters(self):
        self.assertIsNone(self.negotiate(["en-US"], query="?lang=default", storage_blocked=True)["redirect"])
        self.assertEqual(self.negotiate(["en-US"], storage_blocked=True, query="?utm_source=test#intro")["redirect"],
                         "https://example.test/blog/en/?utm_source=test#intro")

    def test_script_fallback_without_intl_locale(self):
        self.assertEqual(self.negotiate(["zh-HK"], intl=False)["redirect"], "https://example.test/blog/zh-TW/")
        self.assertIsNone(self.negotiate(["zh-CN"], choices=("en", "zh-TW"), intl=False)["redirect"])


if __name__ == "__main__":
    unittest.main()
