import os
import tempfile
import threading
import unittest
from functools import partial
from html.parser import HTMLParser
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from urllib.parse import quote
from unittest.mock import patch

from PIL import Image

from paper_runtime.core import PaperConfig, build_site, render_markdown
from paper_runtime.i18n import override_language
from paper_runtime.preview import _PreviewHandler


class PaperVideoTests(unittest.TestCase):
    def test_local_poster_imports_and_reserves_portrait_ratio(self):
        with tempfile.TemporaryDirectory() as root:
            posts = Path(root)
            (posts / "covers").mkdir()
            cover = posts / "covers" / "Portrait Cover.JPG"
            Image.new("RGB", (90, 160), "red").save(cover)
            rendered = render_markdown(
                '![Demo|poster=covers/Portrait Cover.JPG](https://cdn.example.test/demo.mp4)',
                posts_dir=posts, asset_base="/blog/assets/",
            )
            self.assertIn('poster="/blog/assets/Portrait%20Cover.JPG"', rendered)
            self.assertIn('--video-ratio: 90 / 160', rendered)
            self.assertIn('preload="none"', rendered)
            self.assertIn('0:00 / --:--', rendered)
            self.assertEqual((posts / "assets" / cover.name).read_bytes(), cover.read_bytes())
            explicit = render_markdown(
                '![Demo|640x360|poster=covers/Portrait Cover.JPG](https://cdn.example.test/demo.mp4)',
                posts_dir=posts,
            )
            self.assertIn('--video-ratio: 640 / 360', explicit)
            self.assertNotIn('--video-ratio: 90 / 160', explicit)
            self.assertIn('width="640" height="360"', explicit)
            self.assertIn('preload="metadata"', render_markdown(
                '![Demo|preload=metadata|poster=covers/Portrait Cover.JPG](https://cdn.example.test/demo.mp4)', posts_dir=posts,
            ))
            self.assertIn('preload="metadata"', render_markdown(
                '![Demo|autoplay|poster=covers/Portrait Cover.JPG](https://cdn.example.test/demo.mp4)', posts_dir=posts,
            ))

    def test_remote_poster_keeps_case_signed_query_and_attribute_escaping(self):
        source = 'https://cdn.example.test/Demo.mp4?token=Ab%2FC&expires=123'
        poster = 'https://images.example.test/Cover.JPG?token=Cd%2FE&width=315'
        rendered = render_markdown(f'![Demo|315x560|poster={poster}]({source})')
        self.assertIn('src="https://cdn.example.test/Demo.mp4?token=Ab%2FC&amp;expires=123"', rendered)
        self.assertIn('poster="https://images.example.test/Cover.JPG?token=Cd%2FE&amp;width=315"', rendered)
        fragment = render_markdown(f'![Demo]({source}#poster={quote(poster, safe="")})')
        self.assertIn('poster="https://images.example.test/Cover.JPG?token=Cd%2FE&amp;width=315"', fragment)

        class Tags(HTMLParser):
            def handle_starttag(self, tag, attrs):
                if tag == "video":
                    self.attrs = dict(attrs)
        tags = Tags()
        tags.feed(render_markdown('![Demo|poster=https://images.example.test/Cover.jpg?x="onload="bad](assets/demo.mp4)'))
        self.assertNotIn("onload", tags.attrs)
        self.assertIn('poster="Covers/My%20Cover.JPG"', render_markdown('![Demo|poster=Covers/My Cover.JPG](assets/demo.mp4)'))

    def test_obsidian_poster_does_not_replace_video_label(self):
        with tempfile.TemporaryDirectory() as root:
            posts = Path(root)
            (posts / "attachments").mkdir()
            (posts / "attachments" / "demo.mp4").write_bytes(b"demo")
            Image.new("RGB", (90, 160)).save(posts / "attachments" / "Cover.JPG")
            rendered = render_markdown('![[demo.mp4|演示|poster=Cover.JPG]]', posts_dir=posts)
            self.assertIn('poster="/assets/Cover.JPG"', rendered)
            self.assertIn('aria-label="演示"', rendered)
            self.assertNotIn('aria-label="poster=', rendered)

    def test_invalid_or_missing_posters_keep_video_playable(self):
        with tempfile.TemporaryDirectory() as root:
            posts = Path(root)
            outside = posts / "private.jpg"
            Image.new("RGB", (10, 10)).save(outside)
            linked = posts / "linked.jpg"
            linked.symlink_to(outside)
            for poster in ['javascript:alert(1)', 'data:image/svg+xml,bad', 'file:///private.jpg', 'https://[invalid]/Cover.jpg', 'missing.jpg', 'linked.jpg']:
                rendered = render_markdown(f'![Demo|poster={poster}](https://cdn.example.test/demo.mp4)', posts_dir=posts)
                self.assertIn('<video', rendered)
                self.assertNotIn(' poster=', rendered)
            self.assertNotIn(' poster=', render_markdown('![Demo|poster=https://example.test/cover.jpg](https://vimeo.com/123456)'))

    def test_build_retains_poster_across_rebuilds_and_absolutizes_rss(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            posts = base / "posts"
            (posts / "covers").mkdir(parents=True)
            Image.new("RGB", (90, 160), "blue").save(posts / "covers" / "Published Cover.jpg")
            Image.new("RGB", (90, 160), "red").save(posts / "covers" / "draft.jpg")
            for name, cover in [('published', 'Published Cover.jpg'), ('draft', 'draft.jpg')]:
                (posts / f'{name}.md').write_text(
                    f'---\ntitle: {name}\npublished: {str(name == "published").lower()}\n---\n\n'
                    f'![Demo|poster=covers/{cover}](https://cdn.example.test/demo.mp4)'
                )
            config = PaperConfig(posts_dir=posts, site_dir=base / "site", site_url="https://example.test/blog", compress=False)
            for _ in range(2):
                output = build_site(config)
                self.assertTrue((output / 'assets' / 'Published Cover.jpg').exists())
                self.assertFalse((output / 'assets' / 'draft.jpg').exists())
                self.assertIn('poster="/blog/assets/Published%20Cover.jpg"', (output / 'posts' / 'published' / 'index.html').read_text())
                from xml.etree import ElementTree
                feed = ElementTree.parse(output / 'rss.xml')
                description = feed.findtext('channel/item/description')
                self.assertIn('poster="https://example.test/blog/assets/Published%20Cover.jpg"', description)

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
