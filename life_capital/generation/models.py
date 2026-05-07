"""Phase 3 報表生成資料模型

定義 Phase 3 generation 相關的所有資料結構：
- ReportProvenance: 報表來源追蹤（Contract 3）
- ReportCacheKey: 報表快取鍵定義（Contract 4）
- ReportOutput: 報表輸出結果
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ReportProvenance:
    """報表生成的來源追蹤（Contract 3: ReportProvenance 追蹤）

    記錄報表生成的完整來源資訊，支援版本追蹤與增量生成。
    所有報表必須包含此 provenance 資訊，儲存於 sidecar .meta.json 檔案。

    Attributes:
        schema_version: Provenance 結構版本（如 "1.0"）
        contract_version: 報表契約版本（如 "1.0"，對應 Contract 6）
        template_version: 報表模板版本（如 "1.0"）
        generation_version: 生成邏輯版本（如 "1.0"）
        input_hash: 輸入來源 hash（來自 input_sources_hash，見 Contract 4）
        report_type: 報表類型（monthly_summary | projection_table | scenario_comparison）
        scenario_sources: 情境來源清單（如 ["baseline", "conservative", "optimistic"]）
        generated_at: 生成時間戳記（ISO 8601 格式）

    V4.1.1 版本欄位用途：
        - schema_version: provenance 結構變更時更新
        - contract_version: Contract 6 規則變更時更新
        - template_version: 報表 markdown 格式變更時更新
        - generation_version: 生成邏輯變更時更新
    """

    # 版本追蹤
    schema_version: str
    contract_version: str
    template_version: str
    generation_version: str

    # 輸入追蹤
    input_hash: str
    report_type: str
    scenario_sources: list[str]

    # 時間戳（唯一動態欄位，不影響報表內容 hash）
    generated_at: str


@dataclass(frozen=True)
class ReportCacheKey:
    """報表快取鍵（Contract 4: 增量生成邏輯）

    定義報表快取的完整鍵值，用於判斷是否需要重新生成報表。
    所有欄位必須完全匹配才能命中快取。

    Attributes:
        report_type: 報表類型（monthly_summary | projection_table | scenario_comparison）
        format: 輸出格式（md | json）
        input_sources_hash: 輸入來源 hash（按 report_type 計算，見 Contract 4）
        template_version: 模板版本（如 "1.0"）
        report_contract_version: 契約版本（如 "1.0"）
        calc_version: 計算邏輯版本（如 "2.0"，來自 Phase 2）
        rounding_config_hash: RoundingConfig 設定 hash
        missing_inputs: 缺失的輸入集合（--allow-missing 時記錄）

    V4.1.1 input_sources_hash 定義：
        - monthly_summary: sha256(projection.input_hash)[:12]
        - projection_table: sha256(projection.input_hash)[:12]
        - scenario_comparison: sha256(projection.input_hash + comparison.input_hash)[:12]
    """

    report_type: str
    format: str
    input_sources_hash: str
    template_version: str
    report_contract_version: str
    calc_version: str
    rounding_config_hash: str
    missing_inputs: frozenset[str]

    def should_regenerate(self, other: "ReportCacheKey") -> bool:
        """判斷是否需要重新生成報表

        Args:
            other: 另一個快取鍵

        Returns:
            True 若任一欄位不匹配（需重新生成），False 若完全匹配（可使用快取）
        """
        return self != other


@dataclass(frozen=True)
class ReportOutput:
    """報表輸出結果

    包含生成的報表內容與來源追蹤資訊。

    Attributes:
        report_type: 報表類型（monthly_summary | projection_table | scenario_comparison）
        content: 報表內容（Markdown 或 JSON 字串）
        format: 輸出格式（md | json）
        provenance: 來源追蹤資訊

    Methods:
        save: 存檔到指定目錄（使用 Contract 6 命名規則）
    """

    report_type: str
    content: str
    format: str
    provenance: ReportProvenance

    def save(self, output_dir: Path) -> Path:
        """存檔到指定目錄

        使用 Contract 6 命名規則：
        {report_type}_{input_hash[:12]}.{format}

        Args:
            output_dir: 輸出目錄路徑（如 derived/reports/）

        Returns:
            儲存的檔案路徑
        """
        from life_capital.io.registry import REPORT_HASH_LEN

        filename = (
            f"{self.report_type}_{self.provenance.input_hash[:REPORT_HASH_LEN]}.{self.format}"
        )
        output_path = output_dir / filename
        return output_path
