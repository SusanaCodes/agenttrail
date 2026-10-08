# Maintenance and ownership

How AgentTrail is maintained, by whom, for how long, and what happens
when that stops. Vulnerability reporting and response targets are in
the [security policy](../SECURITY.md). Evidence for each control is in
the [open-code assessment](open-code-assessment.md).

## Maintainer

**Susana, GitHub [@SusanaCodes](https://github.com/SusanaCodes)**, is
the sole maintainer. The maintainer is accountable for:

- the repository and its GitHub settings;
- the dependency manifests, locks and update pull requests;
- triaging security reports and fixing or mitigating confirmed
  vulnerabilities;
- the decision to keep maintaining, hand over, or archive.

Maintenance responsibility is not a statement about copyright. The
copyright line is in [LICENSE](../LICENSE), and its provenance position
is recorded in the open-code assessment.

A `CODEOWNERS` file and required code-owner review are not in place
yet. They belong to ticket AC-35.

## Support scope and review date

- Only the head of `main` is maintained. There are no releases or
  maintained older versions.
- The project is a prototype and reference implementation. It is
  maintained as a demonstration, on a best-efforts basis by one person,
  not operated as a service.
- **Next maintenance review: 7 January 2027**, then every three months.
  At each review the maintainer either renews this commitment with a
  new date here or starts the retirement steps below. If the review
  date passes without an update to this file, treat the repository as
  unmaintained.

## Dependencies

The offline application (evaluation, tests, both gates, policy replay,
record view) uses only the Python standard library and has nothing to
install. Three optional tool sets have third-party dependencies, each
with its own manifest and hash-locked file:

| Set | Direct dependency | Used by | Manifest | Lock |
|---|---|---|---|---|
| Recording | `boto3` | `agenttrail/record_fixtures.py` (live fixture recording) | `requirements-recording.in` | `requirements-recording.txt` |
| Showcase | `python-pptx` | `showcase/make_deck.py` (deck generation) | `requirements-showcase.in` | `requirements-showcase.txt` |
| Hygiene | `pip-tools`, `pip-audit` | Lock generation and vulnerability audit | `requirements-hygiene.in` | `requirements-hygiene.txt` |

Each lock pins every direct and transitive package to one version with
package hashes. Install only from a lock, into an isolated virtual
environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --require-hashes --only-binary :all: -r requirements-hygiene.txt
```

### Regenerating a lock

The locks are generated with pip-tools on **Python 3.12**, the version
CI uses. pip-tools resolves for the interpreter it runs on, so a lock
generated on a newer Python can omit packages that 3.12 needs. Run,
from the hygiene environment on Python 3.12:

```bash
python3 -m piptools compile --allow-unsafe --generate-hashes \
  --output-file=requirements-hygiene.txt requirements-hygiene.in
```

and the same for `recording` and `showcase`. `--allow-unsafe` is
required so that `pip` and `setuptools` are pinned too; without it the
hygiene lock cannot be installed with `--require-hashes`.

### Review frequency

| Activity | Frequency |
|---|---|
| Dependabot version-update pull requests (pip and GitHub Actions) | Configured weekly; reviewed within 7 calendar days of being opened |
| `security-hygiene` workflow (pip-audit on all three locks, Gitleaks) | Configured for every pull request, every push to `main`, and daily on a schedule |
| Manual review of the manifests, locks, pinned action SHAs and the pinned Gitleaks version | At each three-monthly maintenance review |

These are the configured frequencies. Dependabot version updates and
the schedule only start once the configuration is on `main`; the
[open-code assessment](open-code-assessment.md) records what has
actually run.

The maintainer merges an update pull request only when the
`security-hygiene` and `ci-gate` checks pass on it. This is a manual
rule until the checks are required by a ruleset (AC-35). Dependabot may
regenerate a lock under a different Python version. The hash-locked
install step in `security-hygiene` is intended to fail in that case,
but this has not been observed; if it happens, regenerate that lock on
Python 3.12 instead of merging.

Critical and high advisories are handled to the targets in the
[security policy](../SECURITY.md), counted from the first automated
report.

GitHub disables scheduled workflows in a public repository with no
activity for 60 days. Re-enabling the schedule is part of each maintenance
review.

## Handover

There is one maintainer and no deputy. To hand over:

1. The new maintainer is named in this file, in the README and in
   `SECURITY.md` by pull request, before any access changes.
2. Repository admin access, or ownership of the repository, is
   transferred on GitHub. Private vulnerability reporting notifications
   follow admin access, so the new maintainer confirms they are
   watching the repository for security alerts.
3. Any open private advisories are handed over in the advisory thread,
   with the reporter told who now owns the report.
4. The outgoing maintainer's access is removed once the new maintainer
   confirms receipt.

If no one takes over, the repository is retired as below. It is not
made private as a substitute for maintenance.

## Unmaintained code and retirement

When the maintainer stops maintaining the project, or cannot respond to
a security report for 14 calendar days:

1. A notice is added at the top of the README saying the project is
   unmaintained, from what date, and that no security fixes will be
   made.
2. `SECURITY.md` is updated to say reports are no longer triaged.
3. Private vulnerability reporting is disabled so reporters are not
   sent to an unmonitored route.
4. Dependabot configuration and the scheduled workflow are removed.
5. The repository is archived on GitHub, which makes it read-only and
   labels it as archived.

## Deployments

AgentTrail has no deployed service. Nothing in this repository is
hosted, exposes a network endpoint, or runs outside a developer machine
or a GitHub Actions runner, so there is nothing to decommission on
retirement.

Anyone who deploys this code, or a derivative, runs their own system.
Before doing so they need a named owner for that deployment and their
own patching route for it and its dependencies. The maintainer of this
repository does not patch, monitor or support other people's
deployments, and archiving this repository does not make a surviving
deployment safe.
