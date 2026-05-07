"""Phase 3 報表格式化器模組

提供 Markdown 與 JSON 格式化功能。

核心組件：
- MarkdownFormatter: Markdown 格式化器
- JSONFormatter: JSON 格式化器

V4.1.1 輸出規範：
- 禁止動態欄位（generated_at 只在 .meta.json）
- 固定格式欄位（金額、百分比、日期）
- 快照比對穩定性
"""

from life_capital.generation.formatters.json_formatter import JSONFormatter
from life_capital.generation.formatters.markdown_formatter import MarkdownFormatter

__all__ = [
    "MarkdownFormatter",
    "JSONFormatter",
]
