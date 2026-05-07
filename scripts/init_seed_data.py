#!/usr/bin/env python3
"""初始化 ~/.life-capital/ 的 seed 資料

此腳本用於快速初始化開發環境，建立完整的測試資料集（7 個月）。
遵守 CLAUDE.md 護欄規則，通過 SeedDataBuilder 建立標準化資料結構。

Usage:
    python scripts/init_seed_data.py
    python scripts/init_seed_data.py --months 3
    python scripts/init_seed_data.py --path /custom/data/dir --months 7

Environment:
    預設資料目錄: ~/.life-capital/
    必要依賴: tests.fixtures.seed_data.SeedDataBuilder
"""

import argparse
import sys
from pathlib import Path

# 新增專案根目錄到 Python path，確保可導入 life_capital 模組
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from tests.fixtures.seed_data import SeedDataBuilder  # noqa: E402  # sys.path.insert above


def main():
    """主入口"""
    parser = argparse.ArgumentParser(
        description="初始化 Life Capital 資料目錄的 seed 資料",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  # 使用預設路徑 (~/.life-capital/) 建立完整資料（7 個月）
  python scripts/init_seed_data.py

  # 自訂資料目錄與月份
  python scripts/init_seed_data.py --path ./data --months 3

  # 建立最小資料集（1 個月）
  python scripts/init_seed_data.py --minimal
        """,
    )

    default_path = project_root / "data" / "seed"
    parser.add_argument(
        "--path",
        type=Path,
        default=default_path,
        help="資料目錄路徑 (預設: ./data/seed)",
    )

    parser.add_argument(
        "--months",
        type=int,
        default=7,
        help="要生成的月份數量，範圍 1-12 (預設: 7)",
    )

    parser.add_argument(
        "--minimal",
        action="store_true",
        help="建立最小資料集（1 個月），忽略 --months",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="強制覆寫既有資料（預設為創建或追加）",
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="決定論 seed（預設: 42）",
    )

    parser.add_argument(
        "--phase",
        type=str,
        default="all",
        help="指定 phase（all 或 1,2,3,4,5）",
    )

    parser.add_argument(
        "--profile",
        type=str,
        default="full",
        choices=["smoke", "full"],
        help="seed profile（預設: full）",
    )

    parser.add_argument(
        "--with-staging",
        action="store_true",
        help="包含 staging 真實範例（Phase 4）",
    )

    parser.add_argument(
        "--with-advisor",
        action="store_true",
        help="包含 advisor 模組資料（Phase 5 Stage 2）",
    )

    args = parser.parse_args()

    # 解析參數
    data_dir = args.path.expanduser().resolve()
    months = 1 if args.minimal else args.months

    # 驗證月份範圍
    if months < 1 or months > 12:
        print(f"❌ 錯誤：月份必須在 1-12 之間，收到: {months}", file=sys.stderr)
        sys.exit(1)

    # 檢查目錄是否已存在
    if data_dir.exists() and not args.force:
        existing_files = list(data_dir.glob("**/*"))
        if existing_files:
            print(
                f"⚠️  警告：資料目錄已存在且包含檔案: {data_dir}",
                file=sys.stderr,
            )
            print(
                "   使用 --force 強制覆寫，或選擇其他目錄",
                file=sys.stderr,
            )
            sys.exit(1)

    # 建立 SeedDataBuilder 實例
    try:
        builder = SeedDataBuilder(data_dir, seed=args.seed, profile=args.profile)

        # 執行建構
        print("🚀 初始化 Life Capital 資料...")
        print(f"   目錄: {data_dir}")
        print(f"   月份: {months}")

        if args.minimal:
            result_dir = builder.build_minimal()
            print(f"✅ 最小資料集已建立: {result_dir}")
        else:
            builder.with_months(months)
            phase_set = {p.strip() for p in args.phase.split(",")}
            if "all" in phase_set:
                phase_set = {"1", "2", "3", "4", "5"}
            with_staging = args.with_staging or "4" in phase_set
            with_advisor = args.with_advisor or "5" in phase_set
            result_dir = builder.build_seed(
                phases=",".join(sorted(phase_set)),
                profile=args.profile,
                with_staging=with_staging,
                with_advisor=with_advisor,
            )
            print(f"✅ Seed 資料已建立: {result_dir}")

        # 列出建立的檔案統計
        canonical_dir = data_dir / "canonical"
        expenses_dir = canonical_dir / "expenses"

        if canonical_dir.exists():
            config_files = list(canonical_dir.glob("*.yaml"))
            expense_files = list(expenses_dir.glob("*.csv")) if expenses_dir.exists() else []

            print("\n📊 資料統計:")
            print(f"   設定檔: {len(config_files)}")
            for f in sorted(config_files):
                print(f"      • {f.name}")

            print(f"   月度支出: {len(expense_files)}")
            for f in sorted(expense_files):
                print(f"      • {f.name}")

        print("\n💡 後續步驟:")
        print(f"   1. 驗證資料: lc doctor --path {data_dir}")
        print("   2. 執行測試: uv run pytest tests/")
        print("   3. 查看説明: lc --help")

    except ValueError as e:
        print(f"❌ 參數錯誤: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ 發生錯誤: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
