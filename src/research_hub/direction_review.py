"""Offline direction-record bindings and planned resource arithmetic.

This module checks supplied records, not scientific adequacy, human selection,
or actual runtime spending. It performs no network requests or writes.
"""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, DecimalException, localcontext
import hashlib
import json
import math
from pathlib import Path, PurePosixPath, PureWindowsPath

import yaml


FORMAT = "research-direction-review/1.0"
KINDS = frozenset({"data", "tool", "model", "license", "cost", "premise", "validation-path"})
STATES = frozenset({"supported", "contradicted", "unknown", "not-applicable"})
MAX_INPUT_BYTES = 4 * 1024 * 1024
MAX_SOURCE_BYTES = 64 * 1024 * 1024
MAX_DECIMAL_PLACES = 4096
MAX_JSON_NODES = 100000


class DirectionReviewError(ValueError):
    """A bounded, machine-readable contract error; no source text is exposed."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _require(condition, code):
    if not condition:
        raise DirectionReviewError(code)


def _text(value):
    if not isinstance(value, str) or not value.strip():
        return False
    _scalar_string(value)
    return True


def _scalar_string(value):
    try:
        value.encode("utf-8")
    except UnicodeError as exc:
        raise DirectionReviewError("non-scalar-unicode") from exc


def _fields(value, fields, code):
    _require(isinstance(value, dict) and set(value) == set(fields), code)


def _list(value, code):
    _require(isinstance(value, list), code)
    return value


def _sha(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _json_value(value, depth=0, budget=None):
    if budget is None:
        budget = [0]
    budget[0] += 1
    _require(budget[0] <= MAX_JSON_NODES, "input-node-limit")
    _require(depth <= 50, "input-nesting-limit")
    if isinstance(value, dict):
        _require(all(isinstance(key, str) for key in value), "non-string-object-key")
        for key in value:
            _scalar_string(key)
        for item in value.values():
            _json_value(item, depth + 1, budget)
    elif isinstance(value, list):
        for item in value:
            _json_value(item, depth + 1, budget)
    else:
        _require(value is None or type(value) in {str, int, float, bool, Decimal}, "non-json-value")
        if isinstance(value, str):
            _scalar_string(value)
        if isinstance(value, float):
            _require(math.isfinite(value), "non-finite-value")
        if isinstance(value, Decimal):
            _require(value.is_finite(), "non-finite-value")
            digits, exponent = value.as_tuple().digits, value.as_tuple().exponent
            _require(len(digits) + abs(exponent) <= MAX_DECIMAL_PLACES, "numeric-precision-limit")


def dumps_direction_json(value, *, pretty=True, sort_keys=False) -> str:
    """Emit finite exact decimals as JSON numbers, without binary64 rounding.

    Decimal's finite spelling is a JSON number (including exponent notation).
    All strings/keys still use the standard JSON escaper. No token substitution
    or precision-losing float conversion is used.
    """
    _json_value(value)

    def encode(item, level=0):
        if isinstance(item, Decimal):
            return str(item)
        if isinstance(item, (dict, list)):
            if not item:
                return "{}" if isinstance(item, dict) else "[]"
            if isinstance(item, dict):
                pairs = sorted(item.items()) if sort_keys else item.items()
                parts = [json.dumps(key, ensure_ascii=False) + (": " if pretty else ":")
                         + encode(val, level + 1) for key, val in pairs]
                opening, closing = "{", "}"
            else:
                parts = [encode(val, level + 1) for val in item]
                opening, closing = "[", "]"
            if pretty:
                indent = "  " * (level + 1)
                return opening + "\n" + indent + (",\n" + indent).join(parts) + "\n" + "  " * level + closing
            return opening + ",".join(parts) + closing
        return json.dumps(item, ensure_ascii=False, allow_nan=False, separators=(",", ":"))

    try:
        return encode(value)
    except (ValueError, UnicodeError, RecursionError, OverflowError) as exc:
        raise DirectionReviewError("input-malformed") from exc


def candidate_sha256(candidate: dict) -> str:
    """Identify the complete candidate, including its explicit version."""
    return hashlib.sha256(dumps_direction_json(candidate, pretty=False, sort_keys=True).encode("utf-8")).hexdigest()


def _quantity(value):
    if value is None:
        return True
    if type(value) not in {int, float, Decimal} or value < 0:
        return False
    try:
        return math.isfinite(float(value))
    except (OverflowError, ValueError):
        return False


def _decimal(value):
    # Decimal inputs retain the original JSON token; API float inputs use the
    # caller's shortest decimal spelling, not their binary expansion.
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _exact_sum(values):
    numbers = [_decimal(value) for value in values]
    minimum_exponent = min(value.as_tuple().exponent for value in numbers)
    maximum_adjusted = max(value.adjusted() for value in numbers)
    # Nonnegative addends need their entire aligned coefficient plus carry
    # space. The normal Decimal context (28 digits) would still lose large + 1.
    precision = max(1, maximum_adjusted - minimum_exponent + 1) + len(str(len(numbers))) + 1
    with localcontext() as context:
        context.prec = precision
        total = sum(numbers, Decimal(0))
    _require(_quantity(total), "resource-total-overflow")
    _json_value(total)
    return int(total) if total == total.to_integral_value() else total


def _unique_texts(value, code, *, nonempty=False):
    _list(value, code)
    _require((bool(value) or not nonempty) and all(_text(v) for v in value), code)
    _require(len(value) == len(set(value)), code)
    return value


def _candidate_ref(value):
    _fields(value, {"candidate_id", "candidate_version", "candidate_sha256"}, "candidate-ref-shape")
    _require(_text(value["candidate_id"]), "candidate-id-invalid")
    _require(type(value["candidate_version"]) is int and value["candidate_version"] >= 1,
             "candidate-version-invalid")
    _require(_sha(value["candidate_sha256"]), "candidate-hash-invalid")
    return value["candidate_id"]


def _check_ref(value, refs):
    key = _candidate_ref(value)
    _require(key in refs and value == refs[key], "candidate-ref-not-in-review")
    return key


def _linked(path):
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    return path.is_symlink() or bool(attributes & 0x400) or (
        hasattr(path, "is_junction") and path.is_junction()
    )


def _source_hash(root, relative):
    """Check manifest-controlled components before resolving or reading them."""
    if (not _text(relative) or "\\" in relative or ":" in relative
            or PurePosixPath(relative).is_absolute() or PureWindowsPath(relative).drive
            or any(part in {"", ".", ".."} for part in relative.split("/"))):
        return "invalid-path", None
    path = root
    try:
        for part in relative.split("/"):
            path = path / part
            if _linked(path):
                return "linked-path", None
        if not path.is_file():
            return "not-file", None
        path.resolve(strict=True).relative_to(root)
        size = 0
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(65536):
                size += len(chunk)
                if size > MAX_SOURCE_BYTES:
                    return "source-too-large", None
                digest.update(chunk)
        return "read", digest.hexdigest()
    except FileNotFoundError:
        return "unavailable", None
    except (OSError, ValueError):
        return "unreadable", None


def _evidence(review, root):
    refs = {}
    bindings = []
    for row in _list(review["evidence"], "evidence-list-required"):
        _fields(row, {"id", "path", "sha256", "locator", "evidence_level", "publication_version"},
                "evidence-shape")
        _require(_text(row["id"]) and row["id"] not in refs, "duplicate-or-invalid-evidence-id")
        _require(_sha(row["sha256"]), "evidence-hash-invalid")
        _require(all(_text(row[key]) for key in ("path", "locator", "evidence_level", "publication_version")),
                 "evidence-description-required")
        status, actual = _source_hash(root, row["path"])
        if status == "read":
            status = "current" if actual == row["sha256"] else "changed"
        bindings.append({"evidence_id": row["id"], "status": status,
                         "expected_sha256": row["sha256"], "actual_sha256": actual,
                         "locator": row["locator"], "locator_verification": "not-performed",
                         "evidence_level": row["evidence_level"],
                         "publication_version": row["publication_version"],
                         "publication_version_status": ("unknown" if row["publication_version"].strip().lower()
                             == "unknown" else "recorded-not-verified")})
        refs[row["id"]] = row
    return refs, bindings


def _evidence_refs(value, evidence, *, required=False):
    _unique_texts(value, "evidence-refs-invalid", nonempty=required)
    _require(set(value).issubset(evidence), "evidence-ref-missing")


def _resource_review(resources, refs, checks, evidence):
    _fields(resources, {"requirements", "components", "capacities"}, "resources-shape")
    costs = {key: [row for row in checks if row["candidate_ref"]["candidate_id"] == key
                  and row["kind"] == "cost"] for key in refs}
    requirements = {}
    for row in _list(resources["requirements"], "requirements-list-required"):
        _fields(row, {"candidate_ref", "units"}, "resource-requirement-shape")
        key = _check_ref(row["candidate_ref"], refs)
        _require(key not in requirements, "duplicate-resource-requirement")
        if row["units"] is not None:
            _unique_texts(row["units"], "required-units-invalid")
            if not row["units"]:
                _require(all(check["status"] == "not-applicable" for check in costs[key]),
                         "applicable-cost-requires-units")
        requirements[key] = row["units"]
    unknown_scope = sorted(key for key in refs if requirements.get(key) is None)
    components = []
    component_ids = set()
    for row in _list(resources["components"], "components-list-required"):
        _fields(row, {"component_id", "candidate_refs", "unit", "amount", "estimate_basis",
                      "evidence_refs", "sharing_basis"}, "resource-component-shape")
        _require(_text(row["component_id"]) and row["component_id"] not in component_ids,
                 "duplicate-or-invalid-component-id")
        component_ids.add(row["component_id"])
        _require(_text(row["unit"]) and _quantity(row["amount"]) and _text(row["estimate_basis"]),
                 "resource-estimate-invalid")
        keys = [_check_ref(ref, refs) for ref in _list(row["candidate_refs"], "component-scope-required")]
        _require(bool(keys) and len(keys) == len(set(keys)), "component-scope-invalid")
        for key in keys:
            _require(requirements.get(key) is None or row["unit"] in requirements[key],
                     "component-unit-not-declared")
        _evidence_refs(row["evidence_refs"], evidence, required=row["amount"] is not None)
        _require(row["sharing_basis"] is None or _text(row["sharing_basis"]), "sharing-basis-invalid")
        # Missing shared-work justification leaves an unresolved estimate, not a discount.
        unresolved_sharing = len(keys) > 1 and not _text(row["sharing_basis"])
        components.append((row, keys, unresolved_sharing))
    capacities = {}
    for row in _list(resources["capacities"], "capacities-list-required"):
        _fields(row, {"unit", "amount", "decision_ref"}, "capacity-shape")
        _require(_text(row["unit"]) and row["unit"] not in capacities and _quantity(row["amount"]),
                 "capacity-invalid")
        _require(_text(row["decision_ref"]), "capacity-decision-ref-required")
        capacities[row["unit"]] = row
    units = set(capacities)
    for wanted in requirements.values():
        if wanted is not None:
            units.update(wanted)
    units.update(row["unit"] for row, _, _ in components)
    totals = []
    for unit in sorted(units):
        parts = [(row, keys, shared) for row, keys, shared in components if row["unit"] == unit]
        wanted = {key for key, values in requirements.items() if values is not None and unit in values}
        covered = {key for _, keys, _ in parts for key in keys}
        missing = sorted(wanted - covered)
        unresolved = sorted(row["component_id"] for row, _, shared in parts
                            if row["amount"] is None or shared)
        demand = None if missing or unresolved or unknown_scope or not parts else _exact_sum(
            [row["amount"] for row, _, _ in parts])
        capacity = capacities.get(unit, {}).get("amount")
        status = "unknown" if demand is None or capacity is None else (
            "exceeds-estimate" if _decimal(demand) > _decimal(capacity) else "within-estimate")
        totals.append({"unit": unit, "demand": demand, "capacity": capacity, "status": status,
                       "missing_candidate_ids": missing, "unresolved_component_ids": unresolved})
    statuses = {row["status"] for row in totals}
    overall = "exceeds-estimate" if "exceeds-estimate" in statuses else (
        "unknown" if unknown_scope or "unknown" in statuses else (
            "within-estimate" if totals else "not-applicable"))
    return {"status": overall, "totals": totals, "unknown_requirement_candidate_ids": unknown_scope,
            "requirements": deepcopy(resources["requirements"]),
            "components": deepcopy(resources["components"]),
            "capacities": deepcopy(resources["capacities"]),
            "runtime_budget_verification": "not-performed"}


def validate_direction_review(dossier: dict, review: dict, source_root: Path) -> dict:
    """Validate supplied records and bind only the candidates explicitly in scope."""
    _json_value(review)
    _fields(review, {"format", "candidate_refs", "evidence", "checks", "resources"}, "review-shape")
    _require(review["format"] == FORMAT, "unsupported-review-format")
    _require(isinstance(dossier, dict), "dossier-object-required")
    candidates = {}
    for row in _list(dossier.get("gaps"), "dossier-gaps-required"):
        _require(isinstance(row, dict) and _text(row.get("id")), "dossier-candidate-invalid")
        _require(row["id"] not in candidates, "duplicate-dossier-candidate")
        candidates[row["id"]] = row
    refs = {}
    candidate_bindings = []
    for ref in _list(review["candidate_refs"], "candidate-refs-required"):
        key = _candidate_ref(ref)
        _require(key not in refs, "duplicate-candidate-ref")
        refs[key] = ref
        candidate = candidates.get(key)
        if candidate is None:
            status = "missing-candidate"
        elif type(candidate.get("candidate_version")) is not int or candidate["candidate_version"] < 1:
            status = "missing-candidate-version"
        else:
            status = "current" if (candidate["candidate_version"] == ref["candidate_version"]
                and candidate_sha256(candidate) == ref["candidate_sha256"]) else "stale-candidate"
        candidate_bindings.append({"candidate_id": key, "status": status})
    _require(bool(refs), "candidate-scope-empty")
    try:
        supplied_root = Path(source_root).absolute()
        for component in reversed((supplied_root, *supplied_root.parents)):
            _require(not _linked(component), "source-root-linked")
        root = supplied_root.resolve(strict=True)
        _require(root.is_dir(), "source-root-not-directory")
    except (OSError, RuntimeError) as exc:
        raise DirectionReviewError("source-root-unavailable") from exc
    evidence, evidence_bindings = _evidence(review, root)
    checks = _list(review["checks"], "checks-list-required")
    seen = set()
    covered = set()
    for row in checks:
        _fields(row, {"check_id", "candidate_ref", "kind", "statement", "status", "evidence_refs",
                      "reason", "next_check"}, "check-shape")
        _require(_text(row["check_id"]) and row["check_id"] not in seen, "duplicate-or-invalid-check-id")
        seen.add(row["check_id"])
        key = _check_ref(row["candidate_ref"], refs)
        _require(_text(row["kind"]) and row["kind"] in KINDS, "check-kind-invalid")
        _require(_text(row["status"]) and row["status"] in STATES, "check-status-invalid")
        _require(_text(row["statement"]) and _text(row["reason"]), "check-description-required")
        _evidence_refs(row["evidence_refs"], evidence, required=row["status"] in {"supported", "contradicted"})
        _require(row["next_check"] is None or _text(row["next_check"]), "next-check-invalid")
        _require(row["status"] != "unknown" or _text(row["next_check"]), "unknown-requires-next-check")
        covered.add((key, row["kind"]))
    _require(covered == {(key, kind) for key in refs for kind in KINDS}, "missing-prerequisite-category")
    resources = _resource_review(review["resources"], refs, checks, evidence)
    binding_current = all(row["status"] == "current" for row in candidate_bindings + evidence_bindings)
    if not binding_current:
        # Retain arithmetic as diagnostic detail, never promote stale input estimates.
        resources["arithmetic_status"] = resources["status"]
        resources["status"] = "unknown"
        for row in resources["totals"]:
            row["arithmetic_status"] = row["status"]
            row["status"] = "unknown"
    return {"format": "research-direction-check/1.0", "record_status": "valid",
            "binding_status": "current" if binding_current else "not-current",
            "candidate_bindings": candidate_bindings, "evidence_bindings": evidence_bindings,
            "prerequisites": deepcopy(checks), "resource_estimates": resources,
            "semantic_assessment": "not-performed", "human_selection": "outside-checker",
            "execution_authorized": False,
            "limitations": ["Bindings identify supplied bytes, not source authenticity or semantic support.",
                            "Estimates do not verify runtime usage, approve a budget or choose a direction."]}


class _UniqueLoader(yaml.SafeLoader):
    def compose_node(self, parent, index):
        # A tiny alias DAG can expand exponentially despite the raw-byte and
        # depth limits. This optional checker deliberately accepts no aliases.
        if self.check_event(yaml.AliasEvent):
            raise DirectionReviewError("yaml-alias-not-supported")
        return super().compose_node(parent, index)


def _mapping(loader, node, deep=False):
    pairs = loader.construct_pairs(node, deep=deep)
    result = {}
    for key, value in pairs:
        _require(isinstance(key, str), "non-string-object-key")
        _require(key not in result, "duplicate-object-key")
        result[key] = value
    return result


_UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def _json_pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "duplicate-object-key")
        result[key] = value
    return result


def _parse_decimal(token):
    try:
        return Decimal(token)
    except DecimalException as exc:
        # A short exponent can exceed Decimal's constructor range before
        # as_tuple/precision validation is possible.
        raise DirectionReviewError("numeric-precision-limit") from exc


def _read_input(path):
    try:
        with Path(path).open("rb") as handle:
            raw = handle.read(MAX_INPUT_BYTES + 1)
        _require(len(raw) <= MAX_INPUT_BYTES, "input-too-large")
        return raw, raw.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise DirectionReviewError("input-unreadable") from exc


def check_direction_review(dossier_path, review_path, source_root) -> dict:
    """Read an explicit YAML dossier and JSON review, returning no write side effects."""
    dossier_raw, dossier_text = _read_input(dossier_path)
    review_raw, review_text = _read_input(review_path)
    try:
        dossier = yaml.load(dossier_text, Loader=_UniqueLoader)
        review = json.loads(review_text, object_pairs_hook=_json_pairs, parse_float=_parse_decimal)
        result = validate_direction_review(dossier, review, Path(source_root))
    except DirectionReviewError:
        raise
    except (yaml.YAMLError, ValueError, TypeError, RecursionError, OverflowError) as exc:
        raise DirectionReviewError("input-malformed") from exc
    result["input_receipts"] = {"dossier_sha256": hashlib.sha256(dossier_raw).hexdigest(),
                                "review_sha256": hashlib.sha256(review_raw).hexdigest()}
    return result
