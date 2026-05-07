"""Seed Data Builder for testing

生成測試資料，遵守 CLAUDE.md 護欄規則。
"""

import csv
import hashlib
import json
import os
import random
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from uuid import UUID

from life_capital.advisor.schemas import AdvisorProposalPayload, DecisionOptionSchema
from life_capital.io.raw_handler import save_raw_manifest
from life_capital.io.registry import (
    CANONICAL_DIR,
    CURRENT_SCHEMA_VERSION,
    EXPENSE_FILE_PATTERN,
    OPERATION_LOG_FILE,
    PROPOSALS_PENDING_DIR,
    RAW_DIR,
    RAW_IMPORTS_DIR,
    RAW_MANIFEST_FILE,
)
from life_capital.io.yaml_handler import load_yaml, save_model, save_yaml
from life_capital.models.assumptions import (
    Basic,
    Calculation,
    Currency,
    LifeAssumptions,
    Member,
    Metadata,
    Rates,
    RatesMode,
    RoundingMethod,
    RoundingStage,
)
from life_capital.models.income import IncomeSource, MonthlyIncome
from life_capital.models.operation import (
    Operation,
    OperationLogEntry,
    OperationType,
    Provenance,
    SourceType,
)
from life_capital.models.targets import LifetimeTargets, Priority, Target, TargetCategory


class SeedDataBuilder:
    """測試資料建構器

    使用 Fluent API 設定參數，然後建立最小或完整的測試資料集。

    Examples:
        >>> builder = SeedDataBuilder(base_dir=Path("./test_data"))
        >>> builder.with_months(3).build_minimal()
        >>> builder.with_months(7).build_full()
    """

    def __init__(self, base_dir: Path, seed: int = 42, profile: str = "full"):
        """初始化資料目錄

        Args:
            base_dir: 測試資料目錄路徑
        """
        self.base_dir = base_dir
        self.months = 1  # 預設 1 個月
        self.seed = seed
        self.profile = profile
        self.rng = random.Random(seed)
        self.base_time = datetime(2024, 12, 31, 0, 0, 0, tzinfo=timezone.utc)
        self._time_offset = 0
        self._id_counter = 0
        self.seed_refs: dict[str, str] = {}

    def _next_time(self, seconds: int = 1) -> datetime:
        """產生固定遞增的時間戳（決定論）"""
        current = self.base_time + timedelta(seconds=self._time_offset)
        self._time_offset += seconds
        return current

    def _next_uuid(self) -> str:
        """產生可重建的 UUID（決定論）"""
        return str(UUID(int=self.rng.getrandbits(128)))

    def _next_hex(self, length: int = 8) -> str:
        """產生可重建的 hex token"""
        alphabet = "0123456789abcdef"
        return "".join(self.rng.choice(alphabet) for _ in range(length))

    def _next_ulid(self) -> str:
        """產生可重建的 ULID（26 字元 Base32）"""
        alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
        return "".join(self.rng.choice(alphabet) for _ in range(26))

    def _iso(self, dt: datetime) -> str:
        """固定格式 ISO 8601（UTC +00:00）"""
        return dt.isoformat()

    def with_months(self, months: int) -> "SeedDataBuilder":
        """設定要生成的月份數量

        Args:
            months: 月份數量（1-12）

        Returns:
            Self (for chaining)
        """
        if months < 1 or months > 12:
            raise ValueError("months 必須在 1-12 之間")
        self.months = months
        return self

    def build_minimal(self) -> Path:
        """建立最小資料集（1 個月）

        Returns:
            資料目錄路徑
        """
        self.with_months(1)
        return self._build_dataset(year=2024, start_month=12, month_count=1)

    def build_full(self) -> Path:
        """建立完整資料集（7 個月：2024-06 ~ 2024-12）

        Returns:
            資料目錄路徑
        """
        self.with_months(7)
        return self._build_dataset(year=2024, start_month=6, month_count=7)

    def build_seed(
        self,
        phases: str = "all",
        profile: Optional[str] = None,
        with_staging: bool = True,
        with_advisor: bool = True,
    ) -> Path:
        """建立完整種子資料（Phase 1 ~ Phase 5 Stage 2）

        Args:
            phases: all 或以逗號分隔的 phase 編號（1,2,3,4,5）
            profile: seed profile（smoke/full）
            with_staging: 是否包含 Phase 4 staging
            with_advisor: 是否包含 Phase 5 advisor

        Returns:
            資料目錄路徑
        """
        if profile:
            self.profile = profile

        phases_set = {p.strip() for p in phases.split(",")}
        if "all" in phases_set:
            phases_set = {"1", "2", "3", "4", "5"}

        self._build_dataset(
            year=2024,
            start_month=6,
            month_count=self.months,
            write_raw_manifest=False,
        )

        if "1" in phases_set:
            self._write_dedupe_raw_imports()
        if "4" in phases_set and with_staging:
            self._write_staging_entries()
        if "5" in phases_set and with_advisor:
            self._write_advisor_seed()

        self._write_schema_fixtures()
        self._write_raw_manifest_deterministic()
        self._write_seed_manifest(phases_set)
        self._write_seed_lock()

        return self.base_dir

    # === 內部實作 ===

    def _build_dataset(
        self,
        year: int,
        start_month: int,
        month_count: int,
        write_raw_manifest: bool = True,
    ) -> Path:
        """建立資料集

        Args:
            year: 年份
            start_month: 起始月份
            month_count: 月份數量
            write_raw_manifest: 是否寫入 raw_manifest.json

        Returns:
            資料目錄路徑
        """
        # 建立完整目錄結構（包含空目錄）
        canonical_dir = self.base_dir / CANONICAL_DIR
        canonical_expenses_dir = canonical_dir / "expenses"
        canonical_decisions_dir = canonical_dir / "decisions"
        raw_imports_dir = self.base_dir / RAW_IMPORTS_DIR
        raw_manual_dir = self.base_dir / RAW_DIR / "manual"
        derived_dir = self.base_dir / "derived"
        derived_reports_dir = derived_dir / "reports"
        derived_scenarios_dir = derived_dir / "scenarios"
        derived_logs_dir = derived_dir / "logs"
        staging_dir = self.base_dir / "staging"
        proposals_pending_dir = self.base_dir / PROPOSALS_PENDING_DIR

        # 建立所有目錄
        canonical_dir.mkdir(parents=True, exist_ok=True)
        canonical_expenses_dir.mkdir(parents=True, exist_ok=True)
        canonical_decisions_dir.mkdir(parents=True, exist_ok=True)
        raw_imports_dir.mkdir(parents=True, exist_ok=True)
        raw_manual_dir.mkdir(parents=True, exist_ok=True)
        derived_dir.mkdir(parents=True, exist_ok=True)
        derived_reports_dir.mkdir(parents=True, exist_ok=True)
        derived_scenarios_dir.mkdir(parents=True, exist_ok=True)
        derived_logs_dir.mkdir(parents=True, exist_ok=True)
        staging_dir.mkdir(parents=True, exist_ok=True)
        proposals_pending_dir.mkdir(parents=True, exist_ok=True)

        # 寫入配置檔案（直接在 base_dir 下，不在 canonical/）
        self._write_life_assumptions(self.base_dir)
        self._write_monthly_income(self.base_dir)
        self._write_expense_policy(self.base_dir)
        self._write_lifetime_targets(self.base_dir)

        # 寫入月度支出
        for i in range(month_count):
            month = start_month + i
            if month > 12:
                year += 1
                month = month - 12
            self._write_monthly_expenses(year, month, canonical_expenses_dir, raw_imports_dir)

        # 生成 raw_manifest.json
        if write_raw_manifest:
            self._write_raw_manifest()

        # 初始化 operation log（空檔案）
        operation_log = self.base_dir / OPERATION_LOG_FILE
        operation_log.parent.mkdir(parents=True, exist_ok=True)
        if not operation_log.exists():
            operation_log.touch()

        return self.base_dir

    def _write_life_assumptions(self, canonical_dir: Path) -> None:
        """生成 life_assumptions.yaml（V1.2 members 結構）

        成員資訊：
        - Person A: 1990 年生，90 歲退休，95 歲壽命
        - Person B: 1992 年生，65 歲退休，90 歲壽命
        """
        assumptions = LifeAssumptions(
            schema_version=CURRENT_SCHEMA_VERSION,
            metadata=Metadata(
                currency=Currency.TWD,
                base_year=2024,
            ),
            basic=Basic(
                primary_member="person_a",
            ),
            members={
                "person_a": Member(
                    display_name="Person A",
                    birth_year=1981,
                    retirement_age=90,
                    expected_lifespan=95,
                ),
                "person_b": Member(
                    display_name="Person B",
                    birth_year=1993,
                    retirement_age=65,
                    expected_lifespan=90,
                ),
            },
            rates=Rates(
                mode=RatesMode.NOMINAL,
                annual_inflation=0.02,
                nominal_investment_return=0.05,
            ),
            calculation=Calculation(
                scale=0,
                rounding=RoundingMethod.ROUND_HALF_UP,
                rounding_stage=RoundingStage.FINAL,
            ),
        )

        save_model(canonical_dir / "life_assumptions.yaml", assumptions)

    def _write_monthly_income(self, canonical_dir: Path) -> None:
        """生成 monthly_income.yaml（person_a 85K, person_b 55K）"""
        income = MonthlyIncome(
            schema_version=CURRENT_SCHEMA_VERSION,
            sources=[
                IncomeSource(
                    name="Person A Salary",
                    amount=60000,
                    frequency="monthly",
                    owner="person_a",
                ),
                IncomeSource(
                    name="Person B Salary",
                    amount=55000,
                    frequency="monthly",
                    owner="person_b",
                ),
            ],
        )

        save_model(canonical_dir / "monthly_income.yaml", income)

    def _write_expense_policy(self, canonical_dir: Path) -> None:
        """生成 expense_policy.yaml（10 類別）"""
        # 10 個類別及其占比（總和 = 1.0）
        categories = {
            "housing": 0.20,  # 28K / 140K
            "food": 0.107,  # 15K / 140K
            "transportation": 0.013,  # 1.8K / 140K
            "utilities": 0.019,  # 2.65K / 140K
            "entertainment": 0.0036,  # 500 / 140K
            "dining_out": 0.013,  # 1.8K / 140K
            "shopping": 0.018,  # 2.5K / 140K
            "savings": 0.107,  # 15K / 140K
            "investment": 0.107,  # 15K / 140K
            "insurance": 0.279,  # 39K / 140K（12 月特殊）
        }

        # 調整為三個群組
        policy_data = {
            "schema_version": CURRENT_SCHEMA_VERSION,
            "metadata": {
                "ratio_base": "income",
                "allow_partial": True,
            },
            "categories": {
                "必要": {
                    "housing": categories["housing"],
                    "food": categories["food"],
                    "transportation": categories["transportation"],
                    "utilities": categories["utilities"],
                },
                "選擇性": {
                    "entertainment": categories["entertainment"],
                    "dining_out": categories["dining_out"],
                    "shopping": categories["shopping"],
                },
                "儲蓄投資": {
                    "savings": categories["savings"],
                    "investment": categories["investment"],
                    "insurance": categories["insurance"],
                },
            },
            "flexibility": {
                "必要": 0.05,
                "選擇性": 0.10,
                "儲蓄投資": 0.15,
            },
            "uncategorized_handling": "warn",
        }

        save_yaml(canonical_dir / "expense_policy.yaml", policy_data)

    def _write_lifetime_targets(self, canonical_dir: Path) -> None:
        """生成 lifetime_targets.yaml（4 個目標）"""
        current_year = datetime.now().year
        targets = LifetimeTargets(
            schema_version=CURRENT_SCHEMA_VERSION,
            targets=[
                Target(
                    name="Emergency Fund",
                    category=TargetCategory.RETIREMENT,
                    priority=Priority.HIGH,
                    amount=500000,
                    target_year=current_year + 1,
                    notes="6 個月生活費",
                ),
                Target(
                    name="Car Purchase",
                    category=TargetCategory.TRANSPORTATION,
                    priority=Priority.MEDIUM,
                    amount=800000,
                    target_year=current_year + 2,
                ),
                Target(
                    name="House Down Payment",
                    category=TargetCategory.HOUSING,
                    priority=Priority.HIGH,
                    amount=3000000,
                    target_year=current_year + 4,
                ),
                Target(
                    name="Retirement Fund",
                    category=TargetCategory.RETIREMENT,
                    priority=Priority.HIGH,
                    amount=20000000,
                    target_year=current_year + 30,
                ),
            ],
        )

        save_model(canonical_dir / "lifetime_targets.yaml", targets)

    def _write_monthly_expenses(
        self, year: int, month: int, canonical_dir: Path, raw_dir: Path
    ) -> None:
        """生成月度支出 CSV + raw Provenance

        Args:
            year: 年份
            month: 月份（1-12）
            canonical_dir: canonical/expenses 目錄
            raw_dir: raw/imports 目錄
        """
        # 基準模板（適用於一般月份）
        base_records = [
            {
                "date": f"{year}-{month:02d}-01",
                "amount": "28000",
                "category": "housing",
                "payer": "shared",
            },
            {
                "date": f"{year}-{month:02d}-05",
                "amount": "8000",
                "category": "food",
                "payer": "person_b",
            },
            {
                "date": f"{year}-{month:02d}-10",
                "amount": "7000",
                "category": "food",
                "payer": "person_a",
            },
            {
                "date": f"{year}-{month:02d}-12",
                "amount": "1800",
                "category": "transportation",
                "payer": "person_a",
            },
            {
                "date": f"{year}-{month:02d}-15",
                "amount": "2650",
                "category": "utilities",
                "payer": "shared",
            },
            {
                "date": f"{year}-{month:02d}-18",
                "amount": "500",
                "category": "entertainment",
                "payer": "shared",
            },
            {
                "date": f"{year}-{month:02d}-20",
                "amount": "1800",
                "category": "dining_out",
                "payer": "shared",
            },
            {
                "date": f"{year}-{month:02d}-22",
                "amount": "2500",
                "category": "shopping",
                "payer": "person_b",
            },
            {
                "date": f"{year}-{month:02d}-25",
                "amount": "20000",
                "category": "savings",
                "payer": "person_a",
            },
            {
                "date": f"{year}-{month:02d}-28",
                "amount": "20000",
                "category": "investment",
                "payer": "person_b",
            },
        ]

        # 特殊月份調整
        if month == 12:
            # 12 月：保險 39K + 聖誕禮物 5K + 退款 -500
            base_records.extend(
                [
                    {
                        "date": f"{year}-{month:02d}-01",
                        "amount": "39000",
                        "category": "insurance",
                        "payer": "shared",
                    },
                    {
                        "date": f"{year}-{month:02d}-24",
                        "amount": "5000",
                        "category": "shopping",
                        "payer": "shared",
                        "note": "Christmas gifts",
                    },
                    {
                        "date": f"{year}-{month:02d}-26",
                        "amount": "-500",
                        "category": "shopping",
                        "payer": "shared",
                        "note": "Refund",
                    },
                ]
            )
        elif month == 7:
            # 7 月：暑假旅遊 8K
            base_records.append(
                {
                    "date": f"{year}-{month:02d}-15",
                    "amount": "8000",
                    "category": "entertainment",
                    "payer": "shared",
                    "note": "Summer vacation",
                }
            )

        # 寫入 canonical CSV
        canonical_csv_path = canonical_dir / EXPENSE_FILE_PATTERN.format(year=year, month=month)
        with open(canonical_csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["date", "amount", "category", "payer", "note", "merchant"],
                lineterminator="\n",
            )
            writer.writeheader()
            for record in base_records:
                # 補齊缺失欄位
                if "note" not in record:
                    record["note"] = ""
                if "merchant" not in record:
                    record["merchant"] = ""
                writer.writerow(record)

        # 寫入 raw/imports（模擬匯入來源）
        raw_csv_path = raw_dir / f"{year}{month:02d}_{self._next_hex(8)}.csv"
        with open(raw_csv_path, "w", encoding="utf-8", newline="") as f:
            # 寫入 Provenance 註解
            provenance = Provenance(
                source_id=UUID(self._next_uuid()),
                import_time=self._next_time(),
                source_type=SourceType.CSV_IMPORT,
                parser_version="1.0",
            )
            f.write(f"# Provenance: {provenance.model_dump_json()}\n")

            # 寫入資料
            writer = csv.DictWriter(
                f,
                fieldnames=["date", "amount", "category", "payer", "note", "merchant"],
                lineterminator="\n",
            )
            writer.writeheader()
            for record in base_records:
                if "note" not in record:
                    record["note"] = ""
                if "merchant" not in record:
                    record["merchant"] = ""
                writer.writerow(record)

        # 設為 read-only
        os.chmod(raw_csv_path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)

        # 固定 mtime 以確保決定論
        fixed_ts = self.base_time.timestamp()
        os.utime(raw_csv_path, (fixed_ts, fixed_ts))

        # 記錄 operation log
        self._log_operation(
            operation_type=OperationType.IMPORT,
            target_path=canonical_csv_path.relative_to(self.base_dir),
            description=f"Seed data import for {year}-{month:02d}",
        )

    def _write_raw_manifest(self) -> None:
        """生成 raw_manifest.json（SHA-256 manifest）"""
        save_raw_manifest(base_dir=self.base_dir)

    def _write_raw_manifest_deterministic(self) -> None:
        """生成可重建的 raw_manifest.json"""
        raw_dir = self.base_dir / RAW_DIR
        manifest_path = self.base_dir / RAW_MANIFEST_FILE
        files_info = []

        if raw_dir.exists():
            for file_path in sorted(raw_dir.rglob("*")):
                if file_path.is_dir() or file_path.name.startswith("."):
                    continue
                if file_path.name == "raw_manifest.json":
                    continue

                relative_path = file_path.relative_to(raw_dir)
                stat_info = file_path.stat()
                files_info.append(
                    {
                        "path": str(relative_path),
                        "size": stat_info.st_size,
                        "mtime": self._iso(self.base_time),
                        "sha256": self._sha256_file(file_path),
                    }
                )

        manifest = {
            "generated_at": self._iso(self.base_time),
            "files": files_info,
        }

        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(manifest_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")

        os.chmod(manifest_path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        fixed_ts = self.base_time.timestamp()
        os.utime(manifest_path, (fixed_ts, fixed_ts))

    def _sha256_file(self, path: Path) -> str:
        """計算檔案 SHA-256"""
        digest = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _write_text(self, path: Path, content: str) -> None:
        """統一寫入 UTF-8 + LF"""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
            if not content.endswith("\n"):
                f.write("\n")

    def _write_dedupe_raw_imports(self) -> None:
        """Phase 1: 生成 dedupe 測試用 raw/imports"""
        raw_dir = self.base_dir / RAW_IMPORTS_DIR
        raw_dir.mkdir(parents=True, exist_ok=True)

        base_date = "2024-08-15"
        records = [
            {
                "row_id": "dup_exact_1",
                "date": base_date,
                "amount": "1200",
                "category": "food",
                "payer": "person_a",
                "note": "duplicate exact",
                "merchant": "cafe-a",
            },
            {
                "row_id": "dup_exact_2",
                "date": base_date,
                "amount": "1200",
                "category": "food",
                "payer": "person_a",
                "note": "duplicate exact",
                "merchant": "cafe-a",
            },
        ]

        self._write_raw_csv_with_provenance(
            raw_dir / "202408_dup_exact.csv",
            records,
        )

        if self.profile == "smoke":
            return

        near_date_records = [
            {
                "row_id": "dup_date_1",
                "date": "2024-08-20",
                "amount": "980",
                "category": "transportation",
                "payer": "person_b",
                "note": "near date",
                "merchant": "metro",
            },
            {
                "row_id": "dup_date_2",
                "date": "2024-08-21",
                "amount": "980",
                "category": "transportation",
                "payer": "person_b",
                "note": "near date",
                "merchant": "metro",
            },
        ]
        self._write_raw_csv_with_provenance(
            raw_dir / "202408_dup_date.csv",
            near_date_records,
        )

        near_amount_records = [
            {
                "row_id": "dup_amount_1",
                "date": "2024-09-05",
                "amount": "1500",
                "category": "shopping",
                "payer": "shared",
                "note": "near amount",
                "merchant": "mall",
            },
            {
                "row_id": "dup_amount_2",
                "date": "2024-09-05",
                "amount": "1520",
                "category": "shopping",
                "payer": "shared",
                "note": "near amount",
                "merchant": "mall",
            },
        ]
        self._write_raw_csv_with_provenance(
            raw_dir / "202409_dup_amount.csv",
            near_amount_records,
        )

        non_dup_records = [
            {
                "row_id": "unique_1",
                "date": "2024-10-03",
                "amount": "3200",
                "category": "housing",
                "payer": "shared",
                "note": "unique",
                "merchant": "rent",
            },
            {
                "row_id": "unique_2",
                "date": "2024-10-12",
                "amount": "600",
                "category": "entertainment",
                "payer": "person_a",
                "note": "unique",
                "merchant": "cinema",
            },
        ]
        self._write_raw_csv_with_provenance(
            raw_dir / "202410_unique.csv",
            non_dup_records,
        )

    def _write_raw_csv_with_provenance(self, path: Path, records: list[dict]) -> None:
        """寫入 raw/imports CSV + Provenance"""
        with open(path, "w", encoding="utf-8", newline="") as f:
            provenance = Provenance(
                source_id=UUID(self._next_uuid()),
                import_time=self._next_time(),
                source_type=SourceType.CSV_IMPORT,
                parser_version="1.0",
            )
            f.write(f"# Provenance: {provenance.model_dump_json()}\n")
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "row_id",
                    "date",
                    "amount",
                    "category",
                    "payer",
                    "note",
                    "merchant",
                ],
                lineterminator="\n",
            )
            writer.writeheader()
            for record in records:
                writer.writerow(record)

        os.chmod(path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        fixed_ts = self.base_time.timestamp()
        os.utime(path, (fixed_ts, fixed_ts))

    def _write_staging_entries(self) -> None:
        """Phase 4: 生成 staging/entries.jsonl"""
        staging_path = self.base_dir / "staging" / "entries.jsonl"
        entries = []

        pending_id = self._next_uuid()
        parsed_id = self._next_uuid()
        approved_id = self._next_uuid()
        error_id = self._next_uuid()
        duplicate_id = self._next_uuid()

        entries.append(
            self._build_staging_entry(
                entry_id=pending_id,
                raw_text="午餐 150 PII_EMAIL_01",
                status="pending",
            )
        )

        if self.profile == "smoke":
            proposal_id = self._write_expense_proposal_for_staging(approved_id)
            entries.append(
                self._build_staging_entry(
                    entry_id=approved_id,
                    raw_text="2024-12-06 晚餐 320",
                    status="approved",
                    parsed_date="2024-12-06",
                    parsed_amount="320",
                    parsed_category="dining_out",
                    amount_source="exact",
                    date_source="builtin_exact",
                    category_source="exact",
                    confidence=0.95,
                    proposal_id=proposal_id,
                    reviewed_by="seed_builder",
                )
            )
            lines = [json.dumps(entry, ensure_ascii=False, sort_keys=True) for entry in entries]
            self._write_text(staging_path, "\n".join(lines))
            return

        entries.append(
            self._build_staging_entry(
                entry_id=parsed_id,
                raw_text="2024-12-05 咖啡 90",
                status="parsed",
                parsed_date="2024-12-05",
                parsed_amount="90",
                parsed_category="food",
                amount_source="exact",
                date_source="builtin_exact",
                category_source="exact",
                confidence=0.92,
            )
        )

        proposal_id = self._write_expense_proposal_for_staging(approved_id)
        entries.append(
            self._build_staging_entry(
                entry_id=approved_id,
                raw_text="2024-12-06 晚餐 320",
                status="approved",
                parsed_date="2024-12-06",
                parsed_amount="320",
                parsed_category="dining_out",
                amount_source="exact",
                date_source="builtin_exact",
                category_source="exact",
                confidence=0.95,
                proposal_id=proposal_id,
                reviewed_by="seed_builder",
            )
        )

        entries.append(
            self._build_staging_entry(
                entry_id=error_id,
                raw_text="昨晚外送 晚餐",
                status="error",
                error_message="missing_amount",
                amount_source="missing",
                date_source="builtin_inferred",
                category_source="fuzzy",
                confidence=0.2,
            )
        )

        entries.append(
            self._build_staging_entry(
                entry_id=duplicate_id,
                raw_text="午餐 150",
                status="duplicate",
                duplicate_of=pending_id,
                duplicate_reason="exact_key_match",
            )
        )

        lines = [json.dumps(entry, ensure_ascii=False, sort_keys=True) for entry in entries]
        self._write_text(staging_path, "\n".join(lines))

    def _build_staging_entry(
        self,
        entry_id: str,
        raw_text: str,
        status: str,
        parsed_date: Optional[str] = None,
        parsed_amount: Optional[str] = None,
        parsed_category: Optional[str] = None,
        parsed_merchant: Optional[str] = None,
        parsed_note: Optional[str] = None,
        amount_source: str = "missing",
        date_source: str = "missing",
        category_source: str = "missing",
        confidence: float = 0.0,
        error_message: Optional[str] = None,
        proposal_id: Optional[str] = None,
        reviewed_by: Optional[str] = None,
        duplicate_of: Optional[str] = None,
        duplicate_reason: Optional[str] = None,
    ) -> dict:
        """建立 staging entry dict（JSONL 用）"""
        created_at = self._iso(self._next_time())
        reviewed_at = self._iso(self._next_time()) if reviewed_by else None
        return {
            "entry_id": entry_id,
            "raw_text": raw_text,
            "created_at": created_at,
            "parser_version": "1.0",
            "batch_id": None,
            "source": "cli",
            "parsed_date": parsed_date,
            "parsed_amount": parsed_amount,
            "parsed_category": parsed_category,
            "parsed_merchant": parsed_merchant,
            "parsed_note": parsed_note,
            "amount_source": amount_source,
            "date_source": date_source,
            "category_source": category_source,
            "status": status,
            "confidence": confidence,
            "confidence_breakdown": None,
            "error_message": error_message,
            "reviewed_at": reviewed_at,
            "reviewed_by": reviewed_by,
            "rejection_reason": None,
            "duplicate_of": duplicate_of,
            "duplicate_reason": duplicate_reason,
            "proposal_id": proposal_id,
            "canonical_record_id": None,
            "raw_locale": "zh-TW",
        }

    def _write_expense_proposal_for_staging(self, entry_id: str) -> str:
        """建立 staging approved 對應的 expense proposal"""
        proposals_dir = self.base_dir / PROPOSALS_PENDING_DIR
        proposals_dir.mkdir(parents=True, exist_ok=True)

        operation_id = self._next_uuid()
        created_at = self._iso(self._next_time())
        proposal_id = f"seed_{entry_id[:8]}_expenses_2024_12.json"

        proposal_data = {
            "operation": {
                "operation_id": operation_id,
                "created_at": created_at,
                "actor": "seed_builder",
                "operation_type": "apply",
                "target_path": "canonical/expenses/expenses_2024_12.yaml",
                "description": "Seed proposal from staging",
                "metadata": {
                    "source_file": f"staging_{entry_id[:8]}.txt",
                    "record_count": 1,
                    "year": 2024,
                    "month": 12,
                },
            },
            "data": {
                "schema_version": CURRENT_SCHEMA_VERSION,
                "year": 2024,
                "month": 12,
                "records": [
                    {
                        "date": "2024-12-06",
                        "amount": "320",
                        "category": "dining_out",
                        "payer": "shared",
                        "note": "",
                        "merchant": "",
                    }
                ],
            },
        }

        self._write_text(
            proposals_dir / proposal_id,
            json.dumps(proposal_data, ensure_ascii=False, sort_keys=True, indent=2),
        )
        return proposal_id

    def _write_advisor_seed(self) -> None:
        """Phase 5 Stage 2: 生成 advisor proposals/decisions/audit"""
        self._write_advisor_proposals()
        self._write_decisions_memory()
        self._write_advisor_audit_log()
        self._write_redaction_fixture()
        self._write_negative_chain_fixture()

    def _write_advisor_proposals(self) -> None:
        proposals_dir = self.base_dir / PROPOSALS_PENDING_DIR
        proposals_dir.mkdir(parents=True, exist_ok=True)

        templates = ["buying_house", "investment", "car_purchase", "travel", "savings_target"]
        if self.profile == "smoke":
            templates = ["buying_house"]
        for template_id in templates:
            operation_id = self._next_ulid()
            if template_id == "buying_house":
                self.seed_refs["chain_proposal_id"] = f"advisor_{template_id}.yaml"
            payload = AdvisorProposalPayload(
                operation_id=operation_id,
                comparability_score=0.78,
                is_comparable=True,
                option_a=DecisionOptionSchema(
                    direction="conservative",
                    label="方案 A：保守選擇",
                    status="comparable",
                    recommendation="建議保守維持現狀",
                    score=0.62,
                ),
                option_b=DecisionOptionSchema(
                    direction="aggressive",
                    label="方案 B：進取選擇",
                    status="comparable",
                    recommendation="可評估進取方案",
                    score=0.71,
                ),
                risk_tags=("low_risk",),
                risk_explanation="風險可控，需維持流動性。",
                input_hash=f"hash_{template_id[:6]}",
                template_id=template_id,
                created_at=self._iso(self._next_time()),
            )

            proposal_path = proposals_dir / f"advisor_{template_id}.yaml"
            save_yaml(proposal_path, payload.to_dict())

    def _write_decisions_memory(self) -> None:
        decisions_path = self.base_dir / "canonical" / "decisions" / "decisions.yaml"
        records = []
        templates = ["buying_house", "investment", "car_purchase", "travel", "savings_target"]
        if self.profile == "smoke":
            templates = ["buying_house"]

        chain_decision_id = f"dec_{self._next_ulid()}"
        chain_operation_id = self._next_ulid()
        self.seed_refs["chain_decision_id"] = chain_decision_id
        self.seed_refs["chain_operation_id"] = chain_operation_id
        chain_record = None

        for template_id in templates:
            if template_id == "buying_house":
                chain_record = self._build_decision_record(
                    template_id,
                    scenario="comparable",
                    forced_id=chain_decision_id,
                    forced_operation_id=chain_operation_id,
                )
                records.append(chain_record)
            else:
                records.append(self._build_decision_record(template_id, scenario="comparable"))
            if self.profile != "smoke":
                records.append(self._build_decision_record(template_id, scenario="not_comparable"))
                records.append(self._build_decision_record(template_id, scenario="extreme_risk"))

        # 事件鏈：apply -> revert
        if chain_record:
            records.append(self._build_reverted_record(chain_record))

        memory = {
            "schema_version": "1.0",
            "version": "1.0",
            "last_updated": self._iso(self._next_time()),
            "records": records,
        }

        save_yaml(decisions_path, memory)

    def _build_decision_record(
        self,
        template_id: str,
        scenario: str,
        forced_id: Optional[str] = None,
        forced_operation_id: Optional[str] = None,
    ) -> dict:
        decision_id = forced_id or f"dec_{self._next_ulid()}"
        operation_id = forced_operation_id or self._next_ulid()
        created_at = self._iso(self._next_time())

        if scenario == "comparable":
            option_status = "comparable"
            score_a = 0.62
            score_b = 0.71
            comparability_score = 0.78
            confidence = "high"
            blocking_reasons = []
            guidance = None
            risk_tags = ["low_risk"]
            risk_explanation = "風險可控，需維持流動性。"
        elif scenario == "not_comparable":
            option_status = "not_comparable"
            score_a = None
            score_b = None
            comparability_score = 0.45
            confidence = "low"
            blocking_reasons = ["MISSING_DATA"]
            guidance = "需補齊月收入與緊急備用金資料。"
            risk_tags = ["data_insufficient"]
            risk_explanation = "資料不足，無法比較。"
        else:
            option_status = "comparable"
            score_a = 0.35
            score_b = 0.28
            comparability_score = 0.62
            confidence = "medium"
            blocking_reasons = []
            guidance = None
            risk_tags = ["high_risk"]
            risk_explanation = "連續赤字風險偏高。"

        return {
            "decision_id": decision_id,
            "operation_id": operation_id,
            "created_at": created_at,
            "template_id": template_id,
            "status": "applied",
            "confidence": confidence,
            "comparability_score": comparability_score,
            "input_hash": f"hash_{template_id[:6]}",
            "option_a": {
                "direction": "conservative",
                "label": "方案 A：保守選擇",
                "recommendation": "維持保守策略",
                "score": score_a,
                "status": option_status,
                "to_comparable_guidance": guidance,
            },
            "option_b": {
                "direction": "aggressive",
                "label": "方案 B：進取選擇",
                "recommendation": "評估進取策略",
                "score": score_b,
                "status": option_status,
                "to_comparable_guidance": guidance,
            },
            "risk_tags": risk_tags,
            "risk_explanation": risk_explanation,
            "blocking_reasons": blocking_reasons,
            "assumption_snapshot": {
                "snapshot_version": "1.0",
                "created_at": created_at,
                "inflation_rate": 0.02,
                "investment_return": 0.05,
                "income_growth": 0.03,
                "expense_growth": 0.02,
                "custom_assumptions": {},
            },
            "preference_weights": {
                "liquidity": 0.25,
                "growth": 0.25,
                "safety": 0.25,
                "flexibility": 0.25,
            },
            "schema_version": "1.0",
        }

    def _build_reverted_record(self, original: dict) -> dict:
        reverted_id = f"dec_{self._next_ulid()}"
        reverted_at = self._iso(self._next_time())
        revert_operation_id = self._next_ulid()
        base = {k: original[k] for k in original if k not in ("decision_id", "status")}
        base["operation_id"] = revert_operation_id
        base["created_at"] = reverted_at
        if original.get("decision_id") == self.seed_refs.get("chain_decision_id"):
            self.seed_refs["chain_revert_operation_id"] = revert_operation_id
        return {
            **base,
            "decision_id": reverted_id,
            "status": "reverted",
            "reverted_at": reverted_at,
            "reverted_by": revert_operation_id,
        }

    def _write_advisor_audit_log(self) -> None:
        audit_path = self.base_dir / "derived" / "logs" / "advisor_audit.jsonl"
        actions = [
            {
                "action": "suggest",
                "template_id": "buying_house",
                "proposal_id": "advisor_buying_house.yaml",
                "operation_id": self.seed_refs.get("chain_operation_id"),
            },
            {
                "action": "apply",
                "template_id": "buying_house",
                "proposal_id": "advisor_buying_house.yaml",
                "operation_id": self.seed_refs.get("chain_operation_id"),
            },
            {
                "action": "undo",
                "template_id": "buying_house",
                "proposal_id": "advisor_buying_house.yaml",
                "operation_id": self.seed_refs.get("chain_revert_operation_id"),
            },
        ]
        if self.profile != "smoke":
            actions.extend(
                [
                    {
                        "action": "suggest",
                        "template_id": "investment",
                        "proposal_id": "advisor_investment.yaml",
                        "operation_id": self.seed_refs.get("chain_operation_id"),
                    },
                    {
                        "action": "suggest",
                        "template_id": "travel",
                        "proposal_id": "advisor_travel.yaml",
                        "operation_id": self.seed_refs.get("chain_operation_id"),
                    },
                ]
            )

        lines = []
        for action in actions:
            line = {
                "timestamp": self._iso(self._next_time()),
                "action": action["action"],
                "template_id": action["template_id"],
                "proposal_id": action["proposal_id"],
                "decision_id": self.seed_refs.get("chain_decision_id"),
                "operation_id": action["operation_id"],
            }
            lines.append(json.dumps(line, ensure_ascii=False, sort_keys=True))

        self._write_text(audit_path, "\n".join(lines))

    def _write_redaction_fixture(self) -> None:
        fixtures_dir = self.base_dir / "fixtures"
        payload = {
            "email": "pii_email_01@example.com",
            "phone_number": "0900-000-000",
            "city": "taipei",
            "job_title": "engineer",
            "salary": 120000,
        }
        self._write_text(
            fixtures_dir / "redaction_payload.json",
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2),
        )

    def _write_schema_fixtures(self) -> None:
        fixtures_dir = self.base_dir / "fixtures"
        fixtures_dir.mkdir(parents=True, exist_ok=True)

        decisions_path = self.base_dir / "canonical" / "decisions" / "decisions.yaml"
        if decisions_path.exists():
            data = load_yaml(decisions_path)
            save_yaml(fixtures_dir / "decisions_v1_0.yaml", data)

        assumptions_path = self.base_dir / "life_assumptions.yaml"
        if assumptions_path.exists():
            data = load_yaml(assumptions_path)
            data["schema_version"] = "1.0"
            save_yaml(fixtures_dir / "life_assumptions_v1_0.yaml", data)

    def _write_negative_chain_fixture(self) -> None:
        fixtures_dir = self.base_dir / "fixtures"
        payload = {
            "dataset_id": "advisor_chain_02_apply_rejected",
            "error_code": "duplicate_operation_id",
            "message_tokens": ["duplicate", "operation_id"],
            "sample_operation_id": self._next_ulid(),
        }
        self._write_text(
            fixtures_dir / "advisor_chain_apply_rejected.json",
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2),
        )

    def _write_seed_manifest(self, phases: set[str]) -> None:
        """寫入 seed_manifest.json（行為契約）"""
        manifest_path = self.base_dir / "seed_manifest.json"
        staging_entries = self._load_staging_entries()
        staging_counts, error_entry_id = self._count_staging_statuses(staging_entries)

        expected_hashes = {}
        decisions_path = self.base_dir / "canonical" / "decisions" / "decisions.yaml"
        staging_path = self.base_dir / "staging" / "entries.jsonl"
        raw_manifest_path = self.base_dir / RAW_MANIFEST_FILE
        if decisions_path.exists():
            expected_hashes["canonical/decisions/decisions.yaml"] = (
                f"sha256:{self._sha256_file(decisions_path)}"
            )
        if staging_path.exists():
            expected_hashes["staging/entries.jsonl"] = f"sha256:{self._sha256_file(staging_path)}"
        if raw_manifest_path.exists():
            expected_hashes["raw/raw_manifest.json"] = (
                f"sha256:{self._sha256_file(raw_manifest_path)}"
            )

        datasets = []
        if (self.base_dir / "raw" / "imports" / "202408_dup_exact.csv").exists():
            datasets.append(
                {
                    "id": "dedupe_exact_01",
                    "purpose": "phase1_dedupe_exact",
                    "inputs": ["raw/imports/202408_dup_exact.csv"],
                    "expected": {"duplicate_pairs": [["dup_exact_1", "dup_exact_2"]]},
                }
            )

        if error_entry_id:
            datasets.append(
                {
                    "id": "staging_error_missing_field",
                    "purpose": "phase4_staging_error",
                    "inputs": ["staging/entries.jsonl"],
                    "expected": {"entry_id": error_entry_id, "error_code": "missing_amount"},
                }
            )

        if self.seed_refs.get("chain_decision_id"):
            datasets.append(
                {
                    "id": "advisor_chain_01_apply_then_undo",
                    "purpose": "phase5_advisor_chain",
                    "inputs": {
                        "proposal_id": self.seed_refs.get("chain_proposal_id"),
                        "operation_id": self.seed_refs.get("chain_operation_id"),
                        "decision_id": self.seed_refs.get("chain_decision_id"),
                    },
                    "expected": {
                        "audit_actions": ["suggest", "apply", "undo"],
                        "decision_statuses": ["applied", "reverted"],
                    },
                }
            )

        negative_fixture = self.base_dir / "fixtures" / "advisor_chain_apply_rejected.json"
        if negative_fixture.exists() and self.profile != "smoke":
            datasets.append(
                {
                    "id": "advisor_chain_02_apply_rejected",
                    "purpose": "phase5_advisor_chain_negative",
                    "inputs": {"fixture": "fixtures/advisor_chain_apply_rejected.json"},
                    "expected": {
                        "error_code": "duplicate_operation_id",
                        "message_tokens": ["duplicate", "operation_id"],
                    },
                }
            )

        manifest = {
            "seed_version": "1.0",
            "phases": sorted(phases),
            "expected_hashes": expected_hashes,
            "expected_counts": {
                "staging": staging_counts,
                "advisor": {
                    "proposals": len(
                        list((self.base_dir / PROPOSALS_PENDING_DIR).glob("advisor_*.yaml"))
                    ),
                    "decisions": self._count_decisions(),
                    "audit_actions": self._count_audit_actions(),
                },
            },
            "supported_read_versions": ["1.0", "1.1"],
            "current_write_version": CURRENT_SCHEMA_VERSION,
            "expected_migration_summary": {
                "yaml": ["schema_version update only"],
            },
            "datasets": datasets,
        }

        self._write_text(
            manifest_path,
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2),
        )

    def _write_seed_lock(self) -> None:
        """寫入 seed_lock.json（hash 鎖）"""
        lock_path = self.base_dir / "seed_lock.json"
        file_hashes = {}

        for file_path in sorted(self.base_dir.rglob("*")):
            if file_path.is_dir():
                continue
            if file_path.name in ("seed_lock.json",):
                continue
            rel_path = file_path.relative_to(self.base_dir).as_posix()
            file_hashes[rel_path] = f"sha256:{self._sha256_file(file_path)}"

        lock_data = {
            "seed_version": "1.0",
            "generated_at": self._iso(self.base_time),
            "files": file_hashes,
        }
        self._write_text(
            lock_path,
            json.dumps(lock_data, ensure_ascii=False, sort_keys=True, indent=2),
        )

    def _load_staging_entries(self) -> list[dict]:
        staging_path = self.base_dir / "staging" / "entries.jsonl"
        if not staging_path.exists():
            return []
        entries = []
        with open(staging_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entries.append(json.loads(line))
        return entries

    def _count_staging_statuses(self, entries: list[dict]) -> tuple[dict, Optional[str]]:
        counts = {}
        error_entry_id = None
        for entry in entries:
            status = entry.get("status")
            counts[status] = counts.get(status, 0) + 1
            if status == "error" and not error_entry_id:
                error_entry_id = entry.get("entry_id")
        return counts, error_entry_id

    def _count_decisions(self) -> int:
        decisions_path = self.base_dir / "canonical" / "decisions" / "decisions.yaml"
        if not decisions_path.exists():
            return 0
        data = load_yaml(decisions_path)
        return len(data.get("records", []))

    def _count_audit_actions(self) -> int:
        audit_path = self.base_dir / "derived" / "logs" / "advisor_audit.jsonl"
        if not audit_path.exists():
            return 0
        with open(audit_path, "r", encoding="utf-8") as f:
            return len([line for line in f if line.strip()])

    def _log_operation(
        self, operation_type: OperationType, target_path: Path, description: str
    ) -> None:
        """記錄 operation log

        Args:
            operation_type: 操作類型
            target_path: 目標路徑（相對於 base_dir）
            description: 操作描述
        """
        operation = Operation(
            operation_id=UUID(self._next_uuid()),
            created_at=self._next_time(),
            actor="seed_builder",
            operation_type=operation_type,
            target_path=target_path,
            description=description,
            metadata={"seed_version": "1.0"},
        )

        entry = OperationLogEntry(operation=operation)

        # 追加到 operation log
        log_path = self.base_dir / OPERATION_LOG_FILE
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(entry.to_jsonl() + "\n")
