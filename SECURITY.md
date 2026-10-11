# Security policy

AgentTrail is a prototype and reference implementation maintained by
one person. It is not a production service and nothing in this
repository is deployed. This policy says what is maintained, how to
report a vulnerability privately, and what response to expect.

## Security owner

**Susana, GitHub [@SusanaCodes](https://github.com/SusanaCodes)**, is
the security contact and is responsible for triaging reports and for
fixing or mitigating confirmed vulnerabilities. There is no deputy;
see [maintenance and ownership](docs/maintenance.md) for handover.

## Supported scope

| Item | Supported |
|---|---|
| The `main` branch at its current head | Yes |
| Any other branch, tag, fork or earlier commit | No |

In scope:

- The `agenttrail/` package, including the evaluation, CI gate,
  redaction gate, policy replay, record view and fixture code.
- The committed data, schemas and fixtures under `data/` and
  `fixtures/`.
- The GitHub Actions workflows and Dependabot configuration under
  `.github/`.
- The hash-locked dependency sets (`requirements-*.txt`) for the
  optional recording, showcase and maintenance tooling.

Out of scope:

- The documented, deliberately seeded `v2` failures only: the `v2`
  prompt and its clearly marked synthetic fixtures miss low-confidence
  escalations, and the gate fails on them by design, as described in
  the README and the [demo scenario](docs/demo-scenario.md). Anything
  else remains reportable, including an unexpected vulnerability in
  the code `v1` and `v2` share, in the workflows, or in gate
  enforcement, for example a way to make the gate pass when it should
  fail.
- The limitations already published in the README and the
  [project manual](docs/project-manual.md), for example that the local
  audit trail is not tamper-evident. Reports that show one of these is
  worse than documented are welcome.
- Vulnerabilities in Amazon Bedrock, GitHub or third-party packages
  themselves. Report those to their owners. Tell us if this repository
  pins an affected version.
- Any deployment of this code by someone else. That deployment's
  operator owns its patching.

## Reporting a vulnerability

Do not open a public issue, pull request or discussion for a suspected
vulnerability.

The chosen route is **GitHub private vulnerability reporting**, which
avoids publishing a personal email address.

> **Status: enabled on 11 October 2026.** The repository was made
> public that day and private vulnerability reporting was enabled
> through the GitHub API and read back as `enabled: true`. A signed-out
> request to the repository's Advisories page shows the "Report a
> vulnerability" link; the form itself requires a GitHub account. No
> test report has been submitted, so nothing here claims that a report
> reaches the maintainer or that the triage process below has been
> exercised. The setting and its read-back are recorded in the
> [open-code assessment](docs/open-code-assessment.md#evidence-update-11-october-2026).

To report:

1. Open the repository's **Security** tab, then **Advisories**, then
   **Report a vulnerability**
   (`https://github.com/SusanaCodes/agenttrail/security/advisories/new`).
2. Fill in the advisory form. The report is not public.

If that button is missing, the route is not active. Do not fall back to
a public issue with details. Open a public issue that says only that
you have a security report and need a private channel, with no
technical content.

## What to include

- The affected file, module or workflow, and the commit SHA you tested.
- What an attacker could do and what they would need to do it.
- The smallest steps or input that reproduce the problem.
- Your Python version and operating system, if relevant.
- Any fix or mitigation you suggest.

Keep the report sanitised:

- Do not include real credentials, tokens or keys. If you found one in
  the repository or its history, give the file path and commit, not the
  value.
- Do not include personal data or real case data. Use synthetic values
  shaped like the committed fixtures.
- Do not include account identifiers, hostnames or other detail from
  your own or your employer's systems.

## Response targets

These are the maintainer's targets for a single-maintainer prototype.
They are not a contractual service level, and there is no track record
yet to show they are met.

| Stage | Target |
|---|---|
| Acknowledge the report | Within 3 working days |
| Initial triage: confirm or reject, assign severity | Within 5 working days |
| Confirmed **critical** vulnerability fixed or mitigated | Within 72 hours of confirmation |
| Confirmed **high** vulnerability fixed or mitigated | Within 14 calendar days of confirmation |
| Progress update while a confirmed report is unresolved | At least every 7 calendar days |

Working days are Monday to Friday, excluding public holidays in
England. Severity is assessed with CVSS v3.1 base scores (critical 9.0
to 10.0, high 7.0 to 8.9), adjusted for how the code is actually used
here: offline, with no deployed service and no stored credentials.
Medium and low findings are fixed in the normal course of maintenance
with no fixed target.

The same remediation targets apply to critical and high advisories in
the locked dependency sets, counted from the day the automated scan or
Dependabot first reports them. Neither has reported on `main` yet; see
the open-code assessment for what is active.

A mitigation is a change that removes or reduces the exposure: a fix
on `main`, a pinned dependency upgrade, or disabling or removing the
affected optional path. A warning or an accepted risk is not a
mitigation and does not meet a critical or high target. If neither a
fix nor a mitigation is in place by the target date, the target has
been missed and the next section applies.

Risk acceptance is recorded separately. Each accepted risk is entered
in the risk-acceptance record in the
[open-code assessment](docs/open-code-assessment.md#risk-acceptance-record)
with a named owner, the justification and a review date, and is
reconsidered on that date. Until disclosure, mitigations, unresolved
findings and any acceptance are tracked in the private advisory, and
the public record holds no detail that would help an attacker.

## If a target is missed

The maintainer will tell the reporter in the advisory thread before
the target passes where possible, with the reason and a new date. If
the maintainer cannot respond at all for 14 calendar days, the
unmaintained-code process in
[maintenance and ownership](docs/maintenance.md) applies: the
repository is marked unmaintained and archived rather than left
looking supported.

## Coordinated disclosure

- Please give the maintainer the chance to fix the issue before you
  publish. There is no fixed embargo period. Disclosure timing is
  agreed with the reporter in the advisory thread, according to the
  risk, remediation progress and any ongoing exposure.
- When a fix is published, the advisory is published with it, with a
  CVE requested through GitHub where the issue warrants one.
- Reporters are credited in the advisory unless they ask not to be.
- Testing that stays within your own clone of this repository is
  welcome. There is no bug bounty.
