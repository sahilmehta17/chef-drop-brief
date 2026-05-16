# Install

Two ways to use `chef-drop-brief`.

## A. As a Claude Code Skill (recommended)

Drop the repo into your Claude Code `skills` directory and Claude Code picks it up automatically.

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/sahilmehta17/chef-drop-brief.git ~/.claude/skills/chef-drop-brief

# install the Python deps the skill calls into
cd ~/.claude/skills/chef-drop-brief
python3.11 -m venv .venv
.venv/bin/pip install -e .
```

Then open Claude Code and prompt:

```
Use the chef-drop-brief skill. Chef: "Maya Patel", segment: "glp1_active",
launch-date: "2026-05-26".
```

The skill will run `scripts/load_context`, draft a brief, run the 9-eval suite,
optionally revise once, and emit three Braze-shaped JSON blocks.

> The first invocation downloads the `sentence-transformers/all-MiniLM-L6-v2`
> model (~80 MB) into `~/.cache/huggingface/`. After that, set
> `HF_HUB_OFFLINE=1` for fully-offline runs.

## B. As a standalone CLI (no Claude Code needed)

The three Python helpers are runnable directly. Useful for CI, testing the
eval suite, or wiring the suite into another LLM stack.

```bash
git clone https://github.com/sahilmehta17/chef-drop-brief.git
cd chef-drop-brief
python3.11 -m venv .venv
.venv/bin/pip install -e ".[dev]"

# load context for a chef × segment × date combo
.venv/bin/python -m scripts.load_context \
    --chef "Maya Patel" \
    --segment "glp1_active" \
    --launch-date "2026-05-26"

# run the eval suite on a brief (stdin: {"brief": {...}, "ctx": {...}})
cat brief_payload.json | .venv/bin/python -m scripts.run_evals

# map a passing brief to three Braze campaign JSONs
cat brief_payload.json | .venv/bin/python -m scripts.format_braze \
    --chef-id maya_patel --segment-id glp1_active --launch-date 2026-05-26
```

## Run the tests

```bash
.venv/bin/pip install -e ".[dev]"
HF_HUB_OFFLINE=1 .venv/bin/pytest -v
```

Expected: **18 passed**.

## Available chefs and segments

```bash
.venv/bin/python -c "import json; print(' '.join(json.load(open('reference/chefs.json'))['chefs']))"
# → aisha_bello anya_petrov camille_roux diego_sanchez marcus_hale maya_patel tomas_vega yuki_tanaka

.venv/bin/python -c "import json; print(' '.join(json.load(open('reference/segments.json'))['segments']))"
# → athletes_high_protein better_than_takeout_winback carnivore_premium families_kids_friendly foodies_lapsed_60d glp1_active
```

## Retargeting for a different brand

The eval suite is brand-agnostic. To retarget:

1. Replace `reference/chefs.json` with your own catalog (same schema).
2. Replace `reference/segments.json` with your segments.
3. Replace `reference/voice_samples.md` with 5 good + 5 anti-pattern samples in your brand voice.
4. Delete `~/.cache/chef-drop-brief/voice_anchors.npy` so the embeddings recompute.
5. Recalibrate `THRESHOLD` in `scripts/_evals_advanced.py` if needed (the docstring shows how).
