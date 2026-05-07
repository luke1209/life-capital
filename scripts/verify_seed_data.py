#!/usr/bin/env python3
"""Seed 資料驗收腳本

驗證 seed 結構、hash、counts、事件鏈與 redaction 規則。
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

# 新增專案根目錄到 Python path，確保可導入 life_capital 模組
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import yaml  # noqa: E402  # sys.path.insert above

from life_capital.privacy.redaction.engine import RedactionEngine  # noqa: E402

TEXT_SUFFIXES = {".json", ".jsonl", ".yaml", ".yml", ".md", ".txt", ".csv"}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_manifest(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_lock(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _collect_text_issues(root: Path) -> list[str]:
    issues = []
    for file_path in root.rglob("*"):
        if file_path.is_dir():
            continue
        if file_path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        data = file_path.read_bytes()
        if data.startswith(b"\xef\xbb\xbf"):
            issues.append(f"BOM found: {file_path}")
        if b"\r\n" in data or b"\r" in data:
            issues.append(f"CRLF found: {file_path}")
    return issues


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    entries = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entries.append(json.loads(line))
    return entries


def _load_decisions(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _count_staging(entries: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in entries:
        status = entry.get("status", "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _verify_hashes(root: Path, manifest: dict, errors: list[str]) -> None:
    expected = manifest.get("expected_hashes", {})
    for rel_path, expected_hash in expected.items():
        file_path = root / rel_path
        if not file_path.exists():
            errors.append(f"missing file for expected_hashes: {rel_path}")
            continue
        actual = f"sha256:{_sha256_file(file_path)}"
        if actual != expected_hash:
            errors.append(f"hash mismatch: {rel_path}")


def _verify_lock(root: Path, lock: dict, errors: list[str]) -> dict[str, str]:
    actual_hashes: dict[str, str] = {}
    for file_path in sorted(root.rglob("*")):
        if file_path.is_dir():
            continue
        if file_path.name in ("seed_lock.json",):
            continue
        rel_path = file_path.relative_to(root).as_posix()
        actual_hashes[rel_path] = f"sha256:{_sha256_file(file_path)}"

    expected = lock.get("files", {})
    for rel_path, expected_hash in expected.items():
        if rel_path not in actual_hashes:
            errors.append(f"lock missing file: {rel_path}")
            continue
        if actual_hashes[rel_path] != expected_hash:
            errors.append(f"lock hash mismatch: {rel_path}")

    return actual_hashes


def _verify_counts(root: Path, manifest: dict, errors: list[str]) -> None:
    expected = manifest.get("expected_counts", {})
    staging_path = root / "staging" / "entries.jsonl"
    if staging_path.exists():
        staging_counts = _count_staging(_load_jsonl(staging_path))
        for status, count in expected.get("staging", {}).items():
            if staging_counts.get(status, 0) != count:
                errors.append(f"staging count mismatch: {status}")

    advisor_expected = expected.get("advisor", {})
    proposals_dir = root / "proposals" / "pending"
    if proposals_dir.exists() and advisor_expected.get("proposals") is not None:
        proposal_count = len(list(proposals_dir.glob("advisor_*.yaml")))
        if proposal_count != advisor_expected.get("proposals"):
            errors.append("advisor proposals count mismatch")
    decisions_path = root / "canonical" / "decisions" / "decisions.yaml"
    if decisions_path.exists():
        decisions = _load_decisions(decisions_path).get("records", [])
        if (
            advisor_expected.get("decisions") is not None
            and len(decisions) != advisor_expected.get("decisions")
        ):
            errors.append("advisor decisions count mismatch")

    audit_path = root / "derived" / "logs" / "advisor_audit.jsonl"
    if audit_path.exists():
        audit_count = len(_load_jsonl(audit_path))
        if (
            advisor_expected.get("audit_actions") is not None
            and audit_count != advisor_expected.get("audit_actions")
        ):
            errors.append("advisor audit count mismatch")


def _verify_invariants(root: Path, errors: list[str]) -> None:
    staging_path = root / "staging" / "entries.jsonl"
    if staging_path.exists():
        entries = _load_jsonl(staging_path)
        entries_by_id = {e.get("entry_id"): e for e in entries}
        for entry in entries:
            status = entry.get("status")
            proposal_id = entry.get("proposal_id")
            if status == "approved" and not proposal_id:
                errors.append(f"approved entry missing proposal_id: {entry.get('entry_id')}")
            if proposal_id:
                proposal_path = root / "proposals" / "pending" / proposal_id
                if not proposal_path.exists():
                    errors.append(f"proposal_id missing file: {proposal_id}")
            if status == "duplicate":
                dup_of = entry.get("duplicate_of")
                if not dup_of or dup_of not in entries_by_id:
                    errors.append(f"duplicate entry invalid reference: {entry.get('entry_id')}")


def _verify_datasets(root: Path, manifest: dict, errors: list[str]) -> None:
    datasets = manifest.get("datasets", [])
    decisions_path = root / "canonical" / "decisions" / "decisions.yaml"
    decisions_data = _load_decisions(decisions_path) if decisions_path.exists() else {}
    decisions = decisions_data.get("records", [])
    audit_path = root / "derived" / "logs" / "advisor_audit.jsonl"
    audit_entries = _load_jsonl(audit_path) if audit_path.exists() else []
    staging_entries = (
        _load_jsonl(root / "staging" / "entries.jsonl")
        if (root / "staging" / "entries.jsonl").exists()
        else []
    )

    for dataset in datasets:
        purpose = dataset.get("purpose")
        expected = dataset.get("expected", {})
        if purpose == "phase1_dedupe_exact":
            for rel_path in dataset.get("inputs", []):
                if not (root / rel_path).exists():
                    errors.append(f"dedupe input missing: {rel_path}")
        elif purpose == "phase4_staging_error":
            entry_id = expected.get("entry_id")
            error_code = expected.get("error_code")
            entry = next((e for e in staging_entries if e.get("entry_id") == entry_id), None)
            if not entry or entry.get("status") != "error":
                errors.append("staging error entry missing or status mismatch")
            if entry and error_code and error_code not in (entry.get("error_message") or ""):
                errors.append("staging error code mismatch")
        elif purpose == "phase5_advisor_chain":
            decision_id = dataset.get("inputs", {}).get("decision_id")
            if decision_id:
                record = next((r for r in decisions if r.get("decision_id") == decision_id), None)
                if not record or record.get("status") != "applied":
                    errors.append("advisor chain applied record missing")
            expected_actions = expected.get("audit_actions", [])
            if expected_actions:
                chain_actions = [
                    e.get("action")
                    for e in audit_entries
                    if e.get("proposal_id") == dataset.get("inputs", {}).get("proposal_id")
                ]
                for action in expected_actions:
                    if action not in chain_actions:
                        errors.append(f"audit action missing: {action}")
            if "reverted" in expected.get("decision_statuses", []):
                reverted = any(r.get("status") == "reverted" for r in decisions)
                if not reverted:
                    errors.append("reverted decision missing")
        elif purpose == "phase5_advisor_chain_negative":
            fixture = dataset.get("inputs", {}).get("fixture")
            if fixture:
                fixture_path = root / fixture
                if not fixture_path.exists():
                    errors.append(f"negative chain fixture missing: {fixture}")
                    continue
                data = json.loads(fixture_path.read_text(encoding="utf-8"))
                if data.get("error_code") != expected.get("error_code"):
                    errors.append("negative chain error_code mismatch")


def _verify_redaction(root: Path, errors: list[str]) -> None:
    payload_path = root / "fixtures" / "redaction_payload.json"
    if not payload_path.exists():
        return
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    engine = RedactionEngine()
    result = engine.redact(payload)
    if "email" not in result.redacted_fields:
        errors.append("redaction missing forbidden field: email")
    if "phone_number" not in result.redacted_fields:
        errors.append("redaction missing forbidden field: phone_number")
    if ("city", "job_title", "salary") not in result.composition_violations:
        errors.append("redaction missing composition violation")


def _verify_fixtures(root: Path, manifest: dict, errors: list[str]) -> None:
    fixtures_dir = root / "fixtures"
    if not fixtures_dir.exists():
        return
    expected = ["decisions_v1_0.yaml", "life_assumptions_v1_0.yaml"]
    for name in expected:
        if not (fixtures_dir / name).exists():
            errors.append(f"missing fixture: {name}")


def main() -> int:
    parser = argparse.ArgumentParser(description="verify seed data")
    parser.add_argument("--path", type=Path, default=Path("data/seed"), help="seed data path")
    parser.add_argument("--update-lock", action="store_true", help="update seed_lock.json")
    parser.add_argument("--report", type=str, default="", help="report format: json")
    parser.add_argument("--diff", action="store_true", help="show diff summary for hash mismatches")
    args = parser.parse_args()

    data_path = args.path.expanduser().resolve()
    manifest_path = data_path / "seed_manifest.json"
    lock_path = data_path / "seed_lock.json"
    errors: list[str] = []

    if not manifest_path.exists():
        print(f"missing manifest: {manifest_path}")
        return 1

    manifest = _load_manifest(manifest_path)

    text_issues = _collect_text_issues(data_path)
    if text_issues:
        errors.extend(text_issues)

    _verify_hashes(data_path, manifest, errors)

    if lock_path.exists():
        lock = _load_lock(lock_path)
    else:
        lock = {"files": {}}

    actual_hashes = _verify_lock(data_path, lock, errors)

    if args.update_lock:
        lock_data = {
            "seed_version": manifest.get("seed_version", "1.0"),
            "generated_at": manifest.get("generated_at", ""),
            "files": actual_hashes,
        }
        lock_path.write_text(
            json.dumps(lock_data, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )

    _verify_counts(data_path, manifest, errors)
    _verify_invariants(data_path, errors)
    _verify_datasets(data_path, manifest, errors)
    _verify_redaction(data_path, errors)
    _verify_fixtures(data_path, manifest, errors)

    if args.report == "json":
        report = {
            "ok": not errors,
            "errors": errors,
        }
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    elif errors:
        print("seed verify failed:")
        for err in errors:
            print(f"- {err}")
    else:
        print("seed verify ok")

    if args.diff and lock.get("files"):
        expected_files = lock.get("files", {})
        mismatch = [
            rel for rel, expected_hash in expected_files.items()
            if actual_hashes.get(rel) != expected_hash
        ]
        if mismatch:
            print("hash mismatches:")
            for rel in mismatch:
                print(f"- {rel}")
                file_path = data_path / rel
                if file_path.exists() and file_path.suffix.lower() in TEXT_SUFFIXES:
                    try:
                        lines = file_path.read_text(encoding="utf-8").splitlines()
                        preview = lines[:5]
                        for line in preview:
                            print(f"  {line}")
                    except Exception:
                        print("  (preview unavailable)")

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
