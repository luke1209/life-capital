"""決策模板子模組

提供決策模板 DSL 與配置管理。
"""

from life_capital.advisor.templates.schema import (
    DecisionTemplate,
    TemplateRegistry,
    get_all_templates,
    load_template,
)

__all__ = [
    "DecisionTemplate",
    "TemplateRegistry",
    "load_template",
    "get_all_templates",
]
