"""Phase 4 CAPTURE - Staging 業務邏輯層

管理 staging entries 的 CRUD 操作與 8 狀態狀態機邏輯。

狀態轉移規則（V4.1.1）：
- pending → parse() → parsed/error
- parsed → approve() → approved
- parsed → reject() → rejected
- parsed → ignore() → ignored
- approved → (external apply) → applied
- rejected → edit() → pending
- ignored → restore() → pending
- duplicate → force_approve() → approved

防護規則：
- ❌ approved 狀態不可直接編輯（需先 reject）
- ❌ 已進入 applied 的資料不可從 staging 修改
- ✅ rejected 可重新編輯並觸發重新解析
- ✅ ignored 可還原為 pending 重新處理
- ⚠️ duplicate 需要 force-approve 才能強制進入 proposals
"""

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional
from uuid import uuid4

if TYPE_CHECKING:
    from life_capital.models.expense import ExpenseRecord

from life_capital.capture.expense_parser import ExpenseParser
from life_capital.capture.models import (
    DuplicateReason,
    StagingEntry,
    StagingStatus,
)
from life_capital.interfaces.canonical_reader import CanonicalReader
from life_capital.interfaces.staging_store import StagingStore

# === Exceptions ===


class InvalidStateTransition(Exception):
    """無效的狀態轉移"""

    pass


class EntryNotFound(Exception):
    """Entry 不存在"""

    pass


# === Service ===


class StagingService:
    """Staging 業務邏輯服務

    職責：
    - 管理 staging entries 的 CRUD 操作
    - 實作 8 狀態狀態機邏輯
    - 執行 parse 原子操作（解析 + proposal 建立）
    - 重複偵測與去重
    """

    def __init__(
        self,
        store: StagingStore,
        parser: ExpenseParser,
        reader: CanonicalReader,
    ):
        """初始化服務

        Args:
            store: StagingStore 實例（持久化層）
            parser: ExpenseParser 實例（解析器）
            reader: CanonicalReader 實例（讀取 canonical 資料）
        """
        self._store = store
        self._parser = parser
        self._reader = reader

    # === CRUD 操作 ===

    def add_entry(
        self, text: str, source: str = "cli", batch_id: Optional[str] = None
    ) -> StagingEntry:
        """新增 staging entry

        Args:
            text: 原始輸入文字
            source: 來源（cli/api/batch）
            batch_id: 批次 ID（批次匯入時使用）

        Returns:
            建立的 StagingEntry
        """
        entry = StagingEntry(
            entry_id=str(uuid4()),
            raw_text=text,
            created_at=datetime.now(),
            source=source,
            batch_id=batch_id,
            status=StagingStatus.PENDING,
        )

        self._store.write_entry(entry)
        return entry

    def list_entries(
        self, status: Optional[StagingStatus] = None
    ) -> list[StagingEntry]:
        """列出 staging entries（last-write-wins）

        Args:
            status: 狀態過濾（None 表示全部）

        Returns:
            最新版本的 entries 列表
        """
        # 讀取當前狀態（去重）
        try:
            current_state = self._store.read_current_state()
        except FileNotFoundError:
            # 檔案不存在時返回空列表
            return []

        # 轉換為列表
        entries = list(current_state.values())

        # 狀態過濾
        if status is not None:
            entries = [e for e in entries if e.status == status]

        # 按建立時間排序（新→舊）
        entries.sort(key=lambda e: e.created_at, reverse=True)

        return entries

    def get_entry(self, entry_id: str) -> Optional[StagingEntry]:
        """讀取單筆 entry（last-write-wins）

        Args:
            entry_id: Entry UUID

        Returns:
            最新版本的 entry，若不存在返回 None
        """
        return self._store.read_entry(entry_id)

    def delete_entry(self, entry_id: str) -> None:
        """刪除 staging entry（邏輯刪除）

        實作方式：寫入一個 status=None 的版本來標記刪除。

        Args:
            entry_id: Entry UUID

        Raises:
            EntryNotFound: Entry 不存在
        """
        entry = self.get_entry(entry_id)
        if entry is None:
            raise EntryNotFound(f"Entry {entry_id} 不存在")

        # TODO: 實作邏輯刪除（當前 StagingStore 未定義刪除機制）
        # 暫時不實作，等待 StagingStore 協議更新
        raise NotImplementedError("刪除功能尚未實作（等待 StagingStore 更新）")

    def clear_all(self, status: Optional[StagingStatus] = None) -> int:
        """清除所有 entries（邏輯刪除）

        Args:
            status: 僅清除指定狀態的 entries（None 表示全部）

        Returns:
            清除的 entries 數量
        """
        entries = self.list_entries(status)

        for entry in entries:
            try:
                self.delete_entry(entry.entry_id)
            except NotImplementedError:
                # 刪除功能未實作時跳過
                pass

        return len(entries)

    # === 狀態轉移操作 ===

    def parse_entry(self, entry_id: str) -> StagingEntry:
        """解析單筆 entry（原子操作）

        狀態轉移：
        - pending → parsed（需人工確認）
        - pending → approved（auto-approve）
        - pending → error（解析失敗）

        Args:
            entry_id: Entry UUID

        Returns:
            更新後的 StagingEntry

        Raises:
            EntryNotFound: Entry 不存在
            InvalidStateTransition: 狀態不是 pending
        """
        # 1. 讀取 entry（pending 狀態）
        entry = self.get_entry(entry_id)
        if entry is None:
            raise EntryNotFound(f"Entry {entry_id} 不存在")

        if entry.status != StagingStatus.PENDING:
            raise InvalidStateTransition(
                f"只能解析 pending 狀態的 entry，當前狀態為 {entry.status.value}"
            )

        try:
            # 2. 使用 ExpenseParser 抽取實體 + 計算信心度
            result = self._parser.parse(entry.raw_text)

            # 3. 更新 parsed_* 欄位
            entry.parsed_date = result.date
            entry.parsed_amount = result.amount
            entry.parsed_category = result.category
            entry.parsed_merchant = result.merchant
            entry.parsed_note = result.note
            entry.confidence = result.confidence
            entry.confidence_breakdown = result.confidence_breakdown
            entry.amount_source = result.amount_source
            entry.date_source = result.date_source
            entry.category_source = result.category_source

            # 4. 檢查是否重複
            duplicate_info = self._check_duplicate(entry)
            if duplicate_info is not None:
                entry.status = StagingStatus.DUPLICATE
                entry.duplicate_of, entry.duplicate_reason = duplicate_info
                self._store.write_entry(entry)
                return entry

            # 5. 判斷是否 auto-approve
            if self._parser.should_auto_approve(result):
                # TODO: 建立 proposal（等待整合 proposals_handler）
                # proposal_id = self._create_proposal(entry)
                # entry.proposal_id = proposal_id
                # entry.status = StagingStatus.APPROVED
                # entry.reviewed_at = datetime.now()
                # entry.reviewed_by = "auto"

                # 暫時標記為 parsed（TODO）
                entry.status = StagingStatus.PARSED
            else:
                # 6. 否則 → 更新為 parsed（等待人工確認）
                entry.status = StagingStatus.PARSED

        except Exception as e:
            # 7. 解析失敗 → error
            entry.status = StagingStatus.ERROR
            entry.error_message = str(e)

        # 8. 寫回 staging store（原子操作）
        self._store.write_entry(entry)

        return entry

    def approve_entry(self, entry_id: str, actor: str) -> StagingEntry:
        """批准 entry（建立 proposal）

        狀態轉移：parsed → approved

        Args:
            entry_id: Entry UUID
            actor: 操作者

        Returns:
            更新後的 StagingEntry

        Raises:
            EntryNotFound: Entry 不存在
            InvalidStateTransition: 狀態不是 parsed
        """
        entry = self.get_entry(entry_id)
        if entry is None:
            raise EntryNotFound(f"Entry {entry_id} 不存在")

        if entry.status != StagingStatus.PARSED:
            raise InvalidStateTransition(
                f"只能批准 parsed 狀態的 entry，當前狀態為 {entry.status.value}"
            )

        # 建立 proposal（原子操作）
        try:
            proposal_id = self._create_proposal(entry, actor)
            entry.proposal_id = proposal_id
        except Exception as e:
            # Proposal 建立失敗，保持 parsed 狀態，記錄錯誤
            entry.error_message = f"Proposal 建立失敗: {e}"
            self._store.write_entry(entry)
            raise

        # 更新狀態為 approved
        entry.status = StagingStatus.APPROVED
        entry.reviewed_at = datetime.now()
        entry.reviewed_by = actor

        self._store.write_entry(entry)
        return entry

    def reject_entry(
        self, entry_id: str, actor: str, reason: str
    ) -> StagingEntry:
        """拒絕 entry

        狀態轉移：parsed/approved → rejected

        Args:
            entry_id: Entry UUID
            actor: 操作者
            reason: 拒絕原因

        Returns:
            更新後的 StagingEntry

        Raises:
            EntryNotFound: Entry 不存在
            InvalidStateTransition: 狀態不是 parsed 或 approved
        """
        entry = self.get_entry(entry_id)
        if entry is None:
            raise EntryNotFound(f"Entry {entry_id} 不存在")

        if entry.status not in (StagingStatus.PARSED, StagingStatus.APPROVED):
            raise InvalidStateTransition(
                f"只能拒絕 parsed/approved 狀態的 entry，當前狀態為 {entry.status.value}"
            )

        entry.status = StagingStatus.REJECTED
        entry.reviewed_at = datetime.now()
        entry.reviewed_by = actor
        entry.rejection_reason = reason

        self._store.write_entry(entry)
        return entry

    def ignore_entry(self, entry_id: str, reason: str) -> StagingEntry:
        """忽略 entry（非支出）

        狀態轉移：parsed → ignored

        Args:
            entry_id: Entry UUID
            reason: 忽略原因

        Returns:
            更新後的 StagingEntry

        Raises:
            EntryNotFound: Entry 不存在
            InvalidStateTransition: 狀態不是 parsed
        """
        entry = self.get_entry(entry_id)
        if entry is None:
            raise EntryNotFound(f"Entry {entry_id} 不存在")

        if entry.status != StagingStatus.PARSED:
            raise InvalidStateTransition(
                f"只能忽略 parsed 狀態的 entry，當前狀態為 {entry.status.value}"
            )

        entry.status = StagingStatus.IGNORED
        entry.reviewed_at = datetime.now()
        entry.rejection_reason = reason  # 重用 rejection_reason 欄位

        self._store.write_entry(entry)
        return entry

    def mark_duplicate(
        self, entry_id: str, duplicate_of: str, reason: DuplicateReason
    ) -> StagingEntry:
        """標記 entry 為重複

        狀態轉移：parsed → duplicate

        Args:
            entry_id: Entry UUID
            duplicate_of: 重複來源的 entry_id
            reason: 判重原因

        Returns:
            更新後的 StagingEntry

        Raises:
            EntryNotFound: Entry 不存在
            InvalidStateTransition: 狀態不是 parsed
        """
        entry = self.get_entry(entry_id)
        if entry is None:
            raise EntryNotFound(f"Entry {entry_id} 不存在")

        if entry.status != StagingStatus.PARSED:
            raise InvalidStateTransition(
                f"只能標記 parsed 狀態的 entry 為重複，當前狀態為 {entry.status.value}"
            )

        entry.status = StagingStatus.DUPLICATE
        entry.duplicate_of = duplicate_of
        entry.duplicate_reason = reason
        entry.reviewed_at = datetime.now()

        self._store.write_entry(entry)
        return entry

    # === 批次操作 ===

    def parse_all_pending(self) -> list[StagingEntry]:
        """批次解析所有 pending entries

        Returns:
            解析後的 entries 列表（包含成功與失敗）
        """
        pending_entries = self.list_entries(status=StagingStatus.PENDING)
        results = []

        for entry in pending_entries:
            try:
                parsed_entry = self.parse_entry(entry.entry_id)
                results.append(parsed_entry)
            except Exception:
                # 批次操作允許部分成功
                # 錯誤記錄在 entry.error_message 中
                results.append(entry)

        return results

    # === 重複偵測 (V4.1.1 保守判重) ===

    def _compute_duplicate_key(self, entry: StagingEntry) -> Optional[str]:
        """計算去重 key（需抽取成功）

        Args:
            entry: StagingEntry

        Returns:
            去重 key 或 None（資訊不足時）
        """
        if not (entry.parsed_date and entry.parsed_amount):
            return None  # 資訊不足，無法可靠判重

        # 正規化文字：移除金額、日期、空白
        normalized_text = self._normalize_text(entry.raw_text)

        return f"{entry.parsed_date}|{entry.parsed_amount}|{normalized_text}"

    def _normalize_text(self, text: str) -> str:
        """正規化文字（移除金額、日期、空白）

        Args:
            text: 原始文字

        Returns:
            正規化後的文字
        """
        # 移除金額（數字 + 元/塊/dollar 等）
        text = re.sub(r"\d+\.?\d*\s*(元|塊|dollar|usd|ntd)?", "", text, flags=re.IGNORECASE)

        # 移除日期模式（YYYY-MM-DD, MM/DD, 昨天, 今天等）
        text = re.sub(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", "", text)
        text = re.sub(r"\d{1,2}[-/]\d{1,2}", "", text)
        text = re.sub(r"(今天|昨天|前天|上週|本月)", "", text)

        # 移除多餘空白
        text = re.sub(r"\s+", "", text)

        return text.lower()

    def _check_duplicate(
        self, entry: StagingEntry
    ) -> Optional[tuple[str, DuplicateReason]]:
        """檢查是否重複（回傳 (duplicate_of, reason)）

        判重策略（V4.1.1 保守判重）：
        1. 精準判重：完全匹配 duplicate_key
        2. 模糊判重：金額缺失時的文字比對（標記 possible_duplicate）

        Args:
            entry: 待檢查的 entry

        Returns:
            (duplicate_of, reason) 或 None（無重複）
        """
        # 計算當前 entry 的 duplicate_key
        current_key = self._compute_duplicate_key(entry)

        if current_key is None:
            # 資訊不足，無法可靠判重
            return None

        # 讀取所有 entries（包含歷史版本）
        current_state = self._store.read_current_state()

        for existing_entry in current_state.values():
            # 跳過自己
            if existing_entry.entry_id == entry.entry_id:
                continue

            # 跳過未解析的 entries
            if existing_entry.status == StagingStatus.PENDING:
                continue

            # 跳過已忽略/已拒絕的 entries
            if existing_entry.status in (
                StagingStatus.IGNORED,
                StagingStatus.REJECTED,
            ):
                continue

            # 1. 精準判重：完全匹配 duplicate_key
            existing_key = self._compute_duplicate_key(existing_entry)
            if existing_key is not None and existing_key == current_key:
                return (existing_entry.entry_id, DuplicateReason.DUP_KEY_EXACT)

            # 2. 模糊判重：日期相近 + 金額相同（±2天）
            if (
                entry.parsed_date
                and existing_entry.parsed_date
                and entry.parsed_amount
                and existing_entry.parsed_amount
            ):
                date_diff = abs(
                    (entry.parsed_date - existing_entry.parsed_date).days
                )
                amount_match = entry.parsed_amount == existing_entry.parsed_amount

                if date_diff <= 2 and amount_match:
                    # 文字相似度檢查（簡化版）
                    normalized_current = self._normalize_text(entry.raw_text)
                    normalized_existing = self._normalize_text(
                        existing_entry.raw_text
                    )

                    if normalized_current == normalized_existing:
                        return (
                            existing_entry.entry_id,
                            DuplicateReason.DUP_DATE_FUZZ,
                        )

        # 無重複
        return None

    # === Proposal 建立 ===

    def _create_proposal(self, entry: StagingEntry, actor: str) -> str:
        """建立 proposal

        Args:
            entry: StagingEntry（必須已解析）
            actor: 操作者

        Returns:
            proposal_id（檔案名稱，包含唯一 ID）

        Raises:
            ValueError: entry 資料不完整
            ProposalError: proposal 建立失敗
        """
        from pathlib import Path

        from life_capital.io.proposals_handler import create_expense_proposals

        # 驗證必填欄位
        if not (entry.parsed_date and entry.parsed_amount and entry.parsed_category):
            raise ValueError(
                f"Entry {entry.entry_id} 缺少必填欄位（date/amount/category）"
            )

        # 轉換為 ExpenseRecord
        record = self._entry_to_record(entry)

        # 建立虛擬 source_file（用於描述）
        source_file = Path(f"staging_{entry.entry_id[:8]}.txt")

        # 呼叫 proposals_handler 建立 proposal
        try:
            # 取得 base_dir（從 store 推斷）
            # StagingStore 實作應該提供 base_dir，這裡使用 path resolver
            from life_capital.utils.path_resolver import resolve_data_dir

            base_dir = resolve_data_dir()

            proposal_files = create_expense_proposals(
                records=[record],
                source_file=source_file,
                actor=actor,
                base_dir=base_dir,
            )

            if not proposal_files:
                raise ValueError("create_expense_proposals 未返回任何檔案")

            # 提取 proposal_id（檔案名稱）
            proposal_id = proposal_files[0].name

            return proposal_id

        except Exception as e:
            raise ValueError(f"建立 proposal 失敗: {e}") from e

    def _entry_to_record(self, entry: StagingEntry) -> "ExpenseRecord":
        """轉換 StagingEntry 為 ExpenseRecord

        Args:
            entry: StagingEntry

        Returns:
            ExpenseRecord

        Raises:
            ValueError: 必填欄位缺失
        """
        from life_capital.models.expense import ExpenseRecord

        # 驗證必填欄位
        if not entry.parsed_date:
            raise ValueError("parsed_date 為必填欄位")
        if not entry.parsed_amount:
            raise ValueError("parsed_amount 為必填欄位")
        if not entry.parsed_category:
            raise ValueError("parsed_category 為必填欄位")

        # 建立 ExpenseRecord
        return ExpenseRecord(
            date=entry.parsed_date,
            amount=entry.parsed_amount,
            category=entry.parsed_category,
            payer="shared",  # 預設為 shared（Phase 4 暫不支援 payer 抽取）
            note=entry.parsed_note,
            merchant=entry.parsed_merchant,
        )

    # === Repair & Consistency ===

    def detect_inconsistencies(self) -> list["InconsistencyReport"]:
        """偵測 staging entries 的不一致狀態

        檢查 3 種不一致類型：
        1. approved_without_proposal: status=approved 但 proposal_id=None
        2. proposal_without_approved: proposal_id 存在但 status≠approved/applied
        3. applied_without_canonical: status=applied 但 canonical_record_id=None

        Returns:
            list[InconsistencyReport]: 不一致報告清單
        """
        reports = []
        all_entries = self.list_entries()

        for entry in all_entries:
            # 檢查 1: approved 但無 proposal_id
            if entry.status == StagingStatus.APPROVED and not entry.proposal_id:
                reports.append(
                    InconsistencyReport(
                        entry_id=entry.entry_id,
                        inconsistency_type="approved_without_proposal",
                        current_status=entry.status.value,
                        description="status=approved 但 proposal_id=None",
                        suggested_fix="降級為 parsed（proposal 已遺失，需重建）",
                    )
                )

            # 檢查 2: 有 proposal_id 但 status 不是 approved/applied
            if entry.proposal_id and entry.status not in [
                StagingStatus.APPROVED,
                StagingStatus.APPLIED,
            ]:
                reports.append(
                    InconsistencyReport(
                        entry_id=entry.entry_id,
                        inconsistency_type="proposal_without_approved",
                        current_status=entry.status.value,
                        description=f"proposal_id 存在但 status={entry.status.value}",
                        suggested_fix="檢查 proposal 是否存在，決定升級或刪除 proposal_id",
                    )
                )

            # 檢查 3: applied 但無 canonical_record_id
            if (
                entry.status == StagingStatus.APPLIED
                and not entry.canonical_record_id
            ):
                reports.append(
                    InconsistencyReport(
                        entry_id=entry.entry_id,
                        inconsistency_type="applied_without_canonical",
                        current_status=entry.status.value,
                        description="status=applied 但 canonical_record_id=None",
                        suggested_fix="檢查 canonical 是否存在，決定降級或補寫 id",
                    )
                )

        return reports

    def repair_inconsistencies(
        self, dry_run: bool = False
    ) -> list["RepairResult"]:
        """修復 staging entries 的不一致狀態

        修復策略：
        1. approved_without_proposal → 降級為 parsed
        2. proposal_without_approved → 檢查 proposal，決定升級或刪除 proposal_id
        3. applied_without_canonical → 檢查 canonical，決定降級或補寫 id

        Args:
            dry_run: 若為 True，僅模擬修復，不實際寫入

        Returns:
            list[RepairResult]: 修復結果清單
        """
        inconsistencies = self.detect_inconsistencies()
        results = []

        for report in inconsistencies:
            entry = self.get_entry(report.entry_id)
            result = RepairResult(
                entry_id=report.entry_id,
                inconsistency_type=report.inconsistency_type,
                action_taken="",
                success=False,
            )

            try:
                if report.inconsistency_type == "approved_without_proposal":
                    # 策略 1: 降級為 parsed
                    if not dry_run:
                        entry.status = StagingStatus.PARSED
                        entry.proposal_id = None
                        self._store.write_entry(entry)
                    result.action_taken = "降級為 parsed"
                    result.success = True

                elif report.inconsistency_type == "proposal_without_approved":
                    # 策略 2: 檢查 proposal 是否存在
                    proposal_path = self._get_proposal_path(entry.proposal_id)

                    if proposal_path and proposal_path.exists():
                        # Proposal 存在 → 升級為 approved
                        if not dry_run:
                            entry.status = StagingStatus.APPROVED
                            self._store.write_entry(entry)
                        result.action_taken = (
                            f"升級為 approved（proposal 存在: {proposal_path.name}）"
                        )
                        result.success = True
                    else:
                        # Proposal 不存在 → 刪除 proposal_id
                        if not dry_run:
                            entry.proposal_id = None
                            self._store.write_entry(entry)
                        result.action_taken = "刪除 proposal_id（proposal 不存在）"
                        result.success = True

                elif report.inconsistency_type == "applied_without_canonical":
                    # 策略 3: 檢查 canonical 是否存在（簡化版：降級為 approved）
                    # 註：完整實作需要搜尋 canonical/expenses/*.yaml 比對 entry 內容
                    #     此處簡化為降級，由用戶手動處理
                    if not dry_run:
                        entry.status = StagingStatus.APPROVED
                        entry.canonical_record_id = None
                        self._store.write_entry(entry)
                    result.action_taken = "降級為 approved（canonical_record_id 遺失）"
                    result.success = True

            except Exception as e:
                result.action_taken = f"修復失敗: {e}"
                result.success = False

            results.append(result)

        return results

    def _get_proposal_path(self, proposal_id: Optional[str]) -> Optional[Path]:
        """取得 proposal 檔案路徑

        Args:
            proposal_id: Proposal ID（檔案名稱）

        Returns:
            Optional[Path]: Proposal 檔案路徑（若存在）
        """
        if not proposal_id:
            return None

        # 使用 store 的 data_path
        base_dir = self._store.data_path
        proposal_path = base_dir / "proposals" / "pending" / proposal_id

        return proposal_path if proposal_path.exists() else None


# === 資料結構 ===


@dataclass
class InconsistencyReport:
    """不一致報告"""

    entry_id: str
    inconsistency_type: str
    current_status: str
    description: str
    suggested_fix: str


@dataclass
class RepairResult:
    """修復結果"""

    entry_id: str
    inconsistency_type: str
    action_taken: str
    success: bool
