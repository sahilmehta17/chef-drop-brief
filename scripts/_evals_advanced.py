"""Placeholder for evals 7-9 — implemented in Hour 4.

These functions are imported lazily by run_evals.run_all so the rest of the
suite stays runnable even when sentence-transformers is not installed.
This stub returns passing results; the real implementations land in the next
commit.
"""

from __future__ import annotations

from scripts.run_evals import EvalResult


def eval_brand_voice_similarity(brief: dict, ctx: dict) -> EvalResult:  # noqa: ARG001
    return EvalResult(name="brand_voice_similarity", passed=True, reason="stub")


def eval_policy_safety(brief: dict, ctx: dict) -> EvalResult:  # noqa: ARG001
    return EvalResult(name="policy_safety", passed=True, reason="stub")


def eval_cookunity_voice_signals(brief: dict, ctx: dict) -> EvalResult:  # noqa: ARG001
    return EvalResult(name="cookunity_voice_signals", passed=True, reason="stub")
