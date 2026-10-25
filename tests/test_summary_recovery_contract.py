"""Actual legacy summary writer/consumer contracts with synthetic adapters only."""
import contextlib
import io
from pathlib import Path
import socket
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from research_hub import auto, cli_summarize, paper_summarize, summarize

ENTRY = {'paper_slug': 'paper', 'key_findings': ['Synthetic finding'],
         'methodology': 'Synthetic method', 'relevance': 'Synthetic scope'}


class Remote:
    def __init__(self, mode, path):
        self.mode, self.path, self.calls = mode, path, 0
        self.remote_text = 'original'
    def children(self, key):
        return [{'data': {'key': 'NOTE0001', 'version': 1, 'parentItem': key,
                 'itemType': 'note', 'note': 'original', 'tags': [{'tag': 'research-hub:summary:v1'}]}}]
    def everything(self, value): return value
    def update_item(self, data):
        self.calls += 1
        self.remote_text = data['note']  # Synthetic remote state, not a provider.
        if self.mode == 'human': self.path.write_text('New human annotation 中文\n', encoding='utf-8')
        if self.mode == 'false': return False
        raise TimeoutError('Synthetic committed update reply lost')


class SummaryRecoveryContracts(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='hub-summary-contract-')
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'paper.md'
        self.original = '## Personal notes\n\nOriginal 中文\n'
        self.path.write_text(self.original, encoding='utf-8')
        for obj, name in [(socket, 'socket'), (socket, 'create_connection'), (subprocess, 'Popen')]:
            blocker = patch.object(obj, name, side_effect=AssertionError('No network or provider process'))
            blocker.start(); self.addCleanup(blocker.stop)

    def apply(self, remote):
        papers = [{'slug': 'paper', 'path': self.path, 'zotero_key': 'PARENT01', 'title': 'Synthetic'}]
        with patch.object(summarize, '_read_cluster_papers_with_abstracts', return_value=papers):
            return summarize.apply_summaries(SimpleNamespace(), 'synthetic', [ENTRY], zot=remote)

    def test_timeout_and_false_ack_remain_unknown_without_retry(self):
        for mode in ('timeout', 'false'):
            with self.subTest(mode=mode):
                self.path.write_text(self.original, encoding='utf-8')
                remote = Remote(mode, self.path)
                result = self.apply(remote)
                self.assertEqual(remote.calls, 1)
                self.assertNotEqual(remote.remote_text, 'original')
                self.assertEqual(result.applied, [])
                self.assertIn('outcome unknown', ' '.join(result.errors))
                self.assertIn('no automatic retry', ' '.join(result.errors))
                self.assertEqual(self.path.read_text(encoding='utf-8'), self.original)

    def test_compensation_does_not_overwrite_observed_newer_human_edit(self):
        remote = Remote('human', self.path)
        result = self.apply(remote)
        self.assertEqual(remote.calls, 1)
        self.assertEqual(self.path.read_text(encoding='utf-8'), 'New human annotation 中文\n')
        self.assertIn('rollback skipped', ' '.join(result.errors))
        self.assertIn('outcome unknown', ' '.join(result.errors))

    def test_compensation_io_failure_keeps_structured_unknown_receipt(self):
        # Reproduce Windows checkout/write newline bytes on any host.
        self.path.write_bytes(self.original.replace('\n', '\r\n').encode('utf-8'))
        original_writer = summarize._write_note_text
        writes = []
        def write(path, text):
            writes.append(text)
            if len(writes) == 2: raise OSError('Synthetic compensation disk full')
            original_writer(path, text)
        remote = Remote('timeout', self.path)
        with patch.object(summarize, '_write_note_text', write):
            result = self.apply(remote)
        self.assertEqual(remote.calls, 1)
        self.assertEqual(result.applied, [])
        self.assertEqual(len(writes), 2)
        self.assertEqual(writes[1].encode('utf-8'), self.original.replace('\n', '\r\n').encode('utf-8'))
        self.assertIn('rollback unavailable', ' '.join(result.to_dict()['errors']))
        self.assertIn('outcome unknown', ' '.join(result.errors))

    def report(self):
        errors = ['first known refusal', 'second unknown remote outcome; inspect both destinations']
        result = summarize.SummaryApplyResult('synthetic', applied=['peer'], errors=errors,
                                               obsidian_writes=1, zotero_writes=1)
        return summarize.SummaryReport('synthetic', ok=False, error='Summary apply failed: ' + errors[0], apply_result=result)

    def test_actual_cli_handler_retains_all_errors_and_partial_counts(self):
        report = self.report()
        args = SimpleNamespace(cluster='synthetic', llm_cli='synthetic', apply=True, no_zotero=False, no_obsidian=False)
        output, error = io.StringIO(), io.StringIO()
        with patch.object(summarize, 'summarize_cluster', return_value=report):
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
                rc = cli_summarize._cmd_summarize(args, object())
        self.assertEqual(rc, 1)
        self.assertIn('applied: 1', output.getvalue())
        for text in report.apply_result.errors: self.assertIn(text, error.getvalue())

    def test_auto_unknown_and_exception_defer_secondary_writer(self):
        for outcome in (self.report(), RuntimeError('Synthetic interrupted first layer')):
            with self.subTest(kind=type(outcome).__name__):
                report = auto.AutoReport(cluster_slug='synthetic', cluster_created=False)
                kwargs = {'side_effect': outcome} if isinstance(outcome, Exception) else {'return_value': outcome}
                with patch.object(summarize, 'summarize_cluster', **kwargs), patch.object(paper_summarize, 'summarize_pending') as second:
                    auto._run_summary_step(object(), 'synthetic', 'synthetic', report, 0, False)
                second.assert_not_called()
                self.assertTrue(any('deferred' in step.detail for step in report.steps))
                if not isinstance(outcome, Exception):
                    self.assertTrue(any(outcome.apply_result.errors[1] in step.detail for step in report.steps))

    def test_auto_known_success_still_allows_secondary_writer(self):
        result = summarize.SummaryReport('synthetic', apply_result=summarize.SummaryApplyResult('synthetic', applied=['paper']))
        report = auto.AutoReport(cluster_slug='synthetic', cluster_created=False)
        with patch.object(summarize, 'summarize_cluster', return_value=result), patch.object(paper_summarize, 'summarize_pending', return_value=[]) as second:
            auto._run_summary_step(object(), 'synthetic', 'synthetic', report, 0, False)
        second.assert_called_once()
