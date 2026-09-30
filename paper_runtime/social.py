"""Static social metadata and locally rendered PNG sharing cards."""

from __future__ import annotations

import hashlib
import html
import json
import re
from functools import lru_cache
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse


CARD_SIZE = (1200, 630)
FONT_PATH = Path(__file__).with_name("assets") / "ZCOOLXiaoWei-Regular.ttf"
SOCIAL_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


class _TextContent(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "pre"}:
            self.hidden += 1
        if tag in {"p", "br", "h1", "h2", "h3", "li", "div"}:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "pre"}:
            self.hidden = max(0, self.hidden - 1)
        self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


def page_description(rendered: str, explicit: str = "") -> str:
    """Use frontmatter when supplied, otherwise a short readable body excerpt."""
    parser = _TextContent()
    if explicit.strip():
        text = explicit
    else:
        parser.feed(rendered)
        text = "".join(parser.parts)
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= 180 else text[:179].rstrip() + "…"


def social_metadata(
    *, title: str, site_name: str, description: str, url: str = "",
    image: str = "", image_size: tuple[int, int] | None = None,
    page_type: str = "website", locale: str = "zh_CN", draft: bool = False,
) -> str:
    """Emit metadata in the static head so crawlers never need JavaScript."""
    values = [
        ("name", "description", description),
        ("property", "og:title", title),
        ("property", "og:site_name", site_name),
        ("property", "og:description", description),
        ("property", "og:type", page_type),
        ("property", "og:locale", locale),
        ("name", "twitter:card", "summary_large_image" if image else "summary"),
        ("name", "twitter:title", title),
        ("name", "twitter:description", description),
    ]
    if url:
        values.append(("property", "og:url", url))
    if image:
        values.extend([
            ("property", "og:image", image),
            ("property", "og:image:alt", title),
            ("name", "twitter:image", image),
            ("name", "twitter:image:alt", title),
        ])
        if image_size:
            values.extend([
                ("property", "og:image:width", str(image_size[0])),
                ("property", "og:image:height", str(image_size[1])),
                ("property", "og:image:type", "image/png"),
            ])
    if draft:
        values.append(("name", "robots", "noindex, nofollow"))
    tags = "".join(
        f'<meta {attribute}="{key}" content="{html.escape(value, quote=True)}">'
        for attribute, key, value in values
    )
    if url:
        tags += f'<link rel="canonical" href="{html.escape(url, quote=True)}">'
    return tags


@lru_cache(maxsize=16)
def _font(size: int):
    from PIL import ImageFont

    return ImageFont.truetype(str(FONT_PATH), size=size)


def _lines(text: str, font, width: int, limit: int) -> list[str]:
    """Wrap by measured glyph widths, including Chinese and long unbroken text."""
    lines: list[str] = []
    current = ""
    text = re.sub(r"\s+", " ", text).strip()
    for char in text:
        if current and font.getlength(current + char) > width:
            boundary = current.rfind(" ")
            if boundary > len(current) // 2:
                lines.append(current[:boundary].rstrip())
                current = current[boundary + 1:] + char
            else:
                lines.append(current.rstrip())
                current = char.lstrip()
            if len(lines) == limit:
                last = lines[-1]
                while last and font.getlength(last + "…") > width:
                    last = last[:-1]
                lines[-1] = last.rstrip() + "…"
                return lines
        else:
            current += char
    if current:
        lines.append(current.rstrip())
    return lines


def generate_card(
    build_dir: Path, *, title: str, site_name: str, description: str,
    color: str, url: str, date: str = "",
) -> str:
    """Return an asset path for a 1200×630 card; changed content gets a new URL."""
    try:
        from PIL import Image, ImageColor, ImageDraw
    except ImportError:
        raise RuntimeError("Paper 的分享图运行依赖未安装；请重新安装 Paper。") from None

    payload = json.dumps([title, site_name, description, color, url, date], ensure_ascii=False)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]
    relative = f"assets/og/{digest}.png"
    target = build_dir / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        return relative

    try:
        accent = ImageColor.getrgb(color)[:3]
    except ValueError:
        accent = (217, 119, 87)
    image = Image.new("RGB", CARD_SIZE, "#f8f5ef")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 1199, 11), fill=accent)
    draw.rounded_rectangle((64, 55, 108, 99), radius=10, fill=accent)
    draw.text((75, 59), "P", font=_font(34), fill="white")
    brand = _lines(site_name, _font(32), 1004, 1)
    if brand:
        draw.text((126, 60), brand[0], font=_font(32), fill="#60564e")

    title_font = _font(72)
    title_lines = _lines(title, title_font, 1072, 3)
    if title_lines and title_lines[-1].endswith("…"):
        title_font = _font(60)
        title_lines = _lines(title, title_font, 1072, 3)
    if len(title_lines) == 2 and title_font.getlength(title_lines[1]) < title_font.getlength(title_lines[0]) * 0.4:
        balanced_width = int(title_font.getlength(title) / 2 + title_font.size / 2)
        balanced = _lines(title, title_font, balanced_width, 3)
        if len(balanced) == 2:
            title_lines = balanced
    for index, line in enumerate(title_lines):
        draw.text((64, 150 + index * 86), line, font=title_font, fill="#26221f")
    for index, line in enumerate(_lines(description, _font(28), 1072, 2)):
        draw.text((64, 428 + index * 39), line, font=_font(28), fill="#746b62")

    draw.line((64, 549, 1136, 549), fill="#dcd5cb", width=2)
    parsed = urlparse(url)
    address = parsed.netloc + parsed.path.rstrip("/")
    label = " / ".join(value for value in [date, address] if value)
    if label:
        draw.text((64, 573), _lines(label, _font(24), 1072, 1)[0], font=_font(24), fill="#746b62")
    image.save(target, "PNG", optimize=True)
    return relative
