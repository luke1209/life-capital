"""去重策略模組 (Phase 1)

實作雙窗口去重策略：
- occurred_at: ±1 天
- posted_at: ±7 天（跨月緩衝）

去重結果：
- AUTO_MERGE: 相似度 ≥95%，自動合併
- MANUAL_REVIEW: 相似度 70%-95% 或退款，需人工裁決
- KEEP_BOTH: 相似度 <70%，保留兩筆
"""

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Optional

from life_capital.io.registry import (
    AUTO_MERGE_THRESHOLD,
    MANUAL_REVIEW_THRESHOLD,
    WINDOW_OCCURRED_DAYS,
    WINDOW_POSTED_DAYS,
)
from life_capital.models.transaction import Transaction


class DedupeResult(str, Enum):
    """去重判定結果 - 各模組共用此介面"""

    AUTO_MERGE = "auto_merge"  # 自動合併（相似度 ≥95%）
    MANUAL_REVIEW = "manual_review"  # 需人工裁決（70-95% 或退款）
    KEEP_BOTH = "keep_both"  # 保留兩筆（相似但不可信）


@dataclass
class DedupeCandidate:
    """去重候選項"""

    transaction: Transaction
    similarity: float
    match_reason: str  # 匹配原因說明


@dataclass
class DedupeDecision:
    """去重決策結果"""

    result: DedupeResult
    record: Transaction
    candidates: list[DedupeCandidate]
    recommendation: Optional[str] = None  # 建議說明


def is_within_window(
    date1: date,
    date2: date,
    window_days: int,
) -> bool:
    """檢查兩個日期是否在指定窗口內

    Args:
        date1: 第一個日期
        date2: 第二個日期
        window_days: 窗口天數

    Returns:
        是否在窗口內
    """
    diff = abs((date1 - date2).days)
    return diff <= window_days


def find_candidates(
    record: Transaction,
    existing: list[Transaction],
    use_posted_at: bool = False,
) -> list[Transaction]:
    """在窗口內找出候選重複項

    使用雙窗口策略：
    - occurred_at: ±WINDOW_OCCURRED_DAYS 天（預設 1 天）
    - posted_at: ±WINDOW_POSTED_DAYS 天（預設 7 天，跨月緩衝）

    Args:
        record: 要檢查的記錄
        existing: 現有記錄列表
        use_posted_at: 是否使用 posted_at 窗口（較寬鬆）

    Returns:
        候選重複項列表
    """
    candidates: list[Transaction] = []

    for t in existing:
        # 跳過自己
        if t.stable_id == record.stable_id:
            continue

        # 使用 occurred_at 窗口
        if is_within_window(
            record.occurred_at, t.occurred_at, WINDOW_OCCURRED_DAYS
        ):
            candidates.append(t)
            continue

        # 若啟用 posted_at 窗口且雙方都有 posted_at
        if use_posted_at and record.posted_at and t.posted_at:
            if is_within_window(
                record.posted_at, t.posted_at, WINDOW_POSTED_DAYS
            ):
                candidates.append(t)

    return candidates


def compute_similarity(a: Transaction, b: Transaction) -> float:
    """計算兩筆交易的相似度 (0.0-1.0)

    評分權重：
    - 金額完全相同: +40%
    - 類別相同: +25%
    - 支付者相同: +15%
    - 商家相同（若有）: +20%

    Args:
        a: 第一筆交易
        b: 第二筆交易

    Returns:
        相似度分數 (0.0-1.0)
    """
    score = 0.0

    # 金額完全相同: +40%
    if a.amount == b.amount:
        score += 0.4

    # 類別相同: +25%
    if a.category.lower() == b.category.lower():
        score += 0.25

    # 支付者相同: +15%
    if a.payer == b.payer:
        score += 0.15

    # 商家相同（若有）: +20%
    if a.merchant and b.merchant:
        if a.merchant.lower() == b.merchant.lower():
            score += 0.2
    elif not a.merchant and not b.merchant:
        score += 0.1  # 都沒有商家，部分分數

    return score


def is_potential_reversal(a: Transaction, b: Transaction) -> bool:
    """檢查是否為潛在的退款/沖正配對

    特徵：
    - 一正一負
    - 金額絕對值相同
    - 類別相同

    Args:
        a: 第一筆交易
        b: 第二筆交易

    Returns:
        是否為潛在沖正配對
    """
    # 一正一負
    if not ((a.amount > 0 and b.amount < 0) or (a.amount < 0 and b.amount > 0)):
        return False

    # 金額絕對值相同
    if abs(a.amount) != abs(b.amount):
        return False

    # 類別相同
    if a.category.lower() != b.category.lower():
        return False

    return True


def resolve(
    record: Transaction,
    candidates: list[Transaction],
) -> DedupeDecision:
    """判定去重結果

    決策邏輯：
    1. 無候選項 → KEEP_BOTH（新記錄）
    2. 高相似度 (≥95%) → AUTO_MERGE
    3. 潛在沖正 → MANUAL_REVIEW（不自動配對）
    4. 中相似度 (70-95%) → MANUAL_REVIEW
    5. 低相似度 (<70%) → KEEP_BOTH

    Args:
        record: 要處理的記錄
        candidates: 候選重複項列表

    Returns:
        去重決策結果
    """
    if not candidates:
        return DedupeDecision(
            result=DedupeResult.KEEP_BOTH,
            record=record,
            candidates=[],
            recommendation="新記錄，無重複項",
        )

    scored_candidates: list[DedupeCandidate] = []
    reversal_detected = False

    for c in candidates:
        similarity = compute_similarity(record, c)

        # 檢查是否為潛在沖正
        if is_potential_reversal(record, c):
            reversal_detected = True
            scored_candidates.append(
                DedupeCandidate(
                    transaction=c,
                    similarity=similarity,
                    match_reason="潛在退款/沖正配對",
                )
            )
            continue

        if similarity >= MANUAL_REVIEW_THRESHOLD:
            reason = "金額+類別相同" if similarity >= AUTO_MERGE_THRESHOLD else "部分欄位相同"
            scored_candidates.append(
                DedupeCandidate(
                    transaction=c,
                    similarity=similarity,
                    match_reason=reason,
                )
            )

    # 沒有達到閾值的候選項
    if not scored_candidates:
        return DedupeDecision(
            result=DedupeResult.KEEP_BOTH,
            record=record,
            candidates=[],
            recommendation="無高相似度候選項",
        )

    # 排序：相似度高的優先
    scored_candidates.sort(key=lambda x: x.similarity, reverse=True)

    # 有潛在沖正 → 強制 MANUAL_REVIEW
    if reversal_detected:
        return DedupeDecision(
            result=DedupeResult.MANUAL_REVIEW,
            record=record,
            candidates=scored_candidates,
            recommendation="偵測到潛在退款/沖正，需人工確認",
        )

    # 最高相似度
    top_similarity = scored_candidates[0].similarity

    # 高相似度 → AUTO_MERGE
    if top_similarity >= AUTO_MERGE_THRESHOLD:
        return DedupeDecision(
            result=DedupeResult.AUTO_MERGE,
            record=record,
            candidates=scored_candidates,
            recommendation=(
                f"相似度 {top_similarity:.0%} ≥ {AUTO_MERGE_THRESHOLD:.0%}，建議自動合併"
            ),
        )

    # 中相似度 → MANUAL_REVIEW
    if top_similarity >= MANUAL_REVIEW_THRESHOLD:
        return DedupeDecision(
            result=DedupeResult.MANUAL_REVIEW,
            record=record,
            candidates=scored_candidates,
            recommendation=f"相似度 {top_similarity:.0%}，建議人工確認",
        )

    # 低相似度 → KEEP_BOTH
    return DedupeDecision(
        result=DedupeResult.KEEP_BOTH,
        record=record,
        candidates=scored_candidates,
        recommendation="相似度不足，保留兩筆",
    )


def batch_dedupe(
    new_records: list[Transaction],
    existing_records: list[Transaction],
    use_posted_at: bool = False,
) -> list[DedupeDecision]:
    """批次去重處理

    對一組新記錄進行去重判定。

    Args:
        new_records: 新記錄列表
        existing_records: 現有記錄列表
        use_posted_at: 是否使用 posted_at 窗口

    Returns:
        去重決策列表
    """
    decisions: list[DedupeDecision] = []

    for record in new_records:
        candidates = find_candidates(record, existing_records, use_posted_at)
        decision = resolve(record, candidates)
        decisions.append(decision)

    return decisions


def summarize_dedupe_results(decisions: list[DedupeDecision]) -> dict[str, int]:
    """統計去重結果

    Args:
        decisions: 去重決策列表

    Returns:
        各類型結果數量統計
    """
    summary = {
        DedupeResult.AUTO_MERGE.value: 0,
        DedupeResult.MANUAL_REVIEW.value: 0,
        DedupeResult.KEEP_BOTH.value: 0,
    }

    for decision in decisions:
        summary[decision.result.value] += 1

    return summary
