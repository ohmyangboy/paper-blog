"""Paper's single Python runtime.

The public surface intentionally stays small so the CLI, tests, and Homebrew
wrapper all use the same build graph.
"""

from .core import (
    ConfigError,
    PaperConfig,
    Post,
    build_site,
    discover_posts,
    load_config,
    load_local_config,
    parse_frontmatter,
    render_markdown,
    save_config,
    set_post_published,
)
from .i18n import (
    LANGUAGE_LABELS,
    SUPPORTED_LANGUAGES,
    get_current_language,
    normalize_locale,
    resolve_language,
    set_current_language,
    t,
)

__all__ = [
    "PaperConfig",
    "ConfigError",
    "Post",
    "build_site",
    "discover_posts",
    "load_config",
    "load_local_config",
    "parse_frontmatter",
    "render_markdown",
    "save_config",
    "set_post_published",
    "LANGUAGE_LABELS",
    "SUPPORTED_LANGUAGES",
    "get_current_language",
    "normalize_locale",
    "resolve_language",
    "set_current_language",
    "t",
]
