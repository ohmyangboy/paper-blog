"""Unit tests for Paper CLI and runtime internationalization (i18n)."""

from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from paper_runtime.core import (
    PaperConfig,
    build_site,
    load_config,
    save_config,
)
from paper_runtime.i18n import (
    DEFAULT_FALLBACK_LANGUAGE,
    LANGUAGE_LABELS,
    SUPPORTED_LANGUAGES,
    TRANSLATIONS,
    detect_system_language,
    get_current_language,
    normalize_locale,
    resolve_language,
    set_current_language,
    t,
)
from paper_cli import _main, cmd_config, make_parser


class PaperI18nTests(unittest.TestCase):
    def setUp(self):
        self.orig_lang = get_current_language()
        self.temp_dir = Path(tempfile.mkdtemp(prefix="paper-i18n-test-"))
        self.old_paper_home = os.environ.get("PAPER_HOME")
        os.environ["PAPER_HOME"] = str(self.temp_dir / ".paper")

    def tearDown(self):
        set_current_language(self.orig_lang)
        if self.old_paper_home is None:
            os.environ.pop("PAPER_HOME", None)
        else:
            os.environ["PAPER_HOME"] = self.old_paper_home
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_normalize_locale(self):
        # Chinese variants
        for val in ("zh", "zh_CN", "zh-CN", "zh_Hans", "zh_TW", "zh_CN.UTF-8", "ZH"):
            self.assertEqual(normalize_locale(val), "zh_CN")

        # English variants
        for val in ("en", "en_US", "en-US", "en_GB", "en_US.UTF-8", "EN"):
            self.assertEqual(normalize_locale(val), "en_US")

        # Unknown / Empty / None fallbacks to DEFAULT_FALLBACK_LANGUAGE (en_US)
        for val in ("ja_JP", "fr_FR", "de", "", None, "invalid_lang"):
            self.assertEqual(normalize_locale(val), DEFAULT_FALLBACK_LANGUAGE)

    def test_detect_system_language_from_env(self):
        with mock.patch.dict(os.environ, {"LC_ALL": "zh_CN.UTF-8", "LANG": "en_US.UTF-8"}):
            self.assertEqual(detect_system_language(), "zh_CN")

        with mock.patch.dict(os.environ, {"LC_ALL": "", "LC_MESSAGES": "en_GB.UTF-8", "LANG": "zh_CN"}):
            self.assertEqual(detect_system_language(), "en_US")

        with mock.patch.dict(os.environ, {"LC_ALL": "", "LC_MESSAGES": "", "LANG": "fr_FR.UTF-8"}):
            self.assertEqual(detect_system_language(), "en_US")

    def test_resolve_language_priority(self):
        # 1. CLI lang overrides everything
        with mock.patch.dict(os.environ, {"PAPER_LANG": "zh_CN", "LANG": "zh_CN"}):
            self.assertEqual(resolve_language(config_lang="zh_CN", cli_lang="en"), "en_US")

        # 2. PAPER_LANG env overrides config and system
        with mock.patch.dict(os.environ, {"PAPER_LANG": "en_US", "LANG": "zh_CN"}):
            self.assertEqual(resolve_language(config_lang="zh_CN"), "en_US")

        # 3. Config language overrides system
        with mock.patch.dict(os.environ, {"PAPER_LANG": "", "LANG": "zh_CN"}):
            self.assertEqual(resolve_language(config_lang="en_US"), "en_US")

        # 4. Auto config delegates to system
        with mock.patch.dict(os.environ, {"PAPER_LANG": "", "LANG": "zh_CN.UTF-8"}):
            self.assertEqual(resolve_language(config_lang="auto"), "zh_CN")

    def test_translations_dictionary_completeness(self):
        # Verify that all keys in TRANSLATIONS define both zh_CN and en_US
        for key, entry in TRANSLATIONS.items():
            for lang in SUPPORTED_LANGUAGES:
                self.assertIn(
                    lang,
                    entry,
                    f"Translation key '{key}' is missing translation for language '{lang}'",
                )
                self.assertTrue(
                    len(entry[lang]) > 0,
                    f"Translation key '{key}' for language '{lang}' is empty",
                )

    def test_t_function_behavior(self):
        set_current_language("zh_CN")
        self.assertEqual(t("yes"), "是")
        self.assertEqual(t("link_linked", path="/path/to/posts"), "✅ 已关联文章目录：/path/to/posts")

        set_current_language("en_US")
        self.assertEqual(t("yes"), "Yes")
        self.assertEqual(t("link_linked", path="/path/to/posts"), "✅ Linked posts directory: /path/to/posts")

        # Unknown key returns fallback or key itself
        self.assertEqual(t("unknown_key_123", default="Default Val {foo}", foo="bar"), "Default Val bar")
        self.assertEqual(t("unknown_key_456"), "unknown_key_456")

    def test_config_language_setting_and_persistence(self):
        config_dir = self.temp_dir / "posts"
        config_dir.mkdir(parents=True)
        (config_dir / "index.md").write_text("# Test\n", encoding="utf-8")

        config = save_config(PaperConfig(posts_dir=config_dir, site_dir=self.temp_dir / "site", language="auto"))
        self.assertEqual(config.language, "auto")

        # Change language via cmd_config
        cmd_config(config_cmd="language", editor_name="en_US")
        reloaded = load_config()
        self.assertEqual(reloaded.language, "en_US")

        cmd_config(config_cmd="lang", editor_name="zh_CN")
        reloaded = load_config()
        self.assertEqual(reloaded.language, "zh_CN")

    def test_build_site_with_language_settings(self):
        posts_dir = self.temp_dir / "posts"
        posts_dir.mkdir(parents=True)
        (posts_dir / "index.md").write_text("# My Blog\n", encoding="utf-8")
        (posts_dir / "post-1.md").write_text(
            "---\ntitle: English Post\ndate: 2026-08-29\npublished: false\n---\n\nDraft content with ![[nonexistent.png]]\n",
            encoding="utf-8",
        )

        site_dir = self.temp_dir / "site"

        # 1. Build in English
        config_en = PaperConfig(
            posts_dir=posts_dir,
            site_dir=site_dir,
            site_name="My Blog",
            language="en_US",
        )
        build_site(config_en, include_drafts=True)

        index_en = (site_dir / "out" / "index.html").read_text(encoding="utf-8")
        self.assertIn('<html lang="en-US">', index_en)
        self.assertIn(" (Draft)", index_en)

        rss_en = (site_dir / "out" / "rss.xml").read_text(encoding="utf-8")
        self.assertIn("<language>en-US</language>", rss_en)
        self.assertIn("Latest posts from My Blog", rss_en)

        post_en = (site_dir / "out" / "posts" / "post-1" / "index.html").read_text(encoding="utf-8")
        self.assertIn("Draft Preview", post_en)
        self.assertIn('aria-label="Back to previous page"', post_en)
        self.assertIn("Image not found: nonexistent.png", post_en)

        # 2. Build in Chinese
        config_zh = PaperConfig(
            posts_dir=posts_dir,
            site_dir=site_dir,
            site_name="My Blog",
            language="zh_CN",
        )
        build_site(config_zh, include_drafts=True)

        index_zh = (site_dir / "out" / "index.html").read_text(encoding="utf-8")
        self.assertIn('<html lang="zh-CN">', index_zh)
        self.assertIn("（草稿）", index_zh)

        rss_zh = (site_dir / "out" / "rss.xml").read_text(encoding="utf-8")
        self.assertIn("<language>zh-CN</language>", rss_zh)
        self.assertIn("My Blog 的最新文章", rss_zh)

        post_zh = (site_dir / "out" / "posts" / "post-1" / "index.html").read_text(encoding="utf-8")
        self.assertIn("草稿预览", post_zh)
        self.assertIn('aria-label="返回上一页"', post_zh)
        self.assertIn("图片未找到：nonexistent.png", post_zh)

    def test_cli_parser_i18n(self):
        set_current_language("en_US")
        parser_en = make_parser()
        self.assertEqual(parser_en.description, "Minimal Markdown static site generator and writing CLI")

        set_current_language("zh_CN")
        parser_zh = make_parser()
        self.assertEqual(parser_zh.description, "极简 Markdown 静态博客生成器与写作 CLI")

    def test_config_menu_options_i18n(self):
        config_dir = self.temp_dir / "posts"
        config_dir.mkdir(parents=True)
        (config_dir / "index.md").write_text("# Test\n", encoding="utf-8")
        save_config(PaperConfig(posts_dir=config_dir, site_dir=self.temp_dir / "site", language="en_US", compress=True))

        # 1. Test in English
        set_current_language("en_US")
        captured_title = None
        captured_options = None

        def fake_menu(title, options):
            nonlocal captured_title, captured_options
            captured_title = title
            captured_options = options
            return "back"

        with mock.patch("sys.stdin.isatty", return_value=True), mock.patch(
            "paper_cli._terminal_menu", side_effect=fake_menu
        ):
            cmd_config()

        self.assertIn("⚙️ Paper Config", captured_title)
        opt_dict = {opt[0]: opt[2] for opt in captured_options}
        self.assertIn("Highlight Color / Favicon Icon", opt_dict["home"])
        self.assertIn("Image Compression · Enabled", opt_dict["compress"])
        self.assertIn("Current: default", opt_dict["editor"])
        self.assertIn("Language · English", opt_dict["language"])
        self.assertIn("Not configured · Guide to create repo", opt_dict["remote"])
        self.assertIn("Pages URL / Custom Domain", opt_dict["pages"])
        self.assertIn("Check Git & Remote Reachability", opt_dict["test"])
        self.assertIn("Path / Repo / Deploy (Not configured)", opt_dict["status"])
        self.assertIn("Return to main menu", opt_dict["back"])

        # 2. Test in Chinese
        set_current_language("zh_CN")
        with mock.patch("sys.stdin.isatty", return_value=True), mock.patch(
            "paper_cli._terminal_menu", side_effect=fake_menu
        ):
            cmd_config()

        opt_dict_zh = {opt[0]: opt[2] for opt in captured_options}
        self.assertIn("高亮颜色 / Favicon 图标", opt_dict_zh["home"])
        self.assertIn("图片压缩 · 开启", opt_dict_zh["compress"])
        self.assertIn("当前 default", opt_dict_zh["editor"])
        self.assertIn("语言设置 · English", opt_dict_zh["language"])
        self.assertIn("未配置 · 引导创建仓库", opt_dict_zh["remote"])
        self.assertIn("Pages 地址 / 自定义域名", opt_dict_zh["pages"])
        self.assertIn("检查 Git 与远程可达性", opt_dict_zh["test"])
        self.assertIn("路径 / 仓库 / 部署（未配置）", opt_dict_zh["status"])
        self.assertIn("返回主菜单", opt_dict_zh["back"])

    def test_deployment_readiness_i18n(self):
        from paper_cli import _deployment_readiness
        config = PaperConfig(posts_dir=self.temp_dir / "posts", site_dir=self.temp_dir / "site")

        set_current_language("en_US")
        state_en, label_en = _deployment_readiness(config)
        self.assertEqual(state_en, "not-configured")
        self.assertEqual(label_en, "Not configured")

        set_current_language("zh_CN")
        state_zh, label_zh = _deployment_readiness(config)
        self.assertEqual(state_zh, "not-configured")
        self.assertEqual(label_zh, "未配置")


if __name__ == "__main__":
    unittest.main()
