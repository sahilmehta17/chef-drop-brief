"""Load chef + segment context for the chef-drop-brief skill.

Usage:
    python -m scripts.load_context --chef "Maya Patel" --segment "glp1_active" --launch-date "2026-05-26"

Writes a single JSON object to stdout containing the chef record, segment record,
voice samples (raw markdown), banned cliches, Braze schemas, and launch date.
Exits non-zero with a clear error on the first stderr line if anything is missing.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REFERENCE_DIR = REPO_ROOT / "reference"


def _slugify(name: str) -> str:
    """Normalize a chef name to its lookup key (e.g. 'Maya Patel' -> 'maya_patel').

    Strips accents conservatively (NFD decomposition + ASCII filter), lowercases,
    and replaces whitespace with underscores.
    """
    import unicodedata

    decomposed = unicodedata.normalize("NFD", name)
    ascii_only = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    cleaned = re.sub(r"[^A-Za-z0-9\s]+", "", ascii_only).strip().lower()
    return re.sub(r"\s+", "_", cleaned)


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _resolve_chef(chefs_data: dict, chef_arg: str) -> tuple[str, dict]:
    """Return (chef_id, chef_record). Try slug, then display-name match."""
    chefs = chefs_data["chefs"]
    slug = _slugify(chef_arg)
    if slug in chefs:
        return slug, chefs[slug]
    # Fallback: case-insensitive display-name match
    for cid, record in chefs.items():
        if _slugify(record["name"]) == slug:
            return cid, record
    available = ", ".join(sorted(chefs.keys()))
    raise KeyError(
        f"Unknown chef '{chef_arg}'. Available chef ids: {available}."
    )


def _resolve_segment(segments_data: dict, segment_arg: str) -> tuple[str, dict]:
    segments = segments_data["segments"]
    if segment_arg in segments:
        return segment_arg, segments[segment_arg]
    available = ", ".join(sorted(segments.keys()))
    raise KeyError(
        f"Unknown segment '{segment_arg}'. Available segment ids: {available}."
    )


def _validate_launch_date(raw: str) -> str:
    """Accept YYYY-MM-DD; return the same string. Raise on bad format."""
    try:
        date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(
            f"Invalid --launch-date '{raw}'. Expected ISO YYYY-MM-DD."
        ) from exc
    return raw


def load_context(chef: str, segment: str, launch_date: str) -> dict:
    """Programmatic entry point. Mirrors the CLI but returns a dict."""
    chefs_data = _load_json(REFERENCE_DIR / "chefs.json")
    segments_data = _load_json(REFERENCE_DIR / "segments.json")
    cliches_data = _load_json(REFERENCE_DIR / "banned_cliches.json")
    voice_samples = (REFERENCE_DIR / "voice_samples.md").read_text(encoding="utf-8")

    chef_id, chef_record = _resolve_chef(chefs_data, chef)
    segment_id, segment_record = _resolve_segment(segments_data, segment)
    _validate_launch_date(launch_date)

    braze_schemas = {
        "email": _load_json(REFERENCE_DIR / "braze_schemas" / "email.schema.json"),
        "sms": _load_json(REFERENCE_DIR / "braze_schemas" / "sms.schema.json"),
        "push": _load_json(REFERENCE_DIR / "braze_schemas" / "push.schema.json"),
    }

    return {
        "chef_id": chef_id,
        "chef": chef_record,
        "segment_id": segment_id,
        "segment": segment_record,
        "voice_samples": voice_samples,
        "banned_cliches": cliches_data["banned_cliches"],
        "braze_schemas": braze_schemas,
        "launch_date": launch_date,
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="scripts.load_context",
        description="Load chef + segment context for the chef-drop-brief skill.",
    )
    parser.add_argument("--chef", required=True, help="Chef display name or slug.")
    parser.add_argument("--segment", required=True, help="Segment id (e.g. glp1_active).")
    parser.add_argument("--launch-date", required=True, help="ISO YYYY-MM-DD.")
    args = parser.parse_args(argv)
    try:
        ctx = load_context(args.chef, args.segment, args.launch_date)
    except (KeyError, ValueError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    json.dump(ctx, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
