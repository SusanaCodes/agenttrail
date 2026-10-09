# Consolidated security assessment (AC-47)

**Status: draft.** Three verification items are still pending (see
[Verification record](#verification-record)). This document does not
authorise publication and does not say the repository is ready to
publish.

| Item | Value |
|---|---|
| Assessment date | 8 October 2026 |
| Commit the two reviews examined | `138cec050e0c176660c59dc98c3df90ac8e9a08d` (`main` on 12 September 2026) |
| Current assessed baseline | `0556eeff9e783044b5b2f8057bb3a7a9172341be` (`main` on 8 October 2026) |
| Later update | 9 October 2026: `CODEOWNERS` added under AC-35. Entries changed by it are dated. The findings and the baseline are otherwise as assessed on 8 October |
| Maintainer responsible for follow-up | Susana ([@SusanaCodes](https://github.com/SusanaCodes)) |

The baseline is the commit this assessment was written against. It is
not a code-freeze commit and it is not the final publication
verification commit; neither of those has been recorded yet.

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
finding below is therefore in the state the reviews found it.

## Findings

Severities are the reviews' own. Where the two differ, both are shown.
"n/r" means that review did not report the finding.

### Open implementation defects and weaknesses

None of these is fixed at the baseline.

| Finding | Review 1 | Review 2 | State at the baseline | Ticket |
|---|---|---|---|---|
| Rejected case-input and model-output values are echoed in exception messages, which reach stderr and CI logs | Low | Medium | Open. The behaviour is now described in the project manual; that is a disclosure, not a fix | [AC-36](https://thesreflow.atlassian.net/browse/AC-36) |
| The redaction gate scans raw line text, so a supported identifier written with JSON `\uXXXX` escapes is not detected. Reported from the source; not executed in either review | n/r | Medium | Open | [AC-37](https://thesreflow.atlassian.net/browse/AC-37) |
| A non-UTF-8 audit trail raises an uncaught decoding error; record lookup then exits with the code documented as "no record found" | Low (probed) | Low | Open | [AC-38](https://thesreflow.atlassian.net/browse/AC-38) |
| No `CODEOWNERS`; merge blocking depends on repository rules outside the repository | Medium | Informational | Open and unverified at the baseline. Update, 9 October 2026: a `CODEOWNERS` file is now on `main`; merge blocking is still unverified. See [Verification record](#verification-record) | [AC-35](https://thesreflow.atlassian.net/browse/AC-35) |
| Evaluation does not check stored inputs, `model_id` or `prompt_version` against the configuration, and fixture metadata is not cross-checked | Low (probed) | Medium (part) | Open. The original ticket, AC-40, was closed unimplemented on 19 September 2026 | [AC-70](https://thesreflow.atlassian.net/browse/AC-70) |
| The decision returned to a caller can differ from the recorded decision without failing evaluation | n/r | Medium (shown by an existing test) | Open. The trail-derived verdict is by design; the correspondence control is absent | [AC-62](https://thesreflow.atlassian.net/browse/AC-62) |
| Audit writes follow a symlink at the trail path, and an existing file keeps wider permissions | Medium for a pilot, Low for the demonstration (probed) | Medium | Open | [AC-71](https://thesreflow.atlassian.net/browse/AC-71) |
| The live recorder stores every response field except two named ones | n/r | Medium (part) | Open | [AC-63](https://thesreflow.atlassian.net/browse/AC-63) |
| The runtime dataset loader is weaker than the schema, and a gate run with `--dataset` can pass on a subset | n/r | Low | Open. The committed dataset is pinned by tests. The `--dataset` flag is now described in `docs/ci-gate.md` | [AC-72](https://thesreflow.atlassian.net/browse/AC-72) |
| Readers have no size, line-length or depth limits | Low | Low | Open | [AC-67](https://thesreflow.atlassian.net/browse/AC-67) |
| Duplicate JSON keys are silently reduced to the last value | n/r | Low (part) | Open | [AC-68](https://thesreflow.atlassian.net/browse/AC-68) |
| Some malformed model-output types raise an untyped error, and envelope fields are unchecked. Reported from the source; not executed | n/r | Low (part) | Open | [AC-74](https://thesreflow.atlassian.net/browse/AC-74) |
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
| Self-referential gate evidence | The fixtures, labels, policy constants, version registry and workflow that define a pass are changed by the same pull request the gate judges. Review of that change, and repository rules, are the only controls, and neither is verifiable from the repository | Review 1 Medium; Review 2 Informational and residual | [AC-35](https://thesreflow.atlassian.net/browse/AC-35) for repository rules and `CODEOWNERS`. Nothing removes the dependence on review. The `CODEOWNERS` file added on 9 October 2026 records ownership; in a sole-owner repository it does not establish independent review |

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

No change in this list fixes an implementation defect in the first
findings table.

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

## Verification record

| Item | Result | Evidence |
|---|---|---|
| Repository enforcement: required check, bypass off, `CODEOWNERS` (AC-35) | **Pending. Not verified.** | At the 8 October baseline there was no `CODEOWNERS` file. **Update, 9 October 2026:** `.github/CODEOWNERS` is on `main`, assigning `agenttrail/`, `data/`, `fixtures/`, `tests/` and `.github/` to the maintainer; evidence is merged [pull request #8](https://github.com/SusanaCodes/agenttrail/pull/8), merge commit `71047b932e729e3c5201cd00aa57795c7c2fbfc9`. Requiring the `evaluation-gate` check and disabling bypass remain unverified, pending activation after authorised publication. Mandatory code-owner approval is deferred because this is a sole-owner repository: `CODEOWNERS` records ownership and does not establish independent review. AC-35 remains open. The repository is private. Reads of branch protection and rulesets were refused with HTTP 403 on 7 and 8 October 2026, which says nothing about what is configured. A read of the branch summary on 8 October 2026 reported `protected: false`; that is one field, not a check of rules. The blocked throwaway pull request that AC-35 requires has not been run. Passing CI is not enforcement |
| Manual redaction sweep of `docs/`, `tests/` and `showcase/` (AC-39) | **Pending. Not run.** | It is defined to run after the AC-37 fix, which is not merged |
| Sweep for absolute claims (AC-44) | Done for the named documents | Commit `2799b58`. Retained uses are negations or statements checked against the code |
| Code-freeze commit | **None recorded.** | The September freeze ticket (AC-42) was closed without a commit hash. The baseline above is not a freeze commit |
| CI at the baseline | Pass | `evaluation-gate` and `deployment-demo` in [run 37841399551](https://github.com/SusanaCodes/agenttrail/actions/runs/37841399551); `secret-scan` and `dependency-audit` in [run 37841399583](https://github.com/SusanaCodes/agenttrail/actions/runs/37841399583). Both ran on `0556eef` |
| Scheduled security scan | **Not yet observed.** | No schedule-triggered run had occurred by the assessment date |
| Dependency audit | See the open-code assessment | [Dependency audit evidence](open-code-assessment.md#dependency-audit-evidence-for-ac-47) |
| Final verification of the commit to be published (AC-48) | **Pending. Not run.** | Any commit after the baseline, including the one that adds this page, requires it to be run against the new commit |

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
- It does not re-test the reviews' findings. It reports what they
  found, what the repository contains at the baseline, and what is
  still unverified.
