"""Provenance 資料模型（Stage 3 專用）

Phase 5 Stage 3 衍生物的來源追溯模型，包含決策 Wiki、風險矩陣、敏感度報告。

設計原則:
- 結構化命令: 使用 list[str] 而非字串拼接，防止注入
- 路徑安全: 所有路徑必須經過驗證
- 可重建性: 包含完整的重建指令與環境資訊

版本歷程:
- V1.0 (2025-12-29): 初版（V7 規範）
"""

import shlex
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


@dataclass(frozen=True)
class RebuildCommand:
    """結構化重建命令（非字串拼接）

    使用結構化格式儲存命令，避免 shell injection 風險。

    Attributes:
        cmd: 命令列表（如 ["lc", "advisor", "wiki", "--force"]）
        cwd: 工作目錄（相對於 data_path）
        env: 環境變數（可選，預設空字典）
        schema_version: 命令格式版本（固定 "1.0"）

    Example:
        >>> rebuild_cmd = RebuildCommand(
        ...     cmd=["lc", "advisor", "wiki", "--force"],
        ...     cwd=".",
        ...     schema_version="1.0"
        ... )
        >>> rebuild_cmd.to_safe_string()
        'lc advisor wiki --force'
    """

    cmd: list[str]
    cwd: str
    env: dict[str, str] = field(default_factory=dict)
    schema_version: str = "1.0"

    def to_safe_string(self) -> str:
        """安全轉換為顯示用字串

        使用 shlex.quote 確保參數安全引用，防止 shell injection。

        Returns:
            安全引用的命令字串
        """
        return " ".join(shlex.quote(arg) for arg in self.cmd)


@dataclass(frozen=True)
class AdvisorDerivedProvenance:
    """Stage 3 衍生物的 Provenance（V7 版）

    記錄決策 Wiki、風險矩陣、敏感度報告等衍生物的完整來源資訊。

    Attributes:
        artifact_type: 衍生物類型（"decision_wiki" | "risk_matrix" | "sensitivity"）
        schema_version: Provenance schema 版本（固定 "1.0"）
        calc_version: 計算邏輯版本（如 "wiki_v1.0"）
        canonicalization_version: 輸入正規化版本（V7 新增）
        input_hash: 輸入內容 SHA-256 hash（完整 64 hex）
        canonical_sources: 使用的 canonical 檔案列表
        generated_at: 生成時間（ISO 8601）
        rebuild_command: 結構化重建命令（V7 新增）
        content_hash: 輸出內容 hash（SHA-256 完整 64 hex，V6）
        redaction_profile_version: 去識別規則版本（如 "1.0"，V6）

    Example:
        >>> provenance = AdvisorDerivedProvenance(
        ...     artifact_type="decision_wiki",
        ...     schema_version="1.0",
        ...     calc_version="wiki_v1.0",
        ...     canonicalization_version="1.0",
        ...     input_hash="abc123...",
        ...     canonical_sources=["canonical/decisions/decisions.yaml"],
        ...     generated_at="2024-12-29T10:00:00Z",
        ...     rebuild_command=RebuildCommand(
        ...         cmd=["lc", "advisor", "wiki", "--force"],
        ...         cwd="."
        ...     ),
        ...     content_hash="def456...",
        ...     redaction_profile_version="1.0"
        ... )
    """

    artifact_type: Literal["decision_wiki", "risk_matrix", "sensitivity"]
    schema_version: str
    calc_version: str
    canonicalization_version: str
    input_hash: str
    canonical_sources: list[str]
    generated_at: str
    rebuild_command: RebuildCommand
    content_hash: str
    redaction_profile_version: str

    def __post_init__(self):
        """驗證欄位值的合法性"""
        # 驗證 artifact_type
        valid_types = {"decision_wiki", "risk_matrix", "sensitivity"}
        if self.artifact_type not in valid_types:
            raise ValueError(
                f"artifact_type 必須是 {valid_types} 之一，收到: {self.artifact_type}"
            )

        # 驗證 input_hash 長度（SHA-256 = 64 hex）
        if len(self.input_hash) != 64:
            raise ValueError(
                f"input_hash 必須是 64 字元的 SHA-256 hash，收到長度: {len(self.input_hash)}"
            )

        # 驗證 content_hash 長度
        if len(self.content_hash) != 64:
            raise ValueError(
                f"content_hash 必須是 64 字元的 SHA-256 hash，收到長度: {len(self.content_hash)}"
            )

        # 驗證 generated_at 格式（ISO 8601）
        try:
            datetime.fromisoformat(self.generated_at.replace("Z", "+00:00"))
        except ValueError as e:
            raise ValueError(f"generated_at 必須是有效的 ISO 8601 時間戳: {e}")


# 為了向後相容，提供 DerivedProvenance 別名
DerivedProvenance = AdvisorDerivedProvenance
