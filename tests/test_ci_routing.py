"""Offline CI contracts and real temporary-Git checkout identity regressions."""

import ast
from copy import deepcopy
from fnmatch import fnmatchcase
import itertools
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import yaml


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/check_ci_checkout.py"
GUARD = runpy.run_path(str(SCRIPT))
VERIFY = GUARD["verify_checkout"]
IDENTITY_ERROR = GUARD["CheckoutIdentityError"]
# BaseLoader preserves the Actions key `on`, which YAML 1.1 otherwise calls True.
WORKFLOW = yaml.load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def expression(source, **context):
    """Evaluate this workflow's small expression subset, not hosted scheduling."""
    source = source.strip().removeprefix("${{").removesuffix("}}").strip()
    parsed = ast.parse(source.replace("&&", " and ").replace("||", " or "), mode="eval")
    allowed = (ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.Compare, ast.Eq,
               ast.NotEq, ast.Name, ast.Load, ast.Attribute, ast.Call, ast.Constant)
    for node in ast.walk(parsed):
        if not isinstance(node, allowed):
            raise AssertionError(f"Unsupported workflow expression: {ast.dump(node)}")
        if isinstance(node, ast.Name) and node.id not in {*context, "format"}:
            raise AssertionError(f"Unexpected expression name: {node.id}")
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise AssertionError("Private attributes are not workflow contexts")
        if isinstance(node, ast.Call) and not (isinstance(node.func, ast.Name) and node.func.id == "format"):
            raise AssertionError("Only Actions format() is supported")
    return eval(compile(parsed, "<workflow expression>", "eval"), {"__builtins__": {}},
                {**context, "format": lambda pattern, *args: pattern.format(*args)})


def concurrency(event="pull_request", action="synchronize", number=212, run_id=100, workflow="CI", ref="refs/heads/master"):
    github = SimpleNamespace(workflow=workflow, event_name=event, run_id=run_id, ref=ref,
                             event=SimpleNamespace(action=action, number=number))
    spec = WORKFLOW["concurrency"]
    group = re.sub(r"\$\{\{(.*?)\}\}", lambda m: str(expression(m.group(1), github=github)), spec["group"])
    return group, expression(spec["cancel-in-progress"], github=github)


class WorkflowContracts(unittest.TestCase):
    def test_event_routing_has_no_base_or_path_filter(self):
        events = WORKFLOW["on"]
        self.assertEqual(set(events), {"push", "pull_request"})
        self.assertEqual(events["push"], {"branches": ["master", "verify/**"]})
        self.assertEqual(events["pull_request"], {"types": [
            "opened", "synchronize", "reopened", "ready_for_review", "edited",
        ]})
        cases = [("push", "master", "", True), ("push", "feature/x", "", False),
                 ("push", "release/x", "", False), ("push", "v1.2.3", "", False),
                 ("push", "verify/exact-commit", "", True), ("push", "verify/nested/recovery", "", True),
                 ("push", "verification/recovery", "", False), ("push", "feature/verify/recovery", "", False)]
        cases += [("pull_request", base, action, True)
                  for base, action in itertools.product(("master", "feature/base", "release/x"),
                                                       events["pull_request"]["types"])]
        cases += [("pull_request", "master", action, False) for action in ("closed", "labeled", "converted_to_draft")]
        for event, base, action, expected in cases:
            with self.subTest(event=event, base=base, action=action):
                routed = any(fnmatchcase(base, pattern) for pattern in events[event]["branches"]) if event == "push" else action in events[event]["types"]
                self.assertEqual(routed, expected)

    def test_normal_pr_runs_supersede_only_the_same_pr_workflow(self):
        first = concurrency(action="opened", run_id=100)
        self.assertEqual(first, ("CI-pr-212", True))
        for action in ("synchronize", "reopened", "ready_for_review"):
            self.assertEqual(concurrency(action=action, run_id=101), first)
        self.assertNotEqual(concurrency(number=213)[0], first[0])
        self.assertNotEqual(concurrency(workflow="Publish")[0], first[0])

    def test_master_and_verify_pushes_have_unique_groups_and_never_cancel(self):
        groups = []
        for index, ref in enumerate(("refs/heads/master", "refs/heads/verify/recovery")):
            for run_id in (100 + 2 * index, 101 + 2 * index):
                with self.subTest(ref=ref, run_id=run_id):
                    actual = concurrency(event="push", action="", ref=ref, run_id=run_id)
                    self.assertEqual(actual, (f"CI-{run_id}", False))
                    self.assertNotEqual(actual[0], concurrency()[0])
                    groups.append(actual[0])
        self.assertEqual(len(set(groups)), 4)

    def test_all_edits_are_isolated_from_normal_pr_and_each_other(self):
        self.assertEqual(concurrency(action="edited", run_id=201), ("CI-201", False))
        self.assertEqual(concurrency(action="edited", run_id=202), ("CI-202", False))
        self.assertNotEqual(concurrency(action="edited")[0], concurrency()[0])

    def test_job_names_and_matrix_remain_full(self):
        jobs = WORKFLOW["jobs"]
        self.assertEqual(set(jobs), {"workspace", "test", "test-ubuntu", "stress-tests", "skill-version-guard"})
        self.assertEqual(jobs["workspace"]["name"], "workspace UI, browser and installed wheel")
        self.assertEqual(jobs["test"]["name"], "test (${{ matrix.os }}, py${{ matrix.python-version }})")
        self.assertEqual(jobs["test-ubuntu"]["name"], "test (ubuntu-latest, py${{ matrix.python-version }}, shard ${{ matrix.split_index }}/4)")
        self.assertEqual(jobs["skill-version-guard"]["name"], "skill-version-guard")
        self.assertNotIn("name", jobs["stress-tests"])
        matrix = jobs["test"]["strategy"]["matrix"]
        self.assertEqual(matrix, {"os": ["windows-latest", "macos-latest"],
            "python-version": ["3.10", "3.11", "3.12", "3.13"],
            "include": [{"os": os_name, "python-version": "3.14", "experimental": "true"}
                        for os_name in ("windows-latest", "macos-latest")]})
        self.assertEqual(jobs["test-ubuntu"]["strategy"]["matrix"], {
            "python-version": ["3.10", "3.11", "3.12", "3.13"], "split_index": ["1", "2", "3", "4"],
            "include": [{"python-version": "3.14", "split_index": "1", "experimental": "true"}],
        })
        for name in ("test", "test-ubuntu"):
            self.assertEqual(jobs[name]["strategy"]["fail-fast"], "false")
            self.assertEqual(jobs[name]["continue-on-error"], "${{ matrix.experimental || false }}")

    def test_every_pr_edit_runs_real_jobs_not_skipped_success_substitutes(self):
        self.assertNotIn("permissions", WORKFLOW)
        for name, job in WORKFLOW["jobs"].items():
            with self.subTest(job=name):
                if name in ("stress-tests", "skill-version-guard"):
                    self.assertEqual(job["if"], "github.event_name == 'pull_request'")
                else:
                    self.assertNotIn("if", job)
                self.assertNotIn("needs", job)
                guards = [s for s in job["steps"] if s.get("name") == "Verify checkout identity"]
                self.assertEqual(len(guards), 1)
                guard = guards[0]
                self.assertNotIn("if", guard)
                self.assertNotIn("continue-on-error", guard)
                self.assertIn(guard["run"], ("python scripts/check_ci_checkout.py", "python3 scripts/check_ci_checkout.py"))
                guard_index = job["steps"].index(guard)
                first_work = next(i for i, s in enumerate(job["steps"]) if "run" in s)
                self.assertEqual(guard_index, first_work)
                self.assertTrue(job["steps"][0]["uses"].startswith("actions/checkout@"))

    def test_download_cache_keeps_dependency_installation(self):
        cached = 0
        for name, job in WORKFLOW["jobs"].items():
            for step in job["steps"]:
                if step.get("uses", "").startswith("actions/setup-python@"):
                    cached += 1
                    self.assertEqual(step["with"]["cache"], "pip")
                    self.assertEqual(step["with"]["cache-dependency-path"].splitlines(),
                                     ["pyproject.toml", "constraints.txt", ".github/workflows/ci.yml"])
            if name in ("test", "test-ubuntu", "stress-tests"):
                install = next(s for s in job["steps"] if s.get("name") == "Install dependencies")
                self.assertEqual(install["run"], "pip install -e '.[mcp,dev,playwright,import]'")
                self.assertNotIn("if", install)
            if name == "workspace":
                install = next(s for s in job["steps"] if s.get("name") == "Install test tooling and build wheel")
                self.assertIn("pip install build playwright==1.58.0", install["run"])
                self.assertNotIn("if", install)
        self.assertEqual(cached, 4)

    def test_every_windows_mac_row_runs_full_suite_exactly_once(self):
        steps = WORKFLOW["jobs"]["test"]["steps"]
        plain = next(s for s in steps if s.get("name") == "Run tests")
        coverage = next(s for s in steps if s.get("name") == "Coverage")
        self.assertEqual(plain["run"], 'pytest -q --maxfail=3 -m "not slow"')
        self.assertEqual(coverage["run"], 'pytest --cov=research_hub --cov-report=term-missing --cov-fail-under=62 -m "not slow"')
        for os_name, version in itertools.product(("windows-latest", "macos-latest"), ("3.10", "3.11", "3.12", "3.13", "3.14")):
            with self.subTest(os=os_name, version=version):
                context = SimpleNamespace(os=os_name, **{"python-version": version})
                # Actions allows hyphenated context names; Python uses attributes.
                clauses = [s["if"].replace("matrix.python-version", "matrix.version") for s in (plain, coverage)]
                context.version = version
                selected = [bool(expression(clause, matrix=context)) for clause in clauses]
                self.assertEqual(sum(selected), 1)
                self.assertEqual(selected[1], os_name == "windows-latest" and version == "3.12")
        for step in (plain, coverage):
            self.assertNotIn("continue-on-error", step)
        ubuntu = next(s for s in WORKFLOW["jobs"]["test-ubuntu"]["steps"] if s.get("name", "").startswith("Run tests"))
        self.assertEqual(ubuntu["run"], 'pytest -q --maxfail=3 -m "not slow" --splits 4 --group ${{ matrix.split_index }}')
        stress = next(s for s in WORKFLOW["jobs"]["stress-tests"]["steps"] if s.get("name") == "Run stress tests")
        self.assertEqual(stress["run"], 'pytest tests/stress/ -v -o "addopts=" -m stress')


class CheckoutIdentity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.git = shutil.which("git")
        if cls.git is None:
            raise RuntimeError("These CI regressions require Git")
        cls.temp = tempfile.TemporaryDirectory(prefix="hub-ci-identity-")
        cls.repo = Path(cls.temp.name)
        cls.git_env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        cls.git_env.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CEILING_DIRECTORIES": str(cls.repo.parent), "GIT_TERMINAL_PROMPT": "0",
            "GIT_AUTHOR_NAME": "CI fixture", "GIT_AUTHOR_EMAIL": "ci@example.invalid",
            "GIT_COMMITTER_NAME": "CI fixture", "GIT_COMMITTER_EMAIL": "ci@example.invalid",
            "GIT_AUTHOR_DATE": "2000-01-01T00:00:00+0000", "GIT_COMMITTER_DATE": "2000-01-01T00:00:00+0000"})
        cls.git_run("init", "--quiet", "--initial-branch=master", "--template=", str(cls.repo))
        cls.tree = cls.git_run("hash-object", "-w", "-t", "tree", "--stdin", data="")
        cls.old_base = cls.commit("old base")
        cls.base = cls.commit("current base", cls.old_base)
        cls.head = cls.commit("PR head", cls.old_base)
        cls.old_head = cls.commit("other head", cls.old_base)
        cls.merge = cls.commit("current merge", cls.base, cls.head)
        cls.stale = cls.commit("stale base merge", cls.old_base, cls.head)
        cls.addClassCleanup(cls.temp.cleanup)

    @classmethod
    def git_run(cls, *args, data=None):
        result = subprocess.run([cls.git, *args], cwd=cls.repo, env=cls.git_env, input=data,
            capture_output=True, text=True, encoding="utf-8", check=False, timeout=10)
        if result.returncode:
            raise AssertionError(f"Fixture Git {args!r} failed ({result.returncode}): {result.stderr}")
        return result.stdout.strip()

    @classmethod
    def commit(cls, message, *parents):
        args = ["commit-tree", cls.tree]
        for parent in parents:
            args += ["-p", parent]
        return cls.git_run(*args, data=message)

    def setUp(self):
        self.git_run("update-ref", "refs/heads/master", self.merge)

    def event(self):
        return {"number": 212, "pull_request": {"base": {"sha": self.base}, "head": {"sha": self.head}}}

    def verify(self, event=None, sha=None, ref="refs/pull/212/merge", name="pull_request", cwd=None):
        with patch.dict(os.environ, self.git_env, clear=True):
            return VERIFY(name, self.event() if event is None else event, self.merge if sha is None else sha,
                          ref, cwd=self.repo if cwd is None else cwd)

    def test_current_merge_matches_both_event_parents(self):
        self.assertEqual(self.verify(), self.merge)

    def test_stale_merge_fails_even_when_head_matches_github_sha(self):
        self.git_run("update-ref", "refs/heads/master", self.stale)
        with self.assertRaisesRegex(IDENTITY_ERROR, "merge parents"):
            self.verify(sha=self.stale)

    def test_wrong_head_parent_and_reversed_parents_fail(self):
        for parents in ((self.base, self.old_head), (self.head, self.base)):
            with self.subTest(parents=parents):
                actual = self.commit("wrong parents", *parents)
                self.git_run("update-ref", "refs/heads/master", actual)
                with self.assertRaisesRegex(IDENTITY_ERROR, "merge parents"):
                    self.verify(sha=actual)

    def test_nonmerge_and_octopus_are_ambiguous(self):
        for parents in ((self.base,), (self.base, self.head, self.old_head)):
            with self.subTest(parents=parents):
                actual = self.commit("bad arity", *parents)
                self.git_run("update-ref", "refs/heads/master", actual)
                with self.assertRaisesRegex(IDENTITY_ERROR, "two-parent merge"):
                    self.verify(sha=actual)

    def test_pr_head_checkout_cannot_replace_event_merge(self):
        self.git_run("update-ref", "refs/heads/master", self.head)
        with self.assertRaisesRegex(IDENTITY_ERROR, "does not match event SHA"):
            self.verify()

    def test_raw_headers_work_at_a_shallow_boundary_where_traversal_hides_parents(self):
        shallow = self.repo / ".git/shallow"
        shallow.write_bytes((self.merge + "\n").encode("ascii"))
        try:
            self.assertEqual(self.git_run("rev-parse", "--is-shallow-repository"), "true")
            self.assertEqual(self.git_run("show", "-s", "--format=%P", "HEAD"), "")
            self.assertEqual(self.verify(), self.merge)
        finally:
            shallow.unlink()

    def test_malformed_or_missing_event_identity_fails_closed(self):
        cases = [None, [], {}, {"number": 212, "pull_request": None}]
        for keys, value in ((["number"], "212"), (["number"], True), (["number"], 0),
                            (["pull_request", "base"], {}), (["pull_request", "base", "sha"], "bad"),
                            (["pull_request", "head", "sha"], "A" * 40)):
            event = deepcopy(self.event())
            parent = event
            for key in keys[:-1]:
                parent = parent[key]
            parent[keys[-1]] = value
            cases.append(event)
        for event in cases:
            with self.subTest(event=event), self.assertRaises(IDENTITY_ERROR):
                self.verify(event=event if event is not None else [])

    def test_pr_number_and_merge_ref_must_agree(self):
        for ref in ("refs/heads/master", "refs/pull/213/merge", "refs/pull/212/head", ""):
            with self.subTest(ref=ref), self.assertRaises(IDENTITY_ERROR):
                self.verify(ref=ref)

    def test_push_requires_matching_event_after_head_and_branch(self):
        event = {"after": self.merge, "ref": "refs/heads/master"}
        self.assertEqual(self.verify(event, ref=event["ref"], name="push"), self.merge)
        for changed in ({**event, "after": self.stale}, {**event, "ref": "refs/heads/other"}, {}):
            with self.subTest(event=changed), self.assertRaises(IDENTITY_ERROR):
                self.verify(changed, ref=event["ref"], name="push")
        self.git_run("update-ref", "refs/heads/master", self.stale)
        with self.assertRaisesRegex(IDENTITY_ERROR, "does not match event SHA"):
            self.verify(event, ref=event["ref"], name="push")

    def test_verify_branch_push_validates_the_exact_commit(self):
        # A final linear commit needs no synthetic PR merge to exercise push CI.
        self.git_run("update-ref", "refs/heads/master", self.base)
        event = {"after": self.base, "ref": "refs/heads/verify/recovery", "deleted": False}
        self.assertEqual(self.verify(event, sha=self.base, ref=event["ref"], name="push"), self.base)
        result = self.run_cli(json.dumps(event), GITHUB_SHA=self.base,
                              GITHUB_EVENT_NAME="push", GITHUB_REF=event["ref"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(self.base, result.stdout)

    def test_push_deletion_and_zero_sha_cannot_be_exact_tree_proof(self):
        event = {"after": self.merge, "ref": "refs/heads/verify/recovery"}
        cases = [({**event, "deleted": True}, self.merge),
                 ({**event, "deleted": "true"}, self.merge),
                 ({**event, "after": "0" * 40}, self.merge),
                 ({**event, "after": "0" * 40, "deleted": True}, "0" * 40)]
        for payload, sha in cases:
            with self.subTest(event=payload, sha=sha):
                with self.assertRaises(IDENTITY_ERROR):
                    self.verify(payload, sha=sha, ref=event["ref"], name="push")
                result = self.run_cli(json.dumps(payload), GITHUB_SHA=sha,
                                      GITHUB_EVENT_NAME="push", GITHUB_REF=event["ref"])
                self.assertEqual(result.returncode, 1)
                self.assertIn("::error::", result.stderr)

    def test_unknown_event_and_invalid_context_sha_fail_closed(self):
        for name in ("workflow_dispatch", "pull_request_target", "", "schedule"):
            with self.subTest(name=name), self.assertRaises(IDENTITY_ERROR):
                self.verify(name=name)
        for sha in ("", "HEAD", self.merge[:7], "z" * 40):
            with self.subTest(sha=sha), self.assertRaises(IDENTITY_ERROR):
                self.verify(sha=sha)

    def run_cli(self, data, **overrides):
        event_path = self.repo / "event.json"
        event_path.write_text(data, encoding="utf-8")
        env = {**self.git_env, "GITHUB_EVENT_PATH": str(event_path), "GITHUB_EVENT_NAME": "pull_request",
               "GITHUB_SHA": self.merge, "GITHUB_REF": "refs/pull/212/merge", **overrides}
        return subprocess.run([sys.executable, "-B", str(SCRIPT)], cwd=self.repo, env=env,
                              capture_output=True, text=True, check=False, timeout=15)

    def test_cli_passes_current_pr_and_push_and_fails_stale_merge(self):
        for data, env in ((self.event(), {}), ({"after": self.merge, "ref": "refs/heads/master"},
                           {"GITHUB_EVENT_NAME": "push", "GITHUB_REF": "refs/heads/master"})):
            result = self.run_cli(json.dumps(data), **env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(self.merge, result.stdout)
        self.git_run("update-ref", "refs/heads/master", self.stale)
        result = self.run_cli(json.dumps(self.event()), GITHUB_SHA=self.stale)
        self.assertEqual(result.returncode, 1)
        self.assertIn("::error::", result.stderr)
        self.assertIn("merge parents", result.stderr)

    def test_cli_rejects_invalid_json_duplicate_keys_and_missing_context(self):
        for data, overrides in (("{", {}), ('{"number":212,"number":213}', {}),
                                (json.dumps(self.event()), {"GITHUB_EVENT_PATH": ""}),
                                (json.dumps(self.event()), {"GITHUB_SHA": ""})):
            with self.subTest(data=data, overrides=overrides):
                result = self.run_cli(data, **overrides)
                self.assertEqual(result.returncode, 1)
                self.assertIn("::error::", result.stderr)

    def test_git_read_failure_cannot_report_success(self):
        with tempfile.TemporaryDirectory(prefix="hub-ci-no-git-") as directory:
            with self.assertRaises(subprocess.CalledProcessError):
                self.verify(cwd=Path(directory))


if __name__ == "__main__":
    unittest.main()
