import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from paper_runtime.core import PaperConfig, build_site
from paper_runtime.domains import custom_domain, dns_records, normalize_pages_url


class PaperDomainTests(unittest.TestCase):
    def test_rebuilding_and_changing_domain_keeps_pages_binding_in_output(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            posts = root / "posts"
            posts.mkdir()
            (posts / "index.md").write_text("# Home", encoding="utf-8")
            (posts / "public.md").write_text("---\ntitle: Public\npublished: true\n---\n\nHello", encoding="utf-8")
            config = PaperConfig(posts_dir=posts, site_dir=root / "site", site_url="https://1leaf.cc")
            for domain in ("1leaf.cc", "1leaf.cc", "blog.1leaf.cc"):
                config = replace(config, site_url=f"https://{domain}")
                out = build_site(config)
                self.assertEqual((out / "CNAME").read_text(), f"{domain}\n")
                self.assertIn(f"https://{domain}/posts/public/", (out / "rss.xml").read_text())
                self.assertIn(f"https://{domain}/", (out / "sitemap.xml").read_text())
            out = build_site(replace(config, site_url="https://ohmyangboy.github.io/blog"))
            self.assertFalse((out / "CNAME").exists())
            self.assertIn("https://ohmyangboy.github.io/blog/posts/public/", (out / "rss.xml").read_text())

    def test_default_pages_and_local_previews_do_not_create_custom_domain_bindings(self):
        for url in ("", "/blog", "https://ohmyangboy.github.io/blog", "https://GITHUB.io", "http://localhost:4176", "http://127.0.0.1", "http://[::1]", "https://user:password@1leaf.cc", "https://1leaf.cc:8443"):
            with self.subTest(url=url):
                self.assertIsNone(custom_domain(url))
        self.assertEqual(custom_domain("https://1leaf.cc/"), "1leaf.cc")
        self.assertEqual(custom_domain("https://博客.1leaf.cc/"), "xn--9krq6q.1leaf.cc")

    def test_pages_url_normalizes_domains_and_preserves_default_pages_paths(self):
        self.assertEqual(normalize_pages_url("1leaf.cc"), "https://1leaf.cc")
        self.assertEqual(normalize_pages_url("https://BLOG.Example.com/"), "https://blog.example.com")
        self.assertEqual(normalize_pages_url("博客.example.com"), "https://xn--9krq6q.example.com")
        self.assertEqual(normalize_pages_url("https://owner.github.io/blog/"), "https://owner.github.io/blog")
        self.assertEqual(normalize_pages_url(""), "")
        for value in ("localhost", "127.0.0.1", "ftp://example.com", "https://user:secret@example.com", "https://example.com:443", "https://example.com/blog", "https://example.com?x=1", "https://example.com/#section", "https://example.com:wrong", "https://owner.github.io/../blog"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_pages_url(value)

    def test_dns_records_use_the_managed_zone_for_apex_and_nested_subdomains(self):
        root = dns_records("example.co.uk", "owner", "example.co.uk")
        self.assertEqual(len(root), 5)
        self.assertEqual([kind for _, kind, _ in root], ["A"] * 4 + ["CNAME"])
        self.assertEqual(root[-1], ("www", "CNAME", "owner.github.io"))
        self.assertEqual(dns_records("docs.blog.example.co.uk", "owner", "example.co.uk"), [("docs.blog", "CNAME", "owner.github.io")])
        self.assertEqual(dns_records("www.example.com", "owner", "EXAMPLE.com"), [("www", "CNAME", "owner.github.io")])
        with self.assertRaises(ValueError):
            dns_records("example.com", "owner", "other.com")
