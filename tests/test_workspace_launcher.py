"""Workspace browser-open failures must not stop an otherwise usable server."""

from contextlib import ExitStack, redirect_stderr, redirect_stdout
from io import StringIO
import unittest
from unittest.mock import Mock, patch

from research_hub.workspace import server as module


class WorkspaceLauncherTests(unittest.TestCase):
    def setUp(self):
        self.server = Mock(server_port=43210)
        self.stdout = StringIO()
        self.stderr = StringIO()
        contexts = ExitStack()
        self.addCleanup(contexts.close)
        self.server_type = contexts.enter_context(patch.object(module, "WorkspaceServer", return_value=self.server))
        self.open_browser = contexts.enter_context(patch.object(module.webbrowser, "open", return_value=True))
        contexts.enter_context(redirect_stdout(self.stdout))
        contexts.enter_context(redirect_stderr(self.stderr))

    def launch(self, **kwargs):
        module.serve_workspace("synthetic-workspace", **kwargs)

    def assert_served_and_closed(self):
        self.server.serve_forever.assert_called_once_with()
        self.server.server_close.assert_called_once_with()

    def test_successful_open_uses_canonical_url_and_closes_server(self):
        self.launch(port=0, human=True, obsidian_vault="synthetic-vault", library_snapshot="synthetic.json")
        self.server_type.assert_called_once_with("synthetic-workspace", port=0, human=True,
            obsidian_vault="synthetic-vault", library_snapshot="synthetic.json")
        self.open_browser.assert_called_once_with("http://127.0.0.1:43210/app/")
        self.assertEqual(self.stdout.getvalue(), "Research workspace: http://127.0.0.1:43210/app/\n")
        self.assertEqual(self.stderr.getvalue(), "")
        self.assert_served_and_closed()

    def test_no_browser_keeps_normal_serving_without_warning(self):
        self.launch(open_browser=False)
        self.open_browser.assert_not_called()
        self.assertEqual(self.stderr.getvalue(), "")
        self.assert_served_and_closed()

    def test_false_browser_result_explains_manual_entry_and_keeps_serving(self):
        self.open_browser.return_value = False
        self.launch()
        self.assertIn("Could not open a browser automatically", self.stderr.getvalue())
        self.assertIn("workspace URL above", self.stderr.getvalue())
        self.assert_served_and_closed()

    def test_browser_error_keeps_serving_without_leaking_exception(self):
        self.open_browser.side_effect = module.webbrowser.Error("private-launcher-detail")
        self.launch()
        self.assertIn("Could not open a browser automatically", self.stderr.getvalue())
        self.assertNotIn("private-launcher-detail", self.stderr.getvalue())
        self.assert_served_and_closed()

    def test_os_error_keeps_serving_without_leaking_exception(self):
        self.open_browser.side_effect = OSError("private-launcher-detail")
        self.launch()
        self.assertIn("Could not open a browser automatically", self.stderr.getvalue())
        self.assertNotIn("private-launcher-detail", self.stderr.getvalue())
        self.assert_served_and_closed()

    def test_unexpected_browser_error_propagates_but_closes_server(self):
        self.open_browser.side_effect = ValueError("unexpected launcher bug")
        with self.assertRaisesRegex(ValueError, "unexpected launcher bug"):
            self.launch()
        self.server.serve_forever.assert_not_called()
        self.server.server_close.assert_called_once_with()

    def test_interrupt_during_browser_open_propagates_but_closes_server(self):
        self.open_browser.side_effect = KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.launch()
        self.server.serve_forever.assert_not_called()
        self.server.server_close.assert_called_once_with()

    def test_interrupt_during_serving_still_closes_server(self):
        self.server.serve_forever.side_effect = KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.launch()
        self.assert_served_and_closed()

    def test_banner_is_flushed_before_browser_open_and_serving(self):
        events = []
        class Output(StringIO):
            def flush(self):
                events.append("flush")
        self.open_browser.side_effect = lambda _url: events.append("open") or True
        self.server.serve_forever.side_effect = lambda: events.append("serve")
        with redirect_stdout(Output()):
            self.launch()
        self.assertEqual(events, ["flush", "open", "serve"])
        self.assert_served_and_closed()

    def test_output_error_also_closes_server(self):
        with patch("builtins.print", side_effect=BrokenPipeError("output closed")):
            with self.assertRaises(BrokenPipeError):
                self.launch()
        self.open_browser.assert_not_called()
        self.server.serve_forever.assert_not_called()
        self.server.server_close.assert_called_once_with()

    def test_server_construction_failure_does_not_attempt_browser_open(self):
        self.server_type.side_effect = OSError("bind failed")
        with self.assertRaisesRegex(OSError, "bind failed"):
            self.launch()
        self.open_browser.assert_not_called()
        self.server.server_close.assert_not_called()

    def test_warning_output_failure_propagates_and_closes_server(self):
        class BrokenOutput(StringIO):
            def write(self, _text):
                raise BrokenPipeError("warning output closed")
        self.open_browser.return_value = False
        with redirect_stderr(BrokenOutput()):
            with self.assertRaises(BrokenPipeError):
                self.launch()
        self.server.serve_forever.assert_not_called()
        self.server.server_close.assert_called_once_with()

    def test_serving_error_propagates_and_closes_server(self):
        self.server.serve_forever.side_effect = OSError("synthetic server failure")
        with self.assertRaisesRegex(OSError, "synthetic server failure"):
            self.launch()
        self.assert_served_and_closed()
