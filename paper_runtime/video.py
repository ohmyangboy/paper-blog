"""Safe Markdown video embeds and the progressively enhanced player assets."""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse, urlunparse

from .i18n import t

VIDEO_SUFFIXES = {".mp4", ".webm", ".ogv", ".mov", ".m4v"}


def _vimeo_url(src: str) -> str | None:
    parsed = urlparse(src)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"vimeo.com", "www.vimeo.com", "player.vimeo.com"}:
        return None
    match = re.fullmatch(r"/(?:video/)?([0-9]+)(?:/([a-zA-Z0-9]+))?/?", parsed.path)
    if not match:
        return None
    privacy_hash = parse_qs(parsed.query).get("h", [match[2] or ""])[0]
    query = {"dnt": "1", "muted": "1", "autoplay": "0", "controls": "1", "title": "0", "byline": "0", "portrait": "0"}
    if re.fullmatch(r"[a-zA-Z0-9]+", privacy_hash):
        query["h"] = privacy_hash
    return f"https://player.vimeo.com/video/{match[1]}?{urlencode(query)}"


def is_video_reference(src: str) -> bool:
    parsed = urlparse(src)
    if parsed.scheme and parsed.scheme not in {"http", "https"}:
        return False
    return Path(unquote(parsed.path)).suffix.lower() in VIDEO_SUFFIXES or _vimeo_url(src) is not None


def _icon(name: str) -> str:
    paths = {
        "play": '<path d="m9 5 11 7-11 7z"/>',
        "pause": '<path d="M8 5v14M16 5v14"/>',
        "muted": '<path d="m11 5-6 5H2v4h3l6 5zM17 9l5 6M22 9l-5 6"/>',
        "sound": '<path d="m11 5-6 5H2v4h3l6 5zM15 8a6 6 0 0 1 0 8M18 5a10 10 0 0 1 0 14"/>',
        "fullscreen": '<path d="M8 3H3v5M16 3h5v5M21 16v5h-5M8 21H3v-5"/>',
    }
    return f'<svg class="video-icon video-icon-{name}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{paths[name]}</svg>'


def render_video(
    token: Any, *, asset_base: str, posts_dir: Path | None,
    import_local: Callable[[str], str | None], import_obsidian: Callable[[str], str | None],
) -> str:
    src = token.attrGet("src") or ""
    parsed = urlparse(src)
    remote = bool(parsed.netloc)
    options = list(token.meta.get("paper_video_modifiers", []))
    label = token.content or t("video_label")
    if not token.meta.get("paper_obsidian_image"):
        parts = label.split("|")
        label, options = parts[0] or t("video_label"), parts[1:]
    # Remote query strings may be signed; only the fragment carries Paper hints.
    options += re.split(r"[&,;]", parsed.fragment)
    if not remote:
        options += re.split(r"[&,;]", parsed.query)
    width, height, radius, align = None, None, None, "center"
    autoplay, loop = False, False
    for option in options:
        option = option.strip().lower()
        if option in {"autoplay", "loop"}:
            autoplay = autoplay or option == "autoplay"
            loop = loop or option == "loop"
        elif option in {"left", "right", "center"}:
            align = option
        elif re.fullmatch(r"[1-9][0-9]{0,3}(?:x[1-9][0-9]{0,3})?", option):
            dimensions = option.split("x")
            width = int(dimensions[0])
            height = int(dimensions[1]) if len(dimensions) == 2 else None
        elif re.fullmatch(r"(?:w|width|h|height|r|radius)=[0-9]{1,4}", option):
            key, value = option.split("=")
            number = int(value)
            if key in {"w", "width"} and number > 0:
                width = number
            elif key in {"h", "height"} and number > 0:
                height = number
            elif key in {"r", "radius"} and number <= 512:
                radius = number
    vimeo = _vimeo_url(src)
    clean_src = urlunparse(parsed._replace(fragment="", query=parsed.query if remote else ""))
    if not remote:
        imported = None
        if posts_dir is not None:
            imported = import_obsidian(clean_src) if token.meta.get("paper_obsidian_image") else import_local(clean_src)
        if imported:
            clean_src = asset_base + quote(imported)
        elif posts_dir is not None:
            return f'<span class="missing-video">{html.escape(t("video_not_found", filename=unquote(parsed.path)))}</span>'
        elif clean_src.startswith("assets/"):
            clean_src = asset_base + clean_src.removeprefix("assets/")
    styles = []
    if width:
        styles.append(f"width: {width}px")
    if width and height:
        styles.append(f"--video-ratio: {width} / {height}")
    elif height:
        styles.append(f"height: {height}px")
    if radius is not None:
        styles.append(f"--video-radius: {radius}px")
    attrs = f' style="{"; ".join(styles)}"' if styles else ""
    escape = lambda value: html.escape(value, quote=True)
    labels = {name: escape(t("video_" + name)) for name in ("play", "pause", "unmute", "mute", "seek", "fullscreen", "error", "open")}
    if vimeo:
        vimeo += "&loop=" + str(int(loop))
        media = f'<iframe src="{escape(vimeo)}" title="{escape(label)}" loading="lazy" allow="autoplay; fullscreen; picture-in-picture" allowfullscreen></iframe>'
        source_link = src.split("#", 1)[0]
    else:
        media = f'<video src="{escape(clean_src)}" controls muted playsinline preload="metadata"{" loop" if loop else ""} aria-label="{escape(label)}"><a href="{escape(clean_src)}">{labels["open"]}</a></video>'
        source_link = clean_src
    dataset = " ".join(f'data-label-{key}="{value}"' for key, value in labels.items())
    return (
        f'<span class="paper-video" role="group" aria-label="{escape(label)}" data-provider="{"vimeo" if vimeo else "native"}"'
        f' data-align="{align}" data-autoplay="{str(autoplay).lower()}" {dataset}{attrs}>'
        f'{media}<button class="video-start" type="button" aria-label="{labels["play"]}">{_icon("play")}</button>'
        f'<span class="video-controls"><button class="video-toggle" type="button" aria-label="{labels["play"]}">{_icon("play")}{_icon("pause")}</button>'
        f'<span class="video-time" aria-hidden="true">0:00 / 0:00</span>'
        f'<input class="video-seek" type="range" min="0" max="100" step="0.1" value="0" disabled aria-label="{labels["seek"]}">'
        f'<button class="video-mute" type="button" aria-label="{labels["unmute"]}" aria-pressed="false">{_icon("muted")}{_icon("sound")}</button>'
        f'<button class="video-fullscreen" type="button" aria-label="{labels["fullscreen"]}">{_icon("fullscreen")}</button></span>'
        f'<span class="video-status" role="status" aria-live="polite"></span>'
        f'<a class="video-fallback" href="{escape(source_link)}" target="_blank" rel="noopener noreferrer">{labels["open"]}</a></span>'
    )


def video_css() -> str:
    return (Path(__file__).parent / "assets" / "video-player.css").read_text(encoding="utf-8")


def video_script() -> str:
    script = (Path(__file__).parent / "assets" / "video-player.js").read_text(encoding="utf-8")
    return f"<script>{script}</script>"
