"""業務規則驗證

提供跨欄位、跨檔案的驗證邏輯。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from life_capital.io.csv_handler import CSVParseError, load_csv
from life_capital.models.policy import ExpensePolicy, UncategorizedHandling


@dataclass(frozen=True)
class BusinessRuleResult:
    errors: list[str]
    warnings: list[str]


def validate_expense_categories(
    *,
    expense_files: list[Path],
    policy: ExpensePolicy,
    dedupe: str = "exact",
) -> BusinessRuleResult:
    """跨檔案驗證：CSV category 必須存在於 expense_policy.yaml。

    Args:
        expense_files: expenses_YYYY_MM.csv 檔案列表
        policy: ExpensePolicy
        dedupe: 去重模式（預設 exact）
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not expense_files:
        return BusinessRuleResult(errors=errors, warnings=warnings)

    allowed = policy.get_all_categories()
    if not allowed:
        return BusinessRuleResult(errors=errors, warnings=warnings)

    unknown: dict[str, set[str]] = {}
    total_duplicates = 0

    for path in expense_files:
        try:
            records, duplicates = load_csv(path, dedupe=dedupe)  # type: ignore[arg-type]
            total_duplicates += duplicates
        except (FileNotFoundError, CSVParseError) as e:
            errors.append(str(e))
            continue

        for record in records:
            if record.category in allowed:
                continue
            unknown.setdefault(record.category, set()).add(path.name)

    if total_duplicates > 0:
        warnings.append(f"CSV 去重：共忽略 {total_duplicates} 筆重複記錄")

    if unknown:
        msg_lines = ["發現未在 expense_policy.yaml 定義的 category："]
        for category in sorted(unknown.keys()):
            files = ", ".join(sorted(unknown[category]))
            msg_lines.append(f"- {category}（出現在 {files}）")
        msg = "\n".join(msg_lines)

        if policy.uncategorized_handling == UncategorizedHandling.ERROR:
            errors.append(msg)
        elif policy.uncategorized_handling == UncategorizedHandling.WARN:
            warnings.append(msg)

    return BusinessRuleResult(errors=errors, warnings=warnings)

