### Hour 7 (optional polish) — Loom demo

Record a 90-second Loom (or QuickTime → upload to Loom) using this shotlist:

1. **0–10s** — Title card: "chef-drop-brief — a Claude Code Skill for CookUnity Growth marketers." Cut to terminal.
2. **10–25s** — `claude code` open, type `/chef-drop chef="Maya Patel" launch-date="2026-05-26" segment="glp1_active"` → output streams cleanly → 3 Braze JSON blocks appear → eval report shows 9/9 ✓.
3. **25–55s** — Type a bad input: `/chef-drop chef="Maya Patel" segment="carnivore_premium"` (forces a dietary contradiction). First draft mentions a meat dish → eval catches `dietary_contradiction` → revision prompt visible → second draft is clean. Eval report shows 9/9 ✓ after revision.
4. **55–75s** — Cut to README in browser: hover over the eval table, scroll to "How it works."
5. **75–90s** — Cut to the GitHub repo: hover over `tests/test_evals.py` → show `pytest` green. End on a card with the Loom URL and "github.com/sahilmehtx/chef-drop-brief".

Embed Loom in README. Final commit: `docs: demo video`.
