# Security policy

## Supported versions

Only the most recent **minor** release receives security fixes. Older minors are best-effort. We backport critical fixes when feasible.

| Version | Supported |
|---|---|
| 0.40.x | ✅ |
| 0.39.x | ✅ critical only |
| < 0.39 | ❌ |

## Reporting a vulnerability

**Do not open a public GitHub issue for security reports.** Instead:

1. Email **wenyuchiou1234@gmail.com** with subject prefix `[SECURITY] research-hub:`.
2. Include:
   - Affected version (`pip show research-hub-pipeline`)
   - Steps to reproduce
   - Expected vs actual behavior
   - Proof-of-concept if available (private gist link is fine)
3. Expect acknowledgement within **5 working days**.
4. Coordinated disclosure window: **30 days** from acknowledgement, or sooner if a fix is available and deployed.

## Threat model and assumptions

research-hub is a **local-first** tool. It runs on the user's own machine, reads/writes to the user's home directory, and talks to APIs the user has explicitly configured (Zotero, NotebookLM via Chrome, OpenAlex, arXiv, Semantic Scholar). It does **not**:

- Send any data to research-hub-operated servers (no telemetry, no analytics, no version-check phone-home — verified in `audit_v0.39.md`).
- Store credentials in cleartext after `init` (Zotero key is encrypted via Fernet at rest; see `src/research_hub/security/secret_box.py`).
- Execute remote code or fetch unsigned Python from the internet.

In-scope vulnerabilities include:

- Path traversal via cluster slugs, paper slugs, file paths
- Credential exposure (Zotero key, encryption salts)
- Code injection via frontmatter, Markdown, or imported documents
- MCP tool input validation bypass (slug validation, identifier validation)
- Browser automation hijacking (NotebookLM via CDP)

Out of scope:

- Social engineering against the user
- Compromised local OS / Python environment
- Bugs in third-party dependencies (report to those projects directly)

## What we won't do

- Pay bug bounties (this is a single-maintainer open-source project).
- Promise faster than 5-day acknowledgement.
- Backport security fixes more than 1 minor version back.

Thank you for helping keep research-hub safe for the academic + research community.
