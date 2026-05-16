"""Advanced evals: brand-voice similarity (eval 7), policy safety (eval 8),
CookUnity voice signals (eval 9).

Pulled out of run_evals so the heavy sentence-transformers import is lazy.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from scripts.run_evals import EvalResult, _channel_bodies_with_keys

REPO_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Voice-anchor cache helpers
# ---------------------------------------------------------------------------

GOOD_SAMPLE_HEADING = re.compile(r"^## Good sample \d+", re.MULTILINE)
ANTIPATTERN_HEADING = re.compile(r"^## Anti-pattern sample", re.MULTILINE)
# Threshold tuned against the 5 good + 5 anti-pattern samples in
# reference/voice_samples.md (see README "How the voice threshold was set").
# Measured distribution:
#   good samples: 0.657-0.774 (min 0.657)
#   anti-pattern samples: 0.393-0.565 (max 0.565)
# 0.55 cleanly separates 4/5 anti-patterns while leaving headroom for good
# copy. To recalibrate after editing voice_samples.md, delete the
# voice_anchors.npy cache, run `python -m scripts.run_evals` on a known-good
# brief, and pick a value 0.05-0.10 below the lowest good-sample cosine.
THRESHOLD = 0.55

DEFAULT_CACHE_DIR = Path(
    os.environ.get("CHEF_DROP_CACHE_DIR")
    or os.path.expanduser("~/.cache/chef-drop-brief")
)
ANCHOR_FILE = "voice_anchors.npy"


def _voice_samples_path() -> Path:
    return REPO_ROOT / "reference" / "voice_samples.md"


def _parse_good_samples(text: str) -> list[str]:
    """Split voice_samples.md into the five 'Good sample' bodies (in order)."""
    # Crude but robust: split on '## Good sample', take bodies, stop at
    # '## Anti-pattern' boundary or EOF.
    parts = re.split(r"^## Good sample \d+[^\n]*\n", text, flags=re.MULTILINE)
    # parts[0] is the preamble, parts[1:] are the good-sample bodies (possibly
    # trailing into the anti-pattern section).
    samples: list[str] = []
    for body in parts[1:]:
        # truncate at anti-pattern section if present
        cut = ANTIPATTERN_HEADING.search(body)
        chunk = body[: cut.start()] if cut else body
        # truncate at next "---" horizontal rule
        chunk = chunk.split("\n---\n")[0]
        cleaned = chunk.strip()
        if cleaned:
            samples.append(cleaned)
    return samples


def _ensure_anchors(cache_dir: Path = DEFAULT_CACHE_DIR):
    """Compute (or load from cache) the matrix of good-sample embeddings.

    Returns a numpy array of shape (n_samples, dim).
    """
    import numpy as np

    cache_dir.mkdir(parents=True, exist_ok=True)
    anchor_path = cache_dir / ANCHOR_FILE
    voice_path = _voice_samples_path()
    if anchor_path.exists() and anchor_path.stat().st_mtime >= voice_path.stat().st_mtime:
        return np.load(anchor_path)

    from sentence_transformers import SentenceTransformer

    samples = _parse_good_samples(voice_path.read_text(encoding="utf-8"))
    if len(samples) < 3:
        raise RuntimeError(
            f"Expected at least 3 good voice samples in {voice_path}, found {len(samples)}."
        )
    model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    embeddings = model.encode(samples, normalize_embeddings=True)
    np.save(anchor_path, embeddings)
    return embeddings


def _embed(text: str):
    """Encode a single string to a unit-length vector."""
    from sentence_transformers import SentenceTransformer

    # Cache the model on the function object to avoid reloading per call.
    if not hasattr(_embed, "_model"):
        _embed._model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    return _embed._model.encode([text], normalize_embeddings=True)[0]


# ---------------------------------------------------------------------------
# Eval 7 — brand_voice_similarity
# ---------------------------------------------------------------------------


def eval_brand_voice_similarity(brief: dict, ctx: dict) -> EvalResult:  # noqa: ARG001
    try:
        import numpy as np  # noqa: F401
    except ImportError:
        return EvalResult(
            name="brand_voice_similarity",
            passed=True,
            reason="numpy not installed; skipping (degrade-safe)",
        )
    email_body = (brief.get("email", {}) or {}).get("body", "") or ""
    sms_body = (brief.get("sms", {}) or {}).get("body", "") or ""
    candidate_text = f"{email_body} {sms_body}".strip()
    if not candidate_text:
        return EvalResult(
            name="brand_voice_similarity",
            passed=False,
            reason="email.body and sms.body both empty; nothing to compare.",
            failing_fields=["email.body", "sms.body"],
        )
    try:
        anchors = _ensure_anchors()
        candidate = _embed(candidate_text)
    except Exception as exc:  # noqa: BLE001
        # If sentence-transformers can't load (offline CI, etc.), degrade-safe:
        # don't block release on a missing model.
        return EvalResult(
            name="brand_voice_similarity",
            passed=True,
            reason=f"voice model unavailable ({exc.__class__.__name__}); eval skipped.",
        )

    import numpy as np

    anchor_mean = anchors.mean(axis=0)
    anchor_mean = anchor_mean / np.linalg.norm(anchor_mean)
    cosine = float(candidate @ anchor_mean)
    if cosine < THRESHOLD:
        return EvalResult(
            name="brand_voice_similarity",
            passed=False,
            reason=(
                f"cosine={cosine:.3f} < threshold={THRESHOLD:.2f} vs. CookUnity voice anchors. "
                "Rewrite with more wordplay, anthropomorphic verbs, and em-dash asides."
            ),
            failing_fields=["email.body", "sms.body"],
        )
    return EvalResult(
        name="brand_voice_similarity",
        passed=True,
        reason=f"cosine={cosine:.3f} >= {THRESHOLD:.2f}",
    )


# ---------------------------------------------------------------------------
# Eval 8 — policy_safety
# ---------------------------------------------------------------------------


POLICY_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("guaranteed weight loss / results", re.compile(r"\bguaranteed\s+(weight\s+loss|results?)\b", re.IGNORECASE)),
    ("clinical / cure framing", re.compile(r"\bcure[s]?\b", re.IGNORECASE)),
    ("medical-approved claim", re.compile(r"\bmedical(?:ly)?\b[^.]{0,40}\b(approved|certified|endorsed)\b", re.IGNORECASE)),
    ("guaranteed outcome", re.compile(r"\b(?:lose|drop)\s+\d+\s*(?:lb|lbs|pounds?|kg)\b", re.IGNORECASE)),
    ("dr.-endorsed", re.compile(r"\b(?:doctor|physician|dietitian)[-\s]+(?:approved|endorsed|recommended)\b", re.IGNORECASE)),
    ("review-for-discount", re.compile(r"\b(?:review|rating)s?\s+for\s+(?:a\s+)?(?:discount|credit|coupon|free)\b", re.IGNORECASE)),
]

ALLERGEN_TOKENS = {
    "peanut": "peanut",
    "dairy": "dairy",
    "gluten": "gluten",
    "shellfish": "shellfish",
    "soy": "soy",
    "egg": "egg",
    "tree nut": "tree_nut",
    "tree-nut": "tree_nut",
    "treenut": "tree_nut",
}


def eval_policy_safety(brief: dict, ctx: dict) -> EvalResult:
    failures: list[str] = []
    failing_fields: list[str] = []
    for key, text in _channel_bodies_with_keys(brief):
        for label, pattern in POLICY_PATTERNS:
            if pattern.search(text or ""):
                failures.append(f"{key} triggers policy rule '{label}'")
                failing_fields.append(key)
                break
    # Allergen-safety cross-check (best-effort, only flags structural absence)
    chef = ctx.get("chef") or {}
    menu = chef.get("menu", []) or []
    if menu:
        all_safe_flags: set[str] = set()
        for dish in menu:
            for flag in dish.get("allergen_safe", []) or []:
                all_safe_flags.add(flag.lower())
        for key, text in _channel_bodies_with_keys(brief):
            lower = (text or "").lower()
            for token, normalized in ALLERGEN_TOKENS.items():
                if token in lower and "safe" in lower:
                    # Looks like the copy is claiming an allergen-safe attribute.
                    safe_aliases = {
                        f"{normalized}_safe",
                        f"{normalized}_free",
                        normalized,
                    }
                    if not (all_safe_flags & safe_aliases):
                        failures.append(
                            f"{key} claims {token}-safe but no menu dish has that allergen flag"
                        )
                        failing_fields.append(key)
                        break
    if failures:
        return EvalResult(
            name="policy_safety",
            passed=False,
            reason="; ".join(failures),
            failing_fields=sorted(set(failing_fields)),
        )
    return EvalResult(name="policy_safety", passed=True)


# ---------------------------------------------------------------------------
# Eval 9 — cookunity_voice_signals
# ---------------------------------------------------------------------------


ANTHRO_VERBS = {
    "whisper", "whispers", "whispering",
    "sing", "sings", "singing",
    "dance", "dances", "dancing",
    "hum", "hums", "humming",
    "wink", "winks", "winking",
    "tease", "teases", "teasing",
    "call", "calls", "calling",
    "apologize", "apologizes", "apologizing", "apologise", "apologises",
    "wait", "waits", "waiting",
}
FOOD_NOUNS = {
    "bowl", "plate", "dish", "sauce", "rice", "noodle", "soup", "salad",
    "steak", "brisket", "salmon", "branzino", "tofu", "curry", "donburi",
    "stew", "kofta", "ceviche", "kibbeh", "pibil", "tagine", "ratatouille",
    "carnitas", "birria", "biryani", "yakitori", "scallion", "scallions",
    "cauliflower", "lentil", "lentils", "lemon", "olive", "tomato",
    "ribeye", "broth", "yogurt", "broccolini", "rice", "pepper",
    "shrimp", "trout", "octopus", "sardine", "sardines", "fork",
}
COINED_WORD = re.compile(
    r"\b(?:[a-zA-Z]+licious\b|chef[-]?[a-zA-Z]+\b|[a-zA-Z]+-(?:craft(?:ed)?|forward|grade|proof|shaped))",
    re.IGNORECASE,
)
NEGATION_AFFIRMATION = re.compile(
    r"\bNot\b[^.\n]{0,60}[.,]\s*(?:Just|Only)\b",
)
EM_DASH_ASIDE = re.compile(r"—[^—\n]{2,80}[—.,]")


def _has_anthro_verb_on_food_noun(text: str) -> bool:
    tokens = re.findall(r"[A-Za-z']+", text.lower())
    for i, tok in enumerate(tokens):
        if tok in ANTHRO_VERBS:
            # Look at +/- 5 tokens for a food-noun co-occurrence.
            window = tokens[max(0, i - 5): i + 6]
            if any(t in FOOD_NOUNS for t in window):
                return True
    return False


def eval_cookunity_voice_signals(brief: dict, ctx: dict) -> EvalResult:  # noqa: ARG001
    body = (brief.get("email", {}) or {}).get("body", "") or ""
    sms_body = (brief.get("sms", {}) or {}).get("body", "") or ""
    subjects = [
        (brief.get("email", {}) or {}).get("subject_a", "") or "",
        (brief.get("email", {}) or {}).get("subject_b", "") or "",
    ]
    haystack = " ".join([body, sms_body, *subjects])

    signals: list[str] = []
    if _has_anthro_verb_on_food_noun(haystack):
        signals.append("anthropomorphic_verb_on_food")
    if COINED_WORD.search(haystack):
        signals.append("coined_word_or_wordplay")
    if NEGATION_AFFIRMATION.search(haystack):
        signals.append("negation_then_affirmation")
    if EM_DASH_ASIDE.search(haystack):
        signals.append("em_dash_aside")
    if not signals:
        return EvalResult(
            name="cookunity_voice_signals",
            passed=False,
            reason=(
                "No CookUnity voice signal found. Add at least one of: "
                "anthropomorphic verb on a food noun, coined/hyphenated word "
                "(chef-X, X-licious, X-forward), Not… Just… construction, or "
                "an em-dash aside."
            ),
            failing_fields=["email.body"],
        )
    return EvalResult(
        name="cookunity_voice_signals",
        passed=True,
        reason="signals: " + ", ".join(signals),
    )
