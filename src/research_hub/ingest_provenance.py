"""Keep research evidence when candidates collapse or reuse existing notes."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import yaml

from research_hub.security import atomic_write_text


def validate_evidence_metadata(paper: dict, index: int) -> list[str]:
    errors = []
    provenance = paper.get("provenance")
    if provenance is not None and not isinstance(provenance, dict):
        errors.append(f"Paper {index}: 'provenance' must be an object")
    records = paper.get("source_records")
    if records is not None and (
        not isinstance(records, list) or any(not isinstance(record, dict) for record in records)
    ):
        errors.append(f"Paper {index}: 'source_records' must be a list of objects")
    return errors


def _merge_values(existing, incoming):
    """Add missing metadata and distinct observations; keep original scalars."""
    if isinstance(existing, dict) and isinstance(incoming, dict):
        merged = copy.deepcopy(existing)
        for key, value in incoming.items():
            merged[key] = _merge_values(merged[key], value) if key in merged else copy.deepcopy(value)
        return merged
    if isinstance(existing, list) and isinstance(incoming, list):
        merged = copy.deepcopy(existing)
        for value in incoming:
            if value not in merged:
                merged.append(copy.deepcopy(value))
        return merged
    return copy.deepcopy(incoming if existing is None else existing)


def merge_paper_evidence(paper: dict, incoming: dict) -> None:
    """Merge only evidence fields, leaving paper content and reading state alone."""
    for field in ("provenance", "source_records"):
        value = incoming.get(field)
        if value:
            paper[field] = _merge_values(paper.get(field), value)


def replace_yaml_field(frontmatter: str, field: str, value) -> str:
    # YAML node offsets let us replace this field without reserializing a
    # user's other frontmatter, comments, or paper annotations.
    document = yaml.compose(frontmatter, Loader=yaml.SafeLoader)
    if not isinstance(document, yaml.MappingNode):
        raise ValueError("Paper note frontmatter must be a mapping")
    matches = [(key, item) for key, item in document.value if key.value == field]
    if len(matches) > 1:
        raise ValueError(f"Paper note has duplicate '{field}' fields")
    line = f"{field}: {json.dumps(value, ensure_ascii=False)}"
    if not matches:
        return frontmatter.rstrip("\n") + "\n" + line + "\n"
    key, item = matches[0]
    start, end = key.start_mark.index, item.end_mark.index
    if item.start_mark.index < key.end_mark.index:
        raise ValueError(f"Cannot safely update aliased '{field}' metadata")
    tokens = list(yaml.scan(frontmatter, Loader=yaml.SafeLoader))
    if any(
        isinstance(token, (yaml.tokens.AnchorToken, yaml.tokens.AliasToken))
        and start <= token.start_mark.index < end
        for token in tokens
    ):
        raise ValueError(f"Cannot safely update anchored or aliased '{field}' metadata")
    # Collection-node end marks include comments between this value and the
    # next key. Stop at its last actual content token to preserve those lines.
    content_ends = [
        token.end_mark.index
        for token in tokens
        if isinstance(token, (
            yaml.tokens.ScalarToken, yaml.tokens.FlowSequenceEndToken,
            yaml.tokens.FlowMappingEndToken, yaml.tokens.ValueToken,
            yaml.tokens.BlockEntryToken,
        ))
        and item.start_mark.index <= token.start_mark.index < end
    ]
    if content_ends:
        end = max(content_ends)
    if frontmatter[start:end].endswith("\n"):
        line += "\n"
    return frontmatter[:start] + line + frontmatter[end:]


def merge_note_evidence(
    note_path: Path, incoming: dict, *, query: str | None = None, topic_cluster: str = ""
) -> bool:
    """Append research provenance to an existing note without replacing its body."""
    if not query and not any(incoming.get(field) for field in ("provenance", "source_records")):
        return False
    text = note_path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError("Paper note has no YAML frontmatter")
    end = text.find("\n---", 4)
    if end < 0:
        raise ValueError("Paper note has no closing frontmatter delimiter")
    frontmatter = text[4:end]
    existing = yaml.safe_load(frontmatter)
    if not isinstance(existing, dict):
        raise ValueError("Paper note frontmatter must be a mapping")
    errors = validate_evidence_metadata(existing, 0)
    if errors:
        raise ValueError("; ".join(errors))
    merged = copy.deepcopy(existing)
    merge_paper_evidence(merged, incoming)
    fields = ["provenance", "source_records"]
    if query:
        queries = existing.get("cluster_queries") or []
        if not isinstance(queries, list):
            raise ValueError("Paper note 'cluster_queries' must be a list")
        if query not in queries:
            merged["cluster_queries"] = [*queries, query]
            for field, value in (("topic_cluster", topic_cluster), ("verified", False), ("status", "unread")):
                if field not in merged:
                    merged[field] = value
            fields.extend(["cluster_queries", "topic_cluster", "verified", "status"])
    changed = False
    for field in fields:
        if merged.get(field) != existing.get(field):
            frontmatter = replace_yaml_field(frontmatter, field, merged[field])
            changed = True
    if changed:
        yaml.safe_load(frontmatter)
        atomic_write_text(note_path, "---\n" + frontmatter.rstrip("\n") + text[end:])
    return changed
