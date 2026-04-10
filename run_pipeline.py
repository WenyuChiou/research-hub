import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from hub_config import get_config

_cfg = get_config()
KB = str(_cfg.root)
LOG = str(_cfg.logs / "pipeline_log.txt")
OUT = str(_cfg.root / "pipeline_test_output.json")
PAPERS_JSON = str(_cfg.root / "papers_input.json")
ERRORS_LOG = str(_cfg.logs / f"pipeline_errors_{int(time.time())}.jsonl")

from zotero_client import add_note, check_duplicate, get_client

COLL = "XZ22GHJA"
log = open(LOG, "w", encoding="utf-8")


def p(message):
    log.write(message + "\n")
    log.flush()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Validate config and input, no writes")
    args = parser.parse_args()

    p("=== PIPELINE START ===")
    if args.dry_run:
        p("DRY RUN MODE - no writes will be made")
        p(f"Config root: {KB}")
        if not Path(PAPERS_JSON).exists():
            p(f"NOTE: {PAPERS_JSON} not found — this is expected in a fresh setup.")
            p("DRY RUN: Config and imports OK. Ready to run. Exiting.")
            return

    with open(PAPERS_JSON, "r", encoding="utf-8") as file_obj:
        papers = json.load(file_obj)
    p(f"Loaded {len(papers)} papers")

    if args.dry_run:
        p(f"DRY RUN: would process {len(papers)} papers. Config OK. Exiting.")
        return

    zot = get_client()
    p("Zotero client ready")
    zr = []
    obr = []
    dr = []
    errors = []

    for i, pp in enumerate(papers):
        p(f"\n--- Paper {i+1}: {pp['title'][:60]}...")
        try:
            dup = check_duplicate(zot, pp["title"], pp["doi"])
        except Exception:
            dup = False
        if dup:
            p("  SKIPPED dup")
            zr.append({"title": pp["title"], "status": "SKIPPED_DUPLICATE", "key": ""})
            continue
        t = zot.item_template("journalArticle")
        t["title"] = pp["title"]
        t["creators"] = pp["authors"]
        t["date"] = pp["year"]
        t["DOI"] = pp["doi"]
        t["url"] = pp["url"]
        t["publicationTitle"] = pp["journal"]
        t["abstractNote"] = pp["abstract"]
        t["tags"] = [{"tag": x} for x in pp["tags"]]
        t["collections"] = [COLL]
        try:
            resp = zot.create_items([t])
            if resp.get("successful"):
                key = list(resp["successful"].values())[0]["key"]
                p(f"  CREATED: {key}")
                pp["zotero_key"] = key
                zr.append({"title": pp["title"], "status": "CREATED", "key": key})
                nh = "<h1>Summary</h1><p>" + pp["summary"] + "</p>"
                nh += "<h2>Key Findings</h2><ul>" + "".join(
                    "<li>" + x + "</li>" for x in pp["key_findings"]
                ) + "</ul>"
                nh += "<h2>Methodology</h2><p>" + pp["methodology"] + "</p>"
                nh += "<h2>Relevance</h2><p>" + pp["relevance"] + "</p>"
                ok = add_note(zot, key, nh)
                p(f"  Note: {'OK' if ok else 'FAIL'}")
            else:
                p(f"  RESP: {resp}")
                zr.append({"title": pp["title"], "status": "FAILED", "key": ""})
        except Exception as e:
            p(f"  ERR: {e}")
            zr.append({"title": pp["title"], "status": "ERROR", "key": ""})
            errors.append(
                {
                    "paper": pp["title"],
                    "step": "zotero",
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                }
            )
        time.sleep(1)

    p("\n=== OBSIDIAN NOTES ===")
    for pp in papers:
        sc = pp["sub_category"]
        folder = os.path.join(KB, "raw", sc)
        os.makedirs(folder, exist_ok=True)
        fp = os.path.join(folder, pp["slug"] + ".md")
        zk = pp.get("zotero_key", "")
        rel = [x["slug"] for x in papers if x["slug"] != pp["slug"]]
        wl = ["[[LLM-Agents]]", "[[Agent-Based-Modeling]]"]
        if "behavioral" in (pp["title"] + " ".join(pp["tags"])).lower():
            wl.append("[[Bounded-Rationality]]")
        if "policy" in pp["title"].lower():
            wl.append("[[Climate-Adaptation]]")
        if "urban" in pp["title"].lower():
            wl.append("[[Disaster-Preparedness]]")
        md = "---\n"
        md += 'title: "' + pp["title"] + '"\n'
        md += 'authors: "' + pp["authors_str"] + '"\n'
        md += "year: " + pp["year"] + "\n"
        md += 'journal: "' + pp["journal"] + '"\n'
        md += 'doi: "' + pp["doi"] + '"\n'
        md += 'zotero-key: "' + zk + '"\n'
        md += 'collections: ["LLM AI agent","Paper3-WRR-LLM-Flood-ABM"]\n'
        md += "tags: " + json.dumps(pp["tags"]) + "\n"
        md += 'category: "' + pp["category"] + '"\n'
        md += 'method-type: "' + pp["method_type"] + '"\n'
        md += 'sub-category: "' + sc + '"\n'
        md += 'status: "unread"\nthesis-chapter: ""\nresearch-questions: []\n'
        md += "citation-count: " + str(pp["citations"]) + "\n"
        md += "related-papers: " + json.dumps(rel) + "\n"
        md += "---\n\n# " + pp["title"] + "\n\n## Summary\n\n" + pp["summary"] + "\n\n## Key Findings\n\n"
        for finding in pp["key_findings"]:
            md += "- " + finding + "\n"
        md += "\n## Methodology\n\n" + pp["methodology"] + "\n\n## Relevance\n\n" + pp["relevance"] + "\n\n## Wiki Links\n\n"
        for wiki_link in wl:
            md += "- " + wiki_link + "\n"
        try:
            with open(fp, "w", encoding="utf-8") as fh:
                fh.write(md)
            p(f"  OK: {fp}")
            obr.append({"file": fp, "status": "CREATED"})
        except Exception as e:
            p(f"  ERR: {fp} {e}")
            obr.append({"file": fp, "status": "ERROR"})
            errors.append(
                {
                    "paper": pp["title"],
                    "step": "obsidian",
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                }
            )

    p("\n=== DOI VALIDATION ===")
    for pp in papers:
        doi = pp["doi"]
        url = pp.get("url", "")
        if "arxiv.org" in url:
            best, typ, ok = url, "arXiv", True
        elif pp.get("pdf_url") and "doi.org" not in pp.get("pdf_url", ""):
            best, typ, ok = pp["pdf_url"], "Direct", True
        elif doi:
            best, typ, ok = "https://doi.org/" + doi, "DOI", "48550" in doi
        else:
            best, typ, ok = "", "NONE", False
        dr.append({"title": pp["title"][:50], "best_url": best, "type": typ, "accessible": ok})
        p(f"  [{'OK' if ok else 'WALL'}] {pp['title'][:50]}... -> {typ}")

    cr = sum(1 for r in zr if r["status"] == "CREATED")
    sk = sum(1 for r in zr if r["status"] == "SKIPPED_DUPLICATE")
    fl = sum(1 for r in zr if r["status"] in ("FAILED", "ERROR"))
    oc = sum(1 for r in obr if r["status"] == "CREATED")
    da = sum(1 for r in dr if r["accessible"])
    p(
        f"\n=== SUMMARY ===\nPapers: {len(papers)}\nZotero created: {cr}\nZotero skipped: {sk}\nZotero failed: {fl}\nObsidian created: {oc}\nDOIs accessible: {da}"
    )
    out = {
        "zotero_results": zr,
        "obsidian_results": obr,
        "doi_results": dr,
        "papers": [
            {
                "title": x["title"],
                "slug": x["slug"],
                "zotero_key": x.get("zotero_key", ""),
                "sub_category": x["sub_category"],
            }
            for x in papers
        ],
    }
    with open(OUT, "w", encoding="utf-8") as file_obj:
        json.dump(out, file_obj, indent=2, ensure_ascii=False)
    if errors:
        with open(ERRORS_LOG, "w", encoding="utf-8") as error_file:
            for err in errors:
                error_file.write(json.dumps(err, ensure_ascii=False) + "\n")
        p(f"Errors logged: {ERRORS_LOG}")
    p(f"JSON: {OUT}\n=== DONE ===")


try:
    main()
except Exception:
    p(traceback.format_exc())
finally:
    log.close()
