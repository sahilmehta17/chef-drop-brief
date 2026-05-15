"""Map a brief JSON object to three Braze Curated-Sends-shaped campaign blocks.

Usage:
    cat brief.json | python -m scripts.format_braze \
        --chef-id maya_patel --segment-id glp1_active

If --chef-id and --segment-id are omitted, the script reads a wrapped payload
of the form {"brief": {...}, "chef_id": "...", "segment_id": "...", "segment_size": int}.

Pure stdlib, no LLM. Validates the resulting campaigns against the JSON schemas
in reference/braze_schemas/.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = REPO_ROOT / "reference" / "braze_schemas"


def _load_schemas() -> dict:
    return {
        "email": json.loads((SCHEMA_DIR / "email.schema.json").read_text("utf-8")),
        "sms": json.loads((SCHEMA_DIR / "sms.schema.json").read_text("utf-8")),
        "push": json.loads((SCHEMA_DIR / "push.schema.json").read_text("utf-8")),
    }


def _parse_send_time(value: str | None) -> tuple[str, str]:
    """Split `send_time_recommendation` -> (iso datetime, rationale).

    Accepts either pure ISO ('2026-05-26T17:00:00Z') or 'ISO — rationale'.
    Falls back to launch_date 17:00 UTC if unparseable.
    """
    if not value:
        return "", ""
    parts = value.split(" — ", 1) if " — " in value else value.split(" - ", 1)
    iso_candidate = parts[0].strip()
    rationale = parts[1].strip() if len(parts) > 1 else ""
    try:
        # tolerate trailing Z
        datetime.fromisoformat(iso_candidate.replace("Z", "+00:00"))
        return iso_candidate, rationale
    except ValueError:
        return "", value.strip()


def _default_send_time(launch_date: str) -> str:
    """5pm UTC on launch day as a fallback."""
    try:
        d = datetime.fromisoformat(launch_date)
    except ValueError:
        d = datetime.now(timezone.utc)
    d = d.replace(hour=17, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
    return d.isoformat().replace("+00:00", "Z")


def _body_to_html(body: str) -> str:
    paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
    return "\n".join(f"<p>{p}</p>" for p in paragraphs)


def format_brief(
    brief: dict,
    chef_id: str,
    segment_id: str,
    segment_display_name: str = "",
    segment_size: int | None = None,
    launch_date: str = "",
) -> dict:
    iso, rationale = _parse_send_time(brief.get("send_time_recommendation", ""))
    if not iso:
        iso = _default_send_time(launch_date)
        rationale = rationale or "Default 17:00 UTC on launch day."

    audience = {
        "segment_id": segment_id,
        "segment_display_name": segment_display_name or segment_id,
    }
    if segment_size is not None:
        audience["estimated_size"] = int(segment_size)

    campaign_stub = f"chef_drop__{chef_id}__{segment_id}__{launch_date or 'undated'}"

    email = brief.get("email", {})
    sms = brief.get("sms", {})
    push = brief.get("push", {})

    email_campaign = {
        "channel": "email",
        "campaign_name": f"{campaign_stub}__email",
        "subject": {
            "variants": [v for v in [email.get("subject_a"), email.get("subject_b")] if v],
            "split": "even",
        },
        "from": {
            "email": "hello@cookunity.example",
            "name": "CookUnity",
        },
        "preheader": "",
        "html_body": _body_to_html(email.get("body", "")),
        "plain_body": email.get("body", ""),
        "cta": {
            "label": email.get("cta", "Order now"),
            "url": "{{short_url}}",
        },
        "audience": audience,
        "send_at": iso,
        "send_at_rationale": rationale,
    }

    sms_campaign = {
        "channel": "sms",
        "campaign_name": f"{campaign_stub}__sms",
        "body": sms.get("body", ""),
        "shortlink_placeholder": "{{short_url}}",
        "audience": audience,
        "send_at": iso,
        "send_at_rationale": rationale,
    }

    # Push goes 30 minutes after email by default
    try:
        push_iso = (
            datetime.fromisoformat(iso.replace("Z", "+00:00")) + timedelta(minutes=30)
        ).isoformat().replace("+00:00", "Z")
    except ValueError:
        push_iso = iso

    push_campaign = {
        "channel": "push",
        "campaign_name": f"{campaign_stub}__push",
        "title": push.get("title", ""),
        "body": push.get("body", ""),
        "deep_link": "cookunity://drop/" + chef_id,
        "audience": audience,
        "send_at": push_iso,
        "send_at_rationale": rationale,
    }

    return {
        "email": email_campaign,
        "sms": sms_campaign,
        "push": push_campaign,
    }


def _validate(campaigns: dict) -> list[str]:
    """Best-effort schema check; returns a list of human-readable errors (empty on pass)."""
    errors: list[str] = []
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        return errors  # silently skip if jsonschema isn't installed
    schemas = _load_schemas()
    for channel, payload in campaigns.items():
        validator = Draft202012Validator(schemas[channel])
        for err in validator.iter_errors(payload):
            errors.append(f"[{channel}] {err.message} (at {'/'.join(map(str, err.path))})")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="scripts.format_braze",
        description="Map a brief JSON object to three Braze Curated-Sends-shaped campaigns.",
    )
    parser.add_argument("--chef-id", default="")
    parser.add_argument("--segment-id", default="")
    parser.add_argument("--segment-display-name", default="")
    parser.add_argument("--segment-size", type=int, default=None)
    parser.add_argument("--launch-date", default="")
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip jsonschema validation (useful in offline environments).",
    )
    args = parser.parse_args(argv)

    raw = sys.stdin.read()
    if not raw.strip():
        print("ERROR: No JSON on stdin.", file=sys.stderr)
        return 2

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"ERROR: stdin is not valid JSON: {exc}", file=sys.stderr)
        return 2

    if "brief" in payload and isinstance(payload["brief"], dict):
        brief = payload["brief"]
        chef_id = args.chef_id or payload.get("chef_id", "")
        segment_id = args.segment_id or payload.get("segment_id", "")
        segment_display_name = (
            args.segment_display_name or payload.get("segment_display_name", "")
        )
        segment_size = (
            args.segment_size if args.segment_size is not None
            else payload.get("segment_size")
        )
        launch_date = args.launch_date or payload.get("launch_date", "")
    else:
        brief = payload
        chef_id = args.chef_id
        segment_id = args.segment_id
        segment_display_name = args.segment_display_name
        segment_size = args.segment_size
        launch_date = args.launch_date

    if not chef_id or not segment_id:
        print(
            "ERROR: chef_id and segment_id are required (via --chef-id / --segment-id "
            "or in a wrapped {brief, chef_id, segment_id} payload).",
            file=sys.stderr,
        )
        return 2

    campaigns = format_brief(
        brief,
        chef_id=chef_id,
        segment_id=segment_id,
        segment_display_name=segment_display_name,
        segment_size=segment_size,
        launch_date=launch_date,
    )

    if not args.no_validate:
        validation_errors = _validate(campaigns)
        if validation_errors:
            print("ERROR: Braze schema validation failed:", file=sys.stderr)
            for line in validation_errors:
                print(f"  - {line}", file=sys.stderr)
            return 3

    json.dump(campaigns, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
