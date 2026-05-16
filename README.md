# chef-drop-brief

A Claude Code Skill that drafts Braze-ready chef-drop campaigns with 9 deterministic copy evals. One install, one slash command.

> Bad input goes in. The eval suite catches it. The skill revises once, then either ships or escalates to a human.

## Install

```bash
git clone https://github.com/sahilmehta17/chef-drop-brief ~/.claude/skills/chef-drop-brief
cd ~/.claude/skills/chef-drop-brief && python3.11 -m venv .venv && .venv/bin/pip install -e .
```

Full install (CLI mode, tests, retargeting): see [INSTALL.md](INSTALL.md).

## Invoke

In Claude Code:

```
Use the chef-drop-brief skill. Chef: "Maya Patel", segment: "glp1_active", launch-date: "2026-05-26"
```

Output: three Braze Curated-Sends JSON blocks (email + SMS + push), an eval report (9/9 ✓ on a clean pass), and a send-time recommendation.

## Why this is more than an API wrapper

Most marketing-copy LLM workflows ship without an eval suite. This one ships nine, plus a one-shot field-scoped revision loop. The architecture is the differentiator, not the prose.

The eval pattern is ported from a production agent I shipped at Enidus (T-Mobile copilot, 52 pytest evals gating an LLM-drafted CSR response) and from a personal project (ClaudeJob, 47 unit tests, 30+ banned-cliché regex, source-fact validation against a pinned base). Same shape. Different domain.

The revision loop is **field-scoped**. When the dietary-contradiction eval fails on `email.body`, the revision prompt asks the model to regenerate `email.body` only — not the world. Most "AI marketing tools" regenerate every channel on every retry, which breaks A/B variant integrity and inflates token spend.

## The 9 evals

| # | Eval | What it catches |
|---|---|---|
| 1 | `claimed_facts` | Hallucinated chef bios, fake dishes, fabricated credentials (token-set substring match against the source) |
| 2 | `dietary_contradiction` | Meat mentions on a vegan chef's drop, pork on a pescatarian, etc. |
| 3 | `banned_cliche` | 35 sanitized-DTC phrases CookUnity-style brands actively avoid ("indulge your senses", "tantalize your taste buds", "in today's fast-paced world", …) |
| 4 | `cta_presence` | Channel-correct CTAs: markdown/HTML link or button-token in email, short-link in SMS, imperative verb in the first 40 chars of push |
| 5 | `channel_char_limits` | Subjects 30–60, SMS ≤ 160, push title ≤ 50, push body ≤ 90 |
| 6 | `personalization_tokens` | `{{first_name}}` present in email; consent-safe in SMS |
| 7 | `brand_voice_similarity` | Cosine similarity (sentence-transformers MiniLM-L6-v2) against the mean of 5 seeded voice anchors, threshold 0.55 |
| 8 | `policy_safety` | No guaranteed-results / cure / medical-approved / doctor-endorsed / review-for-discount language; allergen-flag cross-check against the menu |
| 9 | `cookunity_voice_signals` | At least one of: anthropomorphic verb on a food noun, hyphenated/coined word (chef-X, X-licious, X-forward), "Not… Just…" construction, em-dash aside |

## How it works

```
   ┌─────────────────────┐
   │   /chef-drop input  │  chef + segment + launch_date
   └──────────┬──────────┘
              ▼
   ┌─────────────────────┐
   │  load_context.py    │  reads chefs.json, segments.json,
   │  (deterministic)    │  voice_samples.md, banned_cliches.json
   └──────────┬──────────┘
              ▼
   ┌─────────────────────┐
   │  Claude (LLM)       │  drafts a brief JSON (email + sms + push +
   │                     │  rationale + claimed_facts + send_time)
   └──────────┬──────────┘
              ▼
   ┌─────────────────────┐         ┌──────────────────────┐
   │  run_evals.py       │ ─fail─▶ │ build_revision_prompt│
   │  (9 evals)          │         │  (names ONLY the     │
   └──────┬──────────────┘         │   failing fields)    │
          │ pass                   └─────────┬────────────┘
          ▼                                  │ one retry
   ┌─────────────────────┐                   │
   │  format_braze.py    │                   ▼
   │  → 3 Braze JSONs    │      (re-run evals; if still fail,
   └─────────────────────┘       output ⚠️ NEEDS HUMAN REVIEW)
```

## How the voice threshold was set

The 0.55 cosine threshold in eval 7 isn't a magic number — it's the gap between the 5 hand-written CookUnity-style samples in `reference/voice_samples.md` and the 5 anti-pattern samples in the same file.

Measured against the mean of the good-sample embeddings:

```
good samples:        0.657 - 0.774   (min 0.657)
anti-pattern samples: 0.393 - 0.565  (max 0.565)
```

0.55 cleanly separates 4 of 5 anti-patterns and gives ~0.10 of headroom above the worst good sample. To recalibrate after editing the voice samples, delete `~/.cache/chef-drop-brief/voice_anchors.npy` and re-run the suite — the cache regenerates and you can pick a new threshold 0.05–0.10 below the lowest good-sample cosine.

## Repo tour

```
chef-drop-brief/
├── SKILL.md                     ← Claude Code skill manifest (frontmatter + instructions)
├── README.md                    ← you are here
├── INSTALL.md                   ← skill install + standalone CLI install + retargeting
├── LICENSE                      ← MIT, Sahil Mehta
├── pyproject.toml               ← deps: sentence-transformers, jsonschema, pydantic
├── scripts/
│   ├── load_context.py          ← stdlib; chef/segment/voice/cliches/schemas → JSON
│   ├── run_evals.py             ← evals 1-6, EvalResult dataclass, run_all, revision loop
│   ├── _evals_advanced.py       ← evals 7-9 (semantic, policy, voice signals)
│   └── format_braze.py          ← brief → 3 Braze Curated-Sends JSON blocks
├── reference/
│   ├── chefs.json               ← 8 fictional chefs, 6 dishes each
│   ├── segments.json            ← 6 segments (glp1, foodies-lapsed, athletes, families, winback, carnivore)
│   ├── voice_samples.md         ← 5 good + 5 anti-pattern anchor samples
│   ├── banned_cliches.json      ← 35 phrases in 3 buckets (sanitized DTC, stale promo, AI tells)
│   └── braze_schemas/           ← email.schema.json, sms.schema.json, push.schema.json
└── tests/
    ├── test_evals.py            ← 18 tests
    └── fixtures/                ← 1 good + 9 bad golden fixtures
```

## Tests

```bash
HF_HUB_OFFLINE=1 .venv/bin/pytest -v
```

```
tests/test_evals.py::test_good_brief_passes_all_nine PASSED
tests/test_evals.py::test_bad_fixture_isolates_target_eval[...9 cases...] PASSED
tests/test_evals.py::test_run_with_revision_passes_on_good_brief PASSED
tests/test_evals.py::test_run_with_revision_calls_regenerate_once_on_bad_brief PASSED
tests/test_evals.py::test_run_with_revision_escalates_when_retry_still_fails PASSED
tests/test_evals.py::test_revision_prompt_names_failing_fields PASSED
tests/test_evals.py::test_load_context_unknown_chef_raises_keyerror PASSED
tests/test_evals.py::test_load_context_unknown_segment_raises_keyerror PASSED
tests/test_evals.py::test_load_context_invalid_date_raises_valueerror PASSED
tests/test_evals.py::test_format_braze_cli_emits_three_channels PASSED

============================== 18 passed ==============================
```

## Retargeting for any DTC subscription brand

This skill is themed for a CookUnity-style meal-delivery brand, but the eval suite is brand-agnostic. To retarget for any DTC subscription:

1. Replace `reference/chefs.json` with your own catalog (same schema — names, credentials, menu, dietary tags).
2. Replace `reference/segments.json` with your segments.
3. Replace `reference/voice_samples.md` with 5 good + 5 anti-pattern samples in your brand voice.
4. Delete `~/.cache/chef-drop-brief/voice_anchors.npy` to force the embeddings to recompute.
5. Optionally retune the threshold in `scripts/_evals_advanced.py` — the docstring shows the math.

Eval 9 (`cookunity_voice_signals`) is brand-specific by design. If your brand doesn't use anthropomorphic verbs or em-dash asides, edit the heuristic in `_evals_advanced.py` to match your voice signature.

## About

Built by [Sahil Mehta](https://github.com/sahilmehta17) as a portfolio attachment for the AI Native Engineer, Growth Marketing role at CookUnity. The eval pattern mirrors what I ship in production at Enidus (T-Mobile copilot, 52 pytest evals gating LLM CSR responses) and in [ClaudeJob](https://github.com/sahilmehta17) (47 unit tests, 30+ banned-cliché regex, source-fact validation against a pinned base).
