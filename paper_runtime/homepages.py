"""Language tags and progressive browser controls for translated homepages."""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass

from .i18n import t


HOMEPAGE_LANGUAGES = {
    "en": "English",
    "zh-CN": "简体中文",
    "zh-TW": "繁體中文",
    "ja": "日本語",
    "ko": "한국어",
    "fr": "Français",
    "de": "Deutsch",
    "es": "Español",
    "pt": "Português",
    "pt-BR": "Português (Brasil)",
    "it": "Italiano",
    "ru": "Русский",
    "ar": "العربية",
    "hi": "हिन्दी",
    "nl": "Nederlands",
    "tr": "Türkçe",
    "vi": "Tiếng Việt",
    "th": "ไทย",
    "id": "Bahasa Indonesia",
    "uk": "Українська",
}


def normalize_homepage_language(value: object) -> str:
    """Accept common BCP 47 language/script/region tags and underscore aliases."""

    if not isinstance(value, str):
        raise ValueError(t("homepage_language_invalid", language=value))
    tag = value.strip().replace("_", "-")
    if not re.fullmatch(
        r"[A-Za-z]{2,3}(?:-[A-Za-z]{4})?(?:-(?:[A-Za-z]{2}|[0-9]{3}))?"
        r"(?:-(?:[A-Za-z0-9]{5,8}|[0-9][A-Za-z0-9]{3}))*", tag,
    ):
        raise ValueError(t("homepage_language_invalid", language=value))
    parts = tag.split("-")
    return "-".join(
        part.lower() if index == 0 else
        part.title() if len(part) == 4 and part.isalpha() else
        part.upper() if len(part) == 2 and part.isalpha() else part.lower()
        for index, part in enumerate(parts)
    )


def homepage_language_label(language: str) -> str:
    if language in HOMEPAGE_LANGUAGES:
        return HOMEPAGE_LANGUAGES[language]
    if language == "zh":
        return "中文"
    if language.startswith("zh-Hant"):
        return "繁體中文" if language == "zh-Hant" else f"繁體中文 ({language})"
    if language.startswith("zh-Hans"):
        return "简体中文" if language == "zh-Hans" else f"简体中文 ({language})"
    base = language.split("-")[0]
    label = HOMEPAGE_LANGUAGES.get(base)
    return f"{label} ({language})" if label else language


def homepage_og_locale(language: str) -> str:
    parts = language.split("-")
    region = next((part for part in parts[1:] if len(part) == 2 and part.isalpha()), "")
    defaults = {"en": "US", "zh": "CN", "ja": "JP", "ko": "KR", "fr": "FR", "de": "DE",
                "es": "ES", "pt": "PT", "it": "IT", "ru": "RU", "ar": "SA", "hi": "IN",
                "nl": "NL", "tr": "TR", "vi": "VN", "th": "TH", "id": "ID", "uk": "UA"}
    region = region or ("TW" if "Hant" in parts else defaults.get(parts[0], ""))
    return f"{parts[0]}_{region}" if region else parts[0]


@dataclass(frozen=True)
class HomepageLink:
    choice: str
    language: str
    href: str
    label: str


def homepage_alternates(links: list[HomepageLink], canonical: str) -> str:
    tags = [f'<link rel="canonical" href="{html.escape(canonical, quote=True)}">']
    for link in links:
        language = "x-default" if link.choice == "default" else link.language
        tags.append(f'<link rel="alternate" hreflang="{language}" href="{html.escape(link.href, quote=True)}">')
        if link.choice == "default" and link.language:
            tags.append(f'<link rel="alternate" hreflang="{link.language}" href="{html.escape(link.href, quote=True)}">')
    return "".join(tags)


def homepage_language_menu(links: list[HomepageLink], current: str) -> str:
    if len(links) < 2:
        return ""
    label = html.escape(t("homepage_switch_language"), quote=True)
    items = []
    for link in links:
        href = link.href + ("?lang=default" if link.choice == "default" else "")
        active = ' aria-current="page"' if link.choice == current else ""
        lang = f' lang="{link.language}" hreflang="{link.language}"' if link.language else ""
        name = f"{homepage_language_label(link.language)} · {link.label}" if link.choice == "default" and link.language else link.label
        items.append(f'<a href="{html.escape(href, quote=True)}" data-paper-language="{link.choice}"{lang}{active}>{html.escape(name)}</a>')
    return (
        f'<details class="footer-language"><summary class="footer-language-toggle" title="{label}" aria-label="{label}">'
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true">'
        '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a18 18 0 0 1 0 18 18 18 0 0 1 0-18Z"/></svg>'
        f'</summary><nav class="footer-language-menu" aria-label="{label}">{"".join(items)}</nav></details>'
    )


def homepage_language_bootstrap(links: list[HomepageLink], *, base_path: str, auto: bool) -> str:
    if len(links) < 2:
        return ""
    data = json.dumps({
        "key": "paper-language:" + (base_path or "/"),
        "auto": auto,
        "links": [{"choice": link.choice, "language": link.language, "href": link.href} for link in links],
    }).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return "<script>" + _LANGUAGE_BOOTSTRAP.replace("__SETTINGS__", data) + "</script>"


_LANGUAGE_BOOTSTRAP = """(() => {
  const settings = __SETTINGS__;
  window.paperLanguageSettings = settings;
  const choices = new Map(settings.links.map(link => [link.choice, link]));
  const explicit = new URLSearchParams(location.search).get('lang');
  let preferred = choices.has(explicit) ? explicit : null;
  try {
    if (preferred) localStorage.setItem(settings.key, preferred);
    else preferred = localStorage.getItem(settings.key);
  } catch (_error) {}
  if (!settings.auto) return;
  const normalize = tag => String(tag).replace(/_/g, '-').toLowerCase();
  const available = settings.links.filter(link => link.language);
  const locale = tag => {
    try { return new Intl.Locale(tag).maximize(); } catch (_error) {
      const parts = normalize(tag).split('-');
      const script = parts[0] === 'zh' ? (parts.some(p => ['hant', 'tw', 'hk', 'mo'].includes(p)) ? 'Hant' : 'Hans') : '';
      return {language: parts[0], script, region: ''};
    }
  };
  const match = tag => {
    const normalized = normalize(tag);
    let exact = available.find(link => normalize(link.language) === normalized);
    if (exact) return exact;
    const wanted = locale(normalized);
    const candidates = available.filter(link => {
      const candidate = locale(link.language);
      return candidate.language === wanted.language && (!wanted.script || !candidate.script || candidate.script === wanted.script);
    });
    let parent = normalized;
    while (parent.includes('-')) {
      parent = parent.slice(0, parent.lastIndexOf('-'));
      exact = candidates.find(link => normalize(link.language) === parent);
      if (exact) return exact;
    }
    return candidates.find(link => wanted.region && locale(link.language).region === wanted.region) || candidates[0];
  };
  let target = choices.get(preferred);
  if (!target) {
    const languages = navigator.languages && navigator.languages.length ? navigator.languages : [navigator.language || ''];
    for (const language of languages) {
      target = match(language);
      if (target) break;
    }
  }
  if (target && target.choice !== 'default') {
    const url = new URL(target.href, location.href);
    url.search = location.search;
    url.hash = location.hash;
    location.replace(url.href);
  }
})();"""


def homepage_language_script() -> str:
    return """<script>(() => {
  const menu = document.querySelector('.footer-language');
  const settings = window.paperLanguageSettings;
  if (!menu || !settings) return;
  menu.querySelectorAll('[data-paper-language]').forEach(link => {
    link.addEventListener('click', () => {
      try { localStorage.setItem(settings.key, link.dataset.paperLanguage); } catch (_error) {}
      menu.open = false;
    });
  });
  document.addEventListener('click', event => { if (!menu.contains(event.target)) menu.open = false; });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && menu.open) {
      menu.open = false;
      menu.querySelector('summary').focus();
    }
  });
})();</script>"""


HOMEPAGE_LANGUAGE_CSS = """
.footer-language { position: relative; text-align: start; }
.footer-language-toggle { display: flex; align-items: center; justify-content: center; width: 1.5rem; height: 1.5rem; border-radius: 999px; color: var(--text); opacity: 0.45; cursor: pointer; list-style: none; transition: opacity 0.2s ease, color 0.2s ease; }
.footer-language-toggle::-webkit-details-marker { display: none; }
.footer-language-toggle svg { width: 0.9rem; height: 0.9rem; }
.footer-language-toggle:hover, .footer-language[open] .footer-language-toggle { opacity: 0.8; color: var(--primary); }
.footer-language-toggle:focus-visible { opacity: 0.8; outline: 2px solid var(--primary); outline-offset: 2px; }
.footer-language-menu { position: absolute; bottom: calc(100% + 0.65rem); right: 0; z-index: 10; min-width: 10rem; max-width: min(18rem, calc(100vw - 4rem)); max-height: min(22rem, 60vh); overflow-y: auto; padding: 0.35rem; border: 1px solid var(--border); border-radius: 8px; background: var(--bg); box-shadow: 0 4px 18px #0001; }
.footer-language-menu a { display: block; padding: 0.5rem 0.65rem; border-radius: 4px; font-size: 0.8rem; text-decoration: none; white-space: nowrap; }
.footer-language-menu a:hover, .footer-language-menu a:focus-visible { background: var(--code-bg); color: var(--primary); }
.footer-language-menu a[aria-current="page"] { color: var(--primary); background: var(--code-bg); }
"""
