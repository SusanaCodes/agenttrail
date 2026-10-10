# Consolidated security assessment (AC-47)

**Status: working assessment, not a release sign-off.** Two
verification items are still pending (see
[Verification record](#verification-record)): repository enforcement,
and final verification of the exact commit to be published. This
document does not authorise publication and does not say the
repository is ready to publish.

| Item | Value |
|---|---|
| Assessment date | 8 October 2026 |
| Commit the two reviews examined | `138cec050e0c176660c59dc98c3df90ac8e9a08d` (`main` on 12 September 2026) |
| Current assessed baseline | `0556eeff9e783044b5b2f8057bb3a7a9172341be` (`main` on 8 October 2026) |
| Later updates | 9 October 2026: `CODEOWNERS` added under AC-35, validation error messages fixed under AC-36 (pull request #10), and the redaction gate's escape bypass fixed under AC-37 (pull request #11, merged as `fa285361b0f315025d43989e009fc483f4c5d6d9`). 10 October 2026: a third, pre-publication review of `fa28536`, recorded in [Pre-publication review](#pre-publication-review-10-october-2026); the AC-38 encoding defect fixed; the AC-39 sweep run against `fa28536`, then repeated as an expanded sweep against `3fa9d8f118961ddec5b18437c9f8ee402aa4fce3` (`main` after pull request #13) with the NHS-shaped example replaced, see the AC-39 row of the [Verification record](#verification-record). Entries changed by these are dated. The findings and the baseline are otherwise as assessed on 8 October |
| Maintainer responsible for follow-up | Susana ([@SusanaCodes](https://github.com/SusanaCodes)) |

The baseline is the commit this assessment was written against. It is
not a code-freeze commit and it is not the final publication
verification commit; neither of those has been recorded yet. The
10 October review examined `fa28536`, which is later than the baseline
and is also not the final commit.

This page consolidates two security reviews and records what has and
has not changed since. It supersedes the findings of the earlier
[pre-publication safety review](pre-publication-safety-review.md),
which predates both reviews and stays in the repository as dated
historical evidence. It is separate from the
[open-code assessment](open-code-assessment.md), which maps the
repository to publication guidance under AC-51.

## Scope and method

Two separate AI-assisted reviews were run on 12 September 2026, each by
the maintainer with a different AI coding assistant, from the same
written brief, against the same commit. Neither is an independent human
audit or a penetration test. Both reported a clean working tree before
and after, and neither changed the repository. The raw reviews are not
published here; this page is the maintainer's consolidation of them.

| | Review 1 (probe-based) | Review 2 (read-only) |
|---|---|---|
| Source inspection | Every module in `agenttrail/`, the three schemas, both fixture sets, the golden dataset, the workflow, and key documentation | Implementation, tests, schemas, fixtures, dataset, workflow, documentation, and the structure and metadata of the showcase deck file |
| Existing checks executed | Unit suite (345 tests, pass), redaction gate (pass), gate for `v1` (pass) and `v2` (fail, exit 1) | The same four checks, with the same results |
| Additional method | Scratch-copy probes outside the repository, including two mutated copies of the package and edited copies of the fixtures and trail; a search of every revision for secret-shaped strings | None. Scenarios were verified against the source and, in one case, an existing test; no exploit was executed |
| Stated exclusions | GitHub repository settings (not queried); no network and no AWS | GitHub rules, AWS configuration, installed-package vulnerabilities, and the complete Git history. Earlier review documents were treated as claims, not evidence |
| Overall conclusion | No blocker for public demonstration or publication; the headline safety claim was overstated | No confirmed technical blocker to publishing the synthetic demonstration with its limitations stated; not ready for a real-data pilot; no Critical or High finding |

No file under `agenttrail/`, `tests/`, `data/` or `fixtures/` differs
between the reviewed commit and the baseline. Every implementation
finding below is therefore in the state the reviews found it, unless a
dated update on its row says otherwise.

## Findings

Severities are the reviews' own. Where the two differ, both are shown.
"n/r" means that review did not report the finding.

### Open implementation defects and weaknesses

None of these is fixed at the baseline.

| Finding | Review 1 | Review 2 | State at the baseline | Ticket |
|---|---|---|---|---|
| Rejected case-input and model-output values are echoed in exception messages, which reach stderr and CI logs | Low | Medium | Open at the baseline, where the project manual described the behaviour; that was a disclosure, not a fix. Update, 9 October 2026: fixed in [pull request #10](https://github.com/SusanaCodes/agenttrail/pull/10). Case-input, model-response, audit-record and fixture-entry validation errors no longer include rejected values or unexpected key names. Regression tests cover those validators and the gate and record-lookup error paths | [AC-36](https://thesreflow.atlassian.net/browse/AC-36) |
| The redaction gate scans raw line text, so a supported identifier written with JSON `\uXXXX` escapes is not detected. Reported from the source; not executed in either review | n/r | Medium | Open at the baseline. Update, 9 October 2026: fixed in [pull request #11](https://github.com/SusanaCodes/agenttrail/pull/11), merged as `fa28536`. The gate also scans each decoded key and string value of every valid JSON line, and of every JSON document stored inside a decoded string, as the fixtures store their case fields. Regression tests reproduce the bypass against the earlier gate and pass against the fix. The remaining encoding limits are listed in [redaction-gate.md](redaction-gate.md#known-limitations) and were probed on 10 October (see [Pre-publication review](#pre-publication-review-10-october-2026)) | [AC-37](https://thesreflow.atlassian.net/browse/AC-37) |
| A non-UTF-8 audit trail raises an uncaught decoding error; record lookup then exits with the code documented as "no record found" | Low (probed) | Low | Open at the baseline. The 10 October review reproduced it more widely: the same uncaught error, with a traceback, gave exit `1` from `record_view`, `policy_replay`, `eval` and `ci_gate` for a non-UTF-8 trail, fixture file or dataset, and exit `1` is documented for those two gate commands as a behavioural failure. Update, 10 October 2026: fixed in the change set that adds this entry. Each of the three loaders (`audit_reader`, `fixtures`, `golden`) translates the decoding error into its own typed malformed-input error, naming the file only and not chaining the decoder's message, so every CLI exits `2`. Regression tests plant invalid bytes at the start and end of each input and drive the four CLIs; they fail on `fa28536` and pass with the fix. Recursion-depth and size limits are not part of this fix and stay under AC-67 | [AC-38](https://thesreflow.atlassian.net/browse/AC-38) |
| No `CODEOWNERS`; merge blocking depends on repository rules outside the repository | Medium | Informational | Open and unverified at the baseline. Update, 9 October 2026: a `CODEOWNERS` file is now on `main`; merge blocking is still unverified. See [Verification record](#verification-record) | [AC-35](https://thesreflow.atlassian.net/browse/AC-35) |
| Evaluation does not check stored inputs, `model_id` or `prompt_version` against the configuration, and fixture metadata is not cross-checked | Low (probed) | Medium (part) | Open. The original ticket, AC-40, was closed unimplemented on 19 September 2026 | [AC-70](https://thesreflow.atlassian.net/browse/AC-70) |
| The decision returned to a caller can differ from the recorded decision without failing evaluation | n/r | Medium (shown by an existing test) | Open. The trail-derived verdict is by design; the correspondence control is absent | [AC-62](https://thesreflow.atlassian.net/browse/AC-62) |
| Audit writes follow a symlink at the trail path, and an existing file keeps wider permissions | Medium for a pilot, Low for the demonstration (probed) | Medium | Open | [AC-71](https://thesreflow.atlassian.net/browse/AC-71) |
| The live recorder stores every response field except two named ones | n/r | Medium (part) | Open | [AC-63](https://thesreflow.atlassian.net/browse/AC-63) |
| The runtime dataset loader is weaker than the schema, and a gate run with `--dataset` can pass on a subset | n/r | Low | Open. The committed dataset is pinned by tests. The `--dataset` flag is now described in `docs/ci-gate.md` | [AC-72](https://thesreflow.atlassian.net/browse/AC-72) |
| Readers have no size, line-length or depth limits | Low | Low | Open | [AC-67](https://thesreflow.atlassian.net/browse/AC-67) |
| Duplicate JSON keys are silently reduced to the last value | n/r | Low (part) | Open | [AC-68](https://thesreflow.atlassian.net/browse/AC-68) |
| Some malformed model-output types raise an untyped error, and envelope fields are unchecked. Reported from the source; not executed | n/r | Low (part) | Open. Update, 10 October 2026: one related test gap closed. Relaxing the "exactly one content block" check to accept extra blocks after a valid tool call survived the whole suite; a test now covers a valid tool call followed by a text block and by a second tool call. The production check itself was already correct and is unchanged | [AC-74](https://thesreflow.atlassian.net/browse/AC-74) |
| The fixture recorder's no-overwrite check can be raced. Reported from the source; not executed | n/r | Low | Open | [AC-73](https://thesreflow.atlassian.net/browse/AC-73) |
| Live recorder: unvalidated region, no model restriction, default retries, no call cap, no IAM guidance | Low | Informational | Open, with one part changed: see [Implemented changes](#implemented-changes-since-the-reviews) | [AC-66](https://thesreflow.atlassian.net/browse/AC-66) |
| No test covers concurrent audit writers or storage failures beyond a short write | Test gap | Test gap | Open | [AC-69](https://thesreflow.atlassian.net/browse/AC-69) |

### Disclosed limitations

These are properties of the design. The documentation now states them.
Stating them changed no behaviour.

| Limitation | Review 1 | Review 2 | Where it is stated | Ticket |
|---|---|---|---|---|
| The original headline claim, "an unsafe AI change cannot pass silently", was overstated | Verdict | Verdict | Replaced under AC-43 and AC-44 in commit `2799b58`; see [Publication limitations](#publication-limitations) | [AC-43](https://thesreflow.atlassian.net/browse/AC-43), [AC-44](https://thesreflow.atlassian.net/browse/AC-44) |
| The behavioural gate never exercises the low-confidence override, because no recorded response is a `decide` below the threshold. Review 1 removed the override in a scratch copy: the gate still passed and the unit tests failed | Medium | n/r | [ci-gate.md](ci-gate.md#known-coverage-gap-the-low-confidence-override), added under AC-45 in commit `5d6c4d6` | [AC-61](https://thesreflow.atlassian.net/browse/AC-61) |
| No stored `policy_version`, so policy replay relies on a declared assumption | Informational | Noted | [policy-replay.md](policy-replay.md) | [AC-25](https://thesreflow.atlassian.net/browse/AC-25) |
| The redaction gate covers three committed data files and three identifier formats by default | Informational | Noted | [redaction-gate.md](redaction-gate.md), README | [AC-39](https://thesreflow.atlassian.net/browse/AC-39) for a one-off manual sweep. No ticket widens the default scope |
| A passing gate is not bound to any released artefact | n/r | Informational | [ci-gate.md](ci-gate.md): no real deployment workflow exists | None |
| Real case data would make audit records personal data; there is no retention, encryption or pseudonymisation | Informational | Residual risk | README and project manual: synthetic data only | None |

The four limitations that carry the most weight are recorded as risks
in the next section.

## Risks

These four are recorded as risks of relying on the demonstration. No
formal risk-acceptance decision has been recorded for any of them: the
[risk-acceptance record](open-code-assessment.md#risk-acceptance-record)
in the open-code assessment is empty and covers reported
vulnerabilities, not design limitations. Nothing here is a production
approval.

| Risk | What it means | Reviews | Planned control |
|---|---|---|---|
| Fixture authenticity | The request hash covers the request only. A stored response can be edited or written by hand and still validates. The gate cannot tell a recording from a hand-built set | Review 1 High; Review 2 Medium | [AC-64](https://thesreflow.atlassian.net/browse/AC-64). [AC-32](https://thesreflow.atlassian.net/browse/AC-32) covers replay integrity and drift, not authenticity. Wording: [model-fixtures.md](model-fixtures.md#what-the-request-hash-does-and-does-not-establish) |
| Trail integrity | The trail is a local file with no record authentication. A well-formed forged or edited record validates, and removed records go unnoticed outside a fresh evaluation. It is not tamper-evident and not durable | Review 1 Medium for a pilot, Low for the demonstration; Review 2 Medium | [AC-65](https://thesreflow.atlassian.net/browse/AC-65); path handling under [AC-71](https://thesreflow.atlassian.net/browse/AC-71) |
| Model-owned confidence | Routing depends on a confidence value the model reports about itself. It is uncalibrated, and nothing independent forces escalation when evidence is missing | Review 1 Medium for a pilot, Low for the demonstration; Review 2 Informational | None. No improvement is ticketed |
| Self-referential gate evidence | The fixtures, labels, policy constants, version registry and workflow that define a pass are changed by the same pull request the gate judges. Review of that change, and repository rules, are the only controls, and neither is verifiable from the repository. The 10 October review showed the workflow part concretely: adding `continue-on-error: true` or `\|\| true` to the gate step leaves the unit tests, the redaction gate and the `v1` gate green, so a required `evaluation-gate` check would still report success while its implementation ignored failure. A required check proves the job ran and reported success; it does not prove the job still enforces anything | Review 1 Medium; Review 2 Informational and residual | [AC-35](https://thesreflow.atlassian.net/browse/AC-35) for repository rules and `CODEOWNERS`. Nothing removes the dependence on review of `.github/`. The `CODEOWNERS` file added on 9 October 2026 records ownership; in a sole-owner repository neither it nor a required check establishes independent review |

## Controls confirmed working

Each row says which review confirmed it and how.

| Control | Review 1 | Review 2 |
|---|---|---|
| Closed model-output validation: one tool block, exact field set, enumerated decision, bounded numeric confidence, template consistent with decision, rationale rendered locally | Confirmed, including probes with non-finite and out-of-range confidence values | Confirmed from the source |
| Trail-derived scoring: evaluation scores the reopened trail and fails closed on missing, duplicate, unexpected or malformed records | Confirmed; existing tests cited | Confirmed; existing tests cited |
| Fail-closed replay: a fingerprint miss raises, with no live fallback and no AWS SDK import on the replay path | Confirmed | Confirmed |
| Workflow hardening: read-only token, actions pinned to full commit SHAs, no secrets, no `pull_request_target`, input reaches the shell through an environment variable | Confirmed | Confirmed |
| Search of Git history for secret-shaped strings | Its own search of every revision found none | **Not checked.** Review 2 excluded complete history and did not rely on earlier scans |

The history result therefore rests on Review 1's search and on two
scans recorded elsewhere, not on agreement between the reviews: the
September scan in the
[pre-publication safety review](pre-publication-safety-review.md) and
the 7 October scan in the
[open-code assessment](open-code-assessment.md#refreshed-secret-and-history-review).

## Implemented changes since the reviews

| Change | Commit | Effect on the findings |
|---|---|---|
| Optional dependencies hash-locked; dependency-audit and secret-scan jobs; Dependabot; security policy (AC-51) | `b19f94d` | Addresses the unpinned `boto3` part of the live-recorder finding. The rest of that finding is open |
| Action pins updated by two Dependabot pull requests | `b63ab64`, `37ee14e` | None |
| Headline claim narrowed; absolute wording qualified (AC-43, AC-44) | `2799b58` | Documentation only |
| Coverage gap and fixture-provenance limits documented (AC-45, AC-46) | `5d6c4d6` | Documentation only |
| `CODEOWNERS` added for `agenttrail/`, `data/`, `fixtures/`, `tests/` and `.github/` (AC-35, in part), 9 October 2026 | `d8b67eb`, merged as `71047b9` | Supplies the missing file. Merge enforcement is unchanged and unverified |
| Redaction gate scans decoded JSON keys and string values as well as raw text, including JSON stored inside strings (AC-37), 9 October 2026 | [pull request #11](https://github.com/SusanaCodes/agenttrail/pull/11), merged as `fa285361b0f315025d43989e009fc483f4c5d6d9` | Fixes the JSON-escape bypass, in the line and in JSON documents stored in its strings. Findings still carry file, line and category only. Other encodings are still not decoded |
| Validation error messages no longer echo rejected values or unexpected key names (AC-36), 9 October 2026 | [pull request #10](https://github.com/SusanaCodes/agenttrail/pull/10), merged as `d205b26` | Fixes the echoed-values finding. Message text only; validation behaviour, exception types and exit codes are unchanged |
| Non-UTF-8 trails, fixture files and datasets are typed malformed-input errors with exit `2` (AC-38); a test for extra content blocks after a valid tool call (AC-74, in part), 10 October 2026 | The change set that adds this row | Fixes the exit-code finding across all three loaders and four CLIs; closes one test gap. No evaluation, gate or policy behaviour changes; the suite grows from 430 to 442 tests |

The AC-36, AC-37 and AC-38 changes are the only ones in this list
that fix an implementation defect in the first findings table.

## Publication limitations

The claim the repository makes is this sentence and no more:

> AgentTrail detects tested routing regressions recorded in the audit
> trail for the selected fixture snapshot.

It does not establish that:

- fixture responses are authentic model output;
- a failed gate blocks a merge, which depends on GitHub repository
  rules that are currently unverified;
- a real deployment is blocked, because the only deployment job is a
  no-op simulation;
- the low-confidence override is exercised by the behavioural gate;
- the audit trail has not been altered;
- the current live model behaves as the recorded snapshot did;
- the project meets any legal requirement or is ready for production
  or for real case data.

The `v2` failures are deliberately seeded in synthetic fixtures.

## Deferred improvements

All are deferred, outside the publication scope, and unscheduled. The
maintainer named above is responsible for each.

| Improvement | Ticket |
|---|---|
| `policy_version` on audit records | [AC-25](https://thesreflow.atlassian.net/browse/AC-25) |
| Fixture-replay integrity gate (replay consistency and drift) | [AC-32](https://thesreflow.atlassian.net/browse/AC-32) |
| Synthetic gate scenario for the low-confidence override | [AC-61](https://thesreflow.atlassian.net/browse/AC-61) |
| Returned-versus-recorded decision correspondence | [AC-62](https://thesreflow.atlassian.net/browse/AC-62) |
| Allow-list of stored Bedrock response fields | [AC-63](https://thesreflow.atlassian.net/browse/AC-63) |
| Independent authentication of fixture provenance | [AC-64](https://thesreflow.atlassian.net/browse/AC-64) |
| Audit storage integrity, hash chaining and anchored checkpoints | [AC-65](https://thesreflow.atlassian.net/browse/AC-65) |
| Live recorder IAM, model and region, budget, timeout and retry controls | [AC-66](https://thesreflow.atlassian.net/browse/AC-66) |
| Reader file-size, line-length and JSON-depth limits | [AC-67](https://thesreflow.atlassian.net/browse/AC-67) |
| Duplicate JSON-key rejection | [AC-68](https://thesreflow.atlassian.net/browse/AC-68) |
| Concurrent-writer and storage-failure testing | [AC-69](https://thesreflow.atlassian.net/browse/AC-69) |
| Audit and fixture provenance checks in the evaluator | [AC-70](https://thesreflow.atlassian.net/browse/AC-70) |
| Audit-writer symlink and existing-file permission handling | [AC-71](https://thesreflow.atlassian.net/browse/AC-71) |
| Runtime golden-dataset validation and subset acceptance | [AC-72](https://thesreflow.atlassian.net/browse/AC-72) |
| Fixture recorder overwrite race | [AC-73](https://thesreflow.atlassian.net/browse/AC-73) |
| Typed handling of malformed model-output types | [AC-74](https://thesreflow.atlassian.net/browse/AC-74) |

## Pre-publication review, 10 October 2026

A third review was run on 10 October 2026 against `main` at
`fa285361b0f315025d43989e009fc483f4c5d6d9`, the merge of pull request
#11. Like the first two it was AI-assisted and run by the maintainer;
it is not an independent human audit. It worked from a clean clone of
the exact commit, kept every probe and mutation in copies outside the
checkout, made no network or model call from the code under review,
and left the checkout unchanged. Its purpose was to revalidate the
findings above against the current code before publication, not to
replace them.

**Method.** The AC-48 command set; the README quickstart from a fresh
clone with AWS configuration pointed at `/dev/null`; 31 mutation
probes on copies of the package, data, fixtures and workflow; 37
synthetic encoding variants against the redaction gate; invalid,
truncated, empty, duplicated and non-UTF-8 inputs against every CLI;
an eight-process concurrent-append test of the audit writer; Gitleaks
8.30.1 over every local ref and the reflog; a hash-locked install and
`pip-audit` of all three dependency sets on Python 3.12.14; a read of
the repository's settings; and a download and pattern scan of every
retained GitHub Actions log (69 runs, 270 log files, 4.5 MB).

**Results that confirm the controls above.** All 430 tests passed;
the redaction gate passed on its three targets; `v1` passed with
12/12; `v2` failed with exit `1`, naming the escalation rate on the
low-confidence set, 9/12. Of the 31 mutations, 28 were caught by the
unit tests, the `v1` gate or both, including a lowered baseline, a
raised tolerance, a swallowed exit code, deleted or relabelled failing
cases, edited `v1` and `v2` fixture responses, an audit record that
always says `escalate`, scoring from labels instead of the trail,
tolerated missing or invalid records, a canned fallback on a fixture
miss, the expected label leaking into the model input, and the default
agent version flipped to `v2`. Model confidence values of NaN,
±Infinity, `1e999`, out-of-range, boolean, string, null and a
400-digit integer were all rejected with exit `2`; the threshold
boundary is exact. Eight processes appending 500 records each produced
4,000 intact lines on a local filesystem. Gitleaks found no leak in 51
commits across every ref, nor in the tree; the pattern scan of the
Actions logs found no credential, token, key, account identifier,
personal name or local user path (the only matches were runner and
Dependabot job identifiers, a `pkg:pypi/...@version` package URL, and
GitHub's own `***` masking of the workflow token).

**Three mutations survived.** Relaxing the "exactly one content
block" check (now covered by a test, see the AC-74 row), and the two
workflow edits recorded under [Risks](#risks), which no test can
catch because the workflow file is outside the code under test.

**Findings.** None new of Medium or higher severity in the code. The
review widened AC-38 (fixed above), found the AC-74 test gap (closed
above), and recorded these facts, all Low or Informational:

- No `workflow_dispatch` run of the `v2` demonstration exists in this
  repository's Actions history, so the red run and skipped
  `deployment-demo` job described in the README, the demo scenario and
  the project manual are verified locally and from the workflow file,
  not from an Actions run. One manual `v2` dispatch after publication
  would supply that evidence.
- A commit force-pushed out of pull request #10 on 9 October 2026,
  `8611f3e24220d56e7886d16e9098e526a4ecdb89`, is unreachable from any
  branch but is still retrievable from GitHub by hash. Its CI run
  ([37983821442](https://github.com/SusanaCodes/agenttrail/actions/runs/37983821442))
  failed `secret-scan` on Gitleaks' `generic-api-key` rule at
  `tests/test_error_hygiene.py:58`, and the 10 October reflog scan
  reproduced that one finding. The flagged line was read during the
  review: it is a synthetic test marker whose variable name contained
  the word `KEY`, not a credential. The constant was renamed in the replacement
  commit and no value was rotated because there was none to rotate.
  The CI history scan (`--all`) does not reach that commit; a scan
  with `--reflog` reports it, and a reader who runs one will see the
  same false positive.
- Policy replay accepts a trail that covers only part of the dataset
  and reports the count it replayed (for example `records evaluated:
  10`). A trail left by an interrupted `eval --audit-path` run would
  therefore understate policy impact if the count were not read. A
  rerun of `eval` refuses an existing path.
- The redaction gate's remaining limits were demonstrated rather than
  only described: of 37 synthetic variants, the 14 that were detected
  were the raw and JSON-escaped forms at any nesting depth; the 23
  misses were identifiers split across strings, non-ASCII digits or
  separators, tokens glued to letters or underscores, other encodings,
  and JSON escapes on a line that is not itself a valid JSON document
  (a byte-order mark, trailing text or two documents on one line).
  These are the limits [redaction-gate.md](redaction-gate.md#known-limitations)
  states. An empty target passes.
- The audit writer follows a symlink at the trail path and leaves a
  pre-existing file's wider permissions in place (AC-71, reproduced).
  A forged, well-formed record renders in record lookup (AC-65). An
  edited fixture response validates with its request hash intact
  (AC-64). The `v1` gate stays green with the low-confidence override
  removed; only the unit tests catch it (AC-45, AC-61). None of these
  is new.

**What the review did not do.** It did not change any GitHub setting,
trigger a workflow, open a test pull request, or read branch rules
(refused with HTTP 403 on the current plan). The quickstart was run
from an authenticated clone, because the repository is private; the
logged-out clone belongs to AC-53. Commit signatures were not
verified. The showcase deck was inspected as a file, not rendered.

## Verification record

| Item | Result | Evidence |
|---|---|---|
| Repository enforcement: required check, bypass off, `CODEOWNERS` (AC-35) | **Pending. Not verified.** | At the 8 October baseline there was no `CODEOWNERS` file. **Update, 9 October 2026:** `.github/CODEOWNERS` is on `main`, assigning `agenttrail/`, `data/`, `fixtures/`, `tests/` and `.github/` to the maintainer; evidence is merged [pull request #8](https://github.com/SusanaCodes/agenttrail/pull/8), merge commit `71047b932e729e3c5201cd00aa57795c7c2fbfc9`. Requiring the `evaluation-gate` check and disabling bypass remain unverified, pending activation after authorised publication. Mandatory code-owner approval is deferred because this is a sole-owner repository: `CODEOWNERS` records ownership and does not establish independent review. AC-35 remains open. The repository is private. Reads of branch protection and rulesets were refused with HTTP 403 on 7, 8 and 10 October 2026, which says nothing about what is configured. A read of the branch summary on 8 and 10 October 2026 reported `protected: false` and `enforcement_level: off`; that is a summary, not a check of rules. The blocked throwaway pull request that AC-35 requires has not been run. Passing CI is not enforcement, and a required check does not show that the job still enforces anything (see [Risks](#risks)) |
| Manual redaction sweep of `docs/`, `tests/` and `showcase/` (AC-39) | **Expanded sweep run on 10 October 2026 against `3fa9d8f`, the candidate after pull request #13, and repeated on the committed tree of this change set. Scanner result: exit `1` for `docs/` and `tests/`, exit `0` for `showcase/`. Manual acceptance decision: no unresolved sensitive finding; every retained match is an individually reviewed, intentional detector example. The ticket's original "clean scan" criterion is not met literally and is not claimed.** | Method: the scanner at commit `da59f0e` (the merged AC-37 gate, unchanged since), run as `python3 -m agenttrail.redaction_gate` with each directory's tracked files passed explicitly. The two binary files were excluded because the scanner rejects them with exit `2` (`UnicodeDecodeError`) rather than scanning them. `docs/`: 17 of 18 tracked files, exit `1`, 3 findings, one per category, all on the three detector-example lines of the syntax table in `docs/redaction-gate.md`. `tests/`: all 24 tracked files, exit `1`, 32 findings: 31 in the four `test_redaction_gate*.py` files (detector test vectors and the fragment, escape and nesting cases that exercise the AC-37 decoding) and 1 planted value in `tests/test_record_view.py`, which asserts that the value never reaches record-lookup output. `showcase/`: 7 of 8 tracked files, exit `0`, 0 findings. Files the scanner cannot read were inspected by hand: `docs/assets/ci-gate-v2-failure.png` is a screenshot of the `v2` gate output, and its text transcript `ci-gate-v2-failure.txt` was in the scan; the deck `showcase/AgentTrail-final-showcase.pptx` has no embedded media and empty author metadata, and its slide and notes text was extracted, scanned (exit `0`, 0 findings) and read. All 50 tracked files were also inspected by hand for what the scanner does not detect: no credential, token, key or AWS account identifier; no email address, phone number, IP address, internal hostname or local filesystem path. The maintainer's name and public GitHub handle appear as the accountable owner by design, the showcase templates require witnesses to be recorded by role only, and the AWS region `eu-west-2` remains the documented borderline item. Dispositions: 35 scanner findings, all intentional synthetic detector or test vectors, each occurrence read; 0 genuine sensitive content; 0 unexplained. One change: the NHS-shaped example in the manual and the redaction tests was a published worked example that is checksum-valid and outside the 999 range reserved for test data; it was replaced by a checksum-valid number in that reserved range. The deliberately checksum-invalid vector that pins the no-checksum design is kept, and the finding counts are unchanged. Coverage limits: the scanner detects three identifier shapes only; `.py` and `.md` lines are raw-text scans; the manual inspection is one person's reading for the stated categories and does not prove that no personal data is present. Acceptance basis proposed for AC-39: an exit-`1` scan is recorded as exit `1`; the sweep is accepted on the basis of no unresolved sensitive findings, with every retained intentional vector individually reviewed and documented here, not on the original zero-findings criterion. No scanner exclusion was added and the default target set is unchanged. The SHA of the committed tree and the repeated sweep's figures are recorded on AC-39 |
| Sweep for absolute claims (AC-44) | Done for the named documents | Commit `2799b58`. Retained uses are negations or statements checked against the code |
| Code-freeze commit | **None recorded.** | The September freeze ticket (AC-42) was closed without a commit hash. The baseline above is not a freeze commit |
| CI at the baseline | Pass | `evaluation-gate` and `deployment-demo` in [run 37841399551](https://github.com/SusanaCodes/agenttrail/actions/runs/37841399551); `secret-scan` and `dependency-audit` in [run 37841399583](https://github.com/SusanaCodes/agenttrail/actions/runs/37841399583). Both ran on `0556eef` |
| CI at `fa28536` (the merge of pull request #11) | Pass | `evaluation-gate` and `deployment-demo` in [run 37991186650](https://github.com/SusanaCodes/agenttrail/actions/runs/37991186650); `secret-scan` and `dependency-audit` in [run 37991186644](https://github.com/SusanaCodes/agenttrail/actions/runs/37991186644). Both ran on `fa285361b0f315025d43989e009fc483f4c5d6d9` on 9 October 2026 |
| Scheduled security scan | **Observed.** | Two schedule-triggered `security-hygiene` runs have succeeded: [37936762832](https://github.com/SusanaCodes/agenttrail/actions/runs/37936762832) on 9 October 2026 against `ec2aa90`, and [38052891123](https://github.com/SusanaCodes/agenttrail/actions/runs/38052891123) on 10 October 2026 against `fa28536`. Both passed `dependency-audit` and `secret-scan` |
| Dependency audit | See the open-code assessment; repeated on 10 October 2026 | [Dependency audit evidence](open-code-assessment.md#dependency-audit-evidence-for-ac-47). On 10 October all three locks installed with `--require-hashes --only-binary :all:` on CPython 3.12.14 (Linux aarch64 container), `pip check` was clean, and pip-audit 2.10.1 reported no known vulnerabilities for any set. The repository showed 0 open Dependabot alerts |
| Final verification of the commit to be published (AC-48) | **Pending. Not run on the final commit.** | The AC-48 command set was run on `fa28536` on 10 October 2026 from a clean clone: 430 tests, OK; redaction gate PASS, 3 files, 0 findings; `v1` PASS exit `0`, 12/12; `v2` FAIL exit `1`, 9/12, naming the breached property; working tree clean before and after. That is evidence for `fa28536`. `main` has since advanced through pull request #12 (`53463f8`) and pull request #13 (`3fa9d8f`), and this change set produces a further commit; none of these is the commit to be published while repository changes remain, and AC-48 must be repeated on that exact final commit |

## Provenance and publication position

Ownership of the work and the right to publish it under the MIT
licence are unresolved. The
[open-code assessment](open-code-assessment.md#licence-and-provenance)
records the position: no written determination exists, and AC-51
remains blocked on it. This assessment makes no determination either.
Publication remains conditional on a documented resolution of
ownership and publishing rights, and on completion of the pending
verification above.

## What this assessment is not

- It is not an independent audit, a certification or an endorsement.
- It is not a risk acceptance, a production approval or a statement of
  legal compliance.
- It does not re-test the first two reviews' findings beyond the
  10 October revalidation recorded above. It reports what the reviews
  found, what the repository contains at the baseline and at
  `fa28536`, and what is still unverified.
- It does not settle ownership or publishing rights, and it does not
  record a risk acceptance in their place.
