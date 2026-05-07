"""介面層模組

提供 Phase 4+ 模組與核心系統之間的穩定介面。

此層實現關鍵隔離：
- capture/ 只能依賴 interfaces/
- capture/ 不可直接依賴 models/
- 透過 Protocol 定義契約，確保介面穩定
"""

from life_capital.interfaces.canonical_reader import (
    INTERFACE_VERSION,
    CanonicalReader,
)
from life_capital.interfaces.canonical_reader_impl import get_canonical_reader

__all__ = ["CanonicalReader", "get_canonical_reader", "INTERFACE_VERSION"]
