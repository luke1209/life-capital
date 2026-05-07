"""Staging Store 實作層

提供 StagingEntry 的 JSONL 持久化實作，支援：
- Append-only log 語意
- _seq 自動遞增（O(1) 讀取最後一行）
- 並發控制（threading.Lock）
- Last-write-wins 語意

儲存格式: JSONL (JSON Lines)
儲存路徑: ~/.life-capital/staging/entries.jsonl
"""

import json
import threading
from pathlib import Path
from typing import Dict, List, Optional

from life_capital.capture.models import StagingEntry


class StagingStoreImpl:
    """StagingEntry JSONL 儲存實作

    實作 StagingStore Protocol，提供並發安全的 append-only log。

    Attributes
    ----------
    data_path : Path
        資料根目錄（~/.life-capital）
    _lock : threading.Lock
        寫入鎖，保護並發寫入與 _seq 生成

    Notes
    -----
    此類別實作了以下保證：
    1. Append-only: write_entry() 只追加，不修改既有行
    2. Concurrency: threading.Lock 保護寫入操作
    3. Durability: 每次寫入後 flush（未使用 fsync，效能考量）
    4. Ordering: _seq 嚴格遞增（O(1) 讀取最後一行）
    """

    def __init__(self, data_path: Path):
        """初始化 StagingStore

        Parameters
        ----------
        data_path : Path
            資料根目錄路徑
        """
        self.data_path = data_path
        self._lock = threading.Lock()
        self._ensure_staging_dir()

    def _ensure_staging_dir(self) -> None:
        """確保 staging/ 目錄存在"""
        staging_dir = self.data_path / "staging"
        staging_dir.mkdir(parents=True, exist_ok=True)

    @property
    def _entries_path(self) -> Path:
        """JSONL 檔案路徑"""
        return self.data_path / "staging" / "entries.jsonl"

    def _get_next_seq(self) -> int:
        """取得下一個 _seq 值（O(1) 實作）

        讀取檔案最後一行取得 current_seq，返回 current_seq + 1。
        若檔案不存在或為空，返回 1。

        Returns
        -------
        int
            下一個 _seq 值（從 1 開始）

        Notes
        -----
        此方法假設 _seq 欄位總是存在於每一行。
        使用 seek() 從檔案末尾向前讀取，避免讀取整個檔案。
        """
        if not self._entries_path.exists():
            return 1

        try:
            with open(self._entries_path, "rb") as f:
                # 定位到檔案末尾
                f.seek(0, 2)
                file_size = f.tell()

                if file_size == 0:
                    return 1

                # 從末尾向前找最後一個換行符
                buffer_size = min(1024, file_size)
                f.seek(-buffer_size, 2)
                last_chunk = f.read().decode("utf-8")

                # 找到最後一行（去除尾部空白）
                lines = last_chunk.strip().split("\n")
                if not lines:
                    return 1

                last_line = lines[-1]
                last_entry = json.loads(last_line)
                current_seq = last_entry.get("_seq", 0)
                return current_seq + 1

        except (json.JSONDecodeError, KeyError, ValueError):
            # 若解析失敗，讀取整個檔案找最大 _seq（fallback）
            return self._get_max_seq_fallback() + 1

    def _get_max_seq_fallback(self) -> int:
        """Fallback: 讀取整個檔案找最大 _seq

        當最後一行損壞時使用，效能較差（O(n)）。

        Returns
        -------
        int
            當前最大 _seq，若檔案為空返回 0
        """
        max_seq = 0
        if not self._entries_path.exists():
            return max_seq

        with open(self._entries_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    max_seq = max(max_seq, entry.get("_seq", 0))
                except json.JSONDecodeError:
                    continue

        return max_seq

    def write_entry(self, entry: StagingEntry) -> None:
        """寫入 StagingEntry（append-only）

        實作並發安全的追加寫入：
        1. 獲取寫入鎖
        2. 生成 _seq
        3. 序列化為 JSON
        4. 追加至 JSONL 檔案
        5. flush（不 fsync）

        Parameters
        ----------
        entry : StagingEntry
            待寫入的 entry

        Raises
        ------
        IOError
            寫入失敗
        """
        with self._lock:
            # 生成 _seq
            next_seq = self._get_next_seq()

            # 序列化（加入 _seq）
            entry_dict = entry.to_dict()
            entry_dict["_seq"] = next_seq
            json_line = json.dumps(entry_dict, ensure_ascii=False)

            # 追加寫入
            with open(self._entries_path, "a", encoding="utf-8") as f:
                f.write(json_line + "\n")
                f.flush()  # 確保寫入 OS buffer（未 fsync）

    def read_entries(self, status: Optional[str] = None) -> List[StagingEntry]:
        """讀取所有 entries（全量讀取）

        讀取整個 JSONL 檔案，可依 status 過濾。
        不進行去重，返回所有歷史版本。

        Parameters
        ----------
        status : str | None
            狀態過濾器，None 表示全部

        Returns
        -------
        list[StagingEntry]
            依 _seq 升序排序的 entries

        Raises
        ------
        FileNotFoundError
            entries.jsonl 不存在
        """
        if not self._entries_path.exists():
            raise FileNotFoundError(f"JSONL 檔案不存在: {self._entries_path}")

        entries = []
        with open(self._entries_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    entry_dict = json.loads(line)
                    # 移除 _seq（不屬於 StagingEntry）
                    entry_dict.pop("_seq", None)
                    entry = StagingEntry.from_dict(entry_dict)

                    # 狀態過濾
                    if status is None or entry.status.value == status:
                        entries.append(entry)

                except (json.JSONDecodeError, ValueError) as e:
                    # 記錄錯誤但繼續處理（容錯設計）
                    print(f"警告: 跳過損壞的行: {e}")
                    continue

        return entries

    def read_entry(self, entry_id: str) -> Optional[StagingEntry]:
        """讀取單筆 entry（last-write-wins）

        搜尋整個 JSONL log，返回該 entry_id 的最新版本。

        Parameters
        ----------
        entry_id : str
            Entry UUID

        Returns
        -------
        StagingEntry | None
            最新版本的 entry，若不存在返回 None
        """
        if not self._entries_path.exists():
            return None

        last_seen: Optional[StagingEntry] = None

        with open(self._entries_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    entry_dict = json.loads(line)
                    if entry_dict.get("entry_id") == entry_id:
                        # 移除 _seq
                        entry_dict.pop("_seq", None)
                        last_seen = StagingEntry.from_dict(entry_dict)

                except (json.JSONDecodeError, ValueError):
                    continue

        return last_seen

    def read_current_state(self) -> Dict[str, StagingEntry]:
        """讀取當前狀態（last-write-wins 去重）

        讀取整個 JSONL log，對每個 entry_id 只保留最新版本。

        Returns
        -------
        dict[str, StagingEntry]
            entry_id → 最新版本 entry 的映射

        Raises
        ------
        FileNotFoundError
            entries.jsonl 不存在
        """
        if not self._entries_path.exists():
            raise FileNotFoundError(f"JSONL 檔案不存在: {self._entries_path}")

        current_state: Dict[str, StagingEntry] = {}

        with open(self._entries_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    entry_dict = json.loads(line)
                    entry_id = entry_dict.get("entry_id")
                    if not entry_id:
                        continue

                    # 移除 _seq
                    entry_dict.pop("_seq", None)
                    entry = StagingEntry.from_dict(entry_dict)

                    # Last-write-wins: 後出現的覆蓋先出現的
                    current_state[entry_id] = entry

                except (json.JSONDecodeError, ValueError) as e:
                    # 記錄錯誤但繼續處理
                    print(f"警告: 跳過損壞的行: {e}")
                    continue

        return current_state

    def get_version(self) -> str:
        """取得介面版本

        Returns
        -------
        str
            版本號
        """
        return "1.0"


# 工廠函式
def get_staging_store(data_path: Path) -> StagingStoreImpl:
    """建立 StagingStore 實例

    Parameters
    ----------
    data_path : Path
        資料根目錄路徑

    Returns
    -------
    StagingStoreImpl
        StagingStore 實例
    """
    return StagingStoreImpl(data_path)
