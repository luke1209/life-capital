# Phase 4 CAPTURE 測試說明

## 實體抽取器測試 (`test_entity_extractor.py`)

### 測試涵蓋範圍

**總測試案例**: 44 個

#### 1. 金額抽取測試 (12 個)
- ✅ 精確金額（含/不含貨幣符號）
- ✅ 千分位分隔符正規化
- ✅ 全形數字正規化
- ✅ 中文數字不支援
- ✅ 範圍取值（100-120 → 110）
- ✅ 約略金額（約 120）
- ✅ 負數與退款關鍵字
- ✅ 無金額情境
- ✅ 多筆金額處理
- ✅ 外幣偵測（部分支援）

#### 2. 日期抽取測試 (8 個)
- ✅ 相對日期（今天、昨天、前天）
- ✅ 完整日期（YYYY-MM-DD, YYYY/MM/DD）
- ✅ 不完整日期推斷（MM/DD → 推斷年份）
- ✅ 只有月份（8月 → 8/1）
- ✅ 節慶不支援
- ✅ 週期性不支援
- ✅ 週幾相對日期（上週五）
- ✅ 無日期情境

#### 3. 類別抽取測試 (5 個)
- ✅ 完全匹配 expense_policy
- ✅ 模糊匹配
- ✅ 商家當類別處理
- ✅ 類別優先於商家
- ✅ 無類別情境

#### 4. 商家抽取測試 (4 個)
- ✅ 基本商家抽取
- ✅ 移除金額後抽取
- ✅ 移除類別後抽取
- ✅ 無商家情境

#### 5. 輸入異常處理 (9 個 V3 邊緣情境)
- ✅ 空字串
- ✅ 超長文本（>500 字元）
- ✅ 非支出（收入）識別
- ✅ emoji 輸入
- ✅ 中英混雜
- ✅ 僅空白
- ✅ 特殊符號
- ✅ 多種貨幣符號
- ✅ 小數金額

#### 6. extract_all() 整合測試 (4 個)
- ✅ 完整資訊抽取
- ✅ 部分資訊抽取
- ✅ 複雜情境
- ✅ 退款情境

#### 7. Decimal 護欄測試 (2 個)
- ✅ 確保金額回傳 Decimal 型別
- ✅ 確保無 float 運算

### 執行測試

```bash
# 執行實體抽取器測試
uv run pytest tests/capture/test_entity_extractor.py -v

# 快速執行（不顯示詳細）
uv run pytest tests/capture/test_entity_extractor.py -q

# 執行特定測試類別
uv run pytest tests/capture/test_entity_extractor.py::TestAmountExtraction -v
```

### 預期覆蓋率

**目標**: >90% 覆蓋率

**關鍵路徑**:
- 所有公開方法（extract_amount, extract_date, extract_category, extract_merchant, extract_all）
- 所有 Source enum 回傳路徑
- 所有邊緣情境處理邏輯

### 測試設計原則

1. **隔離性**: 使用 MockCanonicalReader，不依賴真實資料
2. **完整性**: 涵蓋所有 V3 邊緣情境規劃
3. **可維護性**: 測試分類清晰，易於擴展
4. **文件化**: 每個測試都有清晰的 docstring

### V3 邊緣情境對照表

| 規劃項目 | 測試案例 | 狀態 |
|----------|----------|------|
| 金額：含分隔符 | `test_amount_with_separator` | ✅ |
| 金額：全形數字 | `test_fullwidth_digits` | ✅ |
| 金額：中文數字 | `test_chinese_numerals_not_supported` | ✅ |
| 金額：範圍 | `test_amount_range` | ✅ |
| 金額：約略 | `test_approximate_amount` | ✅ |
| 金額：負數/退款 | `test_negative_amount`, `test_refund_keyword` | ✅ |
| 日期：不完整 | `test_incomplete_date` | ✅ |
| 日期：只有月份 | `test_month_only` | ✅ |
| 日期：節慶 | `test_festival_not_supported` | ✅ |
| 日期：週期性 | `test_periodic_not_supported` | ✅ |
| 日期：週幾相對 | `test_weekday_relative` | ✅ |
| 類別：商家衝突 | `test_merchant_as_category` | ✅ |
| 輸入：空字串 | `test_empty_string` | ✅ |
| 輸入：超長文本 | `test_long_text` | ✅ |
| 輸入：非支出 | `test_non_expense_income` | ✅ |
| 輸入：emoji | `test_emoji_input` | ✅ |
| 輸入：中英混雜 | `test_mixed_language` | ✅ |

### 已知限制

1. **外幣判斷**: 目前只能抽取數字，無法完全判斷外幣類型（USD/JPY 等）
2. **中文數字**: 不支援「一百二十」等中文數字表達
3. **節慶日期**: 不支援「中秋」、「端午」等節慶關鍵字
4. **週期性**: 不支援「每週五」等週期性表達

這些限制在規劃文件中已標註為「不支援」，未來可根據需求逐步改進。
