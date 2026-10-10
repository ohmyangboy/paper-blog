import contextlib
from dataclasses import replace
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import paper_cli
from paper_runtime.core import build_site, config_path, load_local_config, normalize_git_remote, save_config
from paper_runtime.i18n import get_current_language, set_current_language
from paper_runtime.pages import PagesError, PagesStatus, enforce_pages_https, get_pages_status


def _response(value=None, *, returncode=0, stderr=""):
    return subprocess.CompletedProcess([], returncode, json.dumps(value) if value is not None else "", stderr)


def _site(cname="1leaf.cc", *, state="approved", enforced=False):
    return {"html_url": "https://1leaf.cc", "status": "built", "cname": cname, "https_certificate": {"state": state}, "https_enforced": enforced}


HEALTH = {"domain": {"is_valid": True, "is_https_eligible": True}}
READY = PagesStatus("1leaf.cc", "built", True, True, "approved", False)


class TerminalOutput(io.StringIO):
    def isatty(self):
        return True


class PagesApiTests(unittest.TestCase):
    def setUp(self):
        self.info = normalize_git_remote("owner/blog")
        self.executable = mock.patch("paper_runtime.pages.shutil.which", return_value="/test/gh")
        self.executable.start()
        self.addCleanup(self.executable.stop)

    def test_async_health_check_is_unknown_and_does_not_hide_certificate_state(self):
        with mock.patch("paper_runtime.pages.subprocess.run", side_effect=[_response(_site()), _response({})]):
            status = get_pages_status(self.info)
        self.assertIsNone(status.dns_valid)
        self.assertEqual(status.certificate_state, "approved")

    def test_certificate_pending_or_wrong_binding_does_not_send_a_write(self):
        for site, kind in ((_site(state="authorization_created"), "https_pending"), (_site(cname="other.example.com"), "binding_mismatch")):
            with self.subTest(kind=kind), mock.patch("paper_runtime.pages.subprocess.run", side_effect=[_response(site), _response(HEALTH)]) as run:
                with self.assertRaises(PagesError) as raised:
                    enforce_pages_https(self.info, "1leaf.cc")
                self.assertEqual(raised.exception.kind, kind)
                self.assertFalse(any("PUT" in call.args[0] for call in run.call_args_list))

    def test_ready_certificate_enforces_only_https_and_reads_back_the_result(self):
        responses = [_response(_site()), _response(HEALTH), _response(), _response(_site(enforced=True)), _response(HEALTH)]
        with mock.patch("paper_runtime.pages.subprocess.run", side_effect=responses) as run:
            result = enforce_pages_https(self.info, "1leaf.cc")
        self.assertTrue(result.https_enforced)
        write = next(call for call in run.call_args_list if "PUT" in call.args[0])
        self.assertEqual(json.loads(write.kwargs["input"]), {"https_enforced": True})
        self.assertIn("github.com", write.args[0])

    def test_successful_request_without_confirmed_setting_is_not_reported_as_success(self):
        responses = [_response(_site()), _response(HEALTH), _response(), _response(_site()), _response(HEALTH)]
        with mock.patch("paper_runtime.pages.subprocess.run", side_effect=responses):
            with self.assertRaises(PagesError) as raised:
                enforce_pages_https(self.info, "1leaf.cc")
        self.assertEqual(raised.exception.kind, "https_unconfirmed")

    def test_dns_failure_blocks_enforcement_even_with_a_certificate(self):
        with mock.patch("paper_runtime.pages.subprocess.run", side_effect=[_response(_site()), _response({"domain": {"is_valid": False}})]) as run:
            with self.assertRaises(PagesError):
                enforce_pages_https(self.info, "1leaf.cc")
        self.assertFalse(any("PUT" in call.args[0] for call in run.call_args_list))

    def test_missing_cli_and_api_failure_have_actionable_error_kinds(self):
        with mock.patch("paper_runtime.pages.shutil.which", return_value=None):
            with self.assertRaises(PagesError) as raised:
                get_pages_status(self.info)
        self.assertEqual(raised.exception.kind, "gh_missing")
        with mock.patch("paper_runtime.pages.subprocess.run", return_value=_response(returncode=1, stderr="HTTP 404")):
            with self.assertRaises(PagesError) as raised:
                get_pages_status(self.info)
        self.assertEqual(raised.exception.kind, "api_error")


    def test_already_enforced_https_does_not_send_another_write(self):
        with mock.patch("paper_runtime.pages.subprocess.run", side_effect=[_response(_site(enforced=True)), _response({"domain": {"is_valid": False}})]) as run:
            status = enforce_pages_https(self.info, "1leaf.cc")
        self.assertTrue(status.https_enforced)
        self.assertFalse(any("PUT" in call.args[0] for call in run.call_args_list))


class PagesConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.previous_language = get_current_language()
        set_current_language("zh_CN")
        self.addCleanup(set_current_language, self.previous_language)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.environment = mock.patch.dict(os.environ, {"PAPER_HOME": str(self.root / "global"), "PAPER_LANG": "zh_CN"})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.updates = mock.patch("paper_cli._check_and_auto_update", return_value=False)
        self.updates.start()
        self.addCleanup(self.updates.stop)
        self.config = save_config(load_local_config(self.root), git_remote="git@github.com:owner/blog.git", site_url="https://1leaf.cc")
        self.config.posts_dir.mkdir()
        (self.config.posts_dir / "index.md").write_text("# Home\n")
        self.draft = self.config.posts_dir / "draft.md"
        self.draft.write_text("---\npublished: false\n---\n\nDraft\n")

    def command(self, *args):
        with contextlib.redirect_stdout(io.StringIO()) as output, contextlib.redirect_stderr(io.StringIO()) as errors:
            code = paper_cli.main(["-C", str(self.root), "config", "pages", *args])
        return code, output.getvalue(), errors.getvalue()

    def test_direct_domain_argument_saves_only_local_configuration(self):
        global_path = config_path()
        global_path.parent.mkdir(parents=True)
        global_path.write_text('{"siteUrl":"https://global.example.com"}')
        original = global_path.read_bytes()
        with mock.patch("paper_cli.cmd_deploy") as deploy, mock.patch("paper_cli.get_pages_status") as status:
            code, output, _ = self.command("blog.example.com")
        self.assertEqual(code, 0)
        self.assertEqual(load_local_config(self.root).site_url, "https://blog.example.com")
        self.assertEqual(global_path.read_bytes(), original)
        self.assertIn("owner.github.io", output)
        deploy.assert_not_called()
        status.assert_not_called()

    def test_invalid_url_or_conflicting_options_leave_configuration_unchanged(self):
        original = self.config.config_path.read_bytes()
        for arguments in (("https://example.com/path",), ("example.com", "--check"), ("example.com", "--https")):
            with self.subTest(arguments=arguments):
                self.assertEqual(self.command(*arguments)[0], 1)
                self.assertEqual(self.config.config_path.read_bytes(), original)

    def test_cancel_before_save_preserves_url_and_does_not_deploy(self):
        original = self.config.config_path.read_bytes()
        with mock.patch("sys.stdin.isatty", return_value=True), mock.patch("builtins.input", return_value="other.example.com"), mock.patch("paper_cli._confirm_or_skip", return_value=False), mock.patch("paper_cli.cmd_deploy") as deploy, contextlib.redirect_stdout(TerminalOutput()):
            result = paper_cli.cmd_pages_url(self.config)
        self.assertEqual(result, self.config)
        self.assertEqual(self.config.config_path.read_bytes(), original)
        deploy.assert_not_called()

    def test_four_step_wizard_deploys_the_selected_project_and_keeps_drafts(self):
        draft_before = self.draft.read_bytes()
        with mock.patch("sys.stdin.isatty", return_value=True), mock.patch("builtins.input", side_effect=["1leaf.cc", "1leaf.cc"]), mock.patch("paper_cli._confirm_or_skip", return_value=True), mock.patch("paper_cli.cmd_deploy", return_value=0) as deploy, mock.patch("paper_cli._open_browser", return_value=True) as browser, mock.patch("paper_cli.get_pages_status", return_value=READY), mock.patch("paper_cli.enforce_pages_https", return_value=replace(READY, https_enforced=True)) as enforce, contextlib.redirect_stdout(TerminalOutput()) as output:
            saved = paper_cli.cmd_pages_url(self.config)
        self.assertEqual(saved.site_url, "https://1leaf.cc")
        deploy.assert_called_once_with(local_dir=self.root)
        browser.assert_called_once_with("https://github.com/owner/blog/settings/pages")
        self.assertEqual(enforce.call_args.args[1], "1leaf.cc")
        self.assertEqual(self.draft.read_bytes(), draft_before)
        for text in ("网站地址", "绑定与部署", "DNS 记录", "HTTPS 检查", "185.199.108.153", "www", "owner.github.io", "已确认开启强制 HTTPS"):
            self.assertIn(text, output.getvalue())
        out = saved.output_dir
        self.assertEqual((out / "CNAME").read_text(), "1leaf.cc\n")
        self.assertFalse((out / "posts" / "draft").exists())

    def test_nested_subdomain_dns_guidance_retries_an_unrelated_zone(self):
        ready = replace(READY, cname="docs.blog.example.co.uk", https_enforced=True)
        with mock.patch("sys.stdin.isatty", return_value=True), mock.patch("builtins.input", side_effect=["docs.blog.example.co.uk", "other.com", "example.co.uk"]), mock.patch("paper_cli._confirm_or_skip", return_value=True), mock.patch("paper_cli.cmd_deploy", return_value=0), mock.patch("paper_cli._open_browser", return_value=True), mock.patch("paper_cli.get_pages_status", return_value=ready), contextlib.redirect_stdout(TerminalOutput()) as output, contextlib.redirect_stderr(io.StringIO()) as errors:
            saved = paper_cli.cmd_pages_url(self.config)
        self.assertEqual(saved.site_url, "https://docs.blog.example.co.uk")
        self.assertIn("docs.blog", output.getvalue())
        self.assertIn("CNAME", output.getvalue())
        self.assertNotIn("185.199.108.153", output.getvalue())
        self.assertIn("不包含", errors.getvalue())

    def test_actions_project_is_guided_without_automatically_committing_source(self):
        workflow = self.root / ".github" / "workflows" / "deploy.yml"
        workflow.parent.mkdir(parents=True)
        workflow.write_text("jobs:\n  deploy:\n    steps:\n      - uses: actions/deploy-pages@v4\n")
        with mock.patch("sys.stdin.isatty", return_value=True), mock.patch("builtins.input", side_effect=["1leaf.cc", "1leaf.cc"]), mock.patch("paper_cli._confirm_or_skip", return_value=True), mock.patch("paper_cli.cmd_deploy") as deploy, mock.patch("paper_cli._open_browser", return_value=True), mock.patch("paper_cli.get_pages_status", return_value=replace(READY, https_enforced=True)), contextlib.redirect_stdout(TerminalOutput()) as output:
            paper_cli.cmd_pages_url(self.config)
        deploy.assert_not_called()
        self.assertIn("GitHub Actions", output.getvalue())

    def test_check_reads_pending_state_without_saving_or_enabling_https(self):
        original = self.config.config_path.read_bytes()
        with mock.patch("paper_cli.get_pages_status", return_value=replace(READY, certificate_state="authorization_created")), mock.patch("paper_cli.enforce_pages_https") as enforce:
            code, output, _ = self.command("--check")
        self.assertEqual(code, 0)
        self.assertIn("签发中", output)
        self.assertEqual(self.config.config_path.read_bytes(), original)
        enforce.assert_not_called()

    def test_https_not_ready_returns_failure_with_no_success_claim(self):
        with mock.patch("paper_cli.get_pages_status", return_value=replace(READY, certificate_state="authorization_created")), mock.patch("paper_cli.enforce_pages_https", side_effect=PagesError("https_pending")):
            code, output, errors = self.command("--https")
        self.assertEqual(code, 1)
        self.assertIn("尚未就绪", errors)
        self.assertNotIn("✅", output)

    def test_missing_github_cli_keeps_configuration_and_shows_manual_settings(self):
        original = self.config.config_path.read_bytes()
        with mock.patch("paper_cli.get_pages_status", side_effect=PagesError("gh_missing")):
            code, output, errors = self.command("--check")
        self.assertEqual(code, 1)
        self.assertIn("gh auth login", errors)
        self.assertIn("https://github.com/owner/blog/settings/pages", output)
        self.assertEqual(self.config.config_path.read_bytes(), original)
