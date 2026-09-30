import os
import tempfile
import threading
import unittest
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

from paper_runtime.core import PaperConfig, build_site, render_markdown
from paper_runtime.i18n import override_language
from paper_runtime.preview import _PreviewHandler


class PaperVideoTests(unittest.TestCase):
    def test_local_video_imports_and_keeps_source(self):
        with tempfile.TemporaryDirectory() as root:
            posts = Path(root)
            (posts / "clips").mkdir()
            source = posts / "clips" / "a clip.mp4"
            source.write_bytes(b"video-source")
            rendered = render_markdown('![演示](<clips/a clip.mp4>)', posts_dir=posts, asset_base="/blog/assets/")
            self.assertIn('<video src="/blog/assets/a%20clip.mp4"', rendered)
            self.assertIn('controls muted playsinline preload="metadata"', rendered)
            self.assertEqual((posts / "assets" / source.name).read_bytes(), source.read_bytes())
            self.assertNotIn("<img", rendered)

    def test_obsidian_video_lookup_hints_and_missing_placeholder(self):
        with tempfile.TemporaryDirectory() as root:
            posts = Path(root)
            (posts / "clips").mkdir()
            (posts / "clips" / "demo.webm").write_bytes(b"demo")
            rendered = render_markdown("![[demo.webm|演示|600x400|right|r=16|autoplay|loop]]", posts_dir=posts)
            self.assertIn('aria-label="演示"', rendered)
            self.assertIn('data-autoplay="true"', rendered)
            self.assertIn('data-align="right"', rendered)
            self.assertIn('width: 600px; --video-ratio: 600 / 400; --video-radius: 16px', rendered)
            self.assertIn(' loop ', rendered)
            with override_language("zh_CN"):
                missing = render_markdown("![[missing.mp4]]", posts_dir=posts)
            self.assertIn("视频未找到：missing.mp4", missing)
            self.assertNotIn("<video", missing)

    def test_remote_video_retains_signed_query(self):
        rendered = render_markdown('![Demo|600|r=20](https://cdn.example.test/demo.mp4?token=a%2Fb&expires=123#autoplay&loop)')
        self.assertIn('src="https://cdn.example.test/demo.mp4?token=a%2Fb&amp;expires=123"', rendered)
        self.assertIn('data-autoplay="true"', rendered)
        self.assertIn('--video-radius: 20px', rendered)
        self.assertIn('height: 400px', render_markdown('![Demo](assets/demo.mp4#h=400)'))

    def test_vimeo_links_preserve_privacy_hash_and_ignore_untrusted_options(self):
        for source in ["https://vimeo.com/123456/abc123", "https://player.vimeo.com/video/123456?h=abc123&autoplay=1"]:
            rendered = render_markdown(f"![Demo]({source}#loop)")
            self.assertIn('data-provider="vimeo"', rendered)
            self.assertIn('https://player.vimeo.com/video/123456?', rendered)
            self.assertIn('h=abc123', rendered)
            self.assertIn('autoplay=0', rendered)
            self.assertIn('controls=1', rendered)
        self.assertNotIn("<iframe", render_markdown("![x](https://vimeo.com.evil.test/123456)"))

    def test_html_labels_and_unsafe_urls_remain_safe(self):
        rendered = render_markdown('![<script>alert(1)</script>](assets/demo.mp4)\n\n<video src="bad.mp4"></video>')
        self.assertNotIn('<script>', rendered)
        self.assertIn('&lt;video', rendered)
        self.assertNotIn('<video', render_markdown('![x](javascript:alert.mp4)'))
        self.assertNotIn('<video', render_markdown('`![[demo.mp4]]`'))
        self.assertNotIn('<video', render_markdown('```\n![x](demo.mp4)\n```'))

    def test_obsidian_ambiguity_and_symlink_escape(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            posts = base / "posts"
            posts.mkdir()
            outside = base / "outside.mp4"
            outside.write_bytes(b"private")
            (posts / "leak.mp4").symlink_to(outside)
            (posts / "linked").symlink_to(base, target_is_directory=True)
            for source in ['![[../outside.mp4]]', '![[leak.mp4]]', '![x](linked/outside.mp4)']:
                self.assertNotIn('<video', render_markdown(source, posts_dir=posts))
            for folder in ["a", "b"]:
                (posts / folder).mkdir()
                (posts / folder / "same.mp4").write_bytes(folder.encode())
            with self.assertRaisesRegex(ValueError, "名称不唯一"):
                render_markdown("![[same.mp4]]", posts_dir=posts)

    def test_colliding_videos_do_not_overwrite_existing_asset(self):
        with tempfile.TemporaryDirectory() as root:
            posts = Path(root)
            for folder in ["a", "b"]:
                (posts / folder).mkdir()
                (posts / folder / "same.mp4").write_bytes(folder.encode())
            first = render_markdown("![x](a/same.mp4)", posts_dir=posts)
            second = render_markdown("![x](b/same.mp4)", posts_dir=posts)
            self.assertNotEqual(first, second)
            self.assertEqual((posts / "assets" / "same.mp4").read_bytes(), b"a")
            self.assertEqual(len(list((posts / "assets").glob("*.mp4"))), 2)

    def test_build_copies_only_published_video_and_localizes_controls(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {"PAPER_LANG": "en_US"}):
            base = Path(root)
            posts = base / "posts"
            assets = posts / "assets"
            assets.mkdir(parents=True)
            for name in ["published", "draft"]:
                (assets / f"{name}.mp4").write_bytes(name.encode())
                (posts / f"{name}.md").write_text(f'---\ntitle: {name}\npublished: {str(name == "published").lower()}\n---\n\n![Demo](assets/{name}.mp4)')
            output = build_site(PaperConfig(posts_dir=posts, site_dir=base / "site", language="en_US", compress=False))
            self.assertTrue((output / "assets" / "published.mp4").exists())
            self.assertFalse((output / "assets" / "draft.mp4").exists())
            page = (output / "posts" / "published" / "index.html").read_text()
            self.assertIn('aria-label="Unmute"', page)
            self.assertIn('IntersectionObserver', page)
            self.assertIn('.video-controls', page)

    def test_preview_video_ranges_allow_seeking(self):
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / 'demo.mp4').write_bytes(b'0123456789')
            server = ThreadingHTTPServer(('127.0.0.1', 0), partial(_PreviewHandler, directory=root, base_path='/blog'))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            url = f'http://127.0.0.1:{server.server_port}/blog/demo.mp4'
            try:
                for byte_range, payload, content_range in [('bytes=2-5', b'2345', 'bytes 2-5/10'), ('bytes=7-', b'789', 'bytes 7-9/10'), ('bytes=-3', b'789', 'bytes 7-9/10')]:
                    with urlopen(Request(url, headers={'Range': byte_range}), timeout=3) as response:
                        self.assertEqual(response.status, 206)
                        self.assertEqual(response.headers['Content-Range'], content_range)
                        self.assertEqual(response.read(), payload)
                for byte_range in ['bytes=99-', 'bytes=5-2', 'bytes=-0', 'bytes=-', 'bytes=1-2,4-5']:
                    with self.assertRaises(HTTPError) as caught:
                        urlopen(Request(url, headers={'Range': byte_range}), timeout=3)
                    self.assertEqual(caught.exception.code, 416)
                    caught.exception.close()
                with urlopen(url, timeout=3) as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.headers['Accept-Ranges'], 'bytes')
                    self.assertEqual(response.read(), b'0123456789')
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
