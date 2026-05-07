# Phase 4 CAPTURE - 狀態機契約測試快速參考

## 快速開始

### 執行所有狀態機測試

```bash
# 執行完整測試套件（43 個測試）
uv run pytest tests/contracts/test_staging_state_machine.py -v

# 執行特定測試類別
uv run pytest tests/contracts/test_staging_state_machine.py::TestValidStateTransitions -v
uv run pytest tests/contracts/test_staging_state_machine.py::TestInvalidStateTransitions -v
uv run pytest tests/contracts/test_staging_state_machine.py::TestTerminalState -v

# 執行特定測試
uv run pytest tests/contracts/test_staging_state_machine.py::TestValidStateTransitions::test_pending_to_parsed -v
```

## 測試結構

### 6 個主要測試類別

| 類別 | 測試數 | 目的 |
|------|--------|------|
| **TestValidStateTransitions** | 14 | 驗證所有合法狀態轉移 |
| **TestInvalidStateTransitions** | 17 | 驗證非法轉移拋出異常 |
| **TestTerminalState** | 3 | 驗證 applied 終態 |
| **TestStateTransitionMatrix** | 2 | 驗證轉移矩陣完整性 |
| **TestExceptionHandling** | 3 | 驗證異常訊息質量 |
| **TestEdgeCases** | 4 | 驗證邊界情況 |

## 狀態轉移速查表

### 允許的轉移

```
pending   ─┬─→ parsed
          ├─→ error
          ├─→ approved
          └─→ duplicate

parsed    ─┬─→ approved
          ├─→ rejected
          ├─→ ignored
          └─→ duplicate

error     ─→ pending

approved  ─┬─→ applied [終態]
          └─→ rejected

rejected  ─→ pending

ignored   ─→ pending

duplicate ─→ approved

applied   ─→ [無] (終態)
```

### 禁止的轉移

```
parsed   ✗ → parsed          (不可重複解析)
error    ✗ → approved        (不可跳過 parsed)
error    ✗ → rejected        (不可直接拒絕)
approved ✗ → parsed          (已批准不可重新解析)
approved ✗ → ignored         (已批准不可忽略)
rejected ✗ → approved        (已拒絕不可直接批准)
ignored  ✗ → approved        (已忽略不可直接批准)
duplicate ✗ → parsed         (重複不可重新解析)
duplicate ✗ → rejected       (重複不可直接拒絕)
duplicate ✗ → ignored        (重複不可忽略)
pending  ✗ → approved        (不可跳過 parsed)
pending  ✗ → rejected        (未解析不可拒絕)
pending  ✗ → ignored         (未解析不可忽略)
pending  ✗ → duplicate       (未解析不可標記重複)
applied  ✗ → *               (終態不可任何轉移)
```

## 測試使用場景

### 場景 1: 驗證完整工作流

```python
def test_complete_workflow(service):
    """pending → parsed → approved → applied"""
    entry = service.add_entry("昨天拉麵 320 元 餐飲")
    assert entry.status == StagingStatus.PENDING

    # ✅ 解析
    parsed = service.parse_entry(entry.entry_id)
    assert parsed.status == StagingStatus.PARSED

    # ✅ 批准
    approved = service.approve_entry(entry.entry_id, actor="person_a")
    assert approved.status == StagingStatus.APPROVED

    # ✅ Apply（外部）
    entry_obj = service.get_entry(entry.entry_id)
    entry_obj.status = StagingStatus.APPLIED
    service._store.write_entry(entry_obj)
    assert entry_obj.status == StagingStatus.APPLIED
```

### 場景 2: 驗證非法轉移

```python
def test_invalid_transition(service):
    """pending 不能直接 → approved"""
    entry = service.add_entry("昨天拉麵 320 元 餐飲")

    # ❌ 拋出 InvalidStateTransition
    with pytest.raises(InvalidStateTransition):
        service.approve_entry(entry.entry_id, actor="person_a")
```

### 場景 3: 驗證終態

```python
def test_terminal_state(service):
    """applied 不可轉移到任何其他狀態"""
    # 設定為 applied
    entry_obj.status = StagingStatus.APPLIED
    service._store.write_entry(entry_obj)

    # ❌ 任何操作都會失敗
    with pytest.raises(InvalidStateTransition):
        service.parse_entry(entry.entry_id)

    with pytest.raises(InvalidStateTransition):
        service.reject_entry(entry.entry_id, actor="person_a", reason="test")
```

## 異常類型

### InvalidStateTransition

當嘗試非法狀態轉移時拋出：

```python
from life_capital.capture.staging_service import InvalidStateTransition

try:
    service.parse_entry(already_parsed_entry.entry_id)
except InvalidStateTransition as e:
    print(f"錯誤: {e}")  # 輸出: "只能解析 pending 狀態的 entry，當前狀態為 parsed"
```

### EntryNotFound

當 entry_id 不存在時拋出：

```python
from life_capital.capture.staging_service import EntryNotFound

try:
    service.parse_entry("nonexistent-id")
except EntryNotFound as e:
    print(f"錯誤: {e}")  # 輸出: "Entry nonexistent-id 不存在"
```

## 測試統計

```
總測試數：43
✅ 通過：43
❌ 失敗：0
⏱️ 執行時間：~0.09 秒

類別分布：
- 合法轉移：14 個
- 非法轉移：17 個
- 終態測試：3 個
- 轉移矩陣：2 個
- 異常處理：3 個
- 邊界情況：4 個
```

## 常見測試模式

### 模式 1: 驗證單一轉移

```python
def test_parse_to_approved(service):
    entry = service.add_entry("昨天拉麵 320 元 餐飲")
    service.parse_entry(entry.entry_id)

    approved = service.approve_entry(entry.entry_id, actor="person_a")
    assert approved.status == StagingStatus.APPROVED
```

### 模式 2: 驗證禁止轉移

```python
def test_invalid_transition(service):
    entry = service.add_entry("test")

    with pytest.raises(InvalidStateTransition):
        service.approve_entry(entry.entry_id, actor="person_a")
```

### 模式 3: 驗證終態

```python
def test_terminal_state(service):
    # 設定為終態
    entry_obj.status = StagingStatus.APPLIED
    service._store.write_entry(entry_obj)

    # 驗證任何轉移都失敗
    operations = [
        lambda: service.parse_entry(entry.entry_id),
        lambda: service.reject_entry(entry.entry_id, actor="person_a", reason="test"),
    ]

    for op in operations:
        with pytest.raises(InvalidStateTransition):
            op()
```

## 導入依賴

```python
from life_capital.capture.staging_service import (
    InvalidStateTransition,
    EntryNotFound,
    StagingService,
)
from life_capital.capture.models import (
    DuplicateReason,
    StagingEntry,
    StagingStatus,
)
```

## 調試技巧

### 查看 entry 當前狀態

```python
entry = service.get_entry(entry_id)
print(f"狀態: {entry.status}")
print(f"信心度: {entry.confidence}")
print(f"解析結果: {entry.parsed_date}, {entry.parsed_amount}, {entry.parsed_category}")
```

### 檢查異常訊息

```python
try:
    service.parse_entry(entry.entry_id)
except InvalidStateTransition as e:
    print(str(e))  # 完整的錯誤訊息
    assert "parsed" in str(e).lower()  # 驗證訊息內容
```

### 驗證狀態轉移序列

```python
entry = service.add_entry("test")
print(f"1. {entry.status}")  # PENDING

entry = service.parse_entry(entry.entry_id)
print(f"2. {entry.status}")  # PARSED

entry = service.approve_entry(entry.entry_id, actor="person_a")
print(f"3. {entry.status}")  # APPROVED
```

## 相關文件

- **實作代碼**: `life_capital/capture/staging_service.py`
- **模型定義**: `life_capital/capture/models.py`
- **詳細報告**: `tests/contracts/STAGING_STATE_MACHINE_TESTS.md`
- **狀態機設計**: 見本文件頂部的狀態轉移圖

## 常見問題

### Q: 為什麼不能直接從 pending → approved？
**A**: 因為 approved 需要 proposal 建立，而 proposal 需要解析完的資料（date/amount/category）。必須先經過 parsed。

### Q: 為什麼 applied 是終態？
**A**: 因為 applied 表示資料已進入 canonical（主資料庫），不應再在 staging 中修改。所有修改應在 canonical 層級進行。

### Q: 如何測試 duplicate 的自動判重？
**A**: 新增兩筆相同內容的 entry，第二筆 parse 時會自動標記為 duplicate。

### Q: 如何恢復 rejected/ignored 的 entry？
**A**: 當前設計允許回到 pending 重新處理，但 API 層面未完全實現。可透過編輯或還原操作實現。

## 版本資訊

- **最後更新**: 2025-12-28
- **測試版本**: V4.1.1
- **狀態機版本**: V4.1.1
- **狀態數**: 8 個
- **終態**: 1 個 (applied)

---

**提示**: 執行 `uv run pytest tests/contracts/test_staging_state_machine.py -v` 查看所有測試的詳細輸出。
