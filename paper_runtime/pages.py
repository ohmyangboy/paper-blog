"""Read GitHub Pages readiness and explicitly enable HTTPS through GitHub CLI."""
from __future__ import annotations

from dataclasses import dataclass
import json
import shutil
import subprocess

from .core import GitRemoteInfo


class PagesError(RuntimeError):
    def __init__(self, kind: str, detail: str = ""):
        self.kind = kind
        self.detail = detail
        super().__init__(detail or kind)


@dataclass(frozen=True)
class PagesStatus:
    cname: str | None
    build_status: str
    dns_valid: bool | None
    https_eligible: bool | None
    certificate_state: str
    https_enforced: bool

    def matches_domain(self, domain: str | None) -> bool:
        return (self.cname or "").lower().rstrip(".") == (domain or "")

    def can_enforce_https(self, domain: str | None) -> bool:
        return (
            self.matches_domain(domain)
            and self.dns_valid is not False
            and self.https_eligible is not False
            and (self.https_enforced or domain is None or self.certificate_state == "approved")
        )


def _api(info: GitRemoteInfo, suffix: str = "", *, payload: dict | None = None) -> dict:
    executable = shutil.which("gh")
    if executable is None:
        raise PagesError("gh_missing")
    args = [
        executable, "api", f"repos/{info.owner}/{info.repo}/pages{suffix}",
        "--hostname", "github.com", "-H", "Accept: application/vnd.github+json",
        "-H", "X-GitHub-Api-Version: 2026-03-10",
    ]
    if payload is not None:
        args += ["--method", "PUT", "--input", "-"]
    try:
        result = subprocess.run(
            args, input=json.dumps(payload) if payload is not None else None,
            text=True, capture_output=True, timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise PagesError("api_error", str(error)) from error
    if result.returncode:
        raise PagesError("api_error", result.stderr.strip()[:350])
    try:
        response = json.loads(result.stdout) if result.stdout.strip() else {}
    except json.JSONDecodeError as error:
        raise PagesError("api_error", "Invalid GitHub response") from error
    if not isinstance(response, dict):
        raise PagesError("api_error", "Invalid GitHub response")
    return response


def get_pages_status(info: GitRemoteInfo) -> PagesStatus:
    pages = _api(info)
    if "html_url" not in pages:
        raise PagesError("api_error", "GitHub Pages is not enabled or is unavailable")
    try:
        health = _api(info, "/health")
    except PagesError:
        health = {}
    domain_health = health.get("domain") or {}
    certificate = pages.get("https_certificate") or {}
    return PagesStatus(
        cname=pages.get("cname"),
        build_status=str(pages.get("status") or ""),
        dns_valid=domain_health.get("is_valid"),
        https_eligible=domain_health.get("is_https_eligible"),
        certificate_state=str(certificate.get("state") or ""),
        https_enforced=pages.get("https_enforced") is True,
    )


def enforce_pages_https(info: GitRemoteInfo, domain: str | None) -> PagesStatus:
    status = get_pages_status(info)
    if not status.matches_domain(domain):
        raise PagesError("binding_mismatch")
    if status.https_enforced:
        return status
    if not status.can_enforce_https(domain):
        raise PagesError("https_pending")
    _api(info, payload={"https_enforced": True})
    confirmed = get_pages_status(info)
    if not confirmed.matches_domain(domain) or not confirmed.https_enforced:
        raise PagesError("https_unconfirmed")
    return confirmed
