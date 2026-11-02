"""One local component-browser fixture; no Workspace, DB, provider or real data.

Actual candidate TSX/CSS is bundled with already installed esbuild. The HTTP
handler reuses the production origin guard/CSP but exposes only fixture files.
This does not exercise production App/API wiring or file registration.
"""
from __future__ import annotations

import hashlib
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATHS = [
    "docs/contracts/source-observation-view.md", "web/src/LiteratureLibrary.tsx",
    "web/src/ObservationHistory.tsx", "web/src/sourceObservations.ts",
    "web/src/sourceObservations.test.tsx", "web/src/i18n.ts", "web/src/library.css",
]
sys.path.insert(0, str(ROOT / "src"))
from research_hub.workspace.server import WorkspaceHandler


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def fixture_data():
    records, artifacts, previews = [], [], []

    def add_source(local, title, summary=None, abstract=None, reading="abstract-snippet"):
        record = {"id": "hub-" + local, "kind": "source", "data": {
            "id": local, "title": title, "locator": "https://example.invalid/" + local,
            "reading_level": reading, "reading_scope": "abstract", "identity_status": "unverified",
            "human_acceptance": "pending", "source_records": []}}
        if summary is not None:
            record["data"]["summary"] = summary
        if abstract is not None:
            record["data"]["abstract"] = abstract
        records.append(record)
        return record

    def add_observation(record, suffix, body, version=None, bound=True, stamp="2026-11-01T01:20:49Z"):
        local = record["data"]["id"]
        content = (f"# Generated summary observation: {local}\n\n"
                   "Evidence level: generated-summary. This is report-derived prose, NOT an original abstract or publisher capture.\n\n"
                   f"## Supplied generated summary\n{body}\n\n"
                   "Role candidate (not human acceptance): Method candidate\n"
                   "Reported later reading: direct_proceedings_full_abstract\n"
                   f"Reported observation time: {stamp}\n"
                   'Reported sources: ["https://example.invalid/reported-source"]\n')
        digest = sha(content.encode())
        path = f"generated/{suffix}.md"
        obs = {"observation_id": suffix, "source_id": local, "work_id": "work-" + local,
               "version_id": version, "version_review_ref": None,
               "acquisition_ref": "Synthetic generated report; no primary capture receipt",
               "status": "available", "evidence_level": "generated-summary", "source_fetch_result": None,
               "raw_path": None, "raw_sha256": None, "text_path": path,
               "text_sha256": digest if bound else None, "source_version": None}
        record["data"]["source_records"].append(obs)
        if bound:
            artifacts.append({"id": "artifact-" + suffix, "project_id": "synthetic-project",
                              "source_record_id": record["id"], "path": path, "role": "evidence",
                              "sha256": digest, "current": version != "2023"})
            previews.append({"artifact_id": "artifact-" + suffix, "path": path, "sha256": digest,
                             "text": content, "codepoint_length": len(content),
                             "bytes_read": len(content.encode()), "truncated": False})
        return obs

    saved = add_source("manual", "Saved summary priority", "Human preserved wording.", "Abstract must not replace summary.")
    generated = add_observation(saved, "manual-generated", "Separate generated draft; never overwrites saved prose.")
    saved["data"]["source_records"].insert(0, {**generated, "observation_id": "stored-snippet",
        "evidence_level": "metadata", "status": "unknown", "text_path": None, "text_sha256": None})
    only = add_source("generated", "Generated-only draft")
    add_observation(only, "only-generated", "Generated-only synthetic summary.")
    unbound = add_source("unbound", "Unbound draft", reading="metadata")
    add_observation(unbound, "missing-binding", "This unbound text must never be shown.", bound=False)
    versions = add_source("versions", "Version conflict draft")
    add_observation(versions, "version-a", "Version A remains separate.", "2023")
    add_observation(versions, "version-b", "Version B remains separate.", "2026")
    add_source("abstract", "Saved abstract only", "  ", "Original saved abstract.", reading="abstract")
    malformed = add_source("time", "Uncertain observation time")
    add_observation(malformed, "invalid-time", "Summary with unknown reported time.", stamp="not-a-date")
    context = {"projectId": "synthetic-project", "artifacts": artifacts, "previews": previews}
    return records, context


def build_fixture(output: Path):
    try:
        output.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        raise RuntimeError("Choose a new scratch directory for this component fixture") from None
    files = [{"path": name, "bytes": (ROOT / name).stat().st_size, "sha256": sha((ROOT / name).read_bytes())} for name in SOURCE_PATHS]
    fingerprint = sha(json.dumps(files, sort_keys=True, separators=(",", ":")).encode())
    manifest = {"source_files": files, "source_fingerprint": fingerprint,
                "checkout_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                "checkout_tree": subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True).strip()}
    records, context = fixture_data()
    entry = f'''import {{createRoot}} from "react-dom/client";
import {{LiteratureLibrary}} from {json.dumps((ROOT / 'web/src/LiteratureLibrary.tsx').as_posix())};
import {{translator}} from {json.dumps((ROOT / 'web/src/i18n.ts').as_posix())};
import {json.dumps((ROOT / 'web/src/styles.css').as_posix())};
import {json.dumps((ROOT / 'web/src/library.css').as_posix())};
const records={json.dumps(records)};
const context={json.dumps(context)};
const before=JSON.stringify(records);
const actions=[];
function freeze(value){{if(value&&typeof value==='object'){{Object.freeze(value);Object.values(value).forEach(freeze);}}return value;}}
freeze(records);freeze(context);
window.__fixture={{inspect:()=>({{before,after:JSON.stringify(records),actions}})}};
function forbidden(name){{actions.push(name);throw new Error('Unexpected fixture action '+name);}}
createRoot(document.getElementById('root')).render(<main><h1>Observation component browser fixture</h1><p>Actual candidate component; synthetic data. Production API wiring is not exercised.</p><LiteratureLibrary sources={{records}} screenings={{[]}} t={{translator('en')}} observationText={{context}} onScreen={{async()=>forbidden('screen')}} onPrepare={{()=>forbidden('prepare')}} /></main>);
'''
    (output / "entry.tsx").write_text(entry, encoding="utf-8")
    (output / "index.html").write_text('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Observation component fixture</title><link rel="stylesheet" href="/fixture.css"></head><body><div id="root"></div><script type="module" src="/fixture.js"></script></body></html>', encoding="utf-8")
    build = "const esbuild=require(" + json.dumps(str(ROOT / "web/node_modules/esbuild/lib/main.js")) + ");\n"
    build += "esbuild.build(" + json.dumps({"entryPoints": [str(output / "entry.tsx")], "bundle": True,
        "platform": "browser", "format": "esm", "target": "es2022", "jsx": "automatic",
        "nodePaths": [str(ROOT / "web/node_modules")], "outfile": str(output / "fixture.js"),
        "define": {"process.env.NODE_ENV": '"production"'}}) + ").catch(e=>{console.error(e);process.exitCode=1;});\n"
    (output / "build.cjs").write_text(build, encoding="utf-8")
    subprocess.run(["node", str(output / "build.cjs")], check=True, timeout=30)
    return manifest


class FixtureHandler(WorkspaceHandler):
    def do_GET(self):
        if not self._trusted_origin():
            return self._reply(403, {"error": "Untrusted origin"})
        path = urlsplit(self.path).path
        allowed = {"/": ("index.html", "text/html; charset=utf-8"),
                   "/fixture.js": ("fixture.js", "text/javascript; charset=utf-8"),
                   "/fixture.css": ("fixture.css", "text/css; charset=utf-8")}
        self.server.fixture_requests.append({"method": "GET", "path": path})
        if path == "/favicon.ico":
            return self._reply(204, b"", "image/x-icon")
        if path not in allowed:
            return self._reply(404, {"error": "No fixture route"})
        name, mime = allowed[path]
        return self._reply(200, (self.server.fixture_output / name).read_bytes(), mime)

    def reject_write(self):
        self.server.write_attempts.append(self.command)
        if not self._trusted_origin():
            return self._reply(403, {"error": "Untrusted origin"})
        return self._reply(405, {"error": "Read-only fixture"})

    do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = reject_write


def run(output: Path, *, port: int = 0):
    from importlib.metadata import version
    from playwright.sync_api import expect, sync_playwright

    started = time.monotonic()
    output = output.resolve()
    manifest = build_fixture(output)
    report = {"kind": "component-browser-fixture", "production_API_or_DB_exercised": False,
              "source_fingerprint": manifest["source_fingerprint"], "python_pid": os.getpid(), "checks": [],
              "checkout_commit": manifest["checkout_commit"], "checkout_tree": manifest["checkout_tree"],
              "source_hash_basis": "Raw checkout bytes; LF/CRLF differences can change these hashes",
              "test_script_sha256": sha(Path(__file__).read_bytes()), "persistent_profile": False,
              "playwright_version": version("playwright"), "page_errors": [],
              "external_requests": [], "mutation_requests": [], "browser_closed": False,
              "server_stopped": False, "status": "RUNNING"}
    server = browser = context = thread = playwright = None
    try:
        # Loopback only; explicit occupied ports fail, with no alternate-port retry.
        server = ThreadingHTTPServer(("127.0.0.1", port), FixtureHandler)
        server.fixture_output = output
        base_url = f"http://127.0.0.1:{server.server_port}"
        report["fixture_origin"] = base_url
        server.daemon_threads = True
        server.fixture_requests, server.write_attempts = [], []
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(headless=True, timeout=20000)
        report["browser_version"] = browser.version
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, service_workers="block")
        context.tracing.start(screenshots=True, snapshots=True, sources=True)

        def route_request(route):
            request = route.request
            parsed = urlsplit(request.url)
            if parsed.scheme not in ("http", "https") or f"{parsed.scheme}://{parsed.netloc}" != base_url:
                report["external_requests"].append(request.url)
                return route.abort()
            if request.method not in ("GET", "HEAD"):
                report["mutation_requests"].append(request.method)
                return route.abort()
            return route.continue_()

        context.route("**/*", route_request)
        page = context.new_page()
        page.set_default_timeout(10000)
        page.on("pageerror", lambda error: report["page_errors"].append(str(error)))
        expect.set_options(timeout=10000)
        page.goto(base_url + "/", wait_until="networkidle", timeout=15000)
        library = page.get_by_role("region", name="Literature & notes", exact=True)

        def check(name):
            assert time.monotonic() - started < 120, "Fixture deadline exceeded"
            report["checks"].append({"check": name, "status": "PASS"})

        def select(title):
            library.get_by_role("button", name=title, exact=True).click()
            expect(page.get_by_role("heading", name=title, exact=True)).to_be_visible()

        def open_observation(identifier):
            summary = library.get_by_text("Generated summary draft · " + identifier, exact=True)
            if summary.locator("..").get_attribute("open") is None:
                summary.click()

        def open_provenance(identifier):
            entry = library.get_by_text("Generated summary draft · " + identifier, exact=True).locator("..")
            provenance = entry.locator(":scope > .observation-provenance")
            if provenance.get_attribute("open") is None:
                provenance.locator(":scope > summary").click()

        expect(library.get_by_text("Human preserved wording.", exact=True)).to_be_visible()
        expect(library.get_by_text("Abstract must not replace summary.", exact=True)).to_have_count(0)
        open_observation("manual-generated")
        expect(library.get_by_text("Separate generated draft; never overwrites saved prose.", exact=True)).to_be_visible()
        expect(library.get_by_text("Human preserved wording.", exact=True)).to_be_visible()
        check("Saved summary remains primary; generated draft is separate")
        entry = library.get_by_text("Generated summary draft · manual-generated", exact=True).locator("..")
        assert entry.locator(".observation-provenance").get_attribute("open") is None
        expect(library.get_by_text("direct_proceedings_full_abstract", exact=True)).not_to_be_visible()
        check("Generated body is readable while detailed provenance is still closed")
        open_provenance("manual-generated")
        library.get_by_text("Saved observation · stored-snippet", exact=True).click()
        expect(library.get_by_text("direct_proceedings_full_abstract", exact=True)).to_be_visible()
        assert library.get_by_text("abstract-snippet", exact=True).count() == 2
        expect(library.get_by_text("Role suggestion (not confirmed classification)", exact=True)).to_be_visible()
        check("Stored snippet and later reported abstract remain separate; role is only a suggestion")
        page.screenshot(path=str(output / "desktop.png"), full_page=True)

        select("Generated-only draft")
        open_observation("only-generated")
        expect(library.get_by_text("Generated-only synthetic summary.", exact=True)).to_be_visible()
        expect(library.get_by_text("No summary saved. Preliminary relevance below is not a full-paper summary.", exact=True)).to_be_visible()
        check("Generated-only body does not replace missing saved summary")
        select("Unbound draft")
        open_observation("missing-binding")
        expect(library.get_by_text("Generated summary body is unknown or not bound to this source.", exact=True)).to_be_visible()
        expect(library.get_by_text("This unbound text must never be shown.", exact=True)).to_have_count(0)
        check("Missing hash/artifact binding stays explicit unknown")

        select("Version conflict draft")
        open_observation("version-a")
        open_observation("version-b")
        expect(library.get_by_text("Version A remains separate.", exact=True)).to_be_visible()
        expect(library.get_by_text("Version B remains separate.", exact=True)).to_be_visible()
        expect(library.get_by_text("Version comparison pending; no latest version selected", exact=True)).to_have_count(1)
        open_provenance("version-a")
        open_provenance("version-b")
        expect(library.get_by_text("2023 · Version comparison pending; no latest version selected", exact=True)).to_be_visible()
        expect(library.get_by_text("2026 · Version comparison pending; no latest version selected", exact=True)).to_be_visible()
        check("Conflicting versions retained; current flag/date does not select a winner")
        page.set_viewport_size({"width": 390, "height": 844})
        expect(library).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=str(output / "narrow.png"), full_page=True)
        library.get_by_role("button", name="Back to selected item in list", exact=True).click()
        expect(library.get_by_role("button", name="Version conflict draft", exact=True)).to_be_focused()
        check("390px component viewport has no horizontal overflow; return restores row focus")

        select("Saved abstract only")
        expect(library.get_by_text("Original saved abstract.", exact=True)).to_be_visible()
        expect(library.get_by_role("region", name="Summary observations and reading history", exact=True)).to_have_count(0)
        check("Legacy abstract fallback has no added observation panel")
        library.get_by_role("button", name="Back to selected item in list", exact=True).click()
        expect(library.get_by_role("button", name="Saved abstract only", exact=True)).to_be_focused()
        select("Uncertain observation time")
        open_observation("invalid-time")
        open_provenance("invalid-time")
        observed = page.get_by_role("region", name="Summary observations and reading history", exact=True).evaluate("el => Object.fromEntries([...el.querySelectorAll('dt')].map(dt => [dt.textContent, dt.nextElementSibling.textContent]))")
        assert observed["Reported observation time (not generation or import time)"] == "Unknown / not verified"
        check("Malformed timestamp stays unknown rather than import/generation time")

        state = page.evaluate("window.__fixture.inspect()")
        assert state["before"] == state["after"] and state["actions"] == []
        assert report["external_requests"] == report["mutation_requests"] == report["page_errors"] == []
        assert server.write_attempts == []
        report["records_unchanged"] = True
        report["fixture_action_calls"] = []
        check("Zero mutation/external requests, no action callbacks, source objects unchanged")
        report["status"] = "PASS"
    except Exception as error:
        report["status"] = "FAIL"
        report["error"] = f"{type(error).__name__}: {error}"
        if context and context.pages:
            context.pages[0].screenshot(path=str(output / "failure.png"), full_page=True)
        raise
    finally:
        cleanup_errors = []
        if context:
            try:
                context.tracing.stop(path=str(output / "trace.zip"))
            except Exception as error:
                cleanup_errors.append("trace: " + str(error))
            try:
                context.close()
            except Exception as error:
                cleanup_errors.append("context: " + str(error))
        if browser:
            try:
                browser.close()
            except Exception as error:
                cleanup_errors.append("browser: " + str(error))
            report["browser_closed"] = not browser.is_connected()
        if playwright:
            try:
                playwright.stop()
            except Exception as error:
                cleanup_errors.append("playwright: " + str(error))
        if server:
            try:
                if thread and thread.is_alive():
                    server.shutdown()
            except Exception as error:
                cleanup_errors.append("server shutdown: " + str(error))
            try:
                server.server_close()
            except Exception as error:
                cleanup_errors.append("server close: " + str(error))
            try:
                if thread and thread.ident is not None:
                    thread.join(timeout=5)
            except Exception as error:
                cleanup_errors.append("server join: " + str(error))
            report["server_stopped"] = not thread or not thread.is_alive()
            report["server_requests"] = server.fixture_requests
            report["server_write_attempts"] = server.write_attempts
        if browser and not report["browser_closed"]:
            cleanup_errors.append("browser remains connected")
        if server and not report["server_stopped"]:
            cleanup_errors.append("server thread remains alive")
        report["cleanup_errors"] = cleanup_errors
        if cleanup_errors:
            report["status"] = "FAIL"
        report["elapsed_seconds"] = time.monotonic() - started
        report["production_integration_not_verified"] = True
        report["full_workspace_layout_not_verified"] = True
        report["native_200percent_zoom_not_verified"] = True
        report["source_unchanged"] = all(sha((ROOT / item["path"]).read_bytes()) == item["sha256"] for item in manifest["source_files"])
        if report["external_requests"] or report["mutation_requests"] or report["page_errors"] or not report["source_unchanged"] or (server and server.write_attempts):
            report["status"] = "FAIL"
            report.setdefault("error", "Final zero-request/error/source invariant failed")
        owned_names = ("entry.tsx", "build.cjs", "fixture.js", "fixture.css", "index.html",
                       "desktop.png", "narrow.png", "failure.png", "trace.zip")
        report["files"] = [{"name": name, "bytes": (output / name).stat().st_size,
                            "sha256": sha((output / name).read_bytes())}
                           for name in owned_names if (output / name).is_file()]
        (output / "browser-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        if report["status"] != "PASS" and sys.exc_info()[0] is None:
            raise RuntimeError(report.get("error", "Fixture cleanup failed; see report"))

    return report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New scratch directory to create; existing directories are rejected")
    parser.add_argument("--port", type=int, default=0, help="Loopback fixture port; default chooses one unused local port")
    args = parser.parse_args()
    print(json.dumps(run(args.output, port=args.port), indent=2))
