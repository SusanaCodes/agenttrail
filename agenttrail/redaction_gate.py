"""Redaction gate: deterministic PII backstop over record data (Ticket 8).

AgentTrail's primary privacy control is architectural: inputs and audit
records use structured, allow-listed fields, applicant free text is
never accepted, and rationales are rendered locally from allow-listed
templates (see ``agenttrail.audit`` and docs/audit-trail.md). This
module is a second, independent layer: a deterministic scan of committed
record data for three structured UK identifiers, in case one somehow
lands in a record despite the schema.

It detects exactly three categories and nothing else:

* ``national_insurance_number`` — two prefix letters, six digits, and a
  suffix letter A-D, with optional single spaces or hyphens between the
  conventional groups (``AB123456C``, ``AB 12 34 56 C``,
  ``AB-12-34-56-C``), any casing. Administrative prefixes that can never
  be issued are excluded: first letter D/F/I/Q/U/V, second letter
  D/F/I/Q/U/V/O, and the pairs BG, GB, KN, NK, NT, TN, ZZ.
* ``uk_postcode`` — the common outward shapes A9, A99, A9A, AA9, AA99,
  AA9A followed by the 9AA inward part, with or without the single
  conventional space, any casing. This is shape matching, not postal
  address validation.
* ``nhs_number`` — exactly ten digits, contiguous or in the
  conventional 3-3-4 grouping with single space or hyphen separators.
  Deliberately no modulus-11 checksum: a backstop must also catch a
  mistyped or corrupted NHS number, which is still sensitive, so the
  gate accepts the higher false-positive rate of shape-only matching.

Matches embedded inside a longer alphanumeric or underscore token (hex
digests, base64 tool-use IDs, model IDs) are ignored on purpose — the
scanned data is full of such tokens and they cannot be a conventionally
presented identifier.

The scan reads raw line text, not parsed schema fields, so an
identifier in an unexpected or nested field is still found. Where a
line is valid JSON it is also decoded with the standard JSON parser,
and every decoded key and string value is scanned on its own, at any
nesting depth: an identifier written with ``\\uXXXX`` escapes is
restored by a parser but is invisible in the raw text. Separate fields
are never joined, and a line that is not valid JSON is scanned as raw
text only. Findings carry only the file, line number, and category —
the matched text and the decoded content are discarded during scanning
and can never appear in output, exceptions, or reports.

This gate provides deterministic detection for the supported structured
identifier formats. It does not prove that arbitrary personal data is
absent, and names, addresses, email addresses, phone numbers, fuzzy
matching, and NER are explicitly out of scope.

Exit codes: 0 scan completed with no findings, 1 one or more supported
identifiers detected, 2 the scan could not be completed.
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from agenttrail.golden import DEFAULT_DATASET_PATH
from agenttrail.versions import AGENT_VERSIONS

# The repository's committed record data: the golden dataset and every
# registered agent version's Bedrock fixture set (the genuine v1
# recording and the synthetic v2 demo set alike). Runtime audit trails
# (audit/, *.audit.jsonl) are git-ignored and never committed, so they
# are not default targets; pass their paths explicitly to scan one.
DEFAULT_SCAN_TARGETS = (DEFAULT_DATASET_PATH,) + tuple(
    version.fixture_path for version in AGENT_VERSIONS.values()
)

REDACTED_MARKER = "[REDACTED]"

# A match must stand alone: not butted against letters, digits, or an
# underscore on either side. This is what keeps hex digests and base64
# identifiers in the fixture data from producing findings.
_EDGE_L = r"(?<![A-Za-z0-9_])"
_EDGE_R = r"(?![A-Za-z0-9_])"

NI_NUMBER_RE = re.compile(
    _EDGE_L
    + r"([A-Za-z]{2})[ -]?[0-9]{2}[ -]?[0-9]{2}[ -]?[0-9]{2}[ -]?[A-Da-d]"
    + _EDGE_R
)
# Prefix letters and pairs that HMRC never issues.
_NI_INVALID_FIRST = frozenset("DFIQUV")
_NI_INVALID_SECOND = frozenset("DFIQUVO")
_NI_INVALID_PREFIXES = frozenset({"BG", "GB", "KN", "NK", "NT", "TN", "ZZ"})

UK_POSTCODE_RE = re.compile(
    _EDGE_L + r"[A-Za-z]{1,2}[0-9][A-Za-z0-9]? ?[0-9][A-Za-z]{2}" + _EDGE_R
)

NHS_NUMBER_RE = re.compile(
    _EDGE_L + r"[0-9]{3}[ -]?[0-9]{3}[ -]?[0-9]{4}" + _EDGE_R
)


class RedactionScanError(RuntimeError):
    """The scan could not be completed; the gate must not report PASS."""


def _ni_prefix_is_issuable(match):
    prefix = match.group(1).upper()
    return (
        prefix[0] not in _NI_INVALID_FIRST
        and prefix[1] not in _NI_INVALID_SECOND
        and prefix not in _NI_INVALID_PREFIXES
    )


# (category, pattern, extra check on the match object or None). Category
# names double as the fixed report vocabulary and sort alphabetically.
DETECTORS = (
    ("national_insurance_number", NI_NUMBER_RE, _ni_prefix_is_issuable),
    ("nhs_number", NHS_NUMBER_RE, None),
    ("uk_postcode", UK_POSTCODE_RE, None),
)


@dataclass(frozen=True)
class Finding:
    """One detected identifier. Deliberately never stores the match."""

    path: str
    line_number: int
    category: str


class _JsonObject(list):
    """A decoded JSON object kept as its (key, value) pairs.

    Pairs, not a dict: a dict would silently drop the earlier of two
    equal keys, and with it a value the scan has to see.
    """


def _scan_text(text):
    """Categories detected in one piece of text, as a set.

    Match objects never escape this function; only category names do.
    """
    found = set()
    for category, pattern, extra_check in DETECTORS:
        for match in pattern.finditer(text):
            if extra_check is None or extra_check(match):
                found.add(category)
                break
    return found


def _decoded_strings(text):
    """Yield every decoded key and string value of a JSON line.

    Yields nothing when the line is not valid JSON. Raises
    RedactionScanError when the line cannot be decoded for another
    reason, because a scan of its raw text alone would be incomplete.
    """
    try:
        document = json.loads(text, object_pairs_hook=_JsonObject)
    except json.JSONDecodeError:
        return
    except (ValueError, RecursionError) as exc:
        raise RedactionScanError(
            f"line could not be decoded for scanning: "
            f"{exc.__class__.__name__}"
        ) from None
    # Iterative walk: no recursion of our own, whatever the nesting.
    pending = [document]
    while pending:
        node = pending.pop()
        if isinstance(node, str):
            yield node
        elif isinstance(node, _JsonObject):
            for key, value in node:
                yield key
                pending.append(value)
        elif isinstance(node, list):
            pending.extend(node)


def scan_line(text):
    """Return the sorted categories detected in one line of text.

    Scans the raw text, then each decoded JSON key and string value
    separately. A category found by both is reported once. Neither the
    matched text nor the decoded content leaves this function.
    """
    found = _scan_text(text)
    for decoded in _decoded_strings(text):
        found |= _scan_text(decoded)
    return tuple(sorted(found))


def scan_file(path):
    """Scan one file line by line; return a list of Findings.

    Raises RedactionScanError if the file is missing or unreadable —
    an expected scan target that cannot be read must never PASS.
    """
    path = Path(path)
    if not path.is_file():
        raise RedactionScanError(f"scan target is not a readable file: {path}")
    findings = []
    try:
        with open(path, encoding="utf-8") as f:
            for line_number, line in enumerate(f, start=1):
                try:
                    categories = scan_line(line)
                except RedactionScanError as exc:
                    raise RedactionScanError(
                        f"{path}:{line_number}: {exc}"
                    ) from None
                for category in categories:
                    findings.append(
                        Finding(
                            path=str(path),
                            line_number=line_number,
                            category=category,
                        )
                    )
    except (OSError, UnicodeDecodeError) as exc:
        raise RedactionScanError(
            f"cannot read scan target {path}: {exc.__class__.__name__}"
        ) from exc
    return findings


def scan_paths(paths):
    """Scan the given files; return (sorted findings, sorted paths).

    Paths are deduplicated and sorted so the scan order — and therefore
    the finding order and the report — is identical on every run.
    """
    targets = sorted({str(p) for p in paths})
    if not targets:
        raise RedactionScanError("no scan targets were configured")
    findings = []
    for target in targets:
        findings.extend(scan_file(target))
    findings.sort(key=lambda f: (f.path, f.line_number, f.category))
    return tuple(findings), tuple(targets)


def format_report(findings, targets):
    """Deterministic report; contains categories and locations, never PII."""
    lines = [
        f"REDACTION GATE: {'FAIL' if findings else 'PASS'}",
        f"scanned_files={len(targets)}",
        f"findings={len(findings)}",
    ]
    lines.extend(f"target: {target}" for target in targets)
    lines.extend(
        f"finding: {f.path}:{f.line_number}: {f.category}: {REDACTED_MARKER}"
        for f in findings
    )
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python3 -m agenttrail.redaction_gate",
        description=(
            "Scan record data for UK National Insurance numbers, UK "
            "postcodes, and NHS numbers. A backstop to the structured "
            "audit schema, not a general PII detector. Offline: no AWS "
            "credentials or network access are used. Detected values "
            "are never printed."
        ),
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help=(
            "files to scan; defaults to the committed record data "
            "(data/golden_cases.jsonl and every registered agent "
            "version's fixture set under fixtures/)"
        ),
    )
    args = parser.parse_args(argv)
    targets = args.paths or [str(p) for p in DEFAULT_SCAN_TARGETS]

    try:
        findings, scanned = scan_paths(targets)
    except RedactionScanError as exc:
        print("REDACTION GATE: ERROR", file=sys.stderr)
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(format_report(findings, scanned))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
