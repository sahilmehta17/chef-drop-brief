# Loom demo shotlist — 90 seconds

Record in Loom Desktop, Screen + Audio (no webcam). Trim head/tail. Set the
thumbnail to a frame from segment 3 (the moment the eval catches the
contradiction).

## Pre-roll (off-camera, before recording starts)

- Skill is installed at `~/.claude/skills/chef-drop-brief` and the venv is built.
- `~/.cache/huggingface/` already contains the MiniLM model so first invocation
  doesn't stall on a download. (Run a throwaway invocation once before recording.)
- Two windows visible during the take:
  1. **Terminal** running Claude Code (`claude` CLI) in a clean shell, full screen,
     font size ≥ 16pt, dark theme.
  2. **Browser** with a tab on `github.com/sahilmehta17/chef-drop-brief`
     (private is fine — viewer never sees the auth state).
- Do Not Disturb on. No Slack / mail / messages / notifications.

## 0–10s — Title card + terminal

Show a Loom title card or just a clean terminal with this on screen:

```
chef-drop-brief — a Claude Code Skill for Growth Marketers
9 deterministic copy evals, one-shot field-scoped revision
```

Cut to the terminal at 0:08.

## 10–35s — Clean run

In Claude Code, type exactly:

```
Use the chef-drop-brief skill. Chef: "Maya Patel", segment: "glp1_active",
launch-date: "2026-05-26".
```

What the viewer sees:
1. Claude loads SKILL.md.
2. Claude runs `python -m scripts.load_context …` — visible in the tool-use log.
3. Claude drafts the brief JSON (rationale + email + sms + push + send_time +
   claimed_facts) — scrolls past on screen.
4. Claude runs `python -m scripts.run_evals` — eval report streams in: **9/9 ✓**.
5. Claude runs `python -m scripts.format_braze` — three Braze campaign JSON
   blocks appear in the output.

## 35–65s — Bad input → eval catches → revision

In the same session, type exactly:

```
Run it again with chef "Maya Patel" but segment "carnivore_premium".
```

What the viewer sees:
1. First draft mentions a meat dish from Tomás Vega's menu, or claims Maya's
   menu has carnivore-tagged items.
2. Eval report flags `dietary_contradiction` (or `claimed_facts` if the model
   invented a dish) — ✗ visible on screen.
3. Claude reads `revision_prompt`, regenerates ONLY the failing field
   (`email.body` / `sms.body` / etc.).
4. Re-runs evals — **9/9 ✓ after revision**.
5. Final three Braze JSONs printed.

Pause for a beat so the "revision happened" moment lands.

## 65–80s — Browser cut: README

Cut to `github.com/sahilmehta17/chef-drop-brief`:
1. Hover over the eval table (the 9-row markdown table).
2. Scroll down to **How it works** so the ASCII diagram is on screen for 3 sec.

## 80–90s — Tests + end card

Cut back to terminal or stay in browser, your call:

- Browser path: navigate to `tests/test_evals.py`. Hover or scroll briefly.
- Terminal path: `HF_HUB_OFFLINE=1 .venv/bin/pytest -v | tail -25` so the
  green `==== 18 passed ====` line lands.

End card (overlay or final screen):

```
github.com/sahilmehta17/chef-drop-brief
```

## Post-record

- Trim head/tail in Loom.
- Title: `chef-drop-brief — 90s demo`.
- Privacy: anyone with the link can view.
- Copy the Loom share URL. Confirm it plays in an incognito window before
  embedding in the README.
