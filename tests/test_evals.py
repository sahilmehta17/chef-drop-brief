"""Golden-fixture pytest suite for chef-drop-brief.

Each bad fixture is hand-crafted to fail exactly one eval and pass the other eight.
Also covers: good_brief → all 9 pass; revision loop happy/escalation paths; revision
prompt scoping; load_context error path; CLI smoke test for format_braze.

Run with HF_HUB_OFFLINE=1 if you've already downloaded the MiniLM-L6-v2 model
once (the test suite skips eval 7 gracefully if it can't load the model).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"

sys.path.insert(0, str(ROOT))

from scripts.load_context import load_context  # noqa: E402
from scripts.run_evals import (  # noqa: E402
    build_revision_prompt,
    eval_claimed_facts,
    eval_dietary_contradiction,
    run_all,
    run_with_revision,
)

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _load_fixture(name: str) -> tuple[dict, dict]:
    payload = json.loads((FIXTURES / name).read_text("utf-8"))
    ctx = load_context(payload["chef"], payload["segment"], payload["launch_date"])
    return payload["brief"], ctx


EVAL_NAMES = [
    "claimed_facts",
    "dietary_contradiction",
    "banned_cliche",
    "cta_presence",
    "channel_char_limits",
    "personalization_tokens",
    "brand_voice_similarity",
    "policy_safety",
    "cookunity_voice_signals",
]


BAD_FIXTURE_TARGET = {
    "bad_brief_claimed_facts.json": "claimed_facts",
    "bad_brief_dietary_contradiction.json": "dietary_contradiction",
    "bad_brief_banned_cliche.json": "banned_cliche",
    "bad_brief_cta_missing.json": "cta_presence",
    "bad_brief_channel_overflow.json": "channel_char_limits",
    "bad_brief_personalization_missing.json": "personalization_tokens",
    "bad_brief_voice_dissimilar.json": "brand_voice_similarity",
    "bad_brief_policy_violation.json": "policy_safety",
    "bad_brief_voice_signals_missing.json": "cookunity_voice_signals",
}


def _voice_model_available() -> bool:
    """Probe whether eval 7 can actually run. Used to skip voice-only tests offline."""
    try:
        from scripts._evals_advanced import _ensure_anchors

        _ensure_anchors()
        return True
    except Exception:  # noqa: BLE001
        return False


VOICE_AVAILABLE = _voice_model_available()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_good_brief_passes_all_nine() -> None:
    if not VOICE_AVAILABLE:
        pytest.skip("MiniLM-L6-v2 unavailable; eval 7 is degrade-safe, skipping suite check")
    brief, ctx = _load_fixture("good_brief.json")
    results = run_all(brief, ctx)
    failed = [r for r in results if not r.passed]
    assert not failed, "good_brief.json should pass all 9 evals; failed: " + ", ".join(
        f"{r.name} ({r.reason})" for r in failed
    )
    assert len(results) == 9
    assert {r.name for r in results} == set(EVAL_NAMES)


@pytest.mark.parametrize("fixture_name,target_eval", sorted(BAD_FIXTURE_TARGET.items()))
def test_bad_fixture_isolates_target_eval(fixture_name: str, target_eval: str) -> None:
    if target_eval == "brand_voice_similarity" and not VOICE_AVAILABLE:
        pytest.skip("MiniLM-L6-v2 unavailable; can't validate eval 7")
    brief, ctx = _load_fixture(fixture_name)
    results = {r.name: r for r in run_all(brief, ctx)}
    target = results[target_eval]
    assert not target.passed, (
        f"{fixture_name}: {target_eval} was supposed to fail but passed (reason={target.reason})"
    )
    others = [r for n, r in results.items() if n != target_eval]
    leaked = [r for r in others if not r.passed]
    if not VOICE_AVAILABLE:
        leaked = [r for r in leaked if r.name != "brand_voice_similarity"]
    assert not leaked, (
        f"{fixture_name}: other evals leaked failures: "
        + ", ".join(f"{r.name}: {r.reason}" for r in leaked)
    )


def test_run_with_revision_passes_on_good_brief() -> None:
    if not VOICE_AVAILABLE:
        pytest.skip("MiniLM-L6-v2 unavailable")
    brief, ctx = _load_fixture("good_brief.json")
    calls: list[int] = []

    def regen(_b, _p):
        calls.append(1)
        return _b

    final, results, status = run_with_revision(brief, ctx, regen, max_retries=1)
    assert status == "passed"
    assert calls == [], "regenerate_fn should not be called on a passing brief"
    assert all(r.passed for r in results)


def test_run_with_revision_calls_regenerate_once_on_bad_brief() -> None:
    if not VOICE_AVAILABLE:
        pytest.skip("MiniLM-L6-v2 unavailable")
    bad_brief, ctx = _load_fixture("bad_brief_personalization_missing.json")
    good_brief, _ = _load_fixture("good_brief.json")
    calls: list[str] = []

    def regen(_brief, prompt):
        calls.append(prompt)
        return good_brief

    _final, results, status = run_with_revision(bad_brief, ctx, regen, max_retries=1)
    assert len(calls) == 1, f"expected exactly one regen call, got {len(calls)}"
    assert status == "passed_after_retry"
    assert all(r.passed for r in results)


def test_run_with_revision_escalates_when_retry_still_fails() -> None:
    if not VOICE_AVAILABLE:
        pytest.skip("MiniLM-L6-v2 unavailable")
    bad_brief, ctx = _load_fixture("bad_brief_personalization_missing.json")

    def regen(b, _p):
        return b  # no-op: still failing

    _final, results, status = run_with_revision(bad_brief, ctx, regen, max_retries=1)
    assert status == "failed_after_retry"
    assert any(not r.passed for r in results)


def test_revision_prompt_names_failing_fields() -> None:
    bad_brief, ctx = _load_fixture("bad_brief_personalization_missing.json")
    results = run_all(bad_brief, ctx)
    failures = [r for r in results if not r.passed]
    prompt = build_revision_prompt(failures)
    assert "email.body" in prompt
    assert "personalization_tokens" in prompt
    assert "Fields to regenerate" in prompt


def test_load_context_unknown_chef_raises_keyerror() -> None:
    with pytest.raises(KeyError, match="Unknown chef"):
        load_context("Definitely Not A Real Chef", "glp1_active", "2026-05-26")


def test_load_context_unknown_segment_raises_keyerror() -> None:
    with pytest.raises(KeyError, match="Unknown segment"):
        load_context("Maya Patel", "not_a_segment", "2026-05-26")


def test_load_context_invalid_date_raises_valueerror() -> None:
    with pytest.raises(ValueError, match="Invalid --launch-date"):
        load_context("Maya Patel", "glp1_active", "yesterday")


def test_dietary_vegetarian_options_does_not_trigger_vegetarian_list() -> None:
    """Regression: chef with 'vegetarian_options' tag is NOT vegetarian.

    A brief mentioning shrimp must pass dietary_contradiction. Previously the
    substring match flagged this as a false positive because 'vegetarian' is a
    prefix of 'vegetarian_options'.
    """
    ctx = {
        "chef": {
            "name": "Test Chef",
            "dietary_tags": ["vegetarian_options", "high_protein"],
            "menu": [],
        },
        "segment": {},
    }
    brief = {
        "email": {"body": "Hot shrimp tonight, {{first_name}}."},
        "sms": {"body": "Shrimp drop. {{short_url}}"},
        "push": {"title": "Shrimp landed", "body": "Tap to claim."},
    }
    result = eval_dietary_contradiction(brief, ctx)
    assert result.passed, f"expected pass, got reason={result.reason}"


def test_claimed_facts_accepts_numeric_protein_claim() -> None:
    """Regression: '28g of protein' must be sourceable to a chef with that dish.

    Previously _source_text omitted dish calories/protein_g, so any numeric
    nutrition claim failed claimed_facts.
    """
    ctx = load_context("Maya Patel", "glp1_active", "2026-05-26")
    brief = {
        "claimed_facts": [
            {"fact": "28g of protein", "source": "chef:maya_patel"},
        ]
    }
    result = eval_claimed_facts(brief, ctx)
    assert result.passed, f"expected pass, got reason={result.reason}"


def test_format_braze_cli_emits_three_channels() -> None:
    """Smoke test the format_braze CLI end-to-end (jsonschema validation included)."""
    good_payload = json.loads((FIXTURES / "good_brief.json").read_text("utf-8"))
    cli_payload = {
        "brief": good_payload["brief"],
        "chef_id": "maya_patel",
        "segment_id": "glp1_active",
        "segment_display_name": "GLP-1 Active Subscribers",
        "segment_size": 47000,
        "launch_date": "2026-05-26",
    }
    result = subprocess.run(
        [sys.executable, "-m", "scripts.format_braze"],
        input=json.dumps(cli_payload).encode("utf-8"),
        cwd=str(ROOT),
        capture_output=True,
        check=False,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
    )
    assert result.returncode == 0, f"stderr: {result.stderr.decode()}"
    payload = json.loads(result.stdout)
    assert set(payload.keys()) == {"email", "sms", "push"}
    assert payload["email"]["channel"] == "email"
    assert payload["sms"]["channel"] == "sms"
    assert payload["push"]["channel"] == "push"
    # Subject A/B both present
    assert len(payload["email"]["subject"]["variants"]) == 2
