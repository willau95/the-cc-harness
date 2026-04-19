# End-to-End Test Trace · 2026-04-20

**Scenario (user specified):** SEO-specialist agent on `Seas-iMac-3` + game-dev agent on this Mac (`mads-mac-mini`). Small browser game gets built locally; when it needs promotion, game-dev messages SEO. Agents communicate across machines. Memory and context behavior observed. Everything driven through the dashboard — **not scripts**.

**Test harness:** Playwright (headless Chromium) drives the real dashboard UI at `http://localhost:9999`. Every action below is either a button click, form submission, or navigation — not a direct API hit. Screenshots saved alongside each step.

**Constraints:** I cannot keep a `claude` TUI open autonomously on either Mac. So an agent's "next turn" (where it would `receive_messages` and `arsenal_add` via Claude Code running) is simulated by running the same skill tools directly from the shell. The tools are the same Python modules Claude Code would invoke — this isolates the harness-mechanism from the LLM-in-the-loop part.

---

## Step inventory (populated as each finishes)

_(this file grows as the test runs. Entries below.)_
