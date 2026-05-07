"""Advisor 衍生物 Handler（Stage 3）

Phase 5 Stage 3 決策 Wiki、風險矩陣、敏感度報告的統一寫入處理器。

設計原則:
- 路徑安全: 嚴格驗證所有路徑，防止 path traversal
- 原子寫入: 使用臨時檔案 + rename 確保一致性
- Provenance 強制: 每個輸出都必須有 sidecar metadata

版本歷程:
- V1.0 (2025-12-29): 初版（路徑安全驗證）
"""

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Literal, Union

from life_capital.io.errors import PathSecurityError
from life_capital.io.registry import ADVISOR_DERIVED_DIR
from life_capital.models.provenance import AdvisorDerivedProvenance


class AdvisorDerivedHandler:
    """Stage 3 衍生物的統一寫入處理器

    負責將決策 Wiki、風險矩陣、敏感度報告等衍生物寫入 derived/advisor/，
    並確保每個輸出都有對應的 .meta.json provenance sidecar。

    Attributes:
        data_path: 資料根目錄（如 ~/.life-capital/）
        ALLOWED_BASE: 允許寫入的基礎目錄（"derived/advisor"）
        ALLOWED_EXTENSIONS: 允許的副檔名白名單

    Example:
        >>> handler = AdvisorDerivedHandler(data_path=Path("~/.life-capital"))
        >>> handler.write_with_provenance(
        ...     artifact_type="decision_wiki",
        ...     content="# Decision Wiki\\n...",
        ...     provenance=provenance_obj,
        ...     format="md"
        ... )
    """

    ALLOWED_BASE = ADVISOR_DERIVED_DIR  # "derived/advisor"
    ALLOWED_EXTENSIONS = {".md", ".json", ".meta.json"}

    def __init__(self, data_path: Path):
        """初始化 Handler

        Args:
            data_path: 資料根目錄（如 ~/.life-capital/）
        """
        self.data_path = data_path.expanduser().resolve()

    def _validate_path(self, path: Path) -> Path:
        """嚴格路徑驗證，防止 path traversal

        檢查項目：
        1. 是否在允許目錄下（ALLOWED_BASE）
        2. 副檔名是否在白名單內
        3. 路徑成分是否安全（禁止 ..、空格開頭）

        Args:
            path: 要驗證的路徑

        Returns:
            驗證通過的絕對路徑

        Raises:
            PathSecurityError: 路徑不符合安全規則
        """
        # 解析為絕對路徑
        if not path.is_absolute():
            path = self.data_path / path

        resolved = path.resolve()
        allowed_base = (self.data_path / self.ALLOWED_BASE).resolve()

        # 檢查 1: 是否在允許範圍內
        if not str(resolved).startswith(str(allowed_base)):
            raise PathSecurityError(
                f"路徑超出允許範圍: {resolved} (允許範圍: {allowed_base})"
            )

        # 檢查 2: 副檔名白名單
        if resolved.suffix not in self.ALLOWED_EXTENSIONS:
            raise PathSecurityError(
                f"不允許的副檔名: {resolved.suffix} (允許: {self.ALLOWED_EXTENSIONS})"
            )

        # 檢查 3: 路徑成分安全性
        for part in resolved.parts:
            if part == "..":
                raise PathSecurityError("路徑包含不安全的成分: '..'")
            if part.startswith(" "):
                raise PathSecurityError(f"路徑成分不可以空格開頭: '{part}'")

        return resolved

    def _compute_content_hash(self, content: Union[str, dict]) -> str:
        """計算內容的 SHA-256 hash

        Args:
            content: 內容（字串或字典）

        Returns:
            SHA-256 hash（完整 64 hex）
        """
        if isinstance(content, dict):
            content_str = json.dumps(content, sort_keys=True, ensure_ascii=False)
        else:
            content_str = content

        return hashlib.sha256(content_str.encode("utf-8")).hexdigest()

    def write_with_provenance(
        self,
        artifact_type: Literal["decision_wiki", "risk_matrix", "sensitivity"],
        content: Union[str, dict],
        provenance: AdvisorDerivedProvenance,
        format: Literal["md", "json"],
        filename: Union[str, None] = None,
    ) -> tuple[Path, Path]:
        """原子寫入衍生物 + sidecar provenance

        流程：
        1. 路徑安全驗證
        2. 寫入內容到 .tmp 檔案
        3. 寫入 provenance 到 .meta.json.tmp
        4. 原子 rename 兩個檔案
        5. 返回寫入路徑

        Args:
            artifact_type: 衍生物類型
            content: 內容（Markdown 字串或 JSON 字典）
            provenance: Provenance metadata
            format: 輸出格式（"md" 或 "json"）
            filename: 自訂檔名（可選，預設自動生成）

        Returns:
            (content_path, meta_path): 寫入的檔案路徑（內容 + metadata）

        Raises:
            PathSecurityError: 路徑不安全
            ValueError: 參數錯誤
            IOError: 寫入失敗
        """
        # 驗證參數一致性
        if provenance.artifact_type != artifact_type:
            raise ValueError(
                f"artifact_type 不一致: {artifact_type} != {provenance.artifact_type}"
            )

        # 生成檔名（如未指定）
        if filename is None:
            input_hash_short = provenance.input_hash[:12]
            schema_ver = provenance.schema_version.replace(".", "_")
            filename = (
                f"{artifact_type}_{input_hash_short}_{schema_ver}.{format}"
            )

        # 構建完整路徑並驗證
        content_path = Path(self.ALLOWED_BASE) / filename
        content_path = self._validate_path(content_path)
        meta_path = content_path.with_suffix(f"{content_path.suffix}.meta.json")
        meta_path = self._validate_path(meta_path)

        # 確保目錄存在
        content_path.parent.mkdir(parents=True, exist_ok=True)

        # 準備內容
        if format == "json":
            content_str = json.dumps(
                content, indent=2, ensure_ascii=False, sort_keys=True
            )
        else:
            content_str = content if isinstance(content, str) else str(content)

        # 使用臨時檔案進行原子寫入
        fd_content, tmp_content_path = tempfile.mkstemp(
            suffix=f".{format}", prefix=".tmp_", dir=content_path.parent
        )
        fd_meta, tmp_meta_path = tempfile.mkstemp(
            suffix=".meta.json", prefix=".tmp_", dir=content_path.parent
        )

        try:
            # 寫入內容
            with os.fdopen(fd_content, "w", encoding="utf-8") as f:
                f.write(content_str)

            # 寫入 provenance（轉為 dict）
            provenance_dict = {
                "artifact_type": provenance.artifact_type,
                "schema_version": provenance.schema_version,
                "calc_version": provenance.calc_version,
                "canonicalization_version": provenance.canonicalization_version,
                "input_hash": provenance.input_hash,
                "canonical_sources": provenance.canonical_sources,
                "generated_at": provenance.generated_at,
                "rebuild_command": {
                    "cmd": provenance.rebuild_command.cmd,
                    "cwd": provenance.rebuild_command.cwd,
                    "env": provenance.rebuild_command.env,
                    "schema_version": provenance.rebuild_command.schema_version,
                },
                "content_hash": provenance.content_hash,
                "redaction_profile_version": provenance.redaction_profile_version,
            }

            with os.fdopen(fd_meta, "w", encoding="utf-8") as f:
                json.dump(provenance_dict, f, indent=2, ensure_ascii=False)

            # 原子 rename
            os.replace(tmp_content_path, content_path)
            os.replace(tmp_meta_path, meta_path)

            return (content_path, meta_path)

        except Exception as e:
            # 清理臨時檔案
            for tmp_path in [tmp_content_path, tmp_meta_path]:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            raise IOError(f"寫入失敗: {e}") from e
