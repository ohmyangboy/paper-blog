"""Explicit iframe blocks without enabling arbitrary Markdown HTML."""

import html
import re
from html.parser import HTMLParser
from urllib.parse import urlparse


class _FrameParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.attrs = None

    def handle_starttag(self, tag, attrs):
        if tag == "iframe":
            self.attrs = dict(attrs)


def render_iframe(source):
    parser = _FrameParser()
    parser.feed(source)
    attrs = parser.attrs or {}
    src = attrs.get("src") or ""
    try:
        url = urlparse(src)
        if url.scheme not in {"https", "http"} or not url.hostname or url.username or url.password:
            return None
    except ValueError:
        return None
    clean = {"src": src, "title": attrs.get("title") or "嵌入内容", "loading": "lazy",
             "sandbox": "allow-scripts allow-same-origin allow-presentation",
             "referrerpolicy": "strict-origin-when-cross-origin"}
    for key in ("width", "height"):
        value = attrs.get(key) or ""
        if re.fullmatch(r"[1-9]\d{0,4}%?", value):
            clean[key] = value
    styles = [f"{key}:{value if value.endswith('%') else value + 'px'}" for key, value in clean.items() if key in {"width", "height"}]
    for declaration in (attrs.get("style") or "").split(";"):
        key, sep, value = declaration.partition(":")
        key, value = key.strip().lower(), value.strip().lower()
        valid = (
            key in {"width", "height", "max-width", "max-height"} and re.fullmatch(r"(?:\d+(?:\.\d+)?(?:px|%|vw|vh|rem|em)|auto)", value)
            or key == "aspect-ratio" and re.fullmatch(r"[1-9]\d*(?:\s*/\s*[1-9]\d*)?", value)
            or key == "display" and value == "block"
            or key in {"margin", "margin-left", "margin-right"} and value in {"auto", "0"}
            or key == "border" and value in {"0", "none"}
        )
        if sep and valid:
            styles.append(f"{key}:{value}")
    if styles:
        clean["style"] = ";".join(styles)
    allowed = {"fullscreen", "autoplay", "picture-in-picture", "encrypted-media"}
    permissions = [p.strip() for p in (attrs.get("allow") or "").split(";") if p.strip() in allowed]
    if "allowfullscreen" in attrs and "fullscreen" not in permissions:
        permissions.append("fullscreen")
    if permissions:
        clean["allow"] = "; ".join(permissions)
    rendered = " ".join(f'{key}="{html.escape(value, quote=True)}"' for key, value in clean.items())
    fullscreen = " allowfullscreen" if "fullscreen" in permissions else ""
    return f'<iframe class="paper-iframe" {rendered}{fullscreen}></iframe>\n'


def iframe_block(state, start_line, end_line, silent):
    if state.is_code_block(start_line):
        return False
    start = state.bMarks[start_line] + state.tShift[start_line]
    if not re.match(r"<iframe(?:\s|>)", state.src[start:], re.I):
        return False
    match = re.match(r"<iframe\b[^>]*>\s*</iframe\s*>[ \t]*(?:\n|$)", state.src[start:state.bMarks[end_line]], re.I)
    if not match:
        return False
    rendered = render_iframe(match.group())
    if rendered is None:
        return False
    if silent:
        return True
    next_line = start_line + match.group().count("\n")
    if not match.group().endswith("\n"):
        next_line += 1
    token = state.push("html_block", "", 0)
    token.content = rendered
    token.map = [start_line, next_line]
    state.line = next_line
    return True
