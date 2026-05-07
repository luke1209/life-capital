# Contract 變更日誌

> 記錄 Schema Contract 與 IO Contract 的變更歷程

## 格式說明

每個條目包含：
- **版本/日期**
- **變更類型**: Breaking / Compatible / Clarification
- **影響範圍**: Schema / IO / Interface
- **說明**

---

## [1.2.0] - 2025-12-29

### Breaking - LifeAssumptions Schema V1.1 → V1.2

- **類型**: Breaking
- **影響範圍**: Schema
- **影響模型/檔案**: `LifeAssumptions`, `life_assumptions.yaml`
- **說明**:
  - 新增 `Member` 類別，使用 `birth_year` 取代 `current_age`
  - 新增 `members: dict[str, Member]` 結構支援多成員
  - `Basic` 新增 `primary_member` 欄位指向 members 中的主要成員
  - `members` 與 legacy 欄位 (`current_age`/`retirement_age`/`expected_lifespan`) 互斥
  - 年齡計算以 `metadata.base_year` 為權威時間軸
- **遷移方式**:
  1. 執行 `lc migrate --dry-run` 預覽變更
  2. 確認後執行 `lc migrate` 自動升級
  3. 檢查 `birth_year_estimated: true` 的成員，確認/修正 `birth_year` 值
  4. 若從 `current_age=35, base_year=2024` 遷移：
     - `birth_year = base_year - current_age = 1989`
     - ⚠️ 可能有 ±1 年誤差（取決於生日是否已過）
- **新增欄位**:
  - `members.<member_id>.display_name`: UI 顯示名稱
  - `members.<member_id>.birth_year`: 出生年份
  - `members.<member_id>.retirement_age`: 退休年齡
  - `members.<member_id>.expected_lifespan`: 預期壽命
  - `members.<member_id>.birth_year_estimated`: 是否為推算值
  - `basic.primary_member`: 主要成員 ID

---

## [1.0.0] - 2025-12-28

### Added - 初版建立

#### Schema Contract (`schema_contract.md`)
- **類型**: Clarification
- **說明**: 定義 Pydantic 模型的變更規則
- **涵蓋模型**:
  - `ExpensePolicy`, `LifeAssumptions`, `MonthlyIncome`
  - `Transaction`, `Expense`, `MonthlyExpenses`
  - `Operation`, `Provenance`, `Scenario`

#### IO Contract (`io_contract.md`)
- **類型**: Clarification
- **說明**: 定義 Normative vs Illustrative 分層
- **Normative 項目**:
  - 檔名 pattern
  - 必要欄位
  - Provenance sidecar
  - Hash 規格
  - 路徑契約
- **Illustrative 項目**:
  - 報表文案
  - 表格欄位順序
  - Markdown 格式
  - JSON/YAML 序列化順序

#### Interface Policy (`interface_policy.md`)
- **類型**: Clarification
- **說明**: 定義 `interfaces/` 層的演進規則
- **Protocol**: `CanonicalReader` v1.0

---

## 變更模板

```markdown
## [X.Y.Z] - YYYY-MM-DD

### Type - Brief Description

- **類型**: Breaking / Compatible / Clarification
- **影響範圍**: Schema / IO / Interface
- **影響模型/檔案**:
- **說明**:
- **遷移方式**:（若 Breaking）
```

---

## 審核要求

| 變更類型 | CODEOWNERS | Label |
|----------|------------|-------|
| Breaking | 雙人 | `contract-breaking` |
| Compatible | 單人 | `contract-approved` |
| Clarification | 無 | 無 |
