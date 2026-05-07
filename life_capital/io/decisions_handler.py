"""決策記憶 Handler

Phase 5 決策記憶的讀寫處理器。

設計原則:
- 只被 `lc apply/undo` 調用（不可獨立使用）
- append-only 語意（回滾以新記錄標記，不修改既有記錄）
- 與 canonical_handler 整合（透過 operation_id 追蹤）

使用方式:
    # 讀取決策記錄（供 history 命令使用）
    handler = DecisionsHandler(data_path)
    records = handler.read_all()

    # 寫入決策記錄（只能透過 lc apply 調用）
    handler.write_decision(record, operation)

版本歷程:
- V1.0 (2025-12-29): 初版
- V1.1 (2025-12-29): 新增 decision_rationale、reverted_from_decision_id、ID 重複檢查、狀態轉換驗證
"""

from datetime import datetime
from pathlib import Path
from typing import List, Optional

import yaml

from life_capital.io.registry import (
    CANONICAL_DECISIONS_DIR,
    DECISIONS_FILE,
    DECISIONS_SCHEMA_VERSION,
)
from life_capital.models.decisions import (
    AssumptionSnapshot,
    ConfidenceLevel,
    DecisionMemory,
    DecisionOption,
    DecisionRecord,
    DecisionStatus,
    PreferenceWeights,
    generate_decision_id,
)
from life_capital.models.operation import Operation


class DecisionsHandlerError(Exception):
    """決策處理器錯誤"""
    pass


class DecisionNotFoundError(DecisionsHandlerError):
    """決策記錄不存在"""

    def __init__(self, decision_id: str):
        super().__init__(f"決策記錄不存在: {decision_id}")
        self.decision_id = decision_id


class InvalidOperationError(DecisionsHandlerError):
    """無效操作錯誤"""
    pass


class DuplicateDecisionError(DecisionsHandlerError):
    """決策 ID 重複錯誤（V1.1 新增）"""
    pass


class InvalidTransitionError(DecisionsHandlerError):
    """非法狀態轉換錯誤（V1.1 新增）"""
    pass


class DecisionsHandler:
    """決策記憶處理器

    提供決策記錄的讀寫操作，遵循 append-only 語意。

    使用方式:
        handler = DecisionsHandler(data_path)

        # 讀取
        records = handler.read_all()
        record = handler.get_by_decision_id("dec_xxx")

        # 寫入（只能透過 apply 命令調用）
        handler.write_decision(record, operation)

        # 回滾（建立新的 reverted 記錄）
        handler.mark_reverted(decision_id, operation)
    """

    def __init__(self, data_path: Path):
        """初始化處理器

        Args:
            data_path: 資料根目錄路徑
        """
        self.data_path = data_path
        self.decisions_dir = data_path / CANONICAL_DECISIONS_DIR
        self.decisions_file = self.decisions_dir / DECISIONS_FILE

    def _ensure_dir(self) -> None:
        """確保決策目錄存在"""
        self.decisions_dir.mkdir(parents=True, exist_ok=True)

    def _load_memory(self) -> DecisionMemory:
        """載入決策記憶庫

        Returns:
            DecisionMemory 實例（若檔案不存在則返回空記憶庫）
        """
        if not self.decisions_file.exists():
            return DecisionMemory()

        try:
            with open(self.decisions_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if data is None:
                return DecisionMemory()

            # 解析記錄
            records = []
            for rec_data in data.get("records", []):
                record = self._parse_record(rec_data)
                records.append(record)

            return DecisionMemory(
                records=records,
                version=data.get("version", DECISIONS_SCHEMA_VERSION),
                last_updated=data.get("last_updated", datetime.now().isoformat()),
            )

        except Exception as e:
            raise DecisionsHandlerError(f"載入決策記憶庫失敗: {e}")

    def _parse_record(self, data: dict) -> DecisionRecord:
        """解析單筆決策記錄

        Args:
            data: 原始字典資料

        Returns:
            DecisionRecord 實例
        """
        # 解析選項
        option_a_data = data.get("option_a", {})
        option_b_data = data.get("option_b", {})

        option_a = DecisionOption(
            direction=option_a_data.get("direction", "conservative"),
            label=option_a_data.get("label", ""),
            recommendation=option_a_data.get("recommendation"),
            score=option_a_data.get("score"),
            status=option_a_data.get("status", "comparable"),
            to_comparable_guidance=option_a_data.get("to_comparable_guidance"),
        )

        option_b = DecisionOption(
            direction=option_b_data.get("direction", "aggressive"),
            label=option_b_data.get("label", ""),
            recommendation=option_b_data.get("recommendation"),
            score=option_b_data.get("score"),
            status=option_b_data.get("status", "comparable"),
            to_comparable_guidance=option_b_data.get("to_comparable_guidance"),
        )

        # 解析假設快照
        snapshot_data = data.get("assumption_snapshot")
        assumption_snapshot = None
        if snapshot_data:
            assumption_snapshot = AssumptionSnapshot(
                snapshot_version=snapshot_data.get("snapshot_version", "1.0"),
                created_at=snapshot_data.get("created_at", ""),
                inflation_rate=snapshot_data.get("inflation_rate"),
                investment_return=snapshot_data.get("investment_return"),
                income_growth=snapshot_data.get("income_growth"),
                expense_growth=snapshot_data.get("expense_growth"),
                custom_assumptions=snapshot_data.get("custom_assumptions", {}),
            )

        # 解析權重
        weights_data = data.get("preference_weights")
        preference_weights = None
        if weights_data:
            preference_weights = PreferenceWeights(
                liquidity=weights_data.get("liquidity", 0.25),
                growth=weights_data.get("growth", 0.25),
                safety=weights_data.get("safety", 0.25),
                flexibility=weights_data.get("flexibility", 0.25),
            )

        # 解析狀態
        status_str = data.get("status", "pending")
        try:
            status = DecisionStatus(status_str)
        except ValueError:
            status = DecisionStatus.PENDING

        # 解析信心度
        confidence_str = data.get("confidence", "medium")
        try:
            confidence = ConfidenceLevel(confidence_str)
        except ValueError:
            confidence = ConfidenceLevel.MEDIUM

        # V1.1 欄位解析（兼容 V1.0）
        decision_rationale = data.get("decision_rationale")
        reverted_from_decision_id = data.get("reverted_from_decision_id")

        return DecisionRecord(
            decision_id=data.get("decision_id", ""),
            operation_id=data.get("operation_id", ""),
            created_at=data.get("created_at", ""),
            template_id=data.get("template_id", "default"),
            status=status,
            confidence=confidence,
            comparability_score=data.get("comparability_score", 0.0),
            input_hash=data.get("input_hash", ""),
            option_a=option_a,
            option_b=option_b,
            risk_tags=data.get("risk_tags", []),
            risk_explanation=data.get("risk_explanation", ""),
            blocking_reasons=data.get("blocking_reasons", []),
            assumption_snapshot=assumption_snapshot,
            preference_weights=preference_weights,
            reverted_at=data.get("reverted_at"),
            reverted_by=data.get("reverted_by"),
            schema_version=data.get("schema_version", DECISIONS_SCHEMA_VERSION),
            # V1.1 欄位（向後相容）
            decision_rationale=decision_rationale,
            reverted_from_decision_id=reverted_from_decision_id,
        )

    def _save_memory(self, memory: DecisionMemory) -> None:
        """儲存決策記憶庫

        Args:
            memory: DecisionMemory 實例
        """
        self._ensure_dir()

        # 轉換為可序列化格式
        data = {
            "version": memory.version,
            "last_updated": memory.last_updated,
            "records": [self._record_to_dict(r) for r in memory.records],
        }

        try:
            with open(self.decisions_file, "w", encoding="utf-8") as f:
                yaml.dump(
                    data,
                    f,
                    default_flow_style=False,
                    allow_unicode=True,
                    sort_keys=False,
                )
        except Exception as e:
            raise DecisionsHandlerError(f"儲存決策記憶庫失敗: {e}")

    def _record_to_dict(self, record: DecisionRecord) -> dict:
        """將決策記錄轉換為字典

        Args:
            record: DecisionRecord 實例

        Returns:
            可序列化的字典
        """
        result = {
            "decision_id": record.decision_id,
            "operation_id": record.operation_id,
            "created_at": record.created_at,
            "template_id": record.template_id,
            "status": record.status.value,
            "confidence": record.confidence.value,
            "comparability_score": record.comparability_score,
            "input_hash": record.input_hash,
            "option_a": {
                "direction": record.option_a.direction,
                "label": record.option_a.label,
                "recommendation": record.option_a.recommendation,
                "score": record.option_a.score,
                "status": record.option_a.status,
                "to_comparable_guidance": record.option_a.to_comparable_guidance,
            },
            "option_b": {
                "direction": record.option_b.direction,
                "label": record.option_b.label,
                "recommendation": record.option_b.recommendation,
                "score": record.option_b.score,
                "status": record.option_b.status,
                "to_comparable_guidance": record.option_b.to_comparable_guidance,
            },
            "risk_tags": list(record.risk_tags),
            "risk_explanation": record.risk_explanation,
            "blocking_reasons": list(record.blocking_reasons),
            "schema_version": record.schema_version,
        }

        # 可選欄位
        if record.assumption_snapshot:
            result["assumption_snapshot"] = {
                "snapshot_version": record.assumption_snapshot.snapshot_version,
                "created_at": record.assumption_snapshot.created_at,
                "inflation_rate": record.assumption_snapshot.inflation_rate,
                "investment_return": record.assumption_snapshot.investment_return,
                "income_growth": record.assumption_snapshot.income_growth,
                "expense_growth": record.assumption_snapshot.expense_growth,
                "custom_assumptions": dict(record.assumption_snapshot.custom_assumptions),
            }

        if record.preference_weights:
            result["preference_weights"] = {
                "liquidity": record.preference_weights.liquidity,
                "growth": record.preference_weights.growth,
                "safety": record.preference_weights.safety,
                "flexibility": record.preference_weights.flexibility,
            }

        if record.reverted_at:
            result["reverted_at"] = record.reverted_at
        if record.reverted_by:
            result["reverted_by"] = record.reverted_by

        # V1.1 可選欄位（僅在非 None 時寫入）
        if record.decision_rationale:
            result["decision_rationale"] = record.decision_rationale
        if record.reverted_from_decision_id:
            result["reverted_from_decision_id"] = record.reverted_from_decision_id

        return result

    def _check_duplicate_decision_id(self, decision_id: str) -> None:
        """檢查 decision_id 是否已存在（V1.1 新增）

        Raises:
            DuplicateDecisionError: decision_id 已存在
        """
        existing = self.get_by_decision_id(decision_id)
        if existing:
            raise DuplicateDecisionError(
                f"Decision ID 已存在: {decision_id}"
            )

    def _validate_transition(
        self,
        from_status: Optional[DecisionStatus],
        to_status: DecisionStatus
    ) -> None:
        """驗證狀態轉換是否合法（V1.1 新增）

        合法轉換:
        - None → PENDING (首次建立)
        - PENDING → APPLIED
        - APPLIED → REVERTED
        - PENDING → REVERTED (取消待確認)

        非法轉換:
        - REVERTED → * (回滾後不可再變更)
        - EXPIRED → * (過期後不可再變更)
        - APPLIED → PENDING (已套用不可退回待確認)

        Raises:
            InvalidTransitionError: 非法狀態轉換
        """
        ALLOWED_TRANSITIONS = {
            (None, DecisionStatus.PENDING),
            (DecisionStatus.PENDING, DecisionStatus.APPLIED),
            (DecisionStatus.APPLIED, DecisionStatus.REVERTED),
            (DecisionStatus.PENDING, DecisionStatus.REVERTED),
        }

        if (from_status, to_status) not in ALLOWED_TRANSITIONS:
            raise InvalidTransitionError(
                f"非法狀態轉換: {from_status} → {to_status}"
            )

    # === 公開 API ===

    def read_all(self) -> List[DecisionRecord]:
        """讀取所有決策記錄

        Returns:
            決策記錄列表（時間順序）
        """
        memory = self._load_memory()
        return memory.records

    def get_by_decision_id(self, decision_id: str) -> Optional[DecisionRecord]:
        """根據決策 ID 查詢記錄

        Args:
            decision_id: 決策 ID（格式: dec_<ULID>）

        Returns:
            DecisionRecord 或 None
        """
        memory = self._load_memory()
        return memory.get_by_decision_id(decision_id)

    def get_by_operation_id(self, operation_id: str) -> Optional[DecisionRecord]:
        """根據操作 ID 查詢記錄

        Args:
            operation_id: 操作 ID（ULID 格式）

        Returns:
            DecisionRecord 或 None
        """
        memory = self._load_memory()
        return memory.get_by_operation_id(operation_id)

    def get_active_records(self) -> List[DecisionRecord]:
        """取得所有有效記錄（非回滾、非過期）

        Returns:
            有效的決策記錄列表
        """
        memory = self._load_memory()
        return memory.get_active_records()

    def get_by_template(self, template_id: str) -> List[DecisionRecord]:
        """根據模板 ID 查詢記錄

        Args:
            template_id: 決策模板 ID

        Returns:
            符合的決策記錄列表
        """
        memory = self._load_memory()
        return memory.get_by_template(template_id)

    def write_decision(
        self,
        record: DecisionRecord,
        operation: Operation,
    ) -> str:
        """寫入決策記錄

        注意：此方法應只被 `lc apply` 調用。

        Args:
            record: 要寫入的決策記錄
            operation: 操作追蹤資訊

        Returns:
            decision_id

        Raises:
            InvalidOperationError: operation_id 為空
            DuplicateDecisionError: decision_id 已存在（V1.1）
            DecisionsHandlerError: 寫入失敗
        """
        if not operation.operation_id:
            raise InvalidOperationError("write_decision() 必須提供 operation_id")

        # V1.1 檢查 ID 重複
        self._check_duplicate_decision_id(record.decision_id)

        memory = self._load_memory()
        memory.add_record(record)
        self._save_memory(memory)

        return record.decision_id

    def mark_reverted(
        self,
        decision_id: str,
        operation: Operation,
    ) -> DecisionRecord:
        """標記決策為已回滾

        建立新的 reverted 記錄，而非修改既有記錄（append-only 語意）。

        Args:
            decision_id: 要回滾的決策 ID
            operation: 執行回滾的操作資訊

        Returns:
            新建立的 reverted 記錄

        Raises:
            DecisionNotFoundError: 找不到決策記錄
            InvalidOperationError: operation_id 為空
        """
        if not operation.operation_id:
            raise InvalidOperationError("mark_reverted() 必須提供 operation_id")

        memory = self._load_memory()
        original = memory.get_by_decision_id(decision_id)

        if original is None:
            raise DecisionNotFoundError(decision_id)

        # 建立新的 reverted 記錄（保留原始資料但標記為回滾）
        reverted_record = DecisionRecord(
            decision_id=generate_decision_id(),  # 新 ID
            operation_id=str(operation.operation_id),
            created_at=datetime.now().isoformat(),
            template_id=original.template_id,
            status=DecisionStatus.REVERTED,
            confidence=original.confidence,
            comparability_score=original.comparability_score,
            input_hash=original.input_hash,
            option_a=original.option_a,
            option_b=original.option_b,
            risk_tags=list(original.risk_tags),
            risk_explanation=original.risk_explanation,
            blocking_reasons=list(original.blocking_reasons),
            assumption_snapshot=original.assumption_snapshot,
            preference_weights=original.preference_weights,
            reverted_at=datetime.now().isoformat(),
            reverted_by=str(operation.operation_id),
            schema_version=original.schema_version,
            # V1.1 新增欄位
            decision_rationale=original.decision_rationale,
            reverted_from_decision_id=original.decision_id,  # 指向原始決策
        )

        memory.add_record(reverted_record)
        self._save_memory(memory)

        return reverted_record

    def get_latest_by_template(self, template_id: str) -> Optional[DecisionRecord]:
        """取得指定模板的最新有效決策

        Args:
            template_id: 決策模板 ID

        Returns:
            最新的有效決策記錄，或 None
        """
        records = self.get_by_template(template_id)
        active_records = [
            r for r in records
            if r.status in (DecisionStatus.PENDING, DecisionStatus.APPLIED)
        ]

        if not active_records:
            return None

        # 按建立時間排序，取最新
        return max(active_records, key=lambda r: r.created_at)

    def count_by_status(self) -> dict:
        """統計各狀態的決策數量

        Returns:
            狀態計數字典，如 {"pending": 1, "applied": 5, "reverted": 2}
        """
        records = self.read_all()
        counts = {status.value: 0 for status in DecisionStatus}

        for record in records:
            counts[record.status.value] += 1

        return counts


# === 便捷函式 ===

def read_decisions(data_path: Path) -> List[DecisionRecord]:
    """便捷函式：讀取所有決策記錄

    Args:
        data_path: 資料根目錄路徑

    Returns:
        決策記錄列表
    """
    handler = DecisionsHandler(data_path)
    return handler.read_all()


def get_decision(data_path: Path, decision_id: str) -> Optional[DecisionRecord]:
    """便捷函式：根據 ID 取得決策記錄

    Args:
        data_path: 資料根目錄路徑
        decision_id: 決策 ID

    Returns:
        DecisionRecord 或 None
    """
    handler = DecisionsHandler(data_path)
    return handler.get_by_decision_id(decision_id)
