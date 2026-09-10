# Fallback recording — checklist and recording sequence (macOS)

The safety net for the live demo: a short screen recording of the
exact two-command terminal sequence, verified end to end, held on the
presentation machine. If the live path fails, the script's fallback
cue switches to this recording within seconds (see
[demo-script.md](demo-script.md), recovery section, and the ~5-second
decision point in [demo-runbook.md](demo-runbook.md)).

**Status: the recording does not exist yet.** This file is the
checklist for making and verifying it. Ticket 13 is not complete —
and this checklist must not be marked done — until a real recording
exists and has been played back successfully from beginning to end.
Do not create a placeholder file and call it a recording.

## Target shape

- **Duration: approximately 45–50 seconds.** It must fit inside the
  two-minute talk when triggered at ~0:50. Substantially longer
  defeats its purpose; substantially shorter means outputs were not
  held long enough to read.
- **Content: the same v1-green / v2-red evidence as the live demo.**
  Policy replay is *not* in the recording — it is not run live either;
  slide 3 states its verified result.

## What the recording must show, in order

1. The v1 gate run ending green: `CI GATE: PASS` with
   `measured_rate=1.0000` and `low_confidence_escalated=12` — held
   ~5 seconds
2. The v2 gate run ending red: `CI GATE: FAIL` with
   `measured_rate=0.7500` and `low_confidence_escalated=9`
3. The **complete** human-readable failure report, on screen long
   enough to read: `AgentTrail safety gate: BLOCKED` through
   `Decision: Gate blocked`, including all three `mismatch:` lines
   (SYN-003, SYN-015, SYN-027) — held ~8–10 seconds

## Preparation checklist (before pressing record)

- [ ] Terminal set up exactly as in
      [demo-runbook.md](demo-runbook.md): full screen, repository
      root, ≥18 pt font (record at the size you will present at),
      high-contrast theme, scrollback cleared, minimal prompt
- [ ] macOS **Do Not Disturb / Focus on**; mail, chat, and calendar
      apps quit — nothing may paint a notification into the recording
- [ ] Privacy sweep: no credentials, tokens, personal data, private
      URLs, or client names anywhere on screen; shell history clean if
      it could scroll into view
- [ ] Cursor: solid block if avoidable; park the mouse pointer in a
      corner — do not wave it around
- [ ] Window: record the full screen or the full terminal window —
      decide once and keep it stable for the whole recording
- [ ] Resolution: the display's native resolution; 1920×1080 or
      better. Confirm text is crisp in a test clip before the real
      take
- [ ] No narration needed — the presenter speaks over the playback
      live. If recording narration anyway, check microphone level
      with a 10-second test
- [ ] Run the two commands once *without* recording, to warm up and
      confirm every expected output

## Recording sequence (macOS)

1. Press **Shift-Cmd-5** → choose *Record Entire Screen* (or *Record
   Selected Window* on the terminal) → under *Options*, microphone
   *None* (presenter narrates live) → **Record**.
2. Pause two seconds on the empty prompt, then perform at
   presentation pace:

   ```bash
   python3 -m agenttrail.ci_gate --agent-version v1

   python3 -m agenttrail.ci_gate --agent-version v2
   ```

   Hold the v1 PASS block ~5 seconds; hold the entire v2 failure
   report ~8–10 seconds, long enough to read `Decision: Gate blocked`
   and all three `mismatch:` lines.
3. Pause two seconds, then stop recording (**Shift-Cmd-5** → Stop, or
   the menu-bar stop button).
4. Check the duration: **~45–50 seconds**. Re-record if it is far off.

Imperfect take? Record again. A clean single take beats an edited one.

## Naming and storage

- Filename convention:
  `agenttrail-fallback-YYYYMMDD-take<N>.mov`
  (e.g. `agenttrail-fallback-20260819-take1.mov`).
- Store the working copy in `showcase/recordings/` — this directory is
  **git-ignored** (see `.gitignore`): the repository has no binary-
  asset or Git LFS policy, so the recording must never be committed.
- Keep a **second copy** on the presentation machine in a separate
  location, or on approved storage. Record *where* both copies live in
  the verification record below — name the kind of location (e.g.
  "presentation-machine Desktop", "approved programme drive") without
  exposing private storage paths or account details in this file.
- **Pre-position the player**: opening the file from the Dock/Finder
  to full-screen playback must take under 10 seconds — this is the
  on-stage path, and the two-minute limit depends on it.

## Verification (after recording — all mandatory)

- [ ] Played back **from beginning to end** on the presentation
      machine, watching the whole thing
- [ ] Duration confirmed at approximately 45–50 seconds
- [ ] All three required elements visible and readable at normal
      viewing distance (checked at the size the audience will see)
- [ ] No notification, credential, personal data, or stray window
      appears at any point
- [ ] Checksum computed and recorded below:

  ```bash
  shasum -a 256 showcase/recordings/agenttrail-fallback-*.mov
  ```

- [ ] Second copy exists; its checksum matches the first
- [ ] Opening the file from the Dock/Finder to full-screen playback
      takes under 10 seconds

## Verification record

To be completed by the presenter after a genuine recording and playback —
leave blank until then (do not fabricate). **This file is public:** no
private paths, hostnames, or account details in any field.

| Field | Record |
|---|---|
| Recording filename | _(to be completed)_ |
| Date recorded | _(to be completed)_ |
| Duration (target ~45–50 s) | _(to be completed)_ |
| SHA-256 checksum | _(to be completed)_ |
| Primary copy location (no private details) | _(to be completed)_ |
| Second copy location (no private details) | _(to be completed)_ |
| Full playback verified (date, generic machine description) | _(to be completed)_ |
| Time from Dock/Finder to full-screen playback | _(to be completed)_ |
