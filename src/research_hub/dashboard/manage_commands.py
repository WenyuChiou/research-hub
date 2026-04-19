"""Python mirror of dashboard command-builder logic from ``script.js``.

This module exists so dashboard command construction can be unit tested
without browser automation. The goal is parity with the static JS logic
used by the dashboard's Manage and Writing tabs.
"""

from __future__ import annotations


def shell_quote(value: str | None) -> str:
    """Mirror ``script.js`` shellQuote().

    Safe bare words stay unquoted. Everything else is wrapped in double
    quotes with backslashes and double quotes escaped.
    """
    if value is None:
        return '""'
    text = str(value)
    if text and all(ch.isalnum() or ch in "_./-" for ch in text):
        return text
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def build_manage_command(action: str, slug: str, **fields) -> str | None:
    """Build the dashboard manage-tab CLI command.

    Returns ``None`` for incomplete action-specific inputs, matching the
    browser implementation. Raises ``ValueError`` for unknown actions so
    tests fail loudly if the Python mirror drifts from the supported set.
    """
    if action == "rename":
        new_name = str(fields.get("new_name", "") or "").strip()
        if not new_name:
            return None
        return f"research-hub clusters rename {shell_quote(slug)} --name {shell_quote(new_name)}"
    if action == "merge":
        target = str(fields.get("target", "") or "").strip()
        if not target or target == slug:
            return None
        return f"research-hub clusters merge {shell_quote(slug)} --into {shell_quote(target)}"
    if action == "split":
        query = str(fields.get("query", "") or "").strip()
        new_name = str(fields.get("new_name", "") or "").strip()
        if not query or not new_name:
            return None
        return (
            f"research-hub clusters split {shell_quote(slug)} "
            f"--query {shell_quote(query)} "
            f"--new-name {shell_quote(new_name)}"
        )
    if action == "bind-zotero":
        key = str(fields.get("zotero", "") or "").strip()
        if not key:
            return None
        return f"research-hub clusters bind {shell_quote(slug)} --zotero {shell_quote(key)}"
    if action == "bind-nlm":
        notebooklm = str(fields.get("notebooklm", "") or "").strip()
        if not notebooklm:
            return None
        return f"research-hub clusters bind {shell_quote(slug)} --notebooklm {shell_quote(notebooklm)}"
    if action == "delete":
        return f"research-hub clusters delete {shell_quote(slug)} --dry-run"
    if action == "notebooklm-bundle":
        return f"research-hub notebooklm bundle --cluster {shell_quote(slug)}"
    if action == "notebooklm-upload":
        visible = bool(fields.get("visible", False))
        cmd = f"research-hub notebooklm upload --cluster {shell_quote(slug)}"
        if visible:
            cmd += " --visible"
        else:
            cmd += " --headless"
        return cmd
    if action == "notebooklm-generate":
        kind = str(fields.get("kind", "brief") or "brief").strip()
        if kind not in {"brief", "audio", "mind_map", "video"}:
            return None
        cli_kind = "mind-map" if kind == "mind_map" else kind
        return f"research-hub notebooklm generate --cluster {shell_quote(slug)} --type {cli_kind}"
    if action == "notebooklm-download":
        kind = str(fields.get("kind", "brief") or "brief").strip()
        if kind != "brief":
            return None
        return f"research-hub notebooklm download --cluster {shell_quote(slug)} --type {kind}"
    if action == "notebooklm-ask":
        question = str(fields.get("question", "") or "").strip()
        if not question:
            return None
        cmd = (
            f"research-hub notebooklm ask --cluster {shell_quote(slug)} "
            f"--question {shell_quote(question)}"
        )
        timeout = str(fields.get("timeout", "") or "").strip()
        if timeout.isdigit():
            cmd += f" --timeout {timeout}"
        return cmd
    if action == "vault-polish-markdown":
        apply = bool(fields.get("apply", False))
        cmd = f"research-hub vault polish-markdown --cluster {shell_quote(slug)}"
        if apply:
            cmd += " --apply"
        return cmd
    if action == "bases-emit":
        force = bool(fields.get("force", False))
        cmd = f"research-hub bases emit --cluster {shell_quote(slug)}"
        if force:
            cmd += " --force"
        return cmd
    raise ValueError(f"unknown action: {action!r}")


def build_compose_draft_command(
    cluster_slug: str,
    outline: str = "",
    quote_slugs: list[str] | None = None,
    style: str = "apa",
) -> str:
    """Mirror the dashboard composer form's CLI command builder."""
    parts = ["research-hub compose-draft", "--cluster", shell_quote(cluster_slug)]
    if outline:
        parts.extend(["--outline", shell_quote(outline)])
    if quote_slugs:
        parts.extend(["--quotes", shell_quote(",".join(quote_slugs))])
    if style and style != "apa":
        parts.extend(["--style", style])
    return " ".join(parts)
