"""decisions_handler 測試

驗證決策記憶 handler 的功能：
- 讀取/寫入決策記錄
- append-only 語意
- 回滾標記
- 查詢功能
"""

from datetime import datetime
from uuid import uuid4

import pytest

from life_capital.io.decisions_handler import (
    DecisionNotFoundError,
    DecisionsHandler,
    InvalidOperationError,
    get_decision,
    read_decisions,
)
from life_capital.models.decisions import (
    AssumptionSnapshot,
    ConfidenceLevel,
    DecisionOption,
    DecisionRecord,
    DecisionStatus,
    PreferenceWeights,
    generate_decision_id,
)
from life_capital.models.operation import Operation, OperationType


def make_operation(
    operation_type: OperationType = OperationType.APPLY,
    description: str = "測試操作",
) -> Operation:
    """建立測試用 Operation"""
    return Operation(
        operation_id=uuid4(),
        operation_type=operation_type,
        actor="test",
        target_path="canonical/decisions/decisions.yaml",
        description=description,
        created_at=datetime.now(),
    )


@pytest.fixture
def data_path(tmp_path):
    """建立臨時資料目錄"""
    return tmp_path


@pytest.fixture
def handler(data_path):
    """建立 handler 實例"""
    return DecisionsHandler(data_path)


@pytest.fixture
def sample_operation():
    """建立範例操作"""
    return make_operation()


@pytest.fixture
def sample_record():
    """建立範例決策記錄"""
    return DecisionRecord(
        decision_id=generate_decision_id(),
        operation_id=str(uuid4()),
        created_at=datetime.now().isoformat(),
        template_id="buying_house",
        status=DecisionStatus.APPLIED,
        confidence=ConfidenceLevel.HIGH,
        comparability_score=0.85,
        input_hash="abc123",
        option_a=DecisionOption(
            direction="conservative",
            label="方案 A：延後購房",
            recommendation="建議延後 6 個月累積更多資金",
            score=0.7,
            status="comparable",
        ),
        option_b=DecisionOption(
            direction="aggressive",
            label="方案 B：立即購房",
            recommendation="可立即開始看房，但需注意現金流",
            score=0.6,
            status="comparable",
        ),
        risk_tags=["現金流壓力"],
        risk_explanation="目前儲蓄率偏低，購房後可能面臨現金流壓力",
    )


class TestDecisionsHandlerBasic:
    """基本功能測試"""

    def test_read_empty(self, handler):
        """讀取空記憶庫"""
        records = handler.read_all()
        assert records == []

    def test_write_and_read(self, handler, sample_record, sample_operation):
        """寫入並讀取決策記錄"""
        decision_id = handler.write_decision(sample_record, sample_operation)

        assert decision_id == sample_record.decision_id

        records = handler.read_all()
        assert len(records) == 1
        assert records[0].decision_id == sample_record.decision_id
        assert records[0].template_id == "buying_house"

    def test_write_without_operation_id_raises(self, handler, sample_record):
        """寫入時未提供 operation_id 應拋出錯誤"""
        # 直接建立無效 operation（跳過 make_operation 的預設值）
        with pytest.raises(InvalidOperationError):
            # 模擬 operation_id 為 None 的情況
            class MockOperation:
                operation_id = None

            handler.write_decision(sample_record, MockOperation())


class TestDecisionsHandlerQuery:
    """查詢功能測試"""

    def test_get_by_decision_id(self, handler, sample_record, sample_operation):
        """根據決策 ID 查詢"""
        handler.write_decision(sample_record, sample_operation)

        found = handler.get_by_decision_id(sample_record.decision_id)
        assert found is not None
        assert found.decision_id == sample_record.decision_id

    def test_get_by_decision_id_not_found(self, handler):
        """查詢不存在的決策 ID"""
        found = handler.get_by_decision_id("dec_nonexistent")
        assert found is None

    def test_get_by_operation_id(self, handler, sample_record, sample_operation):
        """根據操作 ID 查詢"""
        handler.write_decision(sample_record, sample_operation)

        found = handler.get_by_operation_id(sample_record.operation_id)
        assert found is not None
        assert found.operation_id == sample_record.operation_id

    def test_get_by_template(self, handler, sample_operation):
        """根據模板 ID 查詢"""
        # 建立多個不同模板的記錄
        record1 = DecisionRecord(
            decision_id=generate_decision_id(),
            operation_id=str(uuid4()),
            created_at=datetime.now().isoformat(),
            template_id="buying_house",
            status=DecisionStatus.APPLIED,
            confidence=ConfidenceLevel.HIGH,
            comparability_score=0.8,
            input_hash="hash1",
            option_a=DecisionOption(direction="conservative", label="A"),
            option_b=DecisionOption(direction="aggressive", label="B"),
            risk_tags=[],
            risk_explanation="",
        )

        record2 = DecisionRecord(
            decision_id=generate_decision_id(),
            operation_id=str(uuid4()),
            created_at=datetime.now().isoformat(),
            template_id="investment",
            status=DecisionStatus.APPLIED,
            confidence=ConfidenceLevel.MEDIUM,
            comparability_score=0.7,
            input_hash="hash2",
            option_a=DecisionOption(direction="conservative", label="A"),
            option_b=DecisionOption(direction="aggressive", label="B"),
            risk_tags=[],
            risk_explanation="",
        )

        handler.write_decision(record1, sample_operation)
        handler.write_decision(record2, make_operation())

        # 查詢
        buying_house_records = handler.get_by_template("buying_house")
        assert len(buying_house_records) == 1
        assert buying_house_records[0].template_id == "buying_house"

        investment_records = handler.get_by_template("investment")
        assert len(investment_records) == 1
        assert investment_records[0].template_id == "investment"

    def test_get_active_records(self, handler, sample_operation):
        """取得有效記錄（排除已回滾）"""
        # 建立多個狀態的記錄
        active_record = DecisionRecord(
            decision_id=generate_decision_id(),
            operation_id=str(uuid4()),
            created_at=datetime.now().isoformat(),
            template_id="default",
            status=DecisionStatus.APPLIED,
            confidence=ConfidenceLevel.HIGH,
            comparability_score=0.8,
            input_hash="hash1",
            option_a=DecisionOption(direction="conservative", label="A"),
            option_b=DecisionOption(direction="aggressive", label="B"),
            risk_tags=[],
            risk_explanation="",
        )

        reverted_record = DecisionRecord(
            decision_id=generate_decision_id(),
            operation_id=str(uuid4()),
            created_at=datetime.now().isoformat(),
            template_id="default",
            status=DecisionStatus.REVERTED,
            confidence=ConfidenceLevel.HIGH,
            comparability_score=0.8,
            input_hash="hash2",
            option_a=DecisionOption(direction="conservative", label="A"),
            option_b=DecisionOption(direction="aggressive", label="B"),
            risk_tags=[],
            risk_explanation="",
            reverted_at=datetime.now().isoformat(),
            reverted_by=str(uuid4()),
        )

        handler.write_decision(active_record, sample_operation)
        handler.write_decision(reverted_record, make_operation())

        # 取得有效記錄
        active_records = handler.get_active_records()
        assert len(active_records) == 1
        assert active_records[0].status == DecisionStatus.APPLIED


class TestDecisionsHandlerRevert:
    """回滾功能測試"""

    def test_mark_reverted(self, handler, sample_record, sample_operation):
        """標記決策為已回滾"""
        handler.write_decision(sample_record, sample_operation)

        # 回滾
        revert_operation = make_operation(
            operation_type=OperationType.UNDO,
            description="回滾決策",
        )

        reverted = handler.mark_reverted(
            sample_record.decision_id,
            revert_operation,
        )

        assert reverted.status == DecisionStatus.REVERTED
        assert reverted.reverted_by == str(revert_operation.operation_id)
        assert reverted.reverted_at is not None

        # 確認是 append-only（原記錄仍存在 + 新增 reverted 記錄）
        all_records = handler.read_all()
        assert len(all_records) == 2

    def test_mark_reverted_not_found_raises(self, handler, sample_operation):
        """回滾不存在的決策應拋出錯誤"""
        with pytest.raises(DecisionNotFoundError):
            handler.mark_reverted("dec_nonexistent", sample_operation)

    def test_mark_reverted_without_operation_id_raises(
        self, handler, sample_record, sample_operation
    ):
        """回滾時未提供 operation_id 應拋出錯誤"""
        handler.write_decision(sample_record, sample_operation)

        with pytest.raises(InvalidOperationError):
            class MockOperation:
                operation_id = None

            handler.mark_reverted(sample_record.decision_id, MockOperation())


class TestDecisionsHandlerWithSnapshot:
    """含假設快照的測試"""

    def test_write_with_assumption_snapshot(self, handler, sample_operation):
        """寫入含假設快照的決策記錄"""
        snapshot = AssumptionSnapshot(
            snapshot_version="1.0",
            created_at=datetime.now().isoformat(),
            inflation_rate=0.02,
            investment_return=0.05,
            income_growth=0.03,
            expense_growth=0.02,
            custom_assumptions={"mortgage_rate": 0.04},
        )

        record = DecisionRecord(
            decision_id=generate_decision_id(),
            operation_id=str(uuid4()),
            created_at=datetime.now().isoformat(),
            template_id="buying_house",
            status=DecisionStatus.APPLIED,
            confidence=ConfidenceLevel.HIGH,
            comparability_score=0.9,
            input_hash="hash_with_snapshot",
            option_a=DecisionOption(direction="conservative", label="A"),
            option_b=DecisionOption(direction="aggressive", label="B"),
            risk_tags=[],
            risk_explanation="",
            assumption_snapshot=snapshot,
        )

        handler.write_decision(record, sample_operation)

        # 讀取並驗證
        loaded = handler.get_by_decision_id(record.decision_id)
        assert loaded is not None
        assert loaded.assumption_snapshot is not None
        assert loaded.assumption_snapshot.inflation_rate == 0.02
        assert loaded.assumption_snapshot.custom_assumptions["mortgage_rate"] == 0.04

    def test_write_with_preference_weights(self, handler, sample_operation):
        """寫入含偏好權重的決策記錄"""
        weights = PreferenceWeights(
            liquidity=0.3,
            growth=0.2,
            safety=0.4,
            flexibility=0.1,
        )

        record = DecisionRecord(
            decision_id=generate_decision_id(),
            operation_id=str(uuid4()),
            created_at=datetime.now().isoformat(),
            template_id="investment",
            status=DecisionStatus.APPLIED,
            confidence=ConfidenceLevel.MEDIUM,
            comparability_score=0.75,
            input_hash="hash_with_weights",
            option_a=DecisionOption(direction="conservative", label="A"),
            option_b=DecisionOption(direction="aggressive", label="B"),
            risk_tags=[],
            risk_explanation="",
            preference_weights=weights,
        )

        handler.write_decision(record, sample_operation)

        # 讀取並驗證
        loaded = handler.get_by_decision_id(record.decision_id)
        assert loaded is not None
        assert loaded.preference_weights is not None
        assert loaded.preference_weights.safety == 0.4


class TestDecisionsHandlerStats:
    """統計功能測試"""

    def test_count_by_status(self, handler, sample_operation):
        """統計各狀態的決策數量"""
        # 建立不同狀態的記錄
        for i, status in enumerate(
            [DecisionStatus.PENDING, DecisionStatus.APPLIED, DecisionStatus.APPLIED]
        ):
            op = make_operation()
            record = DecisionRecord(
                decision_id=generate_decision_id(),
                operation_id=str(uuid4()),
                created_at=datetime.now().isoformat(),
                template_id="default",
                status=status,
                confidence=ConfidenceLevel.HIGH,
                comparability_score=0.8,
                input_hash=f"hash_{i}",
                option_a=DecisionOption(direction="conservative", label="A"),
                option_b=DecisionOption(direction="aggressive", label="B"),
                risk_tags=[],
                risk_explanation="",
            )
            handler.write_decision(record, op)

        counts = handler.count_by_status()
        assert counts["pending"] == 1
        assert counts["applied"] == 2
        assert counts["reverted"] == 0

    def test_get_latest_by_template(self, handler, sample_operation):
        """取得指定模板的最新決策"""
        # 建立多個相同模板的記錄（不同時間）
        import time

        for i in range(3):
            op = make_operation()
            record = DecisionRecord(
                decision_id=generate_decision_id(),
                operation_id=str(uuid4()),
                created_at=datetime.now().isoformat(),
                template_id="buying_house",
                status=DecisionStatus.APPLIED,
                confidence=ConfidenceLevel.HIGH,
                comparability_score=0.8,
                input_hash=f"hash_{i}",
                option_a=DecisionOption(direction="conservative", label=f"A_{i}"),
                option_b=DecisionOption(direction="aggressive", label="B"),
                risk_tags=[],
                risk_explanation="",
            )
            handler.write_decision(record, op)
            time.sleep(0.01)  # 確保時間戳不同

        latest = handler.get_latest_by_template("buying_house")
        assert latest is not None
        assert latest.option_a.label == "A_2"  # 最新的


class TestConvenienceFunctions:
    """便捷函式測試"""

    def test_read_decisions(self, data_path, sample_record, sample_operation):
        """測試 read_decisions 便捷函式"""
        handler = DecisionsHandler(data_path)
        handler.write_decision(sample_record, sample_operation)

        records = read_decisions(data_path)
        assert len(records) == 1

    def test_get_decision(self, data_path, sample_record, sample_operation):
        """測試 get_decision 便捷函式"""
        handler = DecisionsHandler(data_path)
        handler.write_decision(sample_record, sample_operation)

        found = get_decision(data_path, sample_record.decision_id)
        assert found is not None
        assert found.decision_id == sample_record.decision_id

        not_found = get_decision(data_path, "dec_nonexistent")
        assert not_found is None
