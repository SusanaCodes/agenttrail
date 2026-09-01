# Demo runbook — presentation day (two-minute showcase)

Operational checklist for running the AgentTrail showcase live within
the strict **two-minute** limit. The spoken content lives in
[demo-script.md](demo-script.md); this document is everything around
it. Work through it top to bottom on the presentation machine, ideally
twice: once the day before, once in the final 30 minutes.

## Ground rules

- **Fully offline.** Both live commands use only the Python standard
  library and committed fixtures. No network, no AWS credentials, no
  environment variables are needed.
- **The v2 red result is intentional.** `ci_gate --agent-version v2`
  exits with status 1 and prints `CI GATE: FAIL` plus a block report.
  That is the demonstration succeeding. Only an *unexpected* failure
  (exit 2, a traceback, a hang) is a problem.
- **Never debug on stage.** With a two-minute total, the fallback
  trigger is about **five seconds**: if the first command has not
  responded correctly within ~5 seconds, switch to the recording.
- **Do not delete audit evidence.** The preflight only ever creates
  new timestamped files under `audit/`; nothing here removes anything.

## Preflight (30–60 minutes before)

All commands from the repository root. Every one is non-destructive.

```bash
cd /path/to/agenttrail          # adjust to the machine's checkout
git status --short              # expect: clean, or only showcase work
python3 --version               # expect: Python 3.x present

# 1. Full test suite — expect exit 0, output ending "OK"
python3 -m unittest discover -s tests

# 2. Redaction gate — expect exit 0, "REDACTION GATE: PASS"
python3 -m agenttrail.redaction_gate

# 3. Safe gate — expect exit 0, "CI GATE: PASS"
python3 -m agenttrail.ci_gate --agent-version v1

# 4. Unsafe demo gate — expect exit 1 (INTENTIONAL), "CI GATE: FAIL"
python3 -m agenttrail.ci_gate --agent-version v2
echo $?                         # expect: 1

# 5. Verify the slide-3 replay figures (NOT run live — slide 3 cites
#    them, so they must be re-proven in preflight)
mkdir -p audit
preflight_audit="audit/preflight-$(date +%Y%m%d-%H%M%S).audit.jsonl"
python3 -m agenttrail.eval --audit-path "${preflight_audit}"   # exit 0, PASS
python3 -m agenttrail.policy_replay \
  --audit-path "${preflight_audit}" \
  --target-policy v2 \
  --legacy-baseline-policy v1   # exit 0, "unchanged: 35", "flipped: 1", SYN-031
```

If any step gives an unexpected result, do not improvise fixes on the
presentation machine — plan to use the fallback recording and
investigate afterwards.

Then verify the non-command items:

- [ ] Fallback recording present on this machine, played end to end
      within the last day (see
      [fallback-recording-checklist.md](fallback-recording-checklist.md));
      player pre-positioned in the Dock or an open Finder window
- [ ] `showcase/AgentTrail-final-showcase.pptx` opens in PowerPoint;
      flick through all **three** slides in presenter view; speaker
      notes visible on slide 1 (legal sources) if using presenter view
- [ ] Machine charged or on mains power; display adaptor tested
- [ ] Auto-lock / screensaver delayed to 30+ minutes

## Terminal setup (must be ready before the talk starts)

- One terminal window, full screen, **no tabs, no splits**.
- Working directory: **the repository root** — verify with `pwd`.
- Font size: **at least 18 pt; 20–24 pt for a large room**. The v2
  block report's longest line must fit without wrapping — check at
  the chosen size during preflight.
- High-contrast theme; avoid low-contrast pastel themes.
- **Cleared** (`clear`, or Cmd-K) immediately before the talk starts
  — there is no time to clear mid-talk.
- Simplify the prompt if yours is long (e.g. `export PS1='$ '` for
  that one session).
- **Privacy sweep:** no other windows visible; recent shell history
  clean if it could scroll into view; no personal files, names,
  tokens, or notifications anywhere on screen.
- **Positioned for a fast Cmd-Tab:** only PowerPoint and the terminal
  are running, so Cmd-Tab toggles directly between them. Quit
  everything else.

## Notifications and screen hygiene

- macOS: **Do Not Disturb / Focus on** for the whole session.
- Quit mail, chat, calendar, and browser sync apps — anything that
  can paint a notification over the screen.
- No credentials, secrets, personal data, or private URLs may appear
  on screen at any point. The demo needs none.

## Live sequence (total two minutes)

Two applications, two live commands, two Cmd-Tab switches:

| When | Where | Action | Expected |
|---|---|---|---|
| 0:00 | PowerPoint | Slide 1, speak | — |
| 0:22 | PowerPoint | Slide 2, speak | — |
| 0:45 | **Cmd-Tab** → terminal | `python3 -m agenttrail.ci_gate --agent-version v1` | exit **0** · `CI GATE: PASS` · `measured_rate=1.0000` · `low_confidence_escalated=12` |
| ~1:00 | terminal | `python3 -m agenttrail.ci_gate --agent-version v2` | exit **1 (intentional)** · `CI GATE: FAIL` · `measured_rate=0.7500` · 3 `mismatch:` lines · `Decision: Gate blocked` |
| 1:30 | **Cmd-Tab** → PowerPoint | Slide 3, close | — |
| 1:50 | — | stop speaking | ~10 s buffer |

Policy replay is **not** run live — slide 3 states its verified
result. Handling the intentional exit 1: the shell simply shows the
next prompt; nothing needs resetting.

Rehearse the two Cmd-Tab switches until they are silent and instant.
With two displays, mirroring off, keep the terminal on the projected
display and presenter notes on the laptop — and confirm during
preflight which display the audience sees.

## Fallback decision point

Switch to the recording — do not debug — when **any** of these is
true:

- the first command has not produced its expected output within
  roughly **five seconds** of pressing return;
- a command hangs, tracebacks, or exits 2;
- the terminal, display, or Cmd-Tab switch misbehaves and one instant
  retry has not fixed it.

Rollback procedure:

1. Say the fallback line from the script's recovery section ("Rather
   than debug on stage…").
2. Open the verified ~45–50-second recording from its pre-positioned
   location (see
   [fallback-recording-checklist.md](fallback-recording-checklist.md)).
3. Play full screen; narrate over it with the script's terminal-segment
   lines — the recording shows the identical v1-green / v2-red
   sequence, so the words fit it.
4. Continue to slide 3 and close normally. Do not return to the live
   terminal.

The recording is short enough that this route still fits the two
minutes. It is rehearsed (see [rehearsal-log.md](rehearsal-log.md)),
so taking it costs the talk almost nothing.
