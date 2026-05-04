"""Run the deterministic extraction pipeline against ``tests/fixtures/passports/``.

Each fixture is a pair: ``<id>.{jpg,png,pdf,tiff}`` plus ``<id>.expected.json``
with the ground-truth field values. The script prints per-field accuracy
plus an overall score so we can track progress against the Phase 1 target
of ≥95%.

Usage:
    make benchmark
    python -m scripts.benchmark_extraction --fixtures path/to/dir
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from hawiya.extractors.document_classifier import (
    UnsupportedDocumentError,
    classify,
)
from hawiya.extractors.mrz import MRZFormatError, parse_td3
from hawiya.extractors.ocr import (
    NoMRZFoundError,
    OCRUnavailableError,
    PassportEyeAdapter,
)

DEFAULT_FIXTURES = Path("tests/fixtures/passports")
COMPARED_FIELDS = (
    "document_number",
    "surname",
    "given_names",
    "nationality",
    "issuing_country",
    "date_of_birth",
    "date_of_expiry",
    "sex",
)


async def _extract_one(adapter: PassportEyeAdapter, image_path: Path) -> dict[str, Any]:
    payload = image_path.read_bytes()
    classify(payload, None)
    line1, line2 = await adapter.read_mrz(payload, "application/octet-stream")
    parsed = parse_td3(line1, line2)
    return {
        "document_number": parsed.document_number,
        "surname": parsed.surname,
        "given_names": parsed.given_names,
        "nationality": parsed.nationality,
        "issuing_country": parsed.issuing_country,
        "date_of_birth": parsed.date_of_birth.isoformat() if parsed.date_of_birth else None,
        "date_of_expiry": parsed.date_of_expiry.isoformat() if parsed.date_of_expiry else None,
        "sex": parsed.sex.value if parsed.sex else None,
        "checksum_status": parsed.checksums.status.value,
    }


async def run(fixtures_dir: Path) -> int:
    if not fixtures_dir.exists():
        print(f"No fixtures at {fixtures_dir}. Add anonymised passport samples and re-run.")
        return 0

    pairs = []
    for image_path in sorted(fixtures_dir.iterdir()):
        if image_path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".pdf", ".tiff", ".tif"}:
            continue
        expected_path = image_path.with_suffix(".expected.json")
        if not expected_path.exists():
            print(f"WARN: {image_path.name} has no expected.json — skipping")
            continue
        pairs.append((image_path, expected_path))

    if not pairs:
        print(
            f"No labelled fixtures in {fixtures_dir}. Phase 1 target: 100 samples (BUILD_PLAN pre-week-1)."
        )
        return 0

    adapter = PassportEyeAdapter()

    field_correct: dict[str, int] = defaultdict(int)
    field_total: dict[str, int] = defaultdict(int)
    total = 0
    failed = 0
    failure_reasons: dict[str, int] = defaultdict(int)

    for image_path, expected_path in pairs:
        total += 1
        expected = json.loads(expected_path.read_text(encoding="utf-8"))
        try:
            actual = await _extract_one(adapter, image_path)
        except (
            NoMRZFoundError,
            OCRUnavailableError,
            MRZFormatError,
            UnsupportedDocumentError,
        ) as e:
            failed += 1
            failure_reasons[type(e).__name__] += 1
            print(f"FAIL {image_path.name}: {type(e).__name__}: {e}")
            continue

        for field in COMPARED_FIELDS:
            if field not in expected:
                continue
            field_total[field] += 1
            if str(expected[field]).upper() == str(actual.get(field) or "").upper():
                field_correct[field] += 1

    print()
    print(f"=== Benchmark — {total} fixtures ({failed} extraction failures) ===")
    if failure_reasons:
        for reason, n in sorted(failure_reasons.items()):
            print(f"  {reason}: {n}")
    print()
    overall_correct = sum(field_correct.values())
    overall_total = sum(field_total.values())
    if overall_total == 0:
        print("No comparable fields after extraction failures.")
        return 1
    print(f"{'Field':<20} {'Accuracy':>10}")
    for field in COMPARED_FIELDS:
        if field_total[field] == 0:
            continue
        acc = field_correct[field] / field_total[field]
        print(f"{field:<20} {acc * 100:>9.1f}%")
    overall = overall_correct / overall_total
    print(f"{'OVERALL':<20} {overall * 100:>9.1f}%")
    target_met = overall >= 0.95
    print()
    print("PASS" if target_met else "FAIL", "vs. 95% target")
    return 0 if target_met else 1


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--fixtures",
        type=Path,
        default=DEFAULT_FIXTURES,
        help=f"Directory of labelled fixtures (default: {DEFAULT_FIXTURES})",
    )
    args = p.parse_args()
    sys.exit(asyncio.run(run(args.fixtures)))


if __name__ == "__main__":
    main()
