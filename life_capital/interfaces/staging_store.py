"""Staging Store 資料存取介面

定義 Phase 4 (CAPTURE) 的 StagingEntry 持久化契約。

版本: 1.0
Breaking changes 需要 major version bump。
參見: docs/contracts/interface_policy.md
"""

# TYPE_CHECKING 避免循環 import
from typing import TYPE_CHECKING, Optional, Protocol, runtime_checkable

if TYPE_CHECKING:
    from life_capital.capture.models import StagingEntry


@runtime_checkable
class StagingStore(Protocol):
    """StagingEntry 持久化介面

    此 Protocol 定義了 capture/ 模組的儲存契約。
    實作層必須提供 append-only log 語意與並發安全保證。

    Version: 1.0
    Breaking changes require major version bump.

    變更規則：
    - Breaking: 刪除方法、改變方法簽名、改變返回型別
    - Compatible: 新增方法（需提供 default）
    - Internal: 實作細節變更

    儲存保證：
    - Append-only: 更新操作追加新行，不修改既有行
    - Durability: 寫入後立即 fsync（可選）
    - Concurrency: 支援多執行緒並發寫入
    - Ordering: 保證 _seq 遞增（單調性）

    Examples
    --------
    >>> store = get_staging_store(data_path)
    >>> entry = StagingEntry(entry_id="...", raw_text="...")
    >>> store.write_entry(entry)
    >>> entries = store.read_entries(status="pending")
    >>> current_state = store.read_current_state()  # last-write-wins
    """

    def write_entry(self, entry: "StagingEntry") -> None:
        """寫入 StagingEntry（append-only）

        每次呼叫追加一行至 JSONL log，自動分配 _seq。
        實作必須保證並發安全（threading.Lock）。

        Parameters
        ----------
        entry : StagingEntry
            待寫入的 entry（不含 _seq，由實作層生成）

        Raises
        ------
        IOError
            寫入失敗（磁碟滿、權限不足等）
        ValueError
            entry_id 格式錯誤
        """
        ...

    def read_entries(self, status: Optional[str] = None) -> list["StagingEntry"]:
        """讀取所有 entries（全量讀取）

        讀取 JSONL log 的所有行，可依 status 過濾。
        不進行去重，返回所有歷史版本（含已更新的舊版）。

        Parameters
        ----------
        status : Optional[str]
            狀態過濾器（如 "pending", "approved"），None 表示全部

        Returns
        -------
        list[StagingEntry]
            依 _seq 升序排序的 entries（包含所有版本）

        Raises
        ------
        FileNotFoundError
            entries.jsonl 不存在
        JSONDecodeError
            JSONL 格式錯誤
        """
        ...

    def read_entry(self, entry_id: str) -> Optional["StagingEntry"]:
        """讀取單筆 entry（last-write-wins）

        搜尋整個 JSONL log，返回該 entry_id 的最新版本。

        Parameters
        ----------
        entry_id : str
            Entry UUID

        Returns
        -------
        Optional["StagingEntry"]
            最新版本的 entry，若不存在返回 None

        Raises
        ------
        FileNotFoundError
            entries.jsonl 不存在
        """
        ...

    def read_current_state(self) -> dict[str, "StagingEntry"]:
        """讀取當前狀態（last-write-wins 去重）

        讀取整個 JSONL log，對每個 entry_id 只保留最新版本。
        返回 {entry_id: latest_entry} 字典。

        Returns
        -------
        dict[str, StagingEntry]
            entry_id → 最新版本 entry 的映射

        Raises
        ------
        FileNotFoundError
            entries.jsonl 不存在

        Notes
        -----
        此方法用於取得 "邏輯當前狀態"，實作為：
        1. 讀取全部 entries
        2. 按 _seq 升序排序
        3. 對每個 entry_id，後出現的覆蓋先出現的
        """
        ...

    # V1.0 新增方法（Compatible change，提供 default）
    def get_version(self) -> str:
        """取得介面版本

        Returns
        -------
        str
            版本號，如 "1.0"
        """
        return "1.0"  # default implementation for backwards compatibility


# 介面版本常數
INTERFACE_VERSION = "1.0"
