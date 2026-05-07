"""Canonicalization Golden Fixtures 測試

驗證 canonicalization 正規化的 hash 穩定性。
"""

import hashlib
import json
from decimal import Decimal
from pathlib import Path

import yaml

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "canonicalization"


def canonicalize_decision_record(record: dict) -> dict:
    """正規化單筆決策記錄

    Args:
        record: 原始決策記錄

    Returns:
        正規化後的字典（已排序、已量化）
    """
    # 欄位白名單（按順序）
    canonical = {}

    # 1. decision_id
    if "decision_id" in record:
        canonical["decision_id"] = record["decision_id"]

    # 2. template_id
    if "template_id" in record:
        canonical["template_id"] = record["template_id"].strip()

    # 3. status
    if "status" in record:
        canonical["status"] = record["status"]

    # 4. confidence
    if "confidence" in record:
        canonical["confidence"] = record["confidence"]

    # 5. comparability_score（Decimal 量化）
    if "comparability_score" in record:
        score = Decimal(str(record["comparability_score"]))
        canonical["comparability_score"] = str(score.quantize(Decimal("0.0001")))

    # 6. option_a（遞迴正規化）
    if "option_a" in record:
        canonical["option_a"] = canonicalize_option(record["option_a"])

    # 7. option_b（遞迴正規化）
    if "option_b" in record:
        canonical["option_b"] = canonicalize_option(record["option_b"])

    # 8. risk_tags（排序）
    if "risk_tags" in record:
        canonical["risk_tags"] = sorted(record["risk_tags"])

    return canonical


def canonicalize_option(option: dict) -> dict:
    """正規化 option 物件

    Args:
        option: 原始 option

    Returns:
        正規化後的 option
    """
    canonical = {}

    # 依序處理欄位
    for key in sorted(option.keys()):
        if key in ["direction", "label", "recommendation", "status"]:
            canonical[key] = option[key]
        elif key == "score":
            # 保持原始數值（不量化 float）
            canonical[key] = option[key]

    return canonical


def canonicalize_and_hash(input_data: dict) -> str:
    """正規化並計算 hash

    Args:
        input_data: 原始輸入（包含 records）

    Returns:
        SHA-256 hash（完整 64 hex）
    """
    if "records" not in input_data:
        raise ValueError("input_data 必須包含 'records' 欄位")

    records = input_data["records"]

    # 正規化所有記錄
    canonical_records = [canonicalize_decision_record(r) for r in records]

    # 若有多筆，按 decision_id 排序
    if len(canonical_records) > 1:
        canonical_records.sort(key=lambda r: r.get("decision_id", ""))

    # 序列化為 JSON（緊湊格式）
    if len(canonical_records) == 1:
        canonical_json = json.dumps(
            canonical_records[0],
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    else:
        canonical_json = json.dumps(
            canonical_records,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )

    # 計算 hash
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


class TestCanonicalizationGoldens:
    """Canonicalization Golden Fixtures 測試集"""

    def test_minimal_single_decision_hash(self):
        """測試最小單筆決策的 hash 正確性"""
        fixture_dir = FIXTURES_DIR / "minimal_single_decision"
        input_path = fixture_dir / "input.yaml"
        expected_hash_path = fixture_dir / "canonical.sha256"

        # 讀取輸入
        with open(input_path, "r", encoding="utf-8") as f:
            input_data = yaml.safe_load(f)

        # 讀取預期 hash
        with open(expected_hash_path, "r", encoding="utf-8") as f:
            expected_hash = f.read().strip()

        # 計算實際 hash
        actual_hash = canonicalize_and_hash(input_data)

        # 驗證
        assert actual_hash == expected_hash, (
            f"Hash 漂移偵測！\n"
            f"預期: {expected_hash}\n"
            f"實際: {actual_hash}"
        )

    def test_multiple_decisions_sorted(self):
        """測試多筆決策排序後 hash 一致"""
        fixture_dir = FIXTURES_DIR / "multiple_decisions_unsorted"
        input_path = fixture_dir / "input.yaml"
        expected_hash_path = fixture_dir / "canonical.sha256"

        # 讀取輸入
        with open(input_path, "r", encoding="utf-8") as f:
            input_data = yaml.safe_load(f)

        # 讀取預期 hash
        with open(expected_hash_path, "r", encoding="utf-8") as f:
            expected_hash = f.read().strip()

        # 計算實際 hash
        actual_hash = canonicalize_and_hash(input_data)

        # 驗證（即使輸入亂序，正規化後應相同）
        assert actual_hash == expected_hash, (
            f"排序失敗或 hash 漂移！\n"
            f"預期: {expected_hash}\n"
            f"實際: {actual_hash}"
        )

    def test_decimal_unicode_handling(self):
        """測試 Decimal 精度與 Unicode 處理"""
        fixture_dir = FIXTURES_DIR / "decimal_unicode_edge"
        input_path = fixture_dir / "input.yaml"
        expected_hash_path = fixture_dir / "canonical.sha256"

        # 讀取輸入
        with open(input_path, "r", encoding="utf-8") as f:
            input_data = yaml.safe_load(f)

        # 讀取預期 hash
        with open(expected_hash_path, "r", encoding="utf-8") as f:
            expected_hash = f.read().strip()

        # 計算實際 hash
        actual_hash = canonicalize_and_hash(input_data)

        # 驗證
        assert actual_hash == expected_hash, (
            f"Decimal 或 Unicode 處理錯誤！\n"
            f"預期: {expected_hash}\n"
            f"實際: {actual_hash}"
        )

    def test_all_goldens_have_required_files(self):
        """測試所有 goldens 都有必要檔案"""
        required_files = ["input.yaml", "canonical.json", "canonical.sha256"]

        for golden_dir in FIXTURES_DIR.iterdir():
            if not golden_dir.is_dir():
                continue

            for required_file in required_files:
                file_path = golden_dir / required_file
                assert file_path.exists(), (
                    f"Golden {golden_dir.name} 缺少必要檔案: {required_file}"
                )
