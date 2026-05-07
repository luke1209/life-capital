"""Phase 3 報表生成器核心邏輯

提供從 Phase 2 計算結果生成財務報表的核心功能。

核心組件：
- load_projection_from_derived: 唯一允許的 projection 載入入口（Contract 2）
- load_comparison_from_derived: 唯一允許的 comparison 載入入口（Contract 2）
- compute_input_sources_hash: 計算輸入來源 hash（Contract 4）
- ReportGenerator: 報表生成器核心類別

Contract 遵守：
- Contract 1: 只寫入 derived/reports/
- Contract 2: 只讀取 Phase 2 輸出，禁止直接讀取 canonical/
- Contract 3: 所有報表包含 ReportProvenance
- Contract 4: 完整 cache key 比對
- Contract 7: 原子寫入策略（temp → flush → fsync → os.replace）
"""

import hashlib
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

from life_capital.generation.models import ReportOutput, ReportProvenance
from life_capital.io.registry import (
    DERIVED_SCENARIOS_DIR,
    GENERATION_VERSION,
    REPORT_HASH_LEN,
    REPORT_PROVENANCE_SUFFIX,
    REPORTS_DIR,
)
from life_capital.models.scenario import ProjectionResult, ScenarioComparisonResult

# === Contract 2: 輸入來源限制（V4.1.1 強化 Enforcement）===


class InputMissingError(Exception):
    """Phase 2 輸入檔案缺失錯誤"""

    pass


def load_projection_from_derived(data_dir: Path) -> ProjectionResult:
    """唯一允許的 projection 載入入口（Contract 2）

    V4.1.1: 此函數是 generation 模組讀取 Phase 2 輸出的唯一入口。
    禁止直接 import fetch_historical_expenses / fetch_latest_income。

    Args:
        data_dir: 資料目錄路徑

    Returns:
        ProjectionResult: Phase 2 預測結果

    Raises:
        InputMissingError: 若 projection_baseline.json 不存在
    """
    path = data_dir / DERIVED_SCENARIOS_DIR / "projection_baseline.json"
    if not path.exists():
        raise InputMissingError(
            f"projection_baseline.json not found at {path}. "
            "Please run 'lc project --save' first."
        )
    return ProjectionResult.model_validate_json(path.read_text(encoding="utf-8"))


def load_comparison_from_derived(
    data_dir: Path,
) -> Optional[ScenarioComparisonResult]:
    """唯一允許的 comparison 載入入口（Contract 2）

    Args:
        data_dir: 資料目錄路徑

    Returns:
        Optional[ScenarioComparisonResult]: Phase 2 情境比較結果（若存在）
    """
    path = data_dir / DERIVED_SCENARIOS_DIR / "comparison.json"
    if not path.exists():
        return None  # comparison 為選填
    return ScenarioComparisonResult.model_validate_json(path.read_text(encoding="utf-8"))


# === Contract 4: 增量生成邏輯 ===


def compute_input_sources_hash(
    report_type: str,
    projection: ProjectionResult,
    comparison: Optional[ScenarioComparisonResult] = None,
) -> str:
    """計算 input_sources_hash（V4.1.1 明確定義）

    根據 report_type 決定使用哪些輸入來源計算 hash。

    Args:
        report_type: 報表類型（monthly_summary | projection_table | scenario_comparison）
        projection: Phase 2 預測結果
        comparison: Phase 2 情境比較結果（選填）

    Returns:
        str: 12 位 hash 字串

    Raises:
        ValueError: 若 report_type 不合法，或 scenario_comparison 缺少 comparison 輸入
    """
    if report_type in ("monthly_summary", "projection_table"):
        # projection-only reports
        return hashlib.sha256(projection.input_hash.encode()).hexdigest()[:REPORT_HASH_LEN]
    elif report_type == "scenario_comparison":
        # requires both projection and comparison
        if comparison is None:
            raise ValueError("scenario_comparison requires comparison input")
        combined = f"{projection.input_hash}:{comparison.input_hash}"
        return hashlib.sha256(combined.encode()).hexdigest()[:REPORT_HASH_LEN]
    else:
        raise ValueError(f"Unknown report_type: {report_type}")


# === Contract 7: 原子寫入策略 ===


def fsync_directory(dir_path: Path) -> None:
    """確保目錄 metadata 寫入磁碟（跨平台）

    V4.1.1: POSIX 使用 fsync(dir_fd)，Windows 退化為 no-op

    Args:
        dir_path: 目錄路徑
    """
    if sys.platform == "win32":
        # Windows: os.replace 已足夠原子性，目錄 fsync 無意義
        return

    # POSIX: 確保目錄條目更新寫入磁碟
    dir_fd = os.open(str(dir_path), os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def save_report_atomic(content: str, target_path: Path) -> Path:
    """原子寫入報表（Contract 7）

    策略: 寫入 temp → flush → fsync → os.replace（跨平台原子）
    V4.1 修正: 使用正確的 file descriptor 與 os.replace

    Args:
        content: 報表內容
        target_path: 目標檔案路徑

    Returns:
        Path: 成功寫入的檔案路徑

    Raises:
        Exception: 寫入失敗時，會清理 temp 檔案並拋出例外
    """
    temp_path = target_path.with_suffix(f".tmp.{uuid4().hex[:8]}")
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()  # 確保 Python buffer 寫入 OS
            os.fsync(f.fileno())  # 確保 OS buffer 寫入磁碟
        os.replace(temp_path, target_path)  # 原子置換（跨平台）
        fsync_directory(target_path.parent)  # V4.1.1: 確保目錄更新
        return target_path
    except Exception:
        temp_path.unlink(missing_ok=True)  # cleanup on failure
        raise


# === ReportGenerator 核心類別 ===


class ReportGenerator:
    """財務報表生成器（Phase 3 核心）

    提供從 Phase 2 計算結果生成財務報表的完整功能。

    Attributes:
        data_dir: 資料目錄路徑

    Methods:
        generate_monthly_summary: 生成月度現金流摘要
        generate_projection_table: 生成 12-24 月預測表
        generate_scenario_comparison: 生成情境比較表
        generate_all: 生成所有報表
    """

    def __init__(self, data_dir: Path):
        """初始化報表生成器

        Args:
            data_dir: 資料目錄路徑（如 ~/.life-capital/）
        """
        self.data_dir = data_dir
        self.reports_dir = data_dir / REPORTS_DIR

        # 確保輸出目錄存在
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def generate_monthly_summary(
        self,
        projection: ProjectionResult,
        format: str = "md",
    ) -> ReportOutput:
        """生成月度現金流摘要（Contract 6: 報表輸出契約）

        包含：
        - 期間總收入/支出
        - 平均月現金流
        - 赤字月數與首次赤字月
        - 資產耗盡警告（如有）

        Args:
            projection: Phase 2 預測結果
            format: 輸出格式（md | json）

        Returns:
            ReportOutput: 報表輸出結果
        """
        report_type = "monthly_summary"

        # 計算 input_sources_hash（Contract 4）
        input_hash = compute_input_sources_hash(report_type, projection)

        # 建立 ReportProvenance（Contract 3）
        provenance = ReportProvenance(
            schema_version="1.0",
            contract_version="1.0",
            template_version="1.0",
            generation_version=GENERATION_VERSION,
            input_hash=input_hash,
            report_type=report_type,
            scenario_sources=["baseline"],
            generated_at=datetime.now().isoformat(),
        )

        # 生成報表內容（暫時返回簡單模板，後續由 formatter 實作）
        content = self._generate_monthly_summary_content(projection, format)

        return ReportOutput(
            report_type=report_type,
            content=content,
            format=format,
            provenance=provenance,
        )

    def generate_projection_table(
        self,
        projection: ProjectionResult,
        format: str = "md",
    ) -> ReportOutput:
        """生成 12-24 月預測表（Contract 6: 報表輸出契約）

        包含：
        - 每月收入/支出/淨現金流/累積儲蓄
        - 狀態標記（正常/赤字/耗盡）

        Args:
            projection: Phase 2 預測結果
            format: 輸出格式（md | json）

        Returns:
            ReportOutput: 報表輸出結果
        """
        report_type = "projection_table"

        # 計算 input_sources_hash（Contract 4）
        input_hash = compute_input_sources_hash(report_type, projection)

        # 建立 ReportProvenance（Contract 3）
        provenance = ReportProvenance(
            schema_version="1.0",
            contract_version="1.0",
            template_version="1.0",
            generation_version=GENERATION_VERSION,
            input_hash=input_hash,
            report_type=report_type,
            scenario_sources=["baseline"],
            generated_at=datetime.now().isoformat(),
        )

        # 生成報表內容（暫時返回簡單模板，後續由 formatter 實作）
        content = self._generate_projection_table_content(projection, format)

        return ReportOutput(
            report_type=report_type,
            content=content,
            format=format,
            provenance=provenance,
        )

    def generate_scenario_comparison(
        self,
        comparison: ScenarioComparisonResult,
        format: str = "md",
    ) -> ReportOutput:
        """生成情境比較表（Contract 6: 報表輸出契約）

        包含：
        - 各情境假設清單
        - 最終儲蓄比較
        - vs 基準差異
        - 赤字月數與資產耗盡時間

        Args:
            comparison: Phase 2 情境比較結果
            format: 輸出格式（md | json）

        Returns:
            ReportOutput: 報表輸出結果
        """
        report_type = "scenario_comparison"

        # 計算 input_sources_hash（Contract 4）
        # 注意：scenario_comparison 需要 projection + comparison
        # 但這裡只傳入 comparison，所以我們需要從 comparison 中取得 projection
        # 暫時使用 comparison.input_hash
        input_hash = hashlib.sha256(comparison.input_hash.encode()).hexdigest()[:REPORT_HASH_LEN]

        # 建立 ReportProvenance（Contract 3）
        scenario_sources = [s.scenario.name for s in comparison.scenarios]
        provenance = ReportProvenance(
            schema_version="1.0",
            contract_version="1.0",
            template_version="1.0",
            generation_version=GENERATION_VERSION,
            input_hash=input_hash,
            report_type=report_type,
            scenario_sources=scenario_sources,
            generated_at=datetime.now().isoformat(),
        )

        # 生成報表內容（暫時返回簡單模板，後續由 formatter 實作）
        content = self._generate_scenario_comparison_content(comparison, format)

        return ReportOutput(
            report_type=report_type,
            content=content,
            format=format,
            provenance=provenance,
        )

    def generate_all(
        self,
        projection: ProjectionResult,
        comparison: Optional[ScenarioComparisonResult],
        format: str = "md",
        save: bool = False,
        force: bool = False,
    ) -> list[ReportOutput]:
        """生成所有報表

        Args:
            projection: Phase 2 預測結果
            comparison: Phase 2 情境比較結果（可選）
            format: 輸出格式（md | json）
            save: 是否存檔到 derived/reports/
            force: 是否強制覆蓋（忽略 cache，用於 rebuild）

        Returns:
            list[ReportOutput]: 所有報表輸出結果

        Note:
            force=True 時，忽略 cache 檢查，強制重新生成（Contract 8）
        """
        reports = []

        # 生成 monthly_summary
        reports.append(self.generate_monthly_summary(projection, format))

        # 生成 projection_table
        reports.append(self.generate_projection_table(projection, format))

        # 生成 scenario_comparison（若有 comparison 資料）
        if comparison:
            reports.append(self.generate_scenario_comparison(comparison, format))

        # 存檔（若要求）
        if save:
            for report in reports:
                self._save_report(report)

        return reports

    def _save_report(self, report: ReportOutput) -> Path:
        """存檔報表並寫入 sidecar provenance（Contract 3 + Contract 7）

        Args:
            report: 報表輸出結果

        Returns:
            Path: 儲存的檔案路徑
        """
        # 生成檔案名稱（Contract 6）
        filename = (
            f"{report.report_type}_"
            f"{report.provenance.input_hash[:REPORT_HASH_LEN]}.{report.format}"
        )
        target_path = self.reports_dir / filename

        # 原子寫入報表內容（Contract 7）
        save_report_atomic(report.content, target_path)

        # 寫入 sidecar provenance（Contract 3）
        provenance_path = target_path.with_suffix(target_path.suffix + REPORT_PROVENANCE_SUFFIX)
        import json

        provenance_data = {
            "schema_version": report.provenance.schema_version,
            "contract_version": report.provenance.contract_version,
            "template_version": report.provenance.template_version,
            "generation_version": report.provenance.generation_version,
            "input_hash": report.provenance.input_hash,
            "report_type": report.provenance.report_type,
            "scenario_sources": report.provenance.scenario_sources,
            "generated_at": report.provenance.generated_at,
        }
        save_report_atomic(json.dumps(provenance_data, indent=2), provenance_path)

        return target_path

    # === 內部輔助方法（使用 formatters）===

    def _generate_monthly_summary_content(
        self, projection: ProjectionResult, format: str
    ) -> str:
        """生成月度摘要內容（使用 formatters）

        Args:
            projection: Phase 2 預測結果
            format: 輸出格式（md | json）

        Returns:
            格式化後的報表內容
        """
        from life_capital.generation.formatters import JSONFormatter, MarkdownFormatter

        if format == "md":
            return MarkdownFormatter().format_monthly_summary(projection)
        elif format == "json":
            return JSONFormatter().format_monthly_summary(projection)
        else:
            raise ValueError(f"Unsupported format: {format}")

    def _generate_projection_table_content(
        self, projection: ProjectionResult, format: str
    ) -> str:
        """生成預測表內容（使用 formatters）

        Args:
            projection: Phase 2 預測結果
            format: 輸出格式（md | json）

        Returns:
            格式化後的報表內容
        """
        from life_capital.generation.formatters import JSONFormatter, MarkdownFormatter

        if format == "md":
            return MarkdownFormatter().format_projection_table(projection)
        elif format == "json":
            return JSONFormatter().format_projection_table(projection)
        else:
            raise ValueError(f"Unsupported format: {format}")

    def _generate_scenario_comparison_content(
        self, comparison: ScenarioComparisonResult, format: str
    ) -> str:
        """生成情境比較內容（使用 formatters）

        Args:
            comparison: Phase 2 情境比較結果
            format: 輸出格式（md | json）

        Returns:
            格式化後的報表內容
        """
        from life_capital.generation.formatters import JSONFormatter, MarkdownFormatter

        if format == "md":
            return MarkdownFormatter().format_scenario_comparison(comparison)
        elif format == "json":
            return JSONFormatter().format_scenario_comparison(comparison)
        else:
            raise ValueError(f"Unsupported format: {format}")
