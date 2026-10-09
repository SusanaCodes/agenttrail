# Redaction gate: structured-identifier backstop (Ticket 8)

A narrow, deterministic scan of the repository's committed record data
for three structured UK identifiers. It is defence in depth behind the
schema, not a PII detector.

> The gate provides deterministic detection for the supported
> structured identifier formats. It does not prove that arbitrary
> personal data is absent.

## Two-layer privacy design

**Layer 1 — the primary control — is architectural** (see
docs/audit-trail.md and `agenttrail/audit.py`): inputs and audit
records are built from an explicit allow-list of structured fields;
applicant free text is never accepted; every string field is
constrained by an enum, a bounded identifier pattern, or the canonical
timestamp format; rationales must be exact renderings of local
allow-listed templates; the record schema sets
`additionalProperties: false`. PII is excluded by construction, so
under normal operation there is nothing for a scanner to find.

**Layer 2 — this gate — is a backstop.** If a supported identifier
somehow lands in record data despite the schema (a future code change,
a hand-edited fixture, a schema regression), the scan catches it and
fails CI. The scanner reads the **raw line text** of each target file,
not parsed schema fields, so an identifier hiding in an unexpected or
nested field is still found.

Raw text alone is not enough for JSON. An identifier written with JSON
`\uXXXX` escapes is restored by any JSON parser but does not appear in
the raw line. So where a line is valid JSON, the scanner also decodes
it with the standard JSON parser and scans **every decoded key and
string value**, at any depth of nested objects and arrays:

* Each key and each string value is scanned on its own. Separate fields
  are never joined, so fragments in different fields do not add up to
  an identifier.
* Every key/value pair is scanned, including the earlier of two equal
  keys, which a parser would normally drop.
* A category found in both the raw text and the decoded content of a
  line is reported once.
* A line that is not valid JSON is scanned as raw text only, as before.

## What is checked — and only this

| Category | Recognised syntax |
|---|---|
| `national_insurance_number` | Two prefix letters, six digits, suffix letter A–D. Any casing. Optional single space or hyphen between the conventional groups: `AB123456C`, `AB 12 34 56 C`, `AB-12-34-56-C`, `AB 123456 C`. Prefixes that are never issued are excluded: first letter D/F/I/Q/U/V, second letter D/F/I/Q/U/V/O, pairs BG, GB, KN, NK, NT, TN, ZZ. |
| `uk_postcode` | Outward shapes A9, A99, A9A, AA9, AA99, AA9A plus the 9AA inward part, with or without the single conventional space, any casing (`SW1A 1AA`, `m1 1ae`, `b338th`). Shape matching only — not postal-address validation. |
| `nhs_number` | Exactly ten digits, contiguous or grouped 3-3-4 with single space or hyphen separators (`9434765919`, `943 476 5919`, `943-476-5919`). |

**NHS checksum decision:** the scanner deliberately does **not** apply
the modulus-11 checksum. A mistyped or corrupted NHS number is still
sensitive data, and a privacy backstop that ignores it because its
check digit is wrong would fail exactly when it matters. The cost is a
higher false-positive rate on arbitrary ten-digit numbers; the
committed record data contains none, and
`tests/test_redaction_gate.py` pins the behaviour.

A candidate embedded inside a longer letter/digit/underscore token
(SHA-256 digests, base64 tool-use IDs, model IDs — all common in the
fixture data) is ignored: it cannot be a conventionally presented
identifier, and matching inside random tokens would make the gate cry
wolf.

Out of scope by design: names, arbitrary addresses, email addresses,
phone numbers, fuzzy matching, machine learning, and NER. Do **not**
read this gate as "AgentTrail records contain no PII" — no such
blanket guarantee is made or possible.

## CLI

```bash
python3 -m agenttrail.redaction_gate            # committed record data
python3 -m agenttrail.redaction_gate PATH...    # explicit files
```

The default targets are the repository's committed record data:
`data/golden_cases.jsonl` and every registered agent version's fixture
set (`fixtures/bedrock-converse-v1.jsonl` and the synthetic demo set
`fixtures/bedrock-converse-v2-synthetic.jsonl`).
Runtime audit trails (`audit/`, `*.audit.jsonl`) are git-ignored and
never committed; pass a trail path explicitly to scan one.

Exit codes:

| Code | Report | Meaning |
|---|---|---|
| 0 | `REDACTION GATE: PASS` | Scan completed; no supported identifier found |
| 1 | `REDACTION GATE: FAIL` | One or more supported identifiers detected |
| 2 | `REDACTION GATE: ERROR` | Scan could not be completed (missing, unreadable, or directory target; no targets; or a line of valid JSON that the parser cannot decode, such as one nested too deeply) |

A missing or unreadable configured target is an ERROR, never a silent
PASS. The scan is fully offline: standard library only, no AWS,
Bedrock, or network calls.

## Safe failure reporting

A finding is reported as file, line, category, and a fixed marker —
never the matched text:

```text
finding: data/golden_cases.jsonl:12: national_insurance_number: [REDACTED]
```

The match string and the decoded content are discarded inside the
scanner; the `Finding` type has no field that could carry either, so
CLI output, CI logs, exceptions, and reports do not reproduce the
detected value. An undecodable line is reported by file, line number
and exception class name only. Scanned paths and
findings are sorted (path, line, category), so output is byte-identical
on every run.

## CI integration

`.github/workflows/ci-gate.yml` runs `python3 -m
agenttrail.redaction_gate` as its own "Run redaction gate" step after
the unit tests and the Ticket 6 escalation-rate gate, which continue to
run unchanged. Any non-zero exit (finding or operational error) fails
the `evaluation-gate` job; there is no `|| true`, `continue-on-error`,
or equivalent softening.

## Known limitations

* **False negatives:** identifiers split across lines or across
  fields, unconventional separators (`AB.12.34.56.C`), values embedded
  in longer tokens, and every identifier category not listed above are
  not detected. The never-issued-prefix rule means a malformed
  NI-shaped string with an invalid prefix is skipped.
* **Decoding goes one level deep.** JSON is decoded once per line. An
  escaped identifier inside a line that is not valid JSON, or inside
  JSON text that is itself stored as a string value, is not decoded
  and is not detected. Other encodings (for example base64 or URL
  encoding) are not decoded at all.
* **No size or depth limits.** The scanner sets none of its own. A line
  the standard parser refuses to decode stops the scan with exit 2.
* **False positives:** any ten-digit number in a boundary-delimited
  position matches `nhs_number`; short letter/digit words can match
  postcode shapes. The structured record vocabulary (case refs, enums,
  timestamps, model IDs) is covered by negative tests to keep the
  committed data clean.
* The gate scans files it is pointed at. Data outside the configured
  targets — logs, databases, un-committed trails — is only covered if
  a caller passes those paths.
