# Recorded model fixtures (Ticket 4)

Genuine Amazon Bedrock Converse responses are recorded once, committed,
and replayed locally so evaluation runs are deterministic, fast, offline,
free of Bedrock cost, independent of AWS credentials, and incapable of
silently falling back to the live model.

## Why not evaluate against the live model in CI

A deterministic CI gate needs the same input to produce the same verdict
every run. Live model calls cannot promise that: outputs can vary between
invocations and model revisions, calls cost money, need credentials and
network access, and fail for operational reasons unrelated to the code
under test. A flaky, paid, credential-bearing gate stops being trusted.
Note that `temperature: 0.0` (already set) and fixed seeds were **not**
used as a substitute for recording: they reduce variance but guarantee
nothing across model updates or serving infrastructure, so they cannot
anchor a gate.

## Architecture: record once, replay forever

- **Recording** (`agenttrail.record_fixtures`) is an explicit, human-run
  command. It drives every golden case through the production
  `decide_case` path with a capturing wrapper around the real
  bedrock-runtime client, so the stored request is exactly the request
  production issues — one paid Converse call per case. `boto3` is
  imported only inside this path.
- **Replay** (`agenttrail.fixtures.ReplayBedrockClient`) loads the
  committed fixture file and implements `converse(**request)`, so it is
  injected into `decide_case(...)` / `decide_case_audited(...)` exactly
  like a real client. It never imports boto3, reads no credentials, and
  opens no sockets. The decision parser, confidence policy, and rationale
  templates are the production ones — nothing is duplicated in the
  fixture layer.

## Exact-match request fingerprinting

Each fixture stores a SHA-256 of the **complete** Converse request —
`modelId`, system prompt, messages, tool configuration, and inference
configuration — serialised canonically (sorted keys at every level,
compact separators, ASCII-only, NaN rejected). Replay canonicalises the
incoming request and looks up that fingerprint. The `case_id` in a
fixture is provenance only; it is never a lookup key.

Consequently, changing the prompt text, tool schema, model ID,
temperature, max tokens, or the case input changes the fingerprint and
produces an explicit `FixtureNotFoundError`. An obsolete response can
never be silently replayed against a changed contract.

## Fixture format

`fixtures/bedrock-converse-v1.jsonl` — one JSON object per line:

| field | meaning |
|---|---|
| `fixture_format_version` | format version of the entry (`1.0.0`) |
| `case_id` | golden case recorded (provenance only) |
| `dataset_version` | golden dataset version at recording time |
| `recorded_at` | UTC timestamp of the recording run |
| `model_id` | Bedrock model/profile ID used |
| `prompt_version` | `PROMPT_VERSION` at recording time |
| `request_sha256` | fingerprint of the canonical request |
| `request` | the complete Converse request, verbatim |
| `response` | the genuine Bedrock response body |

The contract is enforced at runtime by
`agenttrail.fixtures.validate_fixture_entry` (closed field set,
identifier patterns, request shape, hash re-verified against the stored
request, duplicate fingerprints and case_ids rejected).
`data/bedrock_fixture.schema.json` documents the same contract; runtime
validation never depends on the schema file.

The model-generated tool input is preserved exactly as produced — never
rewritten to match golden labels. Only transport metadata is stripped:
SDK `ResponseMetadata` (HTTP headers, AWS request IDs) and per-call
latency `metrics`. Credentials and environment details are never
captured. A fixture containing `ResponseMetadata` fails validation.

## Recording a new fixture version safely

```bash
python3 -m agenttrail.record_fixtures --model-id <model-id> [--region <region>]
```

- Reads all golden cases, makes exactly one Bedrock call per case, and
  validates every entry before publishing.
- Writes to a temporary file, re-validates the written bytes, and only
  then atomically replaces the target (`os.replace`). A failure part-way
  leaves no partial authoritative fixture file.
- **Refuses to overwrite an existing fixture set** unless `--overwrite`
  is passed. Replacement changes what CI asserts against, so the new
  recording must be diffed and reviewed like any other behavioural
  change — hence the explicit flag and code review, never an automatic
  refresh.
- There is no record-on-miss, hybrid client, or automatic recording. A
  missing fixture is a hard failure everywhere else.

For a new contract (prompt, tool schema, or model change), bump the
relevant version, record to a new versioned file if the format itself
changed (`bedrock-converse-v2.jsonl`), and review the diff.

## How offline replay is verified

The replay test suite runs the full 36-case replay with `socket.socket`,
`socket.create_connection`, and `socket.getaddrinfo` patched to fail
immediately, and with `AWS_*` environment variables scrubbed or set to
invalid values. Any network attempt fails the test. A separate test
asserts `boto3` is absent from `sys.modules` after the replay path has
executed, and that a fixture miss raises `FixtureNotFoundError` rather
than reaching for any live client — there is no live client to reach.

## What replay does and does not prove

Replay proves **repeatability**: the same request maps to the same
recorded response, hence the same `decision`, `confidence`, and templated
`rationale` (audit timestamps still differ between runs, by design).
It does **not** prove current live-model quality — fixtures are a
snapshot of the model's behaviour at recording time.

**Staleness is a known risk.** Fixtures must be re-recorded when the
prompt contract (`PROMPT_VERSION`), tool schema, inference configuration,
model ID, or golden dataset changes, and should be re-recorded when the
underlying model is revised even under an unchanged ID. Contract changes
are self-announcing (fingerprint misses); silent model-revision drift is
not, which is exactly why fixture replay must be paired with periodic,
deliberate live evaluation rather than treated as evidence about the
current model.
