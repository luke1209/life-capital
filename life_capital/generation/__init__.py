"""Phase 3: Report Generation 模組

提供從 Phase 2 計算結果生成財務報表的功能。

核心組件：
- models: ReportProvenance, ReportCacheKey, ReportOutput 資料模型
- report_generator: ReportGenerator 核心生成器
- formatters: Markdown 與 JSON 格式化器

系統契約（9 個）：
1. Derived 寫入邊界：只寫入 derived/reports/
2. 輸入來源限制：只讀取 Phase 2 輸出（load_*_from_derived）
3. ReportProvenance 追蹤：sidecar .meta.json 為唯一權威
4. 增量生成邏輯：完整 cache key 比對
5. 金額精度輸出：沿用 RoundingConfig.format_currency()
6. 報表輸出契約：統一命名與追蹤規範（12 位 hash）
7. 原子寫入策略：temp → flush → fsync → os.replace
8. Rebuild 整合：lc rebuild --target reports 共享生成器
9. Error Contract：統一錯誤分類與 exit code

詳細規劃請見：docs/plans/phase3-generation/phase3-generation-plan-v4.1.1.md
"""

from life_capital.generation.models import ReportCacheKey, ReportOutput, ReportProvenance
from life_capital.generation.report_generator import (
    InputMissingError,
    ReportGenerator,
    compute_input_sources_hash,
    load_comparison_from_derived,
    load_projection_from_derived,
)

__all__ = [
    "ReportProvenance",
    "ReportCacheKey",
    "ReportOutput",
    "ReportGenerator",
    "load_projection_from_derived",
    "load_comparison_from_derived",
    "compute_input_sources_hash",
    "InputMissingError",
]
