"""Phase 4: 消費記錄擷取模組

此模組負責從各種來源（發票、電子支付紀錄等）擷取消費記錄。

隔離規則
--------
此模組只能依賴 interfaces/，不可直接依賴 models/。

正確:
    from life_capital.interfaces import CanonicalReader

錯誤:
    from life_capital.models import ExpensePolicy  # 禁止

CI 驗證:
    grep -r "from life_capital.models" life_capital/capture/  # 應該為空
    grep -r "from life_capital.interfaces" life_capital/capture/  # 應該有

狀態
----
Phase 4 尚未實作。此為模組骨架，供契約測試驗證隔離性。
"""

__version__ = "0.1.0"  # Phase 4 pre-alpha
