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

* Each key and each string value is scanned on its own. Separate
  strings are never joined, so fragments in different fields, or in
  different layers, do not add up to an identifier.
* Every key/value pair is scanned, including the earlier of two equal
  keys, which a parser would normally drop.
* A category found more than once on a line, by the raw scan or at any
  decoded layer, is reported once.
* A line that is not valid JSON is scanned as raw text only, as before.

One decoding is not enough either, because the record data stores JSON
inside JSON. Each Bedrock fixture entry keeps the case fields as JSON
text in the string `request.messages[].content[].text`. Decoding the
line restores that text, escapes and all; an escaped identifier inside
it only appears when the text is parsed in turn. So **every decoded
string that is itself a valid JSON document is decoded as well**, with
the same parser and the same rules, and so are the strings found
inside it, for as many layers as the data has:

* Each string is first scanned as the text it is. Decoding adds to
  that scan and never replaces it.
* A string that is not valid JSON, such as ordinary prose or text that
  only resembles JSON, is left to the text scan. Nothing interprets
  escape sequences except the JSON parser, so escapes in such a string
  are not decoded.
* This applies to any key or string value at any depth, not only to the
  fixture text field.
* Decoding always ends. A string is only ever decoded from a longer
  text: it either sat between quotes in that text or was its single
  string token. Each further layer is therefore strictly shorter than
  the one before, and the layers run out. No depth limit is involved.

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
| 2 | `REDACTION GATE: ERROR` | Scan could not be completed (missing, unreadable, or directory target; no targets; or valid JSON that the parser refuses to decode, such as a document nested too deeply or holding an integer too long to convert, whether it is the line itself or a document stored in one of its strings) |

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
detected value. A line the parser refuses to decode, or one holding
such a document in a string, is reported by file, line number and
exception class name only. Scanned paths and
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
* **Only JSON is decoded, and only whole documents.** A string is
  decoded when the whole of it is a valid JSON document. An escaped
  identifier is not detected in a line that is not valid JSON, in a
  string that is not valid JSON, or in JSON that makes up only part of
  a string, such as a document with prose before or after it. Other
  encodings (for example base64 or URL encoding) are not decoded at
  all.
* **No size or depth limits.** The scanner sets none of its own. A line
  or a stored document that the standard parser refuses to decode stops
  the scan with exit 2. What the parser refuses depends on the Python
  version and its settings. A string holding nothing but a very long
  run of digits or opening brackets is refused in the same way, since
  it is read as the start of a JSON document.
* **False positives:** any ten-digit number in a boundary-delimited
  position matches `nhs_number`; short letter/digit words can match
  postcode shapes. The structured record vocabulary (case refs, enums,
  timestamps, model IDs) is covered by negative tests to keep the
  committed data clean.
* **Source and documentation files are raw-text scans.** When the gate
  is pointed at `.py` or `.md` files, almost no line is a whole JSON
  document, so only the raw-text detectors apply and the detector
  examples in this document and in the redaction tests are themselves
  reported. The result of that sweep is recorded in the
  [security assessment](security-assessment.md#verification-record).
* **An empty target passes.** A zero-byte file is a completed scan with
  no findings, exit 0. Confirm the target is the file you meant.
* The gate scans files it is pointed at. Data outside the configured
  targets — logs, databases, un-committed trails — is only covered if
  a caller passes those paths.
