# Open-code assessment

**Assessment date:** 7 October 2026. **Assessor and owner:** Susana
(@SusanaCodes), the maintainer. **Ticket:** AC-51.

**Assessed state:** the evidence below was gathered on 7 October 2026
on the then-uncommitted working tree of branch
`chore/open-code-hygiene`, based on commit
`138cec050e0c176660c59dc98c3df90ac8e9a08d` (the head of `main` on the
assessment date). Nothing had been committed, pushed or run in GitHub
Actions at that point. Two wording corrections were made to
`SECURITY.md` on 8 October 2026 before the first commit; no evidence
was re-gathered for them. Those changes were then committed as
`b19f94d98efc54e69f8dbdd01c4eff2efc826c82`, and GitHub Actions ran on
that commit on 8 October 2026. That later evidence is kept apart in
[Evidence update: 8 October 2026](#evidence-update-8-october-2026).
A later change under AC-35 is recorded in
[Evidence update: 9 October 2026](#evidence-update-9-october-2026).
Everything else in this document is the 7 October local evidence
unless it says otherwise.

**Overall result: the minimum standard is not yet met.** Several
controls are implemented and were checked on a local machine on 7
October. The two workflows then passed once in GitHub Actions on 8
October, on a pull request. Nothing has run on `main` or on a schedule,
no check is required for merging, and no failure path has been
exercised. Other controls are configured but not activated or verified
while the repository is private, and some depend on other tickets. The gaps are listed under each item
and collected in [Outstanding before publication](#outstanding-before-publication).

## What this document is

AgentTrail uses the GDS/DSIT guidance
[AI, open code and vulnerability risk in the public sector](https://www.gov.uk/guidance/ai-open-code-and-vulnerability-risk-in-the-public-sector),
published on 14 May 2026, as its publication checklist. This document
maps each item in that guidance's "Minimum standard for
publicly-accessible systems" to repository evidence, an explicit gap,
or a justified exclusion.

It is the maintainer's own assessment of a prototype. It is not a
government endorsement, a certification, a claim of legal compliance,
or a claim of production readiness. The guidance is written for public
sector departments and their systems; it is applied here voluntarily
to a personal prototype repository with no deployed service.

Like every document in this repository, it records conclusions and
locations, never credentials, personal data or matched secret values.

### Status terms

| Status | Meaning |
|---|---|
| **Verified** | Implemented, and checked on the assessment date with the evidence named. "Verified locally" means on the maintainer's machine only, not in GitHub Actions. "As a document" means the text exists; the process it describes has not been exercised |
| **Configured, not active** | The file or setting exists on the branch but has not run, or cannot run, where it counts |
| **Pending** | Not done; needs the named ticket or publication step |
| **Excluded** | Not applicable to this prototype, with the reason given |

### Ticket references

`AC-n` keys are the project's current tickets. Older documents in this
repository use "Ticket N" numbering from the original build plan. The
two series are different and a "Ticket N" must not be read as `AC-N`.

## Scope

- **Repository:** `SusanaCodes/agenttrail`. Visibility on the
  assessment date: **private**.
- **System:** an offline, standard-library Python demonstrator run from
  a developer machine or a GitHub Actions runner. **There is no
  deployed service**: no hosted application, network endpoint,
  database, cloud infrastructure or stored credential. The only network
  path is the optional, human-run fixture recorder that calls Amazon
  Bedrock with the operator's own credentials.
- **Not assessed here:** the correctness of the evaluation and gate
  logic, which belongs to the consolidated security assessment
  (AC-47).

## Summary

| # | Minimum-standard item | Status |
|---|---|---|
| 1 | Named owner and maintenance plan | Verified in documents; `CODEOWNERS` pending on 7 October, on `main` since 9 October; required code-owner review deferred (AC-35 open) |
| 2 | Security contact, intake route and triage process | Policy written; **intake route not active**, pending publication |
| 3 | No secrets or sensitive operational detail, with enforced controls | Scans clean locally (7 October) and in one pull-request CI run (8 October); enforcement pending (required check, push protection) |
| 4 | Secure-by-design baseline | Partial evidence; threat model pending (AC-57); open defects in claimed controls (AC-36, AC-37, AC-38). A fix for AC-36 was proposed on 9 October and is not merged |
| 5 | Automated hygiene | Dependabot alerts and security updates enabled; scanning workflow passed once on a pull request (8 October), not yet on `main` or on schedule; version updates configured, not active; trunk protections unverified and unenforced (AC-35) |
| 6 | Patching expectations and ability to demonstrate them | Targets written; no track record yet |
| 7 | Safe posture for unmaintained code | Process verified in documents; deployed-service part excluded |

## Item-by-item mapping

### 1. Named owner and maintenance plan

> a named owner and maintenance plan, including a current service or
> team owner who is accountable for the repo, its dependencies, and how
> long it will be supported, visible through CODEOWNERS files or
> similar

| Control and scope | Evidence | Owner | Status | Remaining step |
|---|---|---|---|---|
| Named maintainer accountable for the repository and its dependencies | [README](../README.md#maintenance-security-and-dependencies), [maintenance.md](maintenance.md#maintainer), [SECURITY.md](../SECURITY.md#security-owner) | Susana | Verified | None |
| Support duration: head of `main` only, next review 7 January 2027, then three-monthly | [maintenance.md](maintenance.md#support-scope-and-review-date) | Susana | Verified | Renew or retire at each review |
| Dependency ownership and review frequency | [maintenance.md](maintenance.md#dependencies) | Susana | Verified | None |
| Handover arrangements | [maintenance.md](maintenance.md#handover) | Susana | Verified | None |
| `CODEOWNERS` file and required code-owner review | None in the repository on 7 October. Added on 9 October 2026: [CODEOWNERS](../.github/CODEOWNERS), see the [9 October update](#evidence-update-9-october-2026) | Susana | File present. Required code-owner review deferred | AC-35 owns this and remains open. Not duplicated here |

The guidance asks for ownership to be "visible through CODEOWNERS
files or similar". On 7 October the README and maintenance document
were the "similar" evidence; a `CODEOWNERS` file has been on `main`
since 9 October 2026. There is one maintainer and no deputy, which
is a real limit on resilience and is stated in both documents.

### 2. Security contact, intake route and triage process

> a security contact and intake route, with clear instructions for
> reporting vulnerabilities (for example, a SECURITY file and monitored
> mailbox) and a defined triage process

| Control and scope | Evidence | Owner | Status | Remaining step |
|---|---|---|---|---|
| Named security contact | [SECURITY.md](../SECURITY.md#security-owner) | Susana | Verified | None |
| Reporting instructions and sanitised report contents | [SECURITY.md](../SECURITY.md#reporting-a-vulnerability) | Susana | Verified as a document | None |
| Private intake route: GitHub private vulnerability reporting | `GET /repos/SusanaCodes/agenttrail/private-vulnerability-reporting` returned HTTP 404 on 7 October 2026 | Susana | **Pending. Not active** | Publication steps P1 and P2 |
| Monitored route: maintainer receives notifications | Not testable until the route is enabled | Susana | Pending | Publication step P2 |
| Defined triage process and targets | [SECURITY.md](../SECURITY.md#response-targets) | Susana | Verified as a document | None |

GitHub offers private vulnerability reporting on public repositories
only. While the repository is private there is **no operational
private disclosure route**, and nothing here claims the route or its
notifications work. The repository's visibility was not changed and no
test report was submitted for this assessment.

A GitHub-hosted route was chosen over a mailbox so that no personal
email address is published. That is an implementation choice; the
guidance gives a monitored mailbox only as an example.

### 3. No secrets or sensitive operational detail, with enforced controls

> no secrets or sensitive operational detail, and enforced controls to
> prevent committed secrets (tokens or keys), as well as removal of
> environment-specific hostnames, IP ranges, admin endpoints, or
> security thresholds where these would materially increase
> exploitability

| Control and scope | Evidence | Owner | Status | Remaining step |
|---|---|---|---|---|
| Secret scan of full Git history, all refs | [Refreshed scan](#refreshed-secret-and-history-review) below: no leaks | Susana | Verified locally on the assessment date | Repeat at the final commit before publication (AC-53) |
| Secret scan of the working tree including this ticket's files | Same section: no leaks | Susana | Verified locally | Same |
| Continuing secret scanning in CI, redacted output | `secret-scan` job in [security-hygiene.yml](../.github/workflows/security-hygiene.yml); [8 October run](#evidence-update-8-october-2026) | Susana | Ran once on a pull request: pass. Not yet running on `main` or on schedule, so not yet continuing | Step M1 |
| Enforced control: scan required before merge | None established. The settings could not be read ([settings](#repository-settings-read-on-7-october-2026)) | Susana | Pending. Unverified and unenforced | Step P4, with AC-35 |
| Enforced control: GitHub secret scanning and push protection | `security_and_analysis` returned `null` on 7 October 2026 | Susana | Pending | Step P3 |
| Personal data in committed record data | Redaction gate, [redaction-gate.md](redaction-gate.md); PASS on the assessment date | Susana | Verified, with a known defect | AC-37 (gate bypass), AC-39 (manual sweep) |
| Environment-specific hostnames, IP ranges, admin endpoints | September review, [pre-publication-safety-review.md](pre-publication-safety-review.md), historical; no infrastructure exists to describe | Susana | Verified historically; not re-reviewed by hand | AC-39 sweep; AC-53 final check |
| Security thresholds in the repository | The gate policy values are published on purpose | Susana | Excluded | See below |

**Exclusion: published thresholds.** The gate's escalation-rate
minimum and tolerance are in the README and code. They are the
behaviour being demonstrated, they protect no running system, and
knowing them gives no route to harm. The guidance asks for removal only
"where these would materially increase exploitability".

**Scanner exclusions.** None. There is no `.gitleaks.toml`,
`.gitleaksignore` or baseline, inline allow-comments are disabled with
`--ignore-gitleaks-allow`, and no finding was suppressed. There were no
false positives to explain.

**Limit.** Automated scanning reduces risk. It does not prove the
absence of secrets or personal data. The CI scan detects a committed
secret after the commit exists on GitHub; only push protection (step
P3) can stop the push itself.

### 4. Secure-by-design baseline

> a secure-by-design baseline, with evidence that the system follows
> these principles (for example, in threat modelling, safe defaults,
> least privilege, and hardening of publicly accessible endpoints), as
> operational hygiene can not compensate for unsafe architecture or
> configuration

| Control and scope | Evidence | Owner | Status | Remaining step |
|---|---|---|---|---|
| Trust boundaries stated; one network path, human-run | [Project manual, section 4](project-manual.md#4-architecture) | Susana | Documented | AC-57 |
| Safe defaults: offline by default, fail-closed replay with no live fallback, non-overridable gate policy | [Project manual, section 6](project-manual.md#6-safety-properties-and-failure-behaviour); [decision log](decision-log.md) ADR-005 and ADR-009; the existing test suite passes on the assessment date | Susana | Documented; not re-examined for this assessment | AC-47 |
| Model output treated as untrusted input, validated against a closed contract | [Project manual, section 4](project-manual.md#4-architecture); decision log ADR-002 | Susana | Documented; not re-examined for this assessment | AC-36 (error messages echo rejected values); AC-47 |
| Data minimised by construction | [Project manual, section 8](project-manual.md#8-privacy-and-redaction); decision log ADR-003 | Susana | Documented; not re-examined for this assessment | AC-37; AC-47 |
| Least privilege in CI: `contents: read` or no permissions, no secrets, no persisted checkout credentials, actions pinned to commit SHAs, bounded timeouts | [ci-gate.yml](../.github/workflows/ci-gate.yml), [security-hygiene.yml](../.github/workflows/security-hygiene.yml); repository Actions policy read on 7 October 2026: selected actions only, SHA pinning required | Susana | Verified by reading the files and with actionlint. Both workflows ran once on 8 October | None |
| Supply chain: optional dependencies hash-locked, wheels only | [Dependency evidence](#dependency-audit-evidence-for-ac-47); [8 October run](#evidence-update-8-october-2026) | Susana | Verified locally on ARM (7 October) and in GitHub Actions on x86_64 (8 October) | None |
| Written threat model | None in the repository | Susana | Pending | AC-57 |
| Hardening of publicly accessible endpoints | No endpoint exists | Susana | Excluded | See below |
| Least privilege for the AWS recording path | Not in the repository; the operator supplies credentials | Susana | Pending | Deferred under AC-34 |

**Exclusion: endpoint hardening.** AgentTrail exposes no network
endpoint and deploys nothing, so there is nothing to harden. This
exclusion ends the moment any part of it is hosted.

**Known weaknesses at the assessed commit.** Two independent reviews of
`138cec0` found defects in controls this repository claims: rejected
values can appear in exception messages (AC-36), the redaction gate can
be bypassed by an encoding (AC-37), and a malformed audit encoding
returns the wrong exit code (AC-38). None is fixed at the assessed
commit. The published limitations, such as a trail that is not
tamper-evident, are accepted risks and are consolidated under AC-47.
The existing evidence is design documentation and an existing test
suite that passes. This assessment did not re-examine whether the
tests prove each documented property, and it is not an independent
assurance of the architecture.

### 5. Automated hygiene

> automated hygiene, with dependency update tooling, vulnerability and
> secret scanning, and trunk protections (such as prevent force-push
> and require CI checks) so that fixes can be applied quickly without
> introducing new risk

| Control and scope | Evidence | Owner | Status | Remaining step |
|---|---|---|---|---|
| Dependency update tooling: Dependabot for pip and GitHub Actions, weekly | [dependabot.yml](../.github/dependabot.yml) | Susana | **Configured, not active.** Present on the feature branch only; Dependabot reads it from the default branch | Merge, then verify (step M1) |
| Dependabot alerts and security updates | Enabled on 7 October 2026 and read back: alerts HTTP 204, security updates `enabled: true` | Susana | Verified as settings. No alert result yet: Dependabot scans the default branch, and the dependency files are not on `main` | Check for alerts after merge (step M1) |
| Vulnerability scanning: pip-audit on all three locks, on pull requests, pushes to `main` and daily | `dependency-audit` job in [security-hygiene.yml](../.github/workflows/security-hygiene.yml); run locally on ARM on 7 October, see [evidence](#dependency-audit-evidence-for-ac-47); [8 October run](#evidence-update-8-october-2026) | Susana | Ran once on a pull request: pass. Push and schedule triggers not yet exercised | Step M1 |
| Secret scanning: Gitleaks, full history and tree, redacted | `secret-scan` job in the same workflow; run locally with the macOS build on 7 October; [8 October run](#evidence-update-8-october-2026) | Susana | Ran once on a pull request: pass. Push and schedule triggers not yet exercised | Step M1 |
| Scanning kept apart from the intentionally failing `v2` demonstration | Separate workflow file; `ci-gate.yml` unchanged | Susana | Verified | None |
| Trunk protection: prevent force-push and deletion on `main` | None. The rulesets and branch-protection endpoints both refused the read with HTTP 403 on 7 October 2026 ([settings](#repository-settings-read-on-7-october-2026)) | Susana | **Pending. Unverified and unenforced** | Step P4, with AC-35 |
| Trunk protection: required CI checks | None, for the same reason. `evaluation-gate` is AC-35's; `dependency-audit` and `secret-scan` are added by this ticket | Susana | **Pending. Unverified and unenforced** | AC-35 and step P4 |
| Static analysis of the application code | None | Susana | Pending | AC-54 |

Workflow YAML does not enforce anything by itself. Until a ruleset
requires the checks, a red `security-hygiene` run is advisory. The
schedule trigger only runs from the default branch, so "daily" starts
after merge. The workflow is designed to fail on a finding or a
scanner error. Its one run so far passed, so that failure path has not
been exercised.

`security-hygiene.yml` and `ci-gate.yml` were checked on 7 October 2026
with actionlint 1.7.12 and its ShellCheck 0.11.0 integration (both
checksum-verified release binaries): 0 findings. That validates
workflow syntax, expressions and shell scripts. It does not show the
jobs pass on a GitHub runner.

### 6. Patching expectations

> patching expectations with agreed timelines for addressing critical
> and high vulnerabilities, including the ability to demonstrate that
> you meet them

| Control and scope | Evidence | Owner | Status | Remaining step |
|---|---|---|---|---|
| Timelines: critical fixed or mitigated within 72 hours of confirmation, high within 14 calendar days. A warning or accepted risk does not meet a target | [SECURITY.md](../SECURITY.md#response-targets) | Susana | Verified as a document | Maintainer to confirm the targets are realistic |
| Risk acceptance recorded separately, with owner, justification and review date | [Risk-acceptance record](#risk-acceptance-record) | Susana | Verified as a document; no entry yet | None |
| Same targets for dependency advisories, from first automated report | [SECURITY.md](../SECURITY.md#response-targets), [maintenance.md](maintenance.md#review-frequency) | Susana | Verified as a document | None |
| Ability to demonstrate the targets are met | None yet. No advisory has been received and no scheduled scan has run | Susana | **Pending. No track record** | Accrues after publication |

The targets are the maintainer's own, for one person working on a
best-efforts basis. The 72-hour critical target in particular depends
on that one person being available. Once the controls are active, the
demonstrable record will be the timestamps on private advisories,
Dependabot alerts and pull requests, and scheduled `security-hygiene`
runs.

### 7. Safe posture for unmaintained code

> a safe posture for unmaintained code where, if a repo is not actively
> maintained, it is clearly marked and archived, and any deployed
> service is either decommissioned or has an explicit owner and
> patching route

| Control and scope | Evidence | Owner | Status | Remaining step |
|---|---|---|---|---|
| Trigger for treating the repository as unmaintained | [maintenance.md](maintenance.md#support-scope-and-review-date), [SECURITY.md](../SECURITY.md#if-a-target-is-missed) | Susana | Verified | None |
| Marking and archiving steps | [maintenance.md](maintenance.md#unmaintained-code-and-retirement) | Susana | Verified as a document; never exercised | None |
| Deployed service decommissioned or owned | No deployed service exists | Susana | Excluded | See below |
| Ownership and patching for any third-party deployment | [maintenance.md](maintenance.md#deployments) | The deployer | Verified as a statement | None |

**Exclusion: deployed service.** There is nothing to decommission. The
maintenance document says so and puts ownership and patching of any
deployment of this code on whoever deploys it.

## Risk-acceptance record

Accepting a risk is a separate decision from mitigating it and does
not meet a remediation target in the [security policy](../SECURITY.md).
Each acceptance of a reported vulnerability or dependency advisory is
recorded here with its owner, justification and review date. Detail
that would help an attacker stays in the private advisory until
disclosure.

| Reference | Risk accepted | Owner | Justification | Accepted on | Review date |
|---|---|---|---|---|---|
| None | No vulnerability report or dependency advisory has been risk-accepted | | | | |

The design limitations published in the README and project manual,
such as a trail that is not tamper-evident, are a different thing:
they are being consolidated, with their owners, under AC-47 and are
not entries in this record.

## Licence and provenance

| Item | Finding |
|---|---|
| Licence file | One file, [LICENSE](../LICENSE), unmodified MIT text. No duplicate `LICENCE` file. Unchanged by this ticket |
| Copyright line | "Copyright (c) 2026 The AgentTrail authors". Unchanged |
| README | Links the licence and this assessment |
| Third-party notices | No third-party source code is vendored; optional tools are installed from their own distributions. Whether the committed showcase deck, which is built on the python-pptx default template, needs a notice has not been assessed |
| **Provenance and publishing rights** | **Unresolved** |

The September review recorded that it had no evidence about any
employer, programme or Crown ownership arrangement and left the neutral
copyright wording in place "for now".

The AC-1 record was available and was read for this assessment. It
records how the project was built: as a solo final project on a
training programme, on personal resources and accounts, with part of
the build done in allocated working hours. It does not contain a
written determination of who owns the copyright or who may license the
work. A related ticket records that the programme was sent a courtesy
notice of intended publication, and states that any reply would not
settle an employment or intellectual-property position.

None of that is an ownership determination, and none is made here.
Neutral wording in the copyright line and the authorship recorded in
Git are not evidence of the right to publish under MIT. The licence is
retained unchanged because no authoritative evidence requires a
change. **Owner:** Susana. **Remaining step:** obtain a written
position from whoever can give one, or record an explicit decision to
publish without it, before the repository is made public.

## Dependency audit evidence for AC-47

### Dependency sets

The offline application has no third-party dependencies. Three
optional tool sets do:

| Set | Direct requirement | Packages pinned in the lock |
|---|---|---|
| `requirements-recording` | `boto3` | 7 |
| `requirements-showcase` | `python-pptx` | 5 |
| `requirements-hygiene` | `pip-tools==7.6.2`, `pip-audit==2.10.1` | 35 |

Every lock pins each direct and transitive package to one version with
SHA-256 hashes.

### Lock generation environment

| Item | Value |
|---|---|
| Date | 7 October 2026 |
| Interpreter | CPython 3.12.14, in an existing local `python:3.12-slim` container image |
| Platform | Linux, aarch64, glibc 2.41 |
| Tooling | pip 25.0.1, pip-tools 7.6.2 |
| Command, per set | `python -m piptools compile --allow-unsafe --generate-hashes --output-file=requirements-<set>.txt requirements-<set>.in` |
| Bootstrap | pip-tools 7.6.2 was installed by version, without hashes, for this first compile. Later installs use the hash-locked hygiene set |

**Finding fixed during this work.** The hygiene lock was first
generated on macOS with Python 3.14.0. That file could not be installed
on Python 3.12 with `--require-hashes`: it omitted `typing-extensions`,
which a transitive dependency needs only below Python 3.13, and it left
`pip` and `setuptools` unpinned. It was regenerated on Python 3.12 with
`--allow-unsafe`. The recording and showcase locks regenerated on
Python 3.12 pin exactly the same versions and hashes as the Python
3.14 originals; only their header comment changed.

### Platform and Python-version check

| Environment | Hash-locked install of all three sets | `pip check` |
|---|---|---|
| Local: Linux aarch64 (ARM), CPython 3.12.14, container | Pass, exit 0 | No broken requirements |
| Local: macOS 26.6.2 arm64 (ARM), CPython 3.14.0 | Pass, exit 0 | No broken requirements |
| GitHub Actions, `ubuntu-latest` (Ubuntu 24.04 image), x86_64, CPython 3.12.15. Run on 8 October 2026, see [evidence update](#evidence-update-8-october-2026) | Pass | No broken requirements |

Installs used
`python -m pip install --require-hashes --only-binary :all: -r requirements-<set>.txt`
in a fresh virtual environment per set. The locks contain no
environment markers. Both local checks ran on ARM on 7 October. CI
runs on x86_64, where the compiled packages use different wheels, so
the local result did not stand in for the CI result. The CI row was
"Not run, pending" on 7 October and was replaced on 8 October with the
result of the run recorded below. The locks are not claimed to be valid
on Windows or on Python versions other than 3.12 and 3.14.

### Audit

| Item | Value |
|---|---|
| Date and time | 7 October 2026, 21:10 UTC |
| Assessed tree | Uncommitted working tree based on `138cec050e0c176660c59dc98c3df90ac8e9a08d` |
| Tool | pip-audit 2.10.1, run from the hash-locked hygiene environment |
| Environment | Local only: Linux aarch64 (ARM), CPython 3.12.14, container. Not run in GitHub Actions |
| Vulnerability source | pip-audit default (PyPI advisory data) |
| Suppressions | None. No `--ignore-vuln` |

| Command | Exit status | Finding |
|---|---|---|
| `pip-audit --require-hashes --disable-pip --strict --progress-spinner off -r requirements-hygiene.txt` | 0 | No known vulnerabilities found |
| `pip-audit --require-hashes --disable-pip --strict --progress-spinner off -r requirements-recording.txt` | 0 | No known vulnerabilities found |
| `pip-audit --require-hashes --disable-pip --strict --progress-spinner off -r requirements-showcase.txt` | 0 | No known vulnerabilities found |

All three scans completed. The result means no advisory was known for
the pinned versions at that time. It does not show the packages are
free of vulnerabilities, and it goes stale as new advisories are
published, which is what the daily scheduled scan is for.

### Manifest checksums (SHA-256)

| File | SHA-256 |
|---|---|
| `requirements-hygiene.in` | `a46dbe8bf21aa3e3459bf626f4757b9cb1904a52db4c901ca1f9ed10d8e94514` |
| `requirements-hygiene.txt` | `ff50e5c34b7c0d15cc720c74ff72840514c7f6ba2bf8389d98849410ff34ebe3` |
| `requirements-recording.in` | `4da2696c4b21aadaf2ee81ef7d9c1184759940f425a5948ae1e63d83f10c4eaa` |
| `requirements-recording.txt` | `2a0835ca33f67aa426d4431f4f6bad2ca1f5c3498889510e4234286003cb4730` |
| `requirements-showcase.in` | `3600e64415effef1c08c7d53e0c82ae2fb356acb7d77ba15c4ca60c929ecc4f5` |
| `requirements-showcase.txt` | `063afa1dfd300dfc062c202c9732b2cc475eb7e81f07f815714d279198cb78c7` |

## Evidence update: 8 October 2026

This section records GitHub Actions evidence gathered after the 7
October local evidence above. It adds to that evidence and does not
replace it.

| Item | Value |
|---|---|
| Tested commit | `b19f94d98efc54e69f8dbdd01c4eff2efc826c82` on `chore/open-code-hygiene` |
| Trigger | `pull_request` to `main`, draft pull request [#1](https://github.com/SusanaCodes/agenttrail/pull/1) |
| Date | 8 October 2026, started 08:07 UTC |
| Runner | GitHub-hosted `ubuntu-latest`, Ubuntu 24.04 image version 20261004.327.1 |
| Architecture | x86_64. The install log shows `manylinux` `x86_64` wheels and the job ran the `linux_x64` Gitleaks binary |
| Python | CPython 3.12.15, from `actions/setup-python` |

| Job | Result | What the log shows | Link |
|---|---|---|---|
| `dependency-audit` | Pass | All three sets installed with `--require-hashes --only-binary :all:`; `pip check` reported no broken requirements for each; pip-audit 2.10.1 reported no known vulnerabilities for each lock | [job](https://github.com/SusanaCodes/agenttrail/actions/runs/37747780802/job/113213295890) |
| `secret-scan` | Pass | Gitleaks 8.30.1 archive matched its pinned checksum; 23 commits scanned, no leaks; working tree, no leaks | [job](https://github.com/SusanaCodes/agenttrail/actions/runs/37747780802/job/113213295449) |
| `evaluation-gate` (`v1`) | Pass | Existing workflow, unchanged | [job](https://github.com/SusanaCodes/agenttrail/actions/runs/37747780719/job/113213293201) |
| `deployment-demo` | Pass | Existing workflow, unchanged | [job](https://github.com/SusanaCodes/agenttrail/actions/runs/37747780719/job/113213361821) |

Runs: [`security-hygiene` 37747780802](https://github.com/SusanaCodes/agenttrail/actions/runs/37747780802),
[`ci-gate` 37747780719](https://github.com/SusanaCodes/agenttrail/actions/runs/37747780719).
The run links need access to the repository while it is private.

The history scan counted 23 commits against 21 locally on 7 October.
The CI checkout fetches all refs, and the count includes this ticket's
commit and the pull request's merge commit.

What this run establishes: the three locks install and audit cleanly
on GitHub's x86_64 runner with Python 3.12, and both scanning jobs
work there. It is one passing run of one commit.

What it does not establish, and what stays pending:

- **Publication rights.** Provenance behind the copyright line is
  still unresolved.
- **Disclosure activation.** Private vulnerability reporting is still
  not enabled or tested.
- **Enforcement.** No check is required for merging. Branch protection
  and rulesets are unverified and unenforced.
- **Failure paths.** No run has had a finding or a scanner error, so
  the workflow failing when it should is still unexercised.
- **Continuing operation.** The push and schedule triggers, Dependabot
  version updates and Dependabot alerts on the locks all wait for the
  files to be on `main`.

## Evidence update: 9 October 2026

This section records one change made under AC-35 after the assessment
date. Nothing else in this document was re-gathered for it.

| Item | Result |
|---|---|
| `CODEOWNERS` file | On `main`. [.github/CODEOWNERS](../.github/CODEOWNERS) assigns `agenttrail/`, `data/`, `fixtures/`, `tests/` and `.github/` to `@SusanaCodes` |
| Evidence | Merged [pull request #8](https://github.com/SusanaCodes/agenttrail/pull/8), merge commit `71047b932e729e3c5201cd00aa57795c7c2fbfc9` |
| Required `evaluation-gate` check and bypass controls | **Unverified.** Pending activation after authorised publication |
| Blocked throwaway pull request (AC-35's proof) | **Not performed** |
| Mandatory code-owner approval | **Deferred.** This is a sole-owner repository |
| AC-35 | Remains open |

`CODEOWNERS` records ownership. It does not establish independent
review: there is one maintainer and no second reviewer. The trunk
protection rows under [item 5](#5-automated-hygiene) are unchanged and
still unverified and unenforced.

Also on 9 October 2026, a fix for AC-36 was proposed in draft
[pull request #10](https://github.com/SusanaCodes/agenttrail/pull/10).
It removes rejected values and unexpected key names from case-input,
model-response and audit-record validation errors, and adds regression
tests. It is not merged, so AC-36 remains open and the statement under
[item 4](#4-secure-by-design-baseline) that the defect is not fixed at
the assessed commit still stands. AC-37 and AC-38 are unchanged.

## Refreshed secret and history review

The September 2026
[pre-publication safety review](pre-publication-safety-review.md)
covered commit `69beecc` and earlier. It is historical evidence. It
does not verify the commits or the working-tree changes made since.
This refresh was run on 7 October 2026.

| Item | Value |
|---|---|
| Tool | Gitleaks 8.30.1, default rules, no config, ignore file or baseline |
| History scan | `gitleaks git . --log-opts="--all -m" --max-archive-depth 2 --redact --ignore-gitleaks-allow --no-banner` |
| History result | 21 commits across all local and remote-tracking refs scanned. No leaks found, exit 0 |
| Working-tree scan | `gitleaks dir . --max-archive-depth 2 --redact --ignore-gitleaks-allow --no-banner` |
| Working-tree result | No leaks found, exit 0. Includes the files added by this ticket |
| Redaction gate | `python3 -m agenttrail.redaction_gate`: PASS, exit 0 |

Not repeated in this refresh: the September review's purpose-written
supplementary scanner and its manual reading of documents for internal
or personal references. The manual sweep of `docs/`, `tests/` and
`showcase/` belongs to AC-39, and the final full-history scan at the
commit to be published belongs to AC-53.

## Repository settings read on 7 October 2026

Read with the GitHub CLI as the repository owner.

| Setting | Value read |
|---|---|
| Visibility | Private |
| Default branch | `main` |
| Branch protection on `main` | Not read. HTTP 403; GitHub's message said to upgrade the plan or make the repository public |
| Repository rulesets | Not read. HTTP 403 with the same message |
| Private vulnerability reporting | HTTP 404. GitHub documents the feature for public repositories |
| Dependabot alerts | HTTP 404: disabled. Changed by this ticket, below |
| Dependabot security updates | `enabled: false`. Changed by this ticket, below |
| Secret scanning and push protection | `security_and_analysis: null` |
| Actions policy | Selected actions only (`actions/checkout`, `actions/setup-python`); SHA pinning required |

A refused read does not establish what is configured. Whether any
ruleset or protection is stored for `main`, and whether one could be
created on the current plan, is unverified; no attempt was made to
create one. Trunk protection is therefore recorded as unverified and
unenforced, not as absent or unavailable. Nothing was changed.

### Settings changed by this ticket

| Setting | Previous value | New value, read back |
|---|---|---|
| Dependabot alerts | Disabled (HTTP 404) | Enabled (`GET .../vulnerability-alerts` returned HTTP 204) |
| Dependabot security updates | `enabled: false` | `enabled: true`, `paused: false` |

Both were enabled on 7 October 2026 with
`gh api -X PUT repos/SusanaCodes/agenttrail/vulnerability-alerts` and
`gh api -X PUT repos/SusanaCodes/agenttrail/automated-security-fixes`,
and are reversed with the same paths and `-X DELETE`. The alerts API
listed no open alerts afterwards. That is not a clean result: the
dependency files are not on `main`, which is the branch Dependabot
scans. Secret scanning and push protection were not changed and still
read `security_and_analysis: null`.

### Metadata changed by this ticket

| Field | Previous value | New value |
|---|---|---|
| Description | "An auditable AI-agent decision trail with evaluation data and a CI/CD safety gate." | "Prototype reference implementation of an auditable AI-agent decision trail with offline behavioural evaluation and a CI/CD safety gate. Not production-ready." |
| Website | Empty | `https://github.com/SusanaCodes/agenttrail/blob/main/docs/project-manual.md` |
| Topics | None | `ai-safety`, `audit-trail`, `ci-cd`, `eu-ai-act`, `evaluation` |

The website URL is the real location of the project manual. It returns
HTTP 404 to a signed-out reader while the repository is private;
public access is verified at step P5.

## Guidance requirements and additional choices

The guidance sets the seven items above. The following are this
project's own implementation choices, not requirements of the
guidance:

- GitHub private vulnerability reporting instead of a mailbox.
- The specific response targets, and disclosure timing agreed with the
  reporter rather than a fixed embargo.
- Hash-locked dependency sets, wheel-only installs and pip-audit.
- Gitleaks as the scanner, fetched as a checksum-verified binary.
- Actions pinned to commit SHAs, empty default token permissions and
  job timeouts.
- A three-monthly maintenance review.
- The repository description, topics and website field.

## Outstanding before publication

This ticket does not authorise publication and does not close the
security blockers owned by other tickets.

### On this branch

| Step | Action | Verifies |
|---|---|---|
| B1 | Commit and push the branch, open a pull request, observe `security-hygiene` and `ci-gate`. **Done on 8 October 2026**, see [evidence update](#evidence-update-8-october-2026) | Hash-locked installs and audits on CI's x86_64 Python 3.12; Gitleaks in CI |
| M1 | After merge to `main`: confirm Dependabot has read the configuration, list Dependabot alerts for the three locks, and confirm a scheduled `security-hygiene` run has happened | Dependency update tooling, alerts and continuing scans are active |

### At publication

These have not been done. Private vulnerability reporting is documented
by GitHub for public repositories; the ruleset and secret-scanning
steps were not attempted, so their availability is unconfirmed.
Visibility is changed by the owner, not by tooling. Endpoints were checked against
the GitHub REST documentation on 7 October 2026.

| Step | Action |
|---|---|
| P1 | Enable private vulnerability reporting: `gh api -X PUT repos/SusanaCodes/agenttrail/private-vulnerability-reporting` (expect HTTP 204) |
| P2 | Read it back: `gh api repos/SusanaCodes/agenttrail/private-vulnerability-reporting --jq .enabled` (expect `true`). Confirm the maintainer account watches the repository with security alerts on, and that "Report a vulnerability" appears on the Advisories page for a second account. Then remove the "activation pending" notice from `SECURITY.md` |
| P3 | Enable secret scanning with push protection (`PATCH repos/SusanaCodes/agenttrail` with `security_and_analysis.secret_scanning` and `security_and_analysis.secret_scanning_push_protection` set to `enabled`) and read it back. Not attempted for this assessment, so its availability is unconfirmed |
| P4 | With AC-35: a ruleset on `main` that blocks deletion and force-push (`deletion`, `non_fast_forward`) and requires the `evaluation-gate`, `dependency-audit` and `secret-scan` checks. Read back with `gh api repos/SusanaCodes/agenttrail/rules/branches/main`, and prove it with AC-35's blocked throwaway pull request |
| P5 | Confirm the website URL and the README links load for a signed-out reader |

### Owned by other tickets

| Gap | Ticket |
|---|---|
| Required check, bypass off and the blocked throwaway pull request. `CODEOWNERS` was added on 9 October 2026; mandatory code-owner approval is deferred | AC-35 |
| Rejected values in exception messages. A fix was proposed on 9 October 2026 and is not merged | AC-36 |
| Redaction gate bypass | AC-37 |
| Malformed audit encoding exit code | AC-38 |
| Manual redaction sweep of `docs/`, `tests/`, `showcase/` | AC-39 |
| Consolidated security assessment, which takes the dependency evidence above | AC-47 |
| Final full-history scan and visibility change | AC-53 |
| Static analysis, SBOM and enforced scanning proven by seeded violations | AC-54 |
| Threat model | AC-57 |
| Provenance and publishing rights | Unresolved; no ticket currently determines it |
