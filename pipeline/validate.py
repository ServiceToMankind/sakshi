"""Schema validation + summary-size gate.

``schemas/case.schema.json`` is the single source of truth for record shape
(draft-2020-12, ``additionalProperties: false`` at every object level). Every
shard record is validated here before publication; invalid records never ship.
This stage complements -- but does not replace -- ``pipeline.sanitize`` and
``scripts/pii_guard``: schema validation guarantees SHAPE, the guardrails
guarantee absence of PII.

Run as a CLI to gate the published tree::

    python -m pipeline.validate --all           # validate data/ + summary size
    python -m pipeline.validate --all --data-dir path/to/data

Exit code 0 means every shard conforms and ``summary.json`` is within budget;
non-zero means at least one problem was printed.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from pipeline.config import SUMMARY_MAX_BYTES

__all__ = [
    "check_summary_size",
    "has_qualifying_offence_section",
    "iter_shard_files",
    "load_schema",
    "project_to_schema",
    "validate_all_shards",
    "validate_ledger",
    "validate_record",
    "withhold_unsourced_accused_names",
]

_LEDGER_SCHEMA_REL = Path("schemas") / "ledger.schema.json"
# A string is "URL-shaped" if it looks like a link or a bare domain. The committed
# ledger must never contain one (only sha256 keys, an outcome enum, and dates).
_URL_SHAPED_RE = re.compile(r"https?://|www\.|\b[\w-]+\.(?:com|in|org|net|gov|io)\b", re.IGNORECASE)


def _iter_strings(value: Any) -> Iterator[str]:
    """Yield every string (dict keys and all values) within a JSON structure."""
    if isinstance(value, dict):
        for key, sub in value.items():
            yield str(key)
            yield from _iter_strings(sub)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_strings(item)
    elif isinstance(value, str):
        yield value


def validate_ledger(path: Path) -> list[str]:
    """Validate the processed-document ledger: schema shape + no URL-shaped strings.

    The committed ledger (``data/_meta/processed.json``) is operational metadata
    ONLY. This asserts it against ``schemas/ledger.schema.json`` (sha256 keys, an
    outcome enum, ISO dates, ``additionalProperties:false``) and, belt-and-suspenders,
    that no key or value is URL-shaped. Returns error strings (empty = clean).
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{path}: could not read/parse ledger: {exc}"]
    schema = json.loads((_REPO_ROOT / _LEDGER_SCHEMA_REL).read_text(encoding="utf-8"))
    errors = [
        f"{path}: schema: {e.message}" for e in Draft202012Validator(schema).iter_errors(data)
    ]
    errors.extend(
        f"{path}: URL-shaped string in ledger: {s[:60]!r}"
        for s in _iter_strings(data)
        if _URL_SHAPED_RE.search(s)
    )
    return errors


def withhold_unsourced_accused_names(record: dict[str, Any]) -> dict[str, Any]:
    """Null accused[].name_public_court_record unless the record is court-corroborated.

    An accused name publishes ONLY when the record carries BOTH a court name and a
    case anchor (CNR or FIR number) — the marks of an actual judgment/order, not a
    media item or a bare index entry (e.g. an Indian Kanoon news hit). Otherwise the
    name is withheld, per the presumption of innocence and the accused-name policy.
    Deterministic; independent of what the model returned.
    """
    accused = record.get("accused")
    if not isinstance(accused, list) or not accused:
        return record
    court_name = (record.get("court") or {}).get("name")
    case_anchor = record.get("cnr") or (record.get("fir_ref") or {}).get("number")
    if court_name and case_anchor:
        return record  # corroborated: names may stand
    guarded = dict(record)
    guarded["accused"] = [
        {**a, "name_public_court_record": None} if isinstance(a, dict) else a for a in accused
    ]
    return guarded


# Qualifying sexual-offence statutes. A record's cited offence_sections must
# reference at least one of these for it to be in scope; otherwise it is
# quarantined (the deterministic second layer behind the model's in_scope flag).
_BNS_SEXUAL_SECTIONS = frozenset(range(63, 80))  # BNS 2023 Chapter V, ss.63-79
_IPC_SEXUAL_SECTIONS = frozenset({354, 375, 376, 377, 509})
_SECTION_NUMBER_RE = re.compile(r"(\d{1,3})")


def has_qualifying_offence_section(sections: list[str]) -> bool:
    """True if any offence-section string references a sexual-offence statute.

    POCSO anywhere qualifies; BNS 63-79 (Chapter V) and IPC 354/375-377/509 qualify.
    A wholly non-sexual section set (e.g. ["NI Act 138"] for a cheque bounce) does
    not, and a record with such sections is quarantined rather than published.
    """
    for section in sections:
        text = str(section).upper()
        if "POCSO" in text:
            return True
        match = _SECTION_NUMBER_RE.search(text)
        if not match:
            continue
        number = int(match.group(1))
        if "BNS" in text and number in _BNS_SEXUAL_SECTIONS:
            return True
        if "IPC" in text and number in _IPC_SEXUAL_SECTIONS:
            return True
    return False


def project_to_schema(value: Any, schema: dict[str, Any]) -> Any:
    """Recursively drop any key not declared in ``schema`` (an allow-list projection).

    A structural backstop to sanitize: even a model-emitted key that is not in the
    forbidden list and whose value matches no PII pattern cannot reach disk if the
    schema does not declare it. Applied against the case schema before disk.
    """
    if isinstance(value, dict) and (schema.get("type") == "object" or "properties" in schema):
        props: dict[str, Any] = schema.get("properties", {})
        return {
            key: project_to_schema(sub, props[key]) for key, sub in value.items() if key in props
        }
    if isinstance(value, list) and (schema.get("type") == "array" or "items" in schema):
        item_schema: dict[str, Any] = schema.get("items", {})
        return [project_to_schema(item, item_schema) for item in value]
    return value


_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCHEMA_PATH = _REPO_ROOT / "schemas" / "case.schema.json"
_DEFAULT_DATA_DIR = _REPO_ROOT / "data"


def load_schema(path: Path = _SCHEMA_PATH) -> dict[str, Any]:
    """Load and return the case schema as a dict."""
    schema: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return schema


def validate_record(record: dict[str, Any], schema: dict[str, Any]) -> None:
    """Validate a single record against ``schema``.

    Raises ``jsonschema.ValidationError`` on the first violation; returns None
    when the record conforms.
    """
    Draft202012Validator(schema).validate(record)


def iter_shard_files(data_dir: Path) -> Iterator[Path]:
    """Yield every published ``data/{YYYY}/{STATE}.json`` shard.

    Only ``{YYYY}/*.json`` shards count; top-level files (summary.json,
    index.json), the ``_review`` quarantine, and any ``logs/`` are skipped by
    matching the 4-digit year directory pattern.
    """
    yield from sorted(data_dir.glob("[0-9][0-9][0-9][0-9]/*.json"))


def validate_all_shards(data_dir: Path, schema: dict[str, Any] | None = None) -> list[str]:
    """Validate every shard under ``data_dir``. Return a list of error strings.

    An empty list means every record in every shard conforms to the schema.
    """
    resolved = schema if schema is not None else load_schema()
    validator = Draft202012Validator(resolved)
    errors: list[str] = []
    for shard in iter_shard_files(data_dir):
        try:
            records = json.loads(shard.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{shard}: could not read/parse JSON: {exc}")
            continue
        if not isinstance(records, list):
            errors.append(f"{shard}: expected a JSON array of records")
            continue
        for index, record in enumerate(records):
            for error in validator.iter_errors(record):
                errors.append(f"{shard}[{index}]: {error.message}")
    return errors


def check_summary_size(summary_path: Path) -> str | None:
    """Return an error string if summary.json exceeds its budget, else None."""
    if not summary_path.exists():
        return None
    size = summary_path.stat().st_size
    if size > SUMMARY_MAX_BYTES:
        return f"{summary_path}: {size} bytes exceeds the {SUMMARY_MAX_BYTES}-byte budget"
    return None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pipeline.validate",
        description="Validate published shards against the case schema and check summary size.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Validate every shard under the data directory and assert the summary budget.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=_DEFAULT_DATA_DIR,
        help="Data directory to validate (default: ./data).",
    )
    parser.add_argument(
        "--ledger",
        type=Path,
        default=None,
        metavar="PATH",
        help="Validate ONLY the processed-document ledger at PATH (schema + no URLs).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run validation. Returns 0 when clean, 1 when any problem is reported."""
    args = _build_parser().parse_args(argv)

    if args.ledger is not None:
        errors = validate_ledger(args.ledger)
        if errors:
            print("Ledger validation FAILED:", file=sys.stderr)
            for error in errors:
                print(f"  {error}", file=sys.stderr)
            return 1
        print("Ledger validation clean: schema conforms and no URL-shaped strings.")
        return 0

    errors = validate_all_shards(args.data_dir)
    size_error = check_summary_size(args.data_dir / "summary.json")
    if size_error is not None:
        errors.append(size_error)

    if errors:
        print("Validation FAILED:", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        return 1

    print("Validation clean: all shards conform and summary.json is within budget.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
