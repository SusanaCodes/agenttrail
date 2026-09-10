# Pre-publication safety review (Ticket 13)

**Review dates:** 9–10 September 2026. **Planned public date:** 12
September 2026, ahead of the showcase on 16 September. **Publication
approval** is tracked separately under Ticket 14.

**Reviewed baseline:** the rewritten `main` at commit
`69beecca2b9e46653b72f6b4bfb37989aee4e33e` (19 commits, single branch,
no tags). This is the history the public repository is created from;
see "History rewrite" below.

This document is itself public. It records conclusions and locations,
never the values that were examined or removed. Automated scanning
reduces risk; it does not guarantee the absence of secrets or personal
data, and no such guarantee is claimed here.

Verdicts: **PASS** (no publication risk found), **FAIL** (must be fixed
before publication), **MANUAL DECISION REQUIRED** (a human owner must
decide; publication may proceed once the decision is recorded).

## Summary

| Area | Verdict |
|---|---|
| Secrets and credentials in full history | PASS |
| Golden dataset and fixture provenance | PASS |
| Internal and personal references | PASS (after history rewrite) |
| Commit authorship | PASS (after history rewrite) |
| Licence | PASS (copyright line confirmed for now; see D) |
| Publication hygiene | PASS (after changes) |

**Technical recommendation: SAFE TO MAKE PUBLIC**, provided the
publication approval itself is recorded under Ticket 14 and the
cutover follows the checklist at the end of this document.

## History rewrite

The original private history was rewritten once, locally, before
publication, using `git filter-repo` (2.47.0) with a mailmap and a
literal-replacement rule set, then verified as described below. No
public history is being rewritten; the public repository starts from
the rewritten baseline. The original repository is retained privately
as an archive.

What the rewrite changed:

- **Author and committer identity** on the first 11 commits (24 July
  to 7 August 2026), which had used a personal email address, now use
  the same GitHub no-reply identity as every later commit. Names,
  commit messages, author dates and committer dates are unchanged.
- **Seven literal strings in one file** (`docs/agenttrail_demo_runbook.md`,
  in the commit that introduced it): two home-directory repository
  paths, two Desktop recording paths, two recording filenames and one
  local AWS profile name were replaced with neutral placeholders. No
  other blob in any revision contained those strings.

What the rewrite did not change: every other file in every commit.
Tree-hash comparison of all 19 old/new commit pairs showed 18
byte-identical trees; the nineteenth differs only in that one file.

Because the rewrite changes every commit hash, no document in this
repository cites a pre-rewrite hash.

## Phase 1 — full Git history scan

### Automated: Gitleaks

| Item | Value |
|---|---|
| Tool | Gitleaks 8.30.1 (Homebrew), default built-in rule set; no `.gitleaks.toml`, no `.gitleaksignore`, no baseline; `--ignore-gitleaks-allow` so inline allow-comments could not suppress anything; `--redact` so no value is printed |
| History scan | `gitleaks git . --log-opts="--all -m" --max-archive-depth 2` — every commit reachable from every ref, merge-commit diffs included, with traversal into the committed `.pptx` archive |
| Working-tree scan | `gitleaks dir . --max-archive-depth 2` — the checked-out tree including the files added by this review |
| Result | Both scans: no leaks found, exit 0. Run on the original history before the rewrite (19 commits, all refs) and again on the rewritten history and tree |

### Automated: local supplementary scan

A purpose-written, offline, standard-library Python scanner was also
run over every blob reachable from every ref, every commit message and
identity, and the unpacked parts of the `.pptx`, with patterns for AWS
access-key IDs and secret keys, AWS account IDs and ARNs,
GitHub/GitLab/Slack/Google/Anthropic/OpenAI token formats, JWTs, bearer
tokens, credentials embedded in URLs, private keys and certificates,
generic `password=`/`token=`/`api_key=` assignments, UUIDs, UK National
Insurance number shapes, email addresses, URLs, internal-looking
hostnames, IPv4 addresses, local filesystem paths, ticket-style
references, chat channel names, government-internal service names,
credential-file names, and Shannon-entropy screening of long tokens.
Git itself was used to confirm that every path ever committed still
exists (`--diff-filter=DR` returned nothing), so nothing was committed
and later deleted.

### Manual review of scanner output

| Category | Finding | Verdict |
|---|---|---|
| Credentials (AWS, GitHub, GitLab, Slack, model-provider, JWT, bearer, basic-auth URLs) | No match in any object or commit | PASS |
| Private keys / certificates / credential-shaped filenames | None, ever | PASS |
| AWS account / tenant / subscription identifiers | None. The only 12-digit strings are `000000000001`-style placeholders in unit tests | PASS (false positive) |
| Bedrock provenance in fixtures | Fixture records carry only the public model identifier, a timestamp, a request hash, the request body and the response body. No request IDs, response metadata, region, account or endpoint | PASS |
| Internal hostnames, endpoints, IP addresses | None. All URLs are Office Open XML namespaces, the JSON-Schema draft URL, EU legislation links and the repository's own clone URL | PASS |
| High-entropy strings | Python keyword-argument identifiers, XML namespace URLs, and opaque Bedrock `toolUseId` values in the recorded fixtures | PASS (false positive) |
| National Insurance / NHS / postcode shapes | Only in the redaction-gate documentation and tests, as pattern examples: sequential-digit NI examples, deliberately non-issuable prefixes, a public landmark postcode and the canonical NHS test number. The committed redaction gate reports zero findings over the data files | PASS (false positive) |
| Commit messages and branch names | Conventional; refer only to the project's own ticket numbering | PASS |
| Commit identities | Personal address on 11 early commits — removed by the history rewrite | PASS (after rewrite) |

### Limitations

- Gitleaks and the local scanner match known secret formats and entropy
  patterns; neither performs live verification, and neither can detect
  a secret with no recognisable shape. Every document in the tree was
  therefore also read manually (Phase 2).
- Local-only Git state (reflogs, unreachable objects) is outside
  `--all` and is not part of what is published.

## Phase 2 — remaining pre-publication review (manual)

### A. Golden dataset and case provenance — PASS

Datasets inspected: `data/golden_cases.jsonl` (36 records),
`fixtures/bedrock-converse-v1.jsonl` and
`fixtures/bedrock-converse-v2-synthetic.jsonl` (36 records each), the
unit-test fixtures in `tests/`, and every example record in `docs/`.

Evidence that the data is synthetic and cannot identify anyone:

- Every golden record has exactly three input fields, each an enumerated
  band (`age_band`, `income_band`, `evidence_status`), and three expected
  fields, each an enumerated label. There are no names, addresses,
  dates, free text, reference numbers or contact details in the file.
- The 36 records are the complete Cartesian product of 4 × 3 × 3 enum
  values, each combination once, in fixed order — a generated grid, not
  a sample from any real population.
- Labels are a deterministic function of `evidence_status` alone, as
  documented in `docs/golden-dataset.md`; the rules are a synthetic
  labelling policy, not real benefit policy, and the documentation
  states so prominently.
- `data/golden_cases.schema.json` forbids additional properties and
  constrains every string to an enum or pattern, so a record cannot
  carry PII without failing validation; `tests/test_golden_dataset.py`
  pins the count and distribution.
- The dataset has a single revision in history (July 2026); no richer
  version was ever committed and later stripped.
- Fixture request bodies contain only the same three enumerated fields;
  responses contain only enumerated decisions, confidence values and
  rationale template codes.
- Test data uses obvious placeholders (a generic sample name, a
  non-issuable NI-number prefix) solely to prove that PII is rejected.
- A combination of the three bands describes a population segment, not
  a person, so no re-identification risk arises from combining fields.

### B. Internal and personal references — PASS after history rewrite

Searched (tree and full history): department and government service
names, internal hostnames/domains/environment names, incident, change
and ticket-system references, chat channel names, colleague names and
email addresses, local paths and usernames, personal email addresses.

- No government-internal service names, internal hostnames, environment
  names, ServiceNow/Jira-style references, chat channels or team names.
  "Ticket N" references are the project's own numbering.
- No colleague names or third-party personal data. The presenter's
  first name appears in the showcase documents as the named presenter,
  consistent with the public GitHub account, and is intentional.
- **Removed by the history rewrite:** the machine-local details in
  `docs/agenttrail_demo_runbook.md` described above. The current
  version of that file additionally points readers to the git-ignored
  recordings directory and the recording checklist.
- **Borderline, left as is:** the AWS region `eu-west-2` and the public
  model identifier in fixture-recording examples. These are public AWS
  values, not account-specific, and are useful documentation.
- **Borderline, left as is:** the decision log and project manual
  mention that a "programme plan" defines acceptance criteria AC-17 to
  AC-24 and say explicitly that those definitions are not in the
  repository. No content of that plan is disclosed.
- **Mitigated:** `showcase/rehearsal-log.md` and
  `showcase/fallback-recording-checklist.md` are templates to be
  completed later; they now state that the file is public and must not
  receive witness names, hostnames or private paths.

### C. Commit authorship — PASS after history rewrite

Identities on the published history (author and committer fields, 19
commits):

| Identity | Fields | Assessment |
|---|---|---|
| First name, GitHub no-reply address | 34 | Suitable for public attribution |
| Full name, GitHub no-reply address | 2 (merge-commit authors) | Suitable for public attribution |
| GitHub web-flow | 2 (merge-commit committers) | Autogenerated; standard |

The repository's local Git configuration uses the no-reply address, so
new commits carry the same identity.

### D. Licence — PASS

No licence file, licence statement or packaging metadata existed before
this review. A root-level `LICENSE` containing the unmodified MIT
licence text has been added and the README states the licence. The
copyright line reads **"The AgentTrail authors"**: the Git history
attests who wrote the code, and the review has no evidence about any
employer, programme or Crown ownership arrangement, so nothing is
asserted beyond that. The owner has confirmed this neutral wording for
now; it may be revisited if a written publication position later
requires a different holder. No README statement or metadata
contradicts MIT.

### E. General publication hygiene — PASS after changes

| Check | Result |
|---|---|
| Ignored-but-previously-committed sensitive files | None — no path was ever deleted from history and no tracked file matches `.gitignore` |
| Generated reports, prompts, model responses, environment data | Fixture files contain the prompt and recorded responses by design and are documented as such; they contain no environment data. No audit trails, logs or debug output are tracked |
| Debug output | CLI modules print only their reports; no host, user or environment values are written to records |
| Local paths / usernames | Removed from history (above). Remaining paths are placeholders, `/tmp` examples, or repository-relative |
| Binary artefacts | One 41 KB `.pptx`. Its document properties carry the python-pptx default-template metadata (the library author's name and 2013 template dates), not anything from this project. Recordings are git-ignored. Optional: regenerate the deck with explicit core properties |
| README links | All relative links in every Markdown file resolve; no badges, private CI or project-board links |
| Compliance claims | Every regulatory mention is an explicit disclaimer ("not a compliance claim", "not tamper-proof"); no TODO/FIXME markers exist |
| CI workflow | Read-only permissions, pinned action SHAs, `persist-credentials: false`, no secrets referenced |
| Local tooling directories | `.venv/` and `.claude/` had been kept out only by a machine-local global ignore; both are now in `.gitignore` alongside `showcase/recordings/` |

## Files changed by this review

| File | Change |
|---|---|
| `LICENSE` | Added; unmodified MIT text |
| `README.md` | Licence section added |
| `.gitignore` | `.venv/` and `.claude/` added |
| `docs/agenttrail_demo_runbook.md` | Backup-recordings section generalised to the git-ignored recordings directory; placeholders for checkout path and AWS profile |
| `showcase/rehearsal-log.md` | Public-file caution; "machine" and "witness" fields ask for generic descriptions and roles only |
| `showcase/fallback-recording-checklist.md` | Same caution; presenter named by role |
| `docs/pre-publication-safety-review.md` | This document |

## Validation on the rewritten baseline plus these changes

- `git diff --check`: clean.
- `python3 -m unittest discover -s tests`: 345 tests, OK.
- `python3 -m agenttrail.redaction_gate`: PASS, 3 files scanned, 0 findings.
- `python3 -m agenttrail.ci_gate` (v1): exit 0; `--agent-version v2`: exit 1, as designed.
- Markdown relative-link check over all documents: 0 broken links.
- Gitleaks 8.30.1 history scan (all refs, merge diffs, archive traversal) and working-tree scan: no leaks, exit 0.
- Targeted searches across every revision for the removed identity and the seven removed strings: 0 occurrences.

## Outstanding items

1. Publication approval itself: Ticket 14.
2. The pre-rewrite repository must remain private (archive) so that its
   history is never exposed.
3. Optional: regenerate the showcase deck with explicit document
   properties.

## Final publication checklist

- [ ] Ticket 14 approval recorded
- [ ] Pre-rewrite repository renamed to a private archive and confirmed private
- [ ] New public repository created from the rewritten baseline only; no other clone or bundle pushed
- [ ] This branch merged via pull request; `main` carries these review changes
- [ ] Gitleaks history and working-tree scans re-run on the repository as pushed, no leaks
- [ ] Test suite, redaction gate and CI gate green on the commit to be published
- [ ] Rehearsal log and recording checklist still contain no personal or machine details
- [ ] Repository visibility changed to public by the owner (not by tooling), then CI observed green on the public repository
