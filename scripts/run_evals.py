"""Deterministic eval suite for chef-drop briefs.

Nine evals, each implemented as `eval_<name>(brief, ctx) -> EvalResult`. The aggregator
`run_all` returns the full list; `run_with_revision` wires the one-shot retry loop;
`build_revision_prompt` produces a scoped prompt naming only the failing fields.

CLI:
    cat brief_payload.json | python -m scripts.run_evals

The payload shape is {"brief": {...}, "ctx": {...}}. Stdout is the JSON report:
    {
      "all_passed": bool,
      "results": [{"name": ..., "passed": ..., "reason": ..., "failing_fields": [...]}, ...],
      "revision_prompt": "..." | null
    }
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Core types
# ---------------------------------------------------------------------------


@dataclass
class EvalResult:
    name: str
    passed: bool
    reason: str | None = None
    failing_fields: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


EvalFn = Callable[[dict, dict], EvalResult]


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


_WORD_RE = re.compile(r"[A-Za-z0-9]+")

# Small stopword set, stripped when computing fact-vs-source token overlap.
# Kept tight on purpose: only function words that inflate the denominator
# without adding signal. Content words ("protein", "dish", "chef") still count.
_STOPWORDS = frozenset({
    "and", "of", "the", "a", "an", "in", "on", "at", "to",
    "for", "with", "or", "is", "was", "are", "were", "be", "by",
    "as", "that", "this",
})


def _tokens(text: str) -> set[str]:
    return {m.group(0).lower() for m in _WORD_RE.finditer(text or "")}


def _content_tokens(text: str) -> set[str]:
    """_tokens() minus stopwords. Used by eval_claimed_facts for overlap math."""
    return {t for t in _tokens(text) if t not in _STOPWORDS}


def _all_channel_texts(brief: dict) -> dict[str, str]:
    """Map field -> text for every place copy can appear.

    Keys are dotted addresses suitable for the revision prompt
    (e.g. 'email.subject_a', 'sms.body', 'push.title').
    """
    out: dict[str, str] = {}
    email = brief.get("email", {}) or {}
    sms = brief.get("sms", {}) or {}
    push = brief.get("push", {}) or {}
    for key in ("subject_a", "subject_b", "body", "cta"):
        if key in email:
            out[f"email.{key}"] = email.get(key, "") or ""
    if "body" in sms:
        out["sms.body"] = sms.get("body", "") or ""
    if "cta" in sms:
        out["sms.cta"] = sms.get("cta", "") or ""
    if "title" in push:
        out["push.title"] = push.get("title", "") or ""
    if "body" in push:
        out["push.body"] = push.get("body", "") or ""
    return out


# ---------------------------------------------------------------------------
# Eval 1 — claimed_facts
# ---------------------------------------------------------------------------


def _source_text(ctx: dict, source: str) -> str:
    """Resolve a `chef:<id>` or `segment:<id>` source token to its underlying text.

    Nutrition numerics are emitted in both bare ('28') and unit-suffixed ('28g')
    forms so that a copy claim like '28g of protein' can be matched against the
    menu without forcing the LLM to mirror our internal field names. The segment
    size_estimate is included as a string so claims like '47,000 subscribers'
    are sourceable to a segment.
    """
    if not isinstance(source, str) or ":" not in source:
        return ""
    kind, _, _ident = source.partition(":")
    if kind == "chef":
        chef = ctx.get("chef") or {}
        bits = [chef.get("name", ""), chef.get("cuisine", ""), chef.get("bio", "")]
        bits.extend(chef.get("credentials", []) or [])
        for tag in chef.get("dietary_tags", []) or []:
            bits.append(tag.replace("_", " "))
        for dish in chef.get("menu", []) or []:
            bits.append(dish.get("name", ""))
            for ing in dish.get("ingredients", []) or []:
                bits.append(ing)
            for flag in dish.get("allergen_safe", []) or []:
                bits.append(flag.replace("_", " "))
            calories = dish.get("calories")
            if calories is not None:
                bits.append(f"{calories}")
                bits.append(f"{calories} calories")
                bits.append(f"{calories}cal")
                bits.append(f"{calories} cal")
            protein = dish.get("protein_g")
            if protein is not None:
                bits.append(f"{protein}")
                bits.append(f"{protein}g")
                bits.append(f"{protein} g")
                bits.append(f"{protein} grams")
                bits.append(f"{protein}g protein")
        return " ".join(b for b in bits if b)
    if kind == "segment":
        seg = ctx.get("segment") or {}
        bits = [
            seg.get("display_name", ""),
            seg.get("description", ""),
            " ".join(seg.get("tone_hints", []) or []),
        ]
        size = seg.get("size_estimate")
        if size is not None:
            bits.append(f"{size}")
            bits.append(f"{size:,}")  # comma-grouped form
            bits.append(f"{size} subscribers")
        return " ".join(b for b in bits if b)
    return ""


def eval_claimed_facts(brief: dict, ctx: dict) -> EvalResult:
    """Each claimed fact's tokens must appear in its declared source.

    Token-set subset match — robust to word order and punctuation. A fact
    passes if at least 75% of its content tokens (ignoring 1-character) are
    present in the source corpus.
    """
    claims = brief.get("claimed_facts", []) or []
    if not claims:
        return EvalResult(
            name="claimed_facts",
            passed=False,
            reason="No claimed_facts entries. Every factual claim in the copy must be sourced.",
            failing_fields=["claimed_facts"],
        )
    failures: list[str] = []
    failing_fields: list[str] = []
    for i, entry in enumerate(claims):
        if not isinstance(entry, dict):
            failures.append(f"claimed_facts[{i}] not an object")
            failing_fields.append(f"claimed_facts[{i}]")
            continue
        fact = entry.get("fact", "")
        source = entry.get("source", "")
        source_text = _source_text(ctx, source)
        if not source_text:
            failures.append(f"claimed_facts[{i}] source '{source}' not resolvable to chef/segment")
            failing_fields.append(f"claimed_facts[{i}].source")
            continue
        fact_tokens = {t for t in _content_tokens(fact) if len(t) > 1}
        if not fact_tokens:
            continue
        source_tokens = _content_tokens(source_text)
        missing = fact_tokens - source_tokens
        if missing and len(missing) > len(fact_tokens) * 0.25:
            failures.append(
                f"claimed_facts[{i}] '{fact}' contains tokens not in source: "
                + ", ".join(sorted(missing))
            )
            failing_fields.append(f"claimed_facts[{i}].fact")
    if failures:
        return EvalResult(
            name="claimed_facts",
            passed=False,
            reason="; ".join(failures),
            failing_fields=failing_fields,
        )
    return EvalResult(name="claimed_facts", passed=True)


# ---------------------------------------------------------------------------
# Eval 2 — dietary_contradiction
# ---------------------------------------------------------------------------


# Diet-tag -> banned tokens that must not appear in body copy.
DIET_FORBIDDEN: dict[str, list[str]] = {
    "vegan": ["beef", "chicken", "pork", "fish", "cheese", "butter", "egg", "yogurt", "cream", "gelatin", "honey", "shrimp", "salmon", "tuna", "lamb", "turkey", "dairy"],
    "vegetarian": ["beef", "chicken", "pork", "fish", "shrimp", "salmon", "tuna", "lamb", "turkey"],
    "pescatarian": ["beef", "chicken", "pork", "lamb"],
    "plant_based": ["beef", "chicken", "pork", "fish", "cheese", "butter", "egg", "yogurt", "cream", "shrimp", "salmon", "tuna", "lamb", "turkey", "dairy"],
}


def _channel_bodies_with_keys(brief: dict) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    email = brief.get("email", {}) or {}
    if "subject_a" in email:
        out.append(("email.subject_a", email["subject_a"] or ""))
    if "subject_b" in email:
        out.append(("email.subject_b", email["subject_b"] or ""))
    if "body" in email:
        out.append(("email.body", email["body"] or ""))
    sms = brief.get("sms", {}) or {}
    if "body" in sms:
        out.append(("sms.body", sms["body"] or ""))
    push = brief.get("push", {}) or {}
    if "title" in push:
        out.append(("push.title", push["title"] or ""))
    if "body" in push:
        out.append(("push.body", push["body"] or ""))
    return out


def eval_dietary_contradiction(brief: dict, ctx: dict) -> EvalResult:
    chef = ctx.get("chef") or {}
    diet_tags = [t.lower() for t in (chef.get("dietary_tags") or [])]
    # Exact-match against the forbidden-list keys. Substring matching would
    # mis-activate the vegetarian list for "vegetarian_options" (which only
    # means the chef offers vegetarian options, not that they are vegetarian).
    active = [diet_key for diet_key in DIET_FORBIDDEN if diet_key in diet_tags]
    if not active:
        return EvalResult(name="dietary_contradiction", passed=True)

    failures: list[str] = []
    failing_fields: list[str] = []
    for diet_key in active:
        banned = DIET_FORBIDDEN[diet_key]
        for key, text in _channel_bodies_with_keys(brief):
            text_tokens = _tokens(text)
            hits = sorted(t for t in banned if t in text_tokens)
            if hits:
                failures.append(
                    f"{key} mentions {', '.join(hits)} but chef has '{diet_key}' diet tag"
                )
                failing_fields.append(key)
    if failures:
        return EvalResult(
            name="dietary_contradiction",
            passed=False,
            reason="; ".join(failures),
            failing_fields=sorted(set(failing_fields)),
        )
    return EvalResult(name="dietary_contradiction", passed=True)


# ---------------------------------------------------------------------------
# Eval 3 — banned_cliche
# ---------------------------------------------------------------------------


def eval_banned_cliche(brief: dict, ctx: dict) -> EvalResult:
    cliches = ctx.get("banned_cliches") or {}
    # Flatten and lowercase
    flat = [phrase.lower() for bucket in cliches.values() for phrase in bucket]
    failures: list[str] = []
    failing_fields: list[str] = []
    for key, text in _channel_bodies_with_keys(brief):
        lower = (text or "").lower()
        for phrase in flat:
            if phrase in lower:
                failures.append(f"{key} contains banned cliche '{phrase}'")
                failing_fields.append(key)
                break  # one hit per field is enough
    if failures:
        return EvalResult(
            name="banned_cliche",
            passed=False,
            reason="; ".join(failures),
            failing_fields=sorted(set(failing_fields)),
        )
    return EvalResult(name="banned_cliche", passed=True)


# ---------------------------------------------------------------------------
# Eval 4 — cta_presence
# ---------------------------------------------------------------------------


MD_LINK = re.compile(r"\[[^\]]+\]\([^)]+\)")
HTML_ANCHOR = re.compile(r"<a[^>]+>", re.IGNORECASE)
BUTTON_TOKEN = re.compile(r"\{\{\s*(?:cta_button|button|button_url|short_url)\s*\}\}")
IMPERATIVE_VERBS = {
    "tap", "open", "claim", "grab", "try", "see", "order", "add", "save", "swap",
    "skip", "pick", "start", "get", "shop", "explore", "discover", "join", "snag",
    "subscribe", "preview", "unlock", "drop",
}


def eval_cta_presence(brief: dict, ctx: dict) -> EvalResult:
    failures: list[str] = []
    failing_fields: list[str] = []

    email_body = (brief.get("email", {}) or {}).get("body", "") or ""
    if not (MD_LINK.search(email_body) or HTML_ANCHOR.search(email_body) or BUTTON_TOKEN.search(email_body) or (brief.get("email", {}) or {}).get("cta")):
        failures.append("email.body lacks an inline link, HTML anchor, button token, or CTA label")
        failing_fields.append("email.body")

    sms_body = (brief.get("sms", {}) or {}).get("body", "") or ""
    if not (re.search(r"https?://", sms_body) or "{{short_url}}" in sms_body):
        failures.append("sms.body lacks a short-link placeholder ({{short_url}} or https?://)")
        failing_fields.append("sms.body")

    push_body = (brief.get("push", {}) or {}).get("body", "") or ""
    first40 = push_body[:40].lower()
    first40_tokens = {m.group(0) for m in re.finditer(r"[A-Za-z']+", first40)}
    first40_tokens = {t.lower().rstrip("'s") for t in first40_tokens}
    if not (first40_tokens & IMPERATIVE_VERBS):
        failures.append(
            "push.body first 40 chars must include an imperative verb (e.g. tap, claim, try)"
        )
        failing_fields.append("push.body")

    if failures:
        return EvalResult(
            name="cta_presence",
            passed=False,
            reason="; ".join(failures),
            failing_fields=failing_fields,
        )
    return EvalResult(name="cta_presence", passed=True)


# ---------------------------------------------------------------------------
# Eval 5 — channel_char_limits
# ---------------------------------------------------------------------------


def eval_channel_char_limits(brief: dict, ctx: dict) -> EvalResult:
    failures: list[str] = []
    failing_fields: list[str] = []

    email = brief.get("email", {}) or {}
    for key in ("subject_a", "subject_b"):
        val = email.get(key, "") or ""
        if not (30 <= len(val) <= 60):
            failures.append(f"email.{key} length={len(val)}, must be 30-60 chars")
            failing_fields.append(f"email.{key}")

    sms_body = (brief.get("sms", {}) or {}).get("body", "") or ""
    if len(sms_body) > 160:
        failures.append(f"sms.body length={len(sms_body)}, must be <=160 chars")
        failing_fields.append("sms.body")

    push = brief.get("push", {}) or {}
    title = push.get("title", "") or ""
    if len(title) > 50:
        failures.append(f"push.title length={len(title)}, must be <=50 chars")
        failing_fields.append("push.title")
    pbody = push.get("body", "") or ""
    if len(pbody) > 90:
        failures.append(f"push.body length={len(pbody)}, must be <=90 chars")
        failing_fields.append("push.body")

    if failures:
        return EvalResult(
            name="channel_char_limits",
            passed=False,
            reason="; ".join(failures),
            failing_fields=failing_fields,
        )
    return EvalResult(name="channel_char_limits", passed=True)


# ---------------------------------------------------------------------------
# Eval 6 — personalization_tokens
# ---------------------------------------------------------------------------


_FIRSTNAME_TOKEN = re.compile(r"\{\{\s*(?:first_name|FirstName|firstname)\s*\}\}")


def eval_personalization_tokens(brief: dict, ctx: dict) -> EvalResult:
    failures: list[str] = []
    failing_fields: list[str] = []
    email_body = (brief.get("email", {}) or {}).get("body", "") or ""
    if not _FIRSTNAME_TOKEN.search(email_body):
        failures.append("email.body must contain {{first_name}} or {{FirstName}}")
        failing_fields.append("email.body")
    # SMS is consent-safe: either first-name token OR plain greeting acceptable.
    # No failure path here unless an explicit first-name *attempt* is malformed —
    # for now we only fail on email omission.
    if failures:
        return EvalResult(
            name="personalization_tokens",
            passed=False,
            reason="; ".join(failures),
            failing_fields=failing_fields,
        )
    return EvalResult(name="personalization_tokens", passed=True)


# ---------------------------------------------------------------------------
# Evals 7-9 are imported from a lazy module so this file stays importable
# even when sentence-transformers is not installed (CI / pip-extra context).
# ---------------------------------------------------------------------------


def _lazy_load_evals_789() -> tuple[EvalFn, EvalFn, EvalFn]:
    from scripts._evals_advanced import (
        eval_brand_voice_similarity,
        eval_cookunity_voice_signals,
        eval_policy_safety,
    )

    return eval_brand_voice_similarity, eval_policy_safety, eval_cookunity_voice_signals


# ---------------------------------------------------------------------------
# Aggregator + revision prompt + revision loop
# ---------------------------------------------------------------------------


def run_all(brief: dict, ctx: dict) -> list[EvalResult]:
    eval_brand_voice_similarity, eval_policy_safety, eval_cookunity_voice_signals = (
        _lazy_load_evals_789()
    )
    evals: list[EvalFn] = [
        eval_claimed_facts,
        eval_dietary_contradiction,
        eval_banned_cliche,
        eval_cta_presence,
        eval_channel_char_limits,
        eval_personalization_tokens,
        eval_brand_voice_similarity,
        eval_policy_safety,
        eval_cookunity_voice_signals,
    ]
    return [fn(brief, ctx) for fn in evals]


def build_revision_prompt(failures: list[EvalResult]) -> str:
    """Construct a scoped revision prompt naming only the failing fields."""
    if not failures:
        return ""
    lines = [
        "Revise the brief to fix the issues below. Keep every other field byte-identical.",
        "",
    ]
    seen: set[str] = set()
    for result in failures:
        lines.append(f"- {result.name}: {result.reason}")
        for f in result.failing_fields:
            seen.add(f)
    if seen:
        lines.append("")
        lines.append("Fields to regenerate: " + ", ".join(sorted(seen)))
    lines.append("")
    lines.append("Return the full brief JSON with these fields revised. Do not add new fields.")
    return "\n".join(lines)


def run_with_revision(
    brief: dict,
    ctx: dict,
    regenerate_fn: Callable[[dict, str], dict],
    max_retries: int = 1,
) -> tuple[dict, list[EvalResult], str]:
    """One-shot revision loop. Returns (final_brief, final_results, status).

    status ∈ {"passed", "passed_after_retry", "failed_after_retry"}.
    """
    results: list[EvalResult] = []
    for attempt in range(max_retries + 1):
        results = run_all(brief, ctx)
        if all(r.passed for r in results):
            return brief, results, "passed" if attempt == 0 else "passed_after_retry"
        if attempt < max_retries:
            prompt = build_revision_prompt([r for r in results if not r.passed])
            brief = regenerate_fn(brief, prompt)
    return brief, results, "failed_after_retry"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _report(results: list[EvalResult]) -> dict:
    all_passed = all(r.passed for r in results)
    revision_prompt = (
        None if all_passed else build_revision_prompt([r for r in results if not r.passed])
    )
    return {
        "all_passed": all_passed,
        "results": [r.to_dict() for r in results],
        "revision_prompt": revision_prompt,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="scripts.run_evals",
        description="Run the 9-eval suite on a brief and emit a report on stdout.",
    )
    parser.add_argument(
        "--ctx",
        help="Path to a context JSON file. Defaults to reading {brief, ctx} from stdin.",
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

    if args.ctx:
        ctx = json.loads(Path(args.ctx).read_text("utf-8"))
        brief = payload if "brief" not in payload else payload["brief"]
    else:
        if "brief" not in payload or "ctx" not in payload:
            print(
                "ERROR: stdin payload must be {\"brief\": {...}, \"ctx\": {...}} "
                "or pass --ctx <path>.",
                file=sys.stderr,
            )
            return 2
        brief = payload["brief"]
        ctx = payload["ctx"]

    results = run_all(brief, ctx)
    json.dump(_report(results), sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
