"""操作追蹤與來源追溯資料模型

提供 Operation（變更追蹤）與 Provenance（來源追溯）模型，
用於實作完整的資料血統追蹤系統。
"""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class OperationType(str, Enum):
    """操作類型列舉"""

    # === 基本操作 ===
    IMPORT = "import"  # 匯入資料（如 CSV 匯入）
    APPLY = "apply"  # 套用變更
    UNDO = "undo"  # 復原操作
    REBUILD = "rebuild"  # 重建索引或快取

    # === Phase 1: 去重與遷移操作 ===
    DEDUPE_MERGE = "dedupe_merge"  # 去重合併操作
    DEDUPE_REVERSAL = "dedupe_reversal"  # 退款/沖正標記
    MIGRATE = "migrate"  # Schema 遷移操作


class SourceType(str, Enum):
    """資料來源類型列舉"""

    CSV_IMPORT = "csv_import"  # CSV 檔案匯入
    MANUAL_ENTRY = "manual_entry"  # 手動輸入
    MIGRATION = "migration"  # 資料遷移
    AI_GENERATED = "ai_generated"  # AI 生成


class Provenance(BaseModel):
    """變更來源追溯模型

    記錄資料的起源資訊，用於追溯資料的完整生命週期。

    Attributes:
        source_id: 來源唯一識別碼（UUID）
        source_type: 資料來源類型
        import_time: 匯入或建立時間
        parser_version: 解析器版本（用於 CSV 匯入等場景）
        prompt_hash: AI 生成時的 prompt hash（可選）
        model_version: AI 模型版本（可選）
        source_hash: 原始檔案的 SHA-256 hash（用於重複匯入偵測，Phase 1.5）
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        json_encoders={datetime: lambda v: v.isoformat()},
    )

    source_id: UUID = Field(default_factory=uuid4)
    source_type: SourceType
    import_time: datetime = Field(default_factory=datetime.now)
    parser_version: str
    prompt_hash: Optional[str] = None
    model_version: Optional[str] = None
    source_hash: Optional[str] = Field(
        default=None,
        description="原始檔案的 SHA-256 hash（用於重複匯入偵測）",
    )


class Operation(BaseModel):
    """操作追蹤模型

    記錄每次資料變更操作的完整資訊，支援回滾功能。

    Attributes:
        operation_id: 操作唯一識別碼（UUID）
        created_at: 操作建立時間
        actor: 執行者識別碼（user identifier）
        operation_type: 操作類型
        target_path: 目標檔案或目錄路徑
        description: 操作描述
        metadata: 彈性擴展欄位（如受影響的記錄數、檔案大小等）
        rollback_data: 回滾資料（可選，用於 undo 操作）
    """

    model_config = ConfigDict(
        extra="allow",  # 允許額外欄位以支援未來擴展
        validate_assignment=True,
        json_encoders={
            datetime: lambda v: v.isoformat(),
            Path: lambda v: str(v),
        },
    )

    operation_id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=datetime.now)
    actor: str
    operation_type: OperationType
    target_path: Path
    description: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    rollback_data: Optional[dict[str, Any]] = None


class OperationLogEntry(BaseModel):
    """操作日誌條目模型

    組合 Operation 與 Provenance 的完整日誌條目，
    可序列化為 JSONL 格式進行持久化儲存。

    Attributes:
        operation: 操作追蹤資訊
        provenance: 來源追溯資訊（可選）
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        json_encoders={
            datetime: lambda v: v.isoformat(),
            Path: lambda v: str(v),
            UUID: lambda v: str(v),
        },
    )

    operation: Operation
    provenance: Optional[Provenance] = None

    def to_jsonl(self) -> str:
        """序列化為 JSONL 格式單行

        Returns:
            JSON 字串（不含換行符）
        """
        return self.model_dump_json(exclude_none=True)

    @classmethod
    def from_jsonl(cls, line: str) -> "OperationLogEntry":
        """從 JSONL 格式反序列化

        Args:
            line: JSON 字串（單行）

        Returns:
            OperationLogEntry 實例

        Raises:
            ValueError: JSON 格式不正確或驗證失敗
        """
        return cls.model_validate_json(line)

    def to_dict(self) -> dict[str, Any]:
        """轉換為字典格式（用於儲存或序列化）

        Returns:
            包含所有欄位的字典
        """
        return self.model_dump(mode="json", exclude_none=True)
