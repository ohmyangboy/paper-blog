"""Derive the GitHub Pages CNAME from an explicitly configured public URL."""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlparse


GITHUB_PAGES_IPS = ("185.199.108.153", "185.199.109.153", "185.199.110.153", "185.199.111.153")


def normalize_pages_url(value: str) -> str:
    """Accept a bare domain or public Pages URL, rejecting ambiguous bindings."""
    raw = value.strip()
    if not raw:
        return ""
    if "://" not in raw:
        raw = f"https://{raw}"
    try:
        parsed = urlparse(raw)
        host = (parsed.hostname or "").rstrip(".").encode("idna").decode("ascii")
        if parsed.scheme not in {"http", "https"} or parsed.port is not None:
            raise ValueError("Invalid public URL")
    except (ValueError, UnicodeError) as error:
        raise ValueError("Invalid public URL") from error
    if parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment:
        raise ValueError("Invalid public URL")
    label = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    if len(host) > 253 or not re.fullmatch(rf"{label}(?:\.{label})+", host):
        raise ValueError("Invalid public domain")
    normalized = f"{parsed.scheme}://{host}{parsed.path.rstrip('/')}"
    if host.endswith(".github.io"):
        if "//" in parsed.path or any(part in {".", ".."} for part in parsed.path.split("/")):
            raise ValueError("Invalid Pages path")
        return normalized
    if custom_domain(normalized) is None or parsed.path not in {"", "/"}:
        raise ValueError("Custom domains must use the site root")
    return normalized


def dns_records(domain: str, owner: str, zone: str) -> list[tuple[str, str, str]]:
    """Use the user's DNS zone instead of guessing public suffix boundaries."""
    zone_url = normalize_pages_url(zone)
    normalized_zone = custom_domain(zone_url)
    if normalized_zone is None or (domain != normalized_zone and not domain.endswith(f".{normalized_zone}")):
        raise ValueError("The DNS zone must contain the configured domain")
    if domain == normalized_zone:
        return [("@", "A", address) for address in GITHUB_PAGES_IPS] + [("www", "CNAME", f"{owner}.github.io")]
    host = domain[: -len(normalized_zone) - 1]
    return [(host, "CNAME", f"{owner}.github.io")]


def custom_domain(site_url: str) -> str | None:
    try:
        parsed = urlparse(site_url.strip())
        domain = (parsed.hostname or "").rstrip(".").encode("idna").decode("ascii")
        if parsed.scheme not in {"http", "https"} or parsed.port is not None:
            return None
    except (ValueError, UnicodeError):
        return None
    if parsed.username is not None or parsed.password is not None:
        return None
    label = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    if len(domain) > 253 or not re.fullmatch(rf"{label}(?:\.{label})+", domain):
        return None
    if domain == "github.io" or domain.endswith((".github.io", ".localhost")):
        return None
    try:
        ipaddress.ip_address(domain)
    except ValueError:
        return domain
    return None
