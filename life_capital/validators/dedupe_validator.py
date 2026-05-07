"""去重驗證器 (Phase 1)

提供去重相關的驗證功能，包括：
- dedupe_key_version 驗證（hard/soft 分級）
- stable_id 重複檢查
- 去重結果一致性驗證
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from life_capital.io.registry import ALLOWED_DEDUPE_KEY_VERSIONS
from life_capital.models.transaction import Transaction


class ValidationSeverity(str, Enum):
    """驗證嚴重程度"""

    HARD_FAIL = "hard_fail"  # 必須修正，無法繼續
    SOFT_WARN = "soft_warn"  # 警告，可繼續但建議處理
    PASS = "pass"  # 通過


@dataclass
class ValidationResult:
    """驗證結果"""

    severity: ValidationSeverity
    message: str
    details: Optional[dict] = None


def check_dedupe_key_version_allowed(
    transactions: list[Transaction],
) -> ValidationResult:
    """Hard 檢查：版本必須在允許集合內

    Args:
        transactions: 交易列表

    Returns:
        驗證結果
    """
    invalid_versions: list[tuple[str, str]] = []  # (stable_id, version)

    for t in transactions:
        if t.dedupe_key_version not in ALLOWED_DEDUPE_KEY_VERSIONS:
            invalid_versions.append(
                (str(t.stable_id), t.dedupe_key_version)
            )

    if invalid_versions:
        return ValidationResult(
            severity=ValidationSeverity.HARD_FAIL,
            message=f"發現 {len(invalid_versions)} 筆記錄使用未知的 dedupe_key_version",
            details={
                "invalid_records": invalid_versions[:10],  # 只顯示前 10 筆
                "allowed_versions": list(ALLOWED_DEDUPE_KEY_VERSIONS),
            },
        )

    return ValidationResult(
        severity=ValidationSeverity.PASS,
        message="所有 dedupe_key_version 均在允許集合內",
    )


def check_dedupe_key_version_governable(
    transactions: list[Transaction],
) -> ValidationResult:
    """Soft 檢查：檔案內混有多版本則警告

    Args:
        transactions: 交易列表

    Returns:
        驗證結果
    """
    if not transactions:
        return ValidationResult(
            severity=ValidationSeverity.PASS,
            message="無交易記錄",
        )

    versions_in_file = {t.dedupe_key_version for t in transactions}

    if len(versions_in_file) > 1:
        return ValidationResult(
            severity=ValidationSeverity.SOFT_WARN,
            message=f"檔案內混有多個 dedupe_key_version: {versions_in_file}",
            details={
                "versions_found": list(versions_in_file),
                "suggestion": "建議執行 lc migrate --rekey 統一版本",
            },
        )

    return ValidationResult(
        severity=ValidationSeverity.PASS,
        message=f"dedupe_key_version 一致: {list(versions_in_file)[0]}",
    )


def check_no_duplicate_stable_id(
    transactions: list[Transaction],
) -> ValidationResult:
    """Hard 檢查：無重複的 stable_id

    Args:
        transactions: 交易列表

    Returns:
        驗證結果
    """
    seen_ids: dict[str, int] = {}
    duplicates: list[str] = []

    for t in transactions:
        id_str = str(t.stable_id)
        if id_str in seen_ids:
            duplicates.append(id_str)
        else:
            seen_ids[id_str] = 1

    if duplicates:
        return ValidationResult(
            severity=ValidationSeverity.HARD_FAIL,
            message=f"發現 {len(duplicates)} 個重複的 stable_id",
            details={
                "duplicate_ids": duplicates[:10],  # 只顯示前 10 個
            },
        )

    return ValidationResult(
        severity=ValidationSeverity.PASS,
        message="無重複的 stable_id",
    )


def check_stable_id_version_consistency(
    transactions: list[Transaction],
) -> ValidationResult:
    """Hard 檢查：同一 stable_id 不可混版本

    檢查同一 stable_id 是否有不同的 dedupe_key_version。
    正常情況下不應發生（stable_id 唯一），但作為護欄檢查。

    Args:
        transactions: 交易列表

    Returns:
        驗證結果
    """
    id_versions: dict[str, set[str]] = {}

    for t in transactions:
        id_str = str(t.stable_id)
        if id_str not in id_versions:
            id_versions[id_str] = set()
        id_versions[id_str].add(t.dedupe_key_version)

    # 檢查是否有同一 ID 混版本
    inconsistent = [
        (id_str, versions)
        for id_str, versions in id_versions.items()
        if len(versions) > 1
    ]

    if inconsistent:
        return ValidationResult(
            severity=ValidationSeverity.HARD_FAIL,
            message=f"發現 {len(inconsistent)} 個 stable_id 混用多個版本",
            details={
                "inconsistent_records": [
                    {"stable_id": id_str, "versions": list(versions)}
                    for id_str, versions in inconsistent[:5]
                ],
            },
        )

    return ValidationResult(
        severity=ValidationSeverity.PASS,
        message="stable_id 版本一致",
    )


def validate_dedupe_governance(
    transactions: list[Transaction],
) -> list[ValidationResult]:
    """執行完整的 dedupe 治理驗證

    Args:
        transactions: 交易列表

    Returns:
        所有驗證結果列表
    """
    results: list[ValidationResult] = []

    # Hard checks
    results.append(check_dedupe_key_version_allowed(transactions))
    results.append(check_no_duplicate_stable_id(transactions))
    results.append(check_stable_id_version_consistency(transactions))

    # Soft checks
    results.append(check_dedupe_key_version_governable(transactions))

    return results


def has_hard_failures(results: list[ValidationResult]) -> bool:
    """檢查是否有 hard failure

    Args:
        results: 驗證結果列表

    Returns:
        是否有 hard failure
    """
    return any(r.severity == ValidationSeverity.HARD_FAIL for r in results)


def get_failure_messages(results: list[ValidationResult]) -> list[str]:
    """取得所有失敗訊息

    Args:
        results: 驗證結果列表

    Returns:
        失敗訊息列表（hard fail 優先）
    """
    messages: list[str] = []

    # Hard failures 優先
    for r in results:
        if r.severity == ValidationSeverity.HARD_FAIL:
            messages.append(f"[HARD] {r.message}")

    # Soft warnings
    for r in results:
        if r.severity == ValidationSeverity.SOFT_WARN:
            messages.append(f"[WARN] {r.message}")

    return messages
