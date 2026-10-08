# Demo script — AgentTrail final showcase (two minutes)

Word-for-word script for the **strict two-minute** showcase, presented
by Susana. Target **1:50 spoken**, leaving ~10 seconds of operational
buffer. Spoken text is in quotation blocks — say it naturally; it is
written for the ear. Stage directions are in *italics*.

There is **one** route. The previous seven-minute and five-minute
variants are withdrawn; do not rehearse them.

Companion documents: [demo-runbook.md](demo-runbook.md) (preflight and
operational detail) and
[fallback-recording-checklist.md](fallback-recording-checklist.md)
(the recording this script falls back to).

**Fallback cue (memorise this):** if the first terminal command does
not respond correctly within about **five seconds**, do not debug —
say the fallback line in the [recovery section](#recovery-language)
and play the verified recording. Two minutes leaves no troubleshooting
allowance.

Spoken length: ~225 words. At a brisk-but-natural 135–145 words per
minute that is ~93–100 seconds of speech; the two command runs, two
Cmd-Tab switches and the pause on the red result account for the
remaining ~15–20 seconds. **This runs at or slightly over the 1:50
target and has not been timed since the closing claim was lengthened —
time it in rehearsal.** If a timed run exceeds 1:50, the pre-agreed trim is
the sentence "That gives people evidence for review. It does not
automatically approve the policy." (keep it for questions instead).

---

## 0:00–0:22 — Slide 1 (regulatory hook)

*PowerPoint, slide 1. Stand still, speak to the audience.*

> "From December 2027, for many high-risk uses, 'the AI said so' will
> not be enough.
>
> Article 12 of the EU AI Act requires systems to support automatic
> logging, so important decisions can be traced.
>
> AgentTrail turns that principle into an engineering control."

*Advance to slide 2.*

## 0:22–0:45 — Slide 2 (architecture)

*Slide 2. Gesture down the flow, resting on the blue trail box.*

> "Here's how.
>
> The agent makes a decision, and AgentTrail stores it in an
> append-only audit trail.
>
> The evaluation reads that decision back from the trail, compares it
> with the expected behaviour, and the CI gate passes or fails the
> change.
>
> Recorded model responses keep the test deterministic and offline."

*HAND-OFF: Cmd-Tab to the terminal.*

## 0:45–1:30 — Terminal demonstration

*Terminal, already cleared, at the repository root.*

> "First, the safe version."

*Type:*

```bash
python3 -m agenttrail.ci_gate --agent-version v1
```

*While the green PASS block is on screen:*

> "It escalates all twelve low-confidence cases, so the gate passes.
>
> Now I'll run an intentionally unsafe version that has been made
> over-confident."

*Type:*

```bash
python3 -m agenttrail.ci_gate --agent-version v2
```

***PAUSE when the red result appears.** Stop typing. Point, in order,
at: `measured_rate=0.7500` · `9 of 12` escalated · the three
`mismatch:` lines · `Decision: Gate blocked`. Then:*

> "It escalates only nine cases and misses three decisions that
> should have gone to a human.
>
> The process exits with status one, so the gate fails.
>
> This red result is not the demo failing. It is the gate doing its
> job: failing on a regression I seeded for this demo."

*HAND-OFF: Cmd-Tab back to PowerPoint, advance to slide 3.*

## 1:30–1:50 — Slide 3 (result and close)

*Slide 3. Slow down. Deliver the final line to the audience, not the
slide.*

> "And because the trail exists, I can test a proposed policy against
> past decisions before applying it.
>
> Across thirty-six records, one decision would change.
>
> That gives people evidence for review. It does not automatically
> approve the policy.
>
> The claim is deliberately narrow:
>
> AgentTrail detects tested routing regressions recorded in the audit
> trail for the selected fixture snapshot."

**Stop there.** No thank-you slide, no future-work explanation —
keep those for questions if asked.

---

## If asked in questions

- **"Was v2 a real regression?"** — "No. v2 is an intentionally
  unsafe version built as a controlled demonstration, with its three
  failures deliberately seeded. A real change would fail the gate the
  same way only if it showed up in the tested cases and fixtures."
- **"Does a red gate stop the merge or the deployment?"** — "Not by
  itself. Merge blocking depends on GitHub repository rules requiring
  the evaluation-gate check, and that enforcement is currently
  unverified. The deployment job in the workflow is a no-op
  simulation; there is no real deployment."
- **"Can the fixtures be trusted?"** — "They are not authenticated.
  The fingerprint matches a request to its recorded entry; it does
  not sign the response."
- **"Is this EU AI Act compliance?"** — "No. It demonstrates an
  engineering pattern aligned with Article 12's logging and
  traceability requirement. It is not a legal-compliance claim, and
  this demonstrator is not a regulated high-risk system."
- **"Is the trail tamper-proof?"** — "No. It is a local append-only
  JSONL file, a demonstrator, and it is not even tamper-evident.
  Durable, integrity-protected storage is future work."
- **"Which decision changed in the replay?"** — "SYN-031: decided at
  0.90 confidence, it would escalate under the proposed 0.95
  threshold. The replay is change-impact evidence for a human review;
  it approves nothing."

## Recovery language

Two minutes allows exactly one calm retry and no on-stage debugging.

- **Typo / command not found.** Say: "Again." Re-type once. If the
  second attempt also fails, go straight to the fallback.
- **No correct response within ~5 seconds** (hang, traceback,
  exit 2, display trouble). Stop. Say:

  > "Rather than debug on stage, here is the recording of this exact
  > sequence, captured on this machine."

  Play the verified ~45–50-second fallback recording (pre-positioned
  per [demo-runbook.md](demo-runbook.md)) and narrate over it with
  the same terminal-segment lines above, then continue to slide 3.
- **Audience reacts to the red screen.** "This red result is the
  safety control doing its job." Continue.
- **You said a wrong number.** Correct it in three words and move on.
