"""Core content, Markdown, configuration, and static-site behaviour."""

from __future__ import annotations

import datetime as _dt
import hashlib
import html
import json
import os
import re
import shutil
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote, unquote, urlparse

try:
    from markdown_it import MarkdownIt
    from markdown_it.token import Token
    from pygments import highlight as pygments_highlight
    from pygments.formatters import HtmlFormatter
    from pygments.lexers import get_lexer_by_name
    from pygments.util import ClassNotFound
except ImportError:  # pragma: no cover - exercised by doctor/packaging tests
    MarkdownIt = None
    Token = None
    pygments_highlight = None
    HtmlFormatter = None
    get_lexer_by_name = None

    class ClassNotFound(Exception):
        pass


CONFIG_SCHEMA_VERSION = 1
DEFAULT_SITE_NAME = "Paper Blog"
DEFAULT_COLOR = "#D97757"
DEFAULT_INDEX = "# Paper Blog\n\n写简单的文字，做干净的博客。\n"
DEFAULT_ICON_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="32" height="32"><rect width="100" height="100" rx="22" fill="#F9F9FB"/><path d="M 32 25 L 56 25 C 68 25 74 33 74 44 C 74 55 68 63 56 63 L 44 63 L 44 75" fill="none" stroke="currentColor" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/><path d="M 44 37 L 55 37 C 62 37 65 40 65 44 C 65 48 62 51 55 51 Z" fill="none" stroke="currentColor" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/><line x1="32" y1="25" x2="32" y2="75" stroke="currentColor" stroke-width="6" stroke-linecap="round"/></svg>'
_SAFE_SLUG = re.compile(r"[^\w\-\u4e00-\u9fff]+", re.UNICODE)
_BOOLS = {"true": True, "false": False, "yes": True, "no": False}


class ConfigError(RuntimeError):
    """A configuration file exists but cannot safely be used."""


@dataclass
class PaperConfig:
    posts_dir: Path
    site_dir: Path
    git_remote: str = ""
    editor: str = "default"
    deploy: str = "auto"
    site_name: str = DEFAULT_SITE_NAME
    site_url: str = ""
    color: str = DEFAULT_COLOR
    icon: str = DEFAULT_ICON_SVG
    schema_version: int = CONFIG_SCHEMA_VERSION
    config_path: Path | None = field(default=None, repr=False, compare=False)

    @property
    def output_dir(self) -> Path:
        return self.site_dir / "out"

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("config_path", None)
        data["postsDir"] = str(data.pop("posts_dir"))
        data["siteDir"] = str(data.pop("site_dir"))
        data["gitRemote"] = data.pop("git_remote")
        data["siteName"] = data.pop("site_name")
        data["siteUrl"] = data.pop("site_url")
        data["schemaVersion"] = data.pop("schema_version")
        return data


@dataclass(frozen=True)
class Post:
    slug: str
    title: str
    date: str
    published: bool
    description: str
    content: str
    source_path: Path
    modified_time: float
    modified_date: str


@dataclass(frozen=True)
class GitRemoteInfo:
    """Parsed GitHub repository identity stored in canonical SSH form."""

    ssh_url: str
    owner: str
    repo: str

    @property
    def is_user_pages(self) -> bool:
        return self.repo.lower() == f"{self.owner.lower()}.github.io"

    @property
    def pages_url(self) -> str:
        if self.is_user_pages:
            return f"https://{self.owner}.github.io"
        return f"https://{self.owner}.github.io/{self.repo}"

    @property
    def pages_settings_url(self) -> str:
        return f"https://github.com/{self.owner}/{self.repo}/settings/pages"


def paper_home() -> Path:
    return Path(os.environ.get("PAPER_HOME", Path.home() / ".paper")).expanduser()


def config_path() -> Path:
    return paper_home() / "config.json"


def _legacy_config_paths() -> Iterable[Path]:
    if "PAPER_HOME" in os.environ:
        return
    yield Path.home() / ".paper-config.json"
    yield Path.cwd() / ".paper-config.json"


def _default_config(posts_dir: Path | None = None) -> PaperConfig:
    return PaperConfig(
        posts_dir=(posts_dir or (Path.home() / "Documents" / "Paper" / "posts")).expanduser().resolve(),
        site_dir=(paper_home() / "site").resolve(),
        config_path=config_path(),
    )


def _path_value(value: Any, fallback: Path) -> Path:
    if not value:
        return fallback
    return Path(str(value)).expanduser().resolve()


def load_config(*, create: bool = False) -> PaperConfig:
    """Load the single-site config, migrating the old flat config once."""

    target = config_path()
    source = target if target.exists() else next(
        (candidate for candidate in _legacy_config_paths() if candidate.exists()), None
    )
    loaded: dict[str, Any] = {}
    if source:
        try:
            loaded = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raise ConfigError(f"Paper 配置无法读取或不是有效 JSON：{source}") from None

    defaults = _default_config()
    result = PaperConfig(
        posts_dir=_path_value(loaded.get("postsDir") or loaded.get("posts_dir"), defaults.posts_dir),
        site_dir=_path_value(loaded.get("siteDir") or loaded.get("repoDir") or loaded.get("site_dir"), defaults.site_dir),
        git_remote=str(loaded.get("gitRemote") or loaded.get("git_remote") or ""),
        editor=str(loaded.get("editor") or "default"),
        deploy=str(loaded.get("deploy") or "auto"),
        site_name=str(loaded.get("siteName") or loaded.get("site_name") or DEFAULT_SITE_NAME),
        site_url=str(loaded.get("siteUrl") or loaded.get("site_url") or ""),
        color=str(loaded.get("color") or DEFAULT_COLOR),
        icon=str(loaded.get("icon") or DEFAULT_ICON_SVG),
        schema_version=CONFIG_SCHEMA_VERSION,
        config_path=target,
    )
    if create and source and source != target:
        save_config(result)
        backup = source.with_suffix(source.suffix + ".bak")
        try:
            shutil.copy2(source, backup)
        except OSError:
            pass
    elif create and not target.exists():
        save_config(result)
    return result


def save_config(config: PaperConfig | None = None, **changes: Any) -> PaperConfig:
    current = config or load_config()
    values = {
        "posts_dir": current.posts_dir,
        "site_dir": current.site_dir,
        "git_remote": current.git_remote,
        "editor": current.editor,
        "deploy": current.deploy,
        "site_name": current.site_name,
        "site_url": current.site_url,
        "color": current.color,
        "icon": current.icon,
        "schema_version": CONFIG_SCHEMA_VERSION,
        "config_path": config_path(),
    }
    aliases = {
        "postsDir": "posts_dir", "siteDir": "site_dir", "repoDir": "site_dir",
        "gitRemote": "git_remote", "siteName": "site_name", "siteUrl": "site_url",
        "schemaVersion": "schema_version",
    }
    for key, value in changes.items():
        values[aliases.get(key, key)] = value
    result = PaperConfig(
        posts_dir=Path(values["posts_dir"]).expanduser().resolve(),
        site_dir=Path(values["site_dir"]).expanduser().resolve(),
        git_remote=str(values["git_remote"]),
        editor=str(values["editor"]),
        deploy=str(values["deploy"]),
        site_name=str(values["site_name"]),
        site_url=str(values["site_url"]),
        color=str(values["color"]),
        icon=str(values["icon"]),
        schema_version=CONFIG_SCHEMA_VERSION,
        config_path=config_path(),
    )
    target = result.config_path
    assert target is not None
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result.to_json(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def _parse_scalar(value: str) -> Any:
    stripped = value.strip().strip('"\'')
    lower = stripped.lower()
    if lower in _BOOLS:
        return _BOOLS[lower]
    return stripped


def parse_frontmatter(source: str) -> tuple[dict[str, Any], str]:
    """Parse the deliberately small, documented Paper frontmatter profile."""

    if not source.startswith("---"):
        return {"published": False}, source.strip()
    lines = source.splitlines()
    if not lines or lines[0].strip() != "---":
        return {"published": False}, source.strip()
    try:
        closing = next(index for index in range(1, len(lines)) if lines[index].strip() == "---")
    except StopIteration:
        return {"published": False}, source.strip()
    metadata: dict[str, Any] = {"published": False}
    for line in lines[1:closing]:
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = _parse_scalar(value)
    body = "\n".join(lines[closing + 1:]).strip()
    return metadata, body


_formatter = HtmlFormatter(nowrap=True, style="default") if HtmlFormatter else None


def _highlight(code: str, language: str, _attrs: str) -> str:
    if not language or get_lexer_by_name is None or pygments_highlight is None or _formatter is None:
        return html.escape(code)
    try:
        lexer = get_lexer_by_name(language)
    except ClassNotFound:
        return html.escape(code)
    highlighted = pygments_highlight(code, lexer, _formatter)
    return f'<span class="syntax-highlight">{highlighted}</span>'


def _task_list_transform(rendered: str) -> str:
    pattern = re.compile(r"<li>\[([ xX])\]\s*")

    def replace(match: re.Match[str]) -> str:
        checked = " checked" if match.group(1).lower() == "x" else ""
        return f'<li class="task-list-item"><input type="checkbox" disabled{checked}> '

    return pattern.sub(replace, rendered)


def _preserve_top_level_blank_lines(state: Any) -> None:
    """Insert up to two visible spacer tokens between top-level source blocks."""

    if Token is None:
        return
    blocks = [
        (index, token)
        for index, token in enumerate(state.tokens)
        if token.level == 0 and token.map is not None and token.nesting != -1
    ]
    inserts: list[tuple[int, list[Any]]] = []
    for (_previous_index, previous), (current_index, current) in zip(blocks, blocks[1:]):
        blank_lines = max(0, current.map[0] - previous.map[1])
        spacers = []
        for _ in range(min(blank_lines, 2)):
            spacer = Token("html_block", "", 0)
            spacer.content = '<div class="markdown-blank-line" aria-hidden="true"></div>\n'
            spacers.append(spacer)
        if spacers:
            inserts.append((current_index, spacers))
    for index, spacers in reversed(inserts):
        state.tokens[index:index] = spacers


_IMAGE_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
    ".bmp",
    ".avif",
    ".ico",
    ".tif",
    ".tiff",
}


def _copy_local_image(source: Path, posts_dir: Path) -> str | None:
    """Copy one validated image source into Paper's managed assets directory."""

    if source.is_symlink():
        return None
    source = source.resolve()
    if not source.is_file() or source.suffix.lower() not in _IMAGE_SUFFIXES:
        return None
    assets_dir = posts_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    target = assets_dir / source.name
    if target.exists():
        try:
            if target.read_bytes() == source.read_bytes():
                return target.name
        except OSError:
            return None
        digest = hashlib.sha256(source.read_bytes()).hexdigest()[:8]
        target = assets_dir / f"{source.stem}-{digest}{source.suffix}"
    shutil.copy2(source, target)
    return target.name


def _import_local_image(src: str, posts_dir: Path) -> str | None:
    """Copy a local image referenced in Markdown into posts/assets and return its new relative src.

    Returns None when the path is not a readable regular image file, so the original
    reference is left untouched rather than failing the whole build.
    """

    clean = unquote(src.split("?")[0].split("#")[0])
    if not clean:
        return None
    candidate = Path(clean)
    base = posts_dir.resolve()
    source = candidate if candidate.is_absolute() else base / candidate
    return _copy_local_image(source, posts_dir)


def _import_obsidian_image(src: str, posts_dir: Path) -> str | None:
    """Resolve an Obsidian attachment strictly within the linked posts directory."""

    clean = unquote(src.split("?", 1)[0].split("#", 1)[0])
    candidate = Path(clean)
    base = posts_dir.resolve()
    if not clean or candidate.is_absolute() or ".." in candidate.parts:
        return None
    if candidate.parent == Path("."):
        content_matches = [
            path for path in base.rglob(candidate.name)
            if "assets" not in path.relative_to(base).parts
        ]
        matches = content_matches
        if not matches:
            assets = base / "assets"
            matches = list(assets.rglob(candidate.name)) if assets.is_dir() else []
        if len(matches) > 1:
            locations = "、".join(str(path.relative_to(base)) for path in matches)
            raise ValueError(f"Obsidian 图片名称不唯一：{candidate.name}（{locations}）")
        if not matches:
            return None
        source = matches[0]
    else:
        source = base / candidate
    current = base
    for part in candidate.parts if candidate.parent != Path(".") else source.relative_to(base).parts:
        current = current / part
        if current.is_symlink():
            return None
    try:
        source.resolve().relative_to(base)
    except ValueError:
        return None
    return _copy_local_image(source, posts_dir)


def _obsidian_image_rule(state: Any, silent: bool) -> bool:
    """Parse Obsidian image embeds while leaving note embeds as plain text."""

    start = state.pos
    if not state.src.startswith("![[", start):
        return False
    end = state.src.find("]]", start + 3)
    if end < 0 or "\n" in state.src[start:end]:
        return False
    inner = state.src[start + 3:end]
    target, separator, modifier = inner.partition("|")
    target = target.strip()
    if Path(target.split("#", 1)[0]).suffix.lower() not in _IMAGE_SUFFIXES:
        return False
    if not silent:
        token = state.push("image", "img", 0)
        token.attrs = {"src": target, "alt": ""}
        label = modifier.strip() if separator else Path(target).name
        dimensions = re.fullmatch(r"([1-9]\d{0,4})(?:x([1-9]\d{0,4}))?", label)
        if dimensions:
            token.attrSet("width", dimensions.group(1))
            if dimensions.group(2):
                token.attrSet("height", dimensions.group(2))
                token.attrSet(
                    "style", f"aspect-ratio: {dimensions.group(1)} / {dimensions.group(2)}"
                )
            label = Path(target).name
        alt = Token("text", "", 0)
        alt.content = label
        token.children = [alt]
        token.content = label
        token.meta["paper_obsidian_image"] = True
    state.pos = end + 2
    return True


def _render_missing_image(
    _renderer: Any, tokens: list[Any], index: int, _options: Any, _env: Any
) -> str:
    filename = html.escape(tokens[index].content)
    return f'<span class="missing-image" role="img">图片未找到：{filename}</span>'


def render_markdown(source: str, *, asset_base: str = "/assets/", posts_dir: Path | None = None) -> str:
    """Render the Paper Markdown Profile with raw HTML disabled by default.

    When posts_dir is given, local image references (absolute or relative paths)
    are copied into posts/assets so the built site can serve them.
    """

    if MarkdownIt is None:
        raise RuntimeError("Paper 的 Markdown 运行依赖未安装；请重新安装 Paper，不要手动运行 pip。")
    parser = MarkdownIt("js-default", {"highlight": _highlight, "breaks": True})
    parser.enable(["table", "strikethrough"])
    parser.core.ruler.after("block", "paper_blank_lines", _preserve_top_level_blank_lines)
    parser.inline.ruler.before("image", "paper_obsidian_image", _obsidian_image_rule)
    parser.add_render_rule("paper_missing_image", _render_missing_image)

    normalized_asset_base = "/" + asset_base.strip("/") + "/"
    import_dir = posts_dir.resolve() if posts_dir is not None else None

    def decorate_links(state: Any) -> None:
        for token in state.tokens:
            for child in token.children or []:
                if child.type == "image":
                    src = child.attrGet("src") or ""
                    local_src = src.removeprefix("./")
                    is_obsidian = bool(child.meta.get("paper_obsidian_image"))
                    if src.startswith(("http://", "https://")):
                        child.attrSet("referrerpolicy", "no-referrer")
                    elif is_obsidian and import_dir is not None:
                        imported = _import_obsidian_image(local_src, import_dir)
                        if imported:
                            child.attrSet("src", normalized_asset_base + imported)
                        else:
                            child.type = "paper_missing_image"
                            child.tag = "span"
                            child.content = unquote(local_src.split("#", 1)[0])
                            child.attrs = {}
                            child.children = None
                            continue
                    elif local_src.startswith("assets/"):
                        child.attrSet("src", normalized_asset_base + local_src.removeprefix("assets/"))
                    elif import_dir is not None and not src.startswith(("//", "data:")):
                        imported = _import_local_image(local_src, import_dir)
                        if imported:
                            child.attrSet("src", normalized_asset_base + imported)
                    child.attrSet("loading", "lazy")
                    child.attrSet("decoding", "async")
                elif child.type == "link_open":
                    href = child.attrGet("href") or ""
                    if href.startswith(("http://", "https://")):
                        child.attrSet("target", "_blank")
                        child.attrSet("rel", "noopener noreferrer")

    parser.core.ruler.after("inline", "paper_links_and_images", decorate_links)
    rendered = parser.render(source)
    return _task_list_transform(rendered)


def _normalize_date(value: Any, fallback: str) -> str:
    if isinstance(value, _dt.date):
        return value.isoformat()
    text = str(value or "")
    return text[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", text) else fallback


def _slug_for(path: Path) -> str:
    slug = _SAFE_SLUG.sub("-", path.stem.lower()).strip("-")
    return slug or "post"


def discover_posts(posts_dir: Path, *, include_drafts: bool = True) -> list[Post]:
    posts_dir = posts_dir.expanduser().resolve()
    if not posts_dir.exists():
        return []
    result: list[Post] = []
    seen_slugs: dict[str, Path] = {}
    for source_path in sorted(posts_dir.glob("*.md")):
        if source_path.name.lower() in {"index.md", "readme.md"}:
            continue
        metadata, body = parse_frontmatter(source_path.read_text(encoding="utf-8"))
        modified_time = source_path.stat().st_mtime
        modified_date = _dt.date.fromtimestamp(modified_time).isoformat()
        fallback_date = modified_date
        slug = _slug_for(source_path)
        if slug in seen_slugs:
            raise ValueError(
                f"文章 slug 冲突：{seen_slugs[slug].name} 与 {source_path.name} 都生成了 {slug}"
            )
        seen_slugs[slug] = source_path
        post = Post(
            slug=slug,
            title=str(metadata.get("title") or source_path.stem),
            date=_normalize_date(metadata.get("date"), fallback_date),
            published=bool(metadata.get("published", False)),
            description=str(metadata.get("description") or ""),
            content=body,
            source_path=source_path,
            modified_time=modified_time,
            modified_date=modified_date,
        )
        if include_drafts or post.published:
            result.append(post)
    return sorted(result, key=lambda post: (post.modified_time, post.slug), reverse=True)


def set_post_published(source_path: Path, published: bool) -> None:
    """Update only the documented published flag while preserving the body."""

    source = source_path.read_text(encoding="utf-8")
    metadata, body = parse_frontmatter(source)
    metadata["published"] = published
    lines = ["---"]
    for key, value in metadata.items():
        if isinstance(value, bool):
            rendered = "true" if value else "false"
        else:
            rendered = str(value)
            if re.search(r"[:#\n]", rendered):
                rendered = json.dumps(rendered, ensure_ascii=False)
        lines.append(f"{key}: {rendered}")
    lines.extend(["---", "", body, ""])
    source_path.write_text("\n".join(lines), encoding="utf-8")


def normalize_git_remote(value: str) -> GitRemoteInfo | None:
    """Normalize common GitHub remote forms to one canonical SSH URL.

    Accepts SSH (git@github.com:owner/repo[.git]), HTTPS/HTTP
    (https://github.com/owner/repo[.git]), a bare github.com/owner/repo,
    or owner/repo shorthand. Returns None for anything that is not a plain
    GitHub repository address, so callers can reject it safely.
    """

    raw = (value or "").strip()
    if not raw:
        return None
    for prefix in (
        "git@github.com:",
        "ssh://git@github.com/",
        "https://github.com/",
        "http://github.com/",
        "github.com/",
    ):
        if raw.startswith(prefix):
            raw = raw[len(prefix):]
            break
    else:
        if "://" in raw or "git@" in raw or ":" in raw:
            return None
    path = raw.removesuffix(".git").strip("/")
    if not path or any(char.isspace() for char in path):
        return None
    if "?" in path or "#" in path:
        return None
    parts = path.split("/")
    if len(parts) != 2 or not all(parts):
        return None
    owner, repo = parts
    return GitRemoteInfo(
        ssh_url=f"git@github.com:{owner}/{repo}.git",
        owner=owner,
        repo=repo,
    )


def _base_path(config: PaperConfig) -> str:
    raw = config.site_url.strip()
    if not raw and config.git_remote:
        info = normalize_git_remote(config.git_remote)
        if info:
            return "" if info.is_user_pages else f"/{info.repo}"
        return ""
    parsed = urlparse(raw)
    return parsed.path.rstrip("/") if parsed.scheme else raw.rstrip("/")


def _site_root(config: PaperConfig) -> str:
    """Return the absolute public origin plus GitHub Pages base path when known."""

    raw = config.site_url.strip().rstrip("/")
    if raw:
        parsed = urlparse(raw)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"
        return ""
    remote = config.git_remote.strip()
    if remote:
        info = normalize_git_remote(remote)
        if info:
            return info.pages_url
    return ""


def _href(config: PaperConfig, path: str) -> str:
    return f"{_base_path(config)}{path}" or "/"


def _absolute_href(config: PaperConfig, path: str) -> str:
    root = _site_root(config)
    return f"{root}{path}" if root else _href(config, path)


def _css(config: PaperConfig) -> str:
    color = config.color if re.match(r"^#[0-9a-fA-F]{6}$", config.color) else DEFAULT_COLOR
    legacy_css = """
:root {
  --primary: __PAPER_COLOR__;
  --bg: #ffffff;
  --text: #111827;
  --subtext: #6b7280;
  --link: #111827;
  --link-underline: #374151;
  --border: #e5e7eb;
  --code-bg: #f9fafb;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #09090b;
    --text: #e4e4e7;
    --subtext: #71717a;
    --link: #e4e4e7;
    --link-underline: #d1d5db;
    --border: #27272a;
    --code-bg: #18181b;
  }
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  background-color: var(--bg);
  color: var(--text);
  line-height: 1.7;
  letter-spacing: 0.02em;
  padding: 4rem 2rem;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  -webkit-font-smoothing: antialiased;
}
.container { flex: 1; max-width: 60ch; margin: 0 auto; width: 100%; }
header { margin-bottom: 2.25rem; }
h1 { font-size: 1.5rem; font-weight: 500; letter-spacing: -0.02em; margin-bottom: 1.25rem; color: var(--text); line-height: 1.3; position: relative; }
h2 { font-size: 0.875rem; font-weight: 500; letter-spacing: 0.05em; text-transform: uppercase; margin-top: 2.25rem; margin-bottom: 1rem; color: var(--subtext); }
h3 { font-size: 1.1rem; font-weight: 500; margin-top: 1.75rem; margin-bottom: 0.75rem; color: var(--text); }
p { margin-top: 1.25rem; margin-bottom: 1.25rem; color: var(--text); }
a { color: var(--text); cursor: pointer; text-decoration: underline; text-decoration-color: var(--link-underline); text-underline-offset: 3px; transition: color 0.15s ease, text-decoration-color 0.15s ease; }
a:hover { color: var(--primary); text-decoration-color: var(--primary); }
ul, ol { margin-left: 1.25rem; margin-top: 1rem; margin-bottom: 1.25rem; }
li { margin-bottom: 0.4rem; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; font-size: 0.875em; padding: 0.2em 0.4em; border-radius: 4px; background-color: var(--code-bg); }
pre { background-color: var(--code-bg); padding: 1rem; border-radius: 6px; overflow-x: auto; margin-top: 1.25rem; margin-bottom: 1.25rem; border: 1px solid var(--border); }
pre code { padding: 0; background-color: transparent; }
blockquote { border-left: 2px solid var(--primary); padding-left: 1rem; color: var(--subtext); font-style: italic; margin-top: 1.25rem; margin-bottom: 1.25rem; }
.post-list { display: flex; flex-direction: column; gap: 0.6rem; }
.post-item { display: flex; justify-content: space-between; align-items: baseline; }
.post-title { font-weight: 500; text-decoration: none; }
.post-item .post-date { font-size: 0.875rem; color: var(--subtext); font-variant-numeric: tabular-nums; margin-left: 1rem; }
.post-date { font-size: 0.875rem; color: var(--subtext); font-variant-numeric: tabular-nums; }
footer { margin-top: 4rem; text-align: center; }
.footer-brand { font-family: Georgia, Cambria, Baskerville, "Times New Roman", serif; font-style: italic; font-size: 0.725rem; letter-spacing: 0.04em; color: var(--text); text-decoration: none; opacity: 0.12; transition: opacity 0.2s ease, color 0.2s ease; }
.footer-brand:hover { opacity: 0.5; color: var(--primary); }
.back-icon { position: absolute; left: -2rem; top: 0.41rem; width: 18px; height: 18px; display: flex; align-items: center; justify-content: center; color: var(--subtext); text-decoration: none; }
.back-icon:hover { color: var(--primary); }

/* Markdown Profile additions: syntax support without changing the site shell. */
.markdown { font-size: 1rem; line-height: 1.5; }
.markdown > * + * { margin-top: 1.25rem; }
.markdown > .markdown-blank-line { height: 1.5em; margin-top: 0; }
.markdown > .markdown-blank-line + * { margin-top: 0; }
.markdown h1, .markdown h2, .markdown h3, .markdown h4, .markdown h5, .markdown h6 { font-weight: 650; line-height: 1.35; letter-spacing: -0.02em; color: var(--text); text-transform: none; }
.markdown h1 { font-size: 1.75rem; margin-top: 2.5rem; }
.markdown h2 { font-size: 1.375rem; margin-top: 2.75rem; }
.markdown h3 { font-size: 1.125rem; margin-top: 2rem; }
.markdown h4 { font-size: 1rem; font-weight: 600; }
.markdown h1:first-child, .markdown h2:first-child, .markdown h3:first-child, .markdown h4:first-child { margin-top: 0; }
.markdown p { margin: 0; }
.markdown strong { font-weight: 650; }
.markdown ul, .markdown ol { margin-top: 0; margin-bottom: 0; padding-left: 0.25rem; }
.markdown li { margin: 0.25rem 0; }
.markdown li > p { margin: 0; }
.markdown li > ul, .markdown li > ol { margin-top: 0.25rem; }
.markdown a { text-underline-offset: 0.2em; text-decoration-thickness: 1px; }
.markdown pre { position: relative; margin: 0; font-size: 0.875em; line-height: 1.7; }
.markdown pre code { display: block; padding: 0; background-color: transparent; font-size: inherit; }
.markdown blockquote { margin: 0; }
.markdown blockquote blockquote { border-left-color: var(--border); }
.markdown table { width: 100%; border-collapse: collapse; border: 1px solid var(--border); font-size: 0.875rem; }
.markdown th, .markdown td { border: 1px solid var(--border); padding: 0.5rem 0.75rem; text-align: left; vertical-align: top; }
.markdown th { background-color: var(--code-bg); font-weight: 600; color: var(--text); }
.markdown tbody tr:nth-child(even) td { background-color: var(--code-bg); }
.markdown hr { border: 0; border-top: 1px solid var(--border); margin: 2.5rem 0; }
.markdown :not(pre) > code { white-space: nowrap; }
.markdown img { display: block; max-width: 100%; height: auto; margin: 1.5em auto; border: 1px solid var(--border); border-radius: 8px; }
.markdown .missing-image { display: inline-block; padding: 0.5rem 0.75rem; border: 1px dashed var(--border); border-radius: 6px; color: var(--subtext); background: var(--code-bg); font-size: 0.875rem; }
.task-list-item { list-style: none; margin-left: -1.25rem; }
.task-list-item input { margin-right: 0.4rem; accent-color: var(--primary); }
@media (max-width: 640px) { body { padding: 2.5rem 1.5rem; } .post-item { align-items: flex-start; gap: 0.5rem; } .back-icon { left: -1.5rem; } }
@media (min-width: 48rem) { .home-container { margin-top: 4rem; } }
"""
    pygments_css = _formatter.get_style_defs(".syntax-highlight") if _formatter else ""
    pygments_css += "\n.syntax-highlight { background: transparent !important; }"
    return legacy_css.replace("__PAPER_COLOR__", color) + "\n" + pygments_css


def _github_url(config: PaperConfig) -> str:
    remote = config.git_remote.strip()
    if not remote:
        return "https://github.com"
    if remote.startswith(("http://", "https://")):
        return remote.removesuffix(".git")
    info = normalize_git_remote(remote)
    if info:
        return f"https://github.com/{info.owner}/{info.repo}"
    return "https://github.com"


def _favicon_href(config: PaperConfig) -> str:
    icon = config.icon.strip() or DEFAULT_ICON_SVG
    lowered = icon.lower()
    if "<svg" in lowered:
        return "data:image/svg+xml;utf8," + quote(icon)
    if lowered.startswith("data:image/"):
        return icon
    local_icon = icon.removeprefix("./")
    if local_icon.startswith("assets/"):
        return _href(config, "/assets/" + local_icon.removeprefix("assets/"))
    return icon


def _live_reload_script() -> str:
    return """<script>(()=>{let v=null;setInterval(async()=>{try{const r=await fetch('/.paper-revision',{cache:'no-store'});const n=await r.text();if(v===null){v=n}else if(n!==v){location.reload()}}catch(_e){}},1000)})();</script>"""


def _layout(config: PaperConfig, title: str, body: str, *, draft: bool = False, live_reload: bool = False, home: bool = False) -> str:
    marker = '<p><strong>草稿预览</strong></p>' if draft else ""
    script = _live_reload_script() if live_reload else ""
    favicon = html.escape(_favicon_href(config), quote=True)
    page_title = config.site_name if title == config.site_name else f"{title} | {config.site_name}"
    container_class = "container home-container" if home else "container"
    return f"""<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><meta name=\"referrer\" content=\"strict-origin-when-cross-origin\"><meta name=\"theme-color\" content=\"{html.escape(config.color, quote=True)}\"><link rel=\"icon\" href=\"{favicon}\"><title>{html.escape(page_title)}</title><style>{_css(config)}</style></head><body><div class=\"{container_class}\">{marker}{body}</div><footer><a href=\"{html.escape(_github_url(config), quote=True)}\" target=\"_blank\" rel=\"noopener noreferrer\" class=\"footer-brand\">Paper Blog</a></footer>{script}</body></html>"""


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _copy_referenced_assets(build_dir: Path, posts_dir: Path, asset_base: str) -> None:
    """Copy only assets referenced by generated HTML into the build output."""

    assets = posts_dir / "assets"
    if not assets.is_dir():
        return
    symlinks = [path for path in assets.rglob("*") if path.is_symlink()]
    if symlinks:
        raise ValueError(f"assets 不允许包含符号链接：{symlinks[0]}")
    pattern = re.compile(r'(?:src|href)="' + re.escape(asset_base) + r'([^"?#]+)')
    referenced: set[Path] = set()
    for page in build_dir.rglob("*.html"):
        rendered = page.read_text(encoding="utf-8")
        for match in pattern.finditer(rendered):
            relative = Path(unquote(html.unescape(match.group(1))))
            if relative.is_absolute() or ".." in relative.parts:
                continue
            referenced.add(relative)
    for relative in sorted(referenced, key=str):
        source = assets / relative
        if not source.is_file():
            continue
        target = build_dir / "assets" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def build_site(config: PaperConfig, *, include_drafts: bool = False, live_reload: bool = False) -> Path:
    """Build into a temporary tree, then atomically replace only generated output."""

    config.site_dir.mkdir(parents=True, exist_ok=True)
    posts_dir = config.posts_dir
    posts_dir.mkdir(parents=True, exist_ok=True)
    posts = discover_posts(posts_dir, include_drafts=include_drafts)
    published = [post for post in posts if post.published]
    index_path = posts_dir / "index.md"
    index_source = index_path.read_text(encoding="utf-8") if index_path.exists() else DEFAULT_INDEX
    _, index_body = parse_frontmatter(index_source)
    temp_parent = Path(tempfile.mkdtemp(prefix="paper-build-", dir=config.site_dir))
    try:
        listing = ["<main><h2>Writing</h2><div class=\"post-list\">"]
        for post in posts:
            if not post.published and not include_drafts:
                continue
            marker = "（草稿）" if not post.published else ""
            listing.append(
                f'<div class="post-item"><a class="post-title" href="{_href(config, f"/posts/{post.slug}/")}">'
                f'{html.escape(post.title)}{marker}</a><time class="post-date">{html.escape(post.date)}</time></div>'
            )
        listing.append("</div></main>")
        asset_base = _href(config, "/assets/")
        index_html = f'<header><div class="markdown">{render_markdown(index_body, asset_base=asset_base, posts_dir=posts_dir)}</div></header>' + "\n" + "\n".join(listing)
        _write(temp_parent / "index.html", _layout(config, config.site_name, index_html, draft=False, live_reload=live_reload, home=True))
        _write(temp_parent / "404.html", _layout(config, "Not found", "<main><h1>Not found</h1></main>", live_reload=live_reload))
        for post in posts:
            if not post.published and not include_drafts:
                continue
            back_icon = '<a href="javascript:history.back()" class="back-icon" title="返回上一页" aria-label="返回上一页"><svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M19 12H5"/><path d="M12 19l-7-7 7-7"/></svg></a>'
            article = f'<main><article><h1>{back_icon}{html.escape(post.title)}</h1><p class="post-date">{html.escape(post.date)}</p>'
            article += f'<div class="markdown">{render_markdown(post.content, asset_base=asset_base, posts_dir=posts_dir)}</div></article></main>'
            _write(temp_parent / "posts" / post.slug / "index.html", _layout(config, post.title, article, draft=not post.published, live_reload=live_reload))

        _copy_referenced_assets(temp_parent, posts_dir, asset_base)

        rss_items = []
        sitemap_urls = [_absolute_href(config, "/")]
        for post in published:
            url = _absolute_href(config, f"/posts/{post.slug}/")
            rss_items.append(f"<item><title>{html.escape(post.title)}</title><link>{html.escape(url)}</link><pubDate>{html.escape(post.date)}</pubDate><description>{html.escape(post.description)}</description></item>")
            sitemap_urls.append(url)
        rss = "<?xml version=\"1.0\" encoding=\"UTF-8\"?><rss version=\"2.0\"><channel><title>" + html.escape(config.site_name) + "</title>" + "".join(rss_items) + "</channel></rss>"
        _write(temp_parent / "rss.xml", rss)
        sitemap = "<?xml version=\"1.0\" encoding=\"UTF-8\"?><urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">" + "".join(f"<url><loc>{html.escape(url)}</loc></url>" for url in sitemap_urls) + "</urlset>"
        _write(temp_parent / "sitemap.xml", sitemap)
        output = config.output_dir
        backup = config.site_dir / ".paper-out-backup"
        if backup.exists():
            shutil.rmtree(backup)
        try:
            if output.exists():
                output.rename(backup)
            temp_parent.rename(output)
            if backup.exists():
                shutil.rmtree(backup)
            return output
        except Exception:
            if output.exists():
                shutil.rmtree(output, ignore_errors=True)
            if backup.exists():
                backup.rename(output)
            raise
    except Exception:
        shutil.rmtree(temp_parent, ignore_errors=True)
        raise
