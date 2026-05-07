"""Schema 遷移模組 (Phase 1.4)

提供 canonical/ 資料的 schema 遷移功能，包含：
1. 版本檢查
2. 備份機制
3. 遷移執行
4. 遷移日誌

契約保證：
- raw 永遠不動
- 遷移必須產生 migration_log / operation_id
- 遷移後 lc rebuild 仍可從 raw + canonical 重建 derived
"""

import json
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from life_capital.io.registry import (
    CANONICAL_DIR,
    CURRENT_SCHEMA_VERSION,
    DATA_LAYOUT_VERSION,
    MIGRATION_LOG_DIR,
)


class MigrationError(Exception):
    """遷移錯誤"""

    pass


class MigrationEntry(BaseModel):
    """遷移日誌條目"""

    migration_id: str = Field(default_factory=lambda: str(uuid4()))
    from_version: str
    to_version: str
    files_migrated: list[str] = Field(default_factory=list)
    backup_path: str
    started_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    status: str = "in_progress"  # in_progress, completed, failed, rolled_back
    error_message: Optional[str] = None
    actor: str = Field(default="system")

    def to_jsonl(self) -> str:
        """轉換為 JSONL 格式"""
        return self.model_dump_json()

    @classmethod
    def from_jsonl(cls, line: str) -> "MigrationEntry":
        """從 JSONL 行解析"""
        data = json.loads(line)
        return cls.model_validate(data)


def check_schema_version(data_dir: Path) -> dict[str, list[Path]]:
    """檢查 canonical/ 內檔案的 schema 版本

    Args:
        data_dir: 資料目錄根路徑

    Returns:
        字典，鍵為版本號，值為該版本的檔案列表

    Raises:
        MigrationError: 無法讀取檔案
    """
    canonical_dir = data_dir / CANONICAL_DIR
    if not canonical_dir.exists():
        return {}

    version_map: dict[str, list[Path]] = {}

    # 掃描所有 YAML 和 JSON 檔案
    for pattern in ("**/*.yaml", "**/*.json"):
        for file_path in canonical_dir.glob(pattern):
            # 跳過隱藏檔案和日誌
            if file_path.name.startswith("."):
                continue

            try:
                version = _extract_schema_version(file_path)
                if version not in version_map:
                    version_map[version] = []
                version_map[version].append(file_path)
            except Exception as e:
                raise MigrationError(f"無法讀取檔案版本 ({file_path}): {e}")

    return version_map


def _extract_schema_version(file_path: Path) -> str:
    """從檔案中提取 schema_version

    Args:
        file_path: 檔案路徑

    Returns:
        schema_version 字串，若不存在則返回 "unknown"
    """
    import yaml

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            if file_path.suffix == ".yaml":
                data = yaml.safe_load(f)
            else:
                data = json.load(f)

        if isinstance(data, dict):
            return str(data.get("schema_version", "unknown"))
        return "unknown"
    except Exception:
        return "unknown"


def create_backup(data_dir: Path, migration_id: str) -> Path:
    """建立 canonical/ 的備份

    Args:
        data_dir: 資料目錄根路徑
        migration_id: 遷移 ID

    Returns:
        備份目錄路徑

    Raises:
        MigrationError: 備份失敗
    """
    canonical_dir = data_dir / CANONICAL_DIR
    if not canonical_dir.exists():
        raise MigrationError(f"canonical/ 目錄不存在: {canonical_dir}")

    # 建立備份目錄
    backup_dir = data_dir / MIGRATION_LOG_DIR / f"backup_{migration_id}"
    backup_dir.parent.mkdir(parents=True, exist_ok=True)

    try:
        # 複製整個 canonical 目錄
        shutil.copytree(canonical_dir, backup_dir / "canonical")
        return backup_dir
    except Exception as e:
        raise MigrationError(f"備份失敗: {e}")


def restore_backup(backup_path: Path, data_dir: Path) -> None:
    """從備份還原 canonical/

    Args:
        backup_path: 備份目錄路徑
        data_dir: 資料目錄根路徑

    Raises:
        MigrationError: 還原失敗
    """
    canonical_dir = data_dir / CANONICAL_DIR
    backup_canonical = backup_path / "canonical"

    if not backup_canonical.exists():
        raise MigrationError(f"備份目錄不存在: {backup_canonical}")

    try:
        # 移除現有 canonical/
        if canonical_dir.exists():
            shutil.rmtree(canonical_dir)

        # 從備份還原
        shutil.copytree(backup_canonical, canonical_dir)
    except Exception as e:
        raise MigrationError(f"還原失敗: {e}")


def append_migration_log(entry: MigrationEntry, data_dir: Path) -> None:
    """追加遷移日誌

    Args:
        entry: 遷移日誌條目
        data_dir: 資料目錄根路徑

    Raises:
        MigrationError: 寫入失敗
    """
    log_dir = data_dir / MIGRATION_LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / "migration_log.jsonl"

    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(entry.to_jsonl() + "\n")
    except Exception as e:
        raise MigrationError(f"寫入遷移日誌失敗: {e}")


def read_migration_log(data_dir: Path) -> list[MigrationEntry]:
    """讀取遷移日誌

    Args:
        data_dir: 資料目錄根路徑

    Returns:
        遷移日誌條目列表
    """
    log_file = data_dir / MIGRATION_LOG_DIR / "migration_log.jsonl"

    if not log_file.exists():
        return []

    entries = []
    with open(log_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = MigrationEntry.from_jsonl(line)
                entries.append(entry)
            except Exception:
                # 跳過無效條目
                continue

    return entries


def needs_migration(data_dir: Path) -> tuple[bool, str, list[Path]]:
    """檢查是否需要遷移

    Args:
        data_dir: 資料目錄根路徑

    Returns:
        (是否需要遷移, 原因說明, 需遷移的檔案列表)
    """
    version_map = check_schema_version(data_dir)

    if not version_map:
        return False, "無 canonical/ 檔案", []

    # 檢查是否有非當前版本的檔案
    outdated_files: list[Path] = []
    versions_found = set()

    for version, files in version_map.items():
        versions_found.add(version)
        if version != CURRENT_SCHEMA_VERSION:
            outdated_files.extend(files)

    if not outdated_files:
        return False, f"所有檔案都是當前版本 ({CURRENT_SCHEMA_VERSION})", []

    versions_str = ", ".join(sorted(versions_found))
    reason = f"發現版本: {versions_str}，當前版本: {CURRENT_SCHEMA_VERSION}"
    return True, reason, outdated_files


def _migrate_1_1_to_1_2(data: dict, file_path: Path) -> dict:
    """將 life_assumptions.yaml 從 V1.1 遷移至 V1.2

    V1.1 → V1.2 變更：
    - 新增 members dict（使用 birth_year 取代 current_age）
    - basic.primary_member 指向 members 中的成員
    - 移除 basic 中的 current_age/retirement_age/expected_lifespan

    注意：
    - 此遷移僅適用於 life_assumptions.yaml
    - birth_year 從 current_age 推算，標記為 estimated

    Args:
        data: 原始 YAML 資料
        file_path: 檔案路徑（用於識別檔案類型）

    Returns:
        遷移後的資料字典
    """
    from life_capital.io.registry import ASSUMPTIONS_FILE
    from life_capital.models.common import DEFAULT_PRIMARY_MEMBER

    # 只處理 life_assumptions.yaml
    if file_path.name != ASSUMPTIONS_FILE:
        return data

    # 檢查是否有 V1.1 legacy 欄位
    basic = data.get("basic", {})
    current_age = basic.get("current_age")
    retirement_age = basic.get("retirement_age")
    expected_lifespan = basic.get("expected_lifespan")

    if current_age is None or retirement_age is None or expected_lifespan is None:
        # 沒有 legacy 欄位，可能已經是 V1.2 或不需要遷移
        return data

    # 取得 base_year 用於推算 birth_year
    metadata = data.get("metadata", {})
    base_year = metadata.get("base_year")
    if base_year is None:
        from datetime import datetime

        base_year = datetime.now().year

    # 推算 birth_year
    birth_year = base_year - current_age

    # 建立預設成員（使用 DEFAULT_PRIMARY_MEMBER）
    member_id = DEFAULT_PRIMARY_MEMBER
    members = {
        member_id: {
            "display_name": member_id.capitalize(),
            "birth_year": birth_year,
            "birth_year_estimated": True,  # 標記為推算值
            "retirement_age": retirement_age,
            "expected_lifespan": expected_lifespan,
        }
    }

    # 更新資料結構
    data["members"] = members

    # 更新 basic（移除 legacy 欄位，新增 primary_member）
    new_basic = {
        "primary_member": member_id,
    }
    data["basic"] = new_basic

    return data


def get_migration_dry_run_message(data: dict, file_path: Path) -> list[str]:
    """取得遷移預覽訊息

    Args:
        data: 原始 YAML 資料
        file_path: 檔案路徑

    Returns:
        訊息列表
    """
    from life_capital.io.registry import ASSUMPTIONS_FILE

    messages = []

    if file_path.name != ASSUMPTIONS_FILE:
        return messages

    basic = data.get("basic", {})
    current_age = basic.get("current_age")

    if current_age is not None:
        metadata = data.get("metadata", {})
        base_year = metadata.get("base_year")
        if base_year is None:
            from datetime import datetime

            base_year = datetime.now().year

        birth_year = base_year - current_age

        messages.append("⚠️  birth_year 推算說明：")
        messages.append(
            f"   - 公式：base_year ({base_year}) - current_age ({current_age}) = {birth_year}"
        )
        messages.append("   - 可能誤差：±1 年（取決於生日是否已過）")
        messages.append("   - 建議：遷移後請確認/修正 birth_year 值")
        messages.append("   - birth_year_estimated 將標記為 true")

    return messages


def migrate_file(
    file_path: Path,
    from_version: str,
    to_version: str,
) -> dict:
    """遷移單一檔案

    注意：此函式目前只更新 schema_version 欄位。
    未來可擴展為支援特定版本間的資料轉換。

    Args:
        file_path: 檔案路徑
        from_version: 原始版本
        to_version: 目標版本

    Returns:
        遷移後的資料字典

    Raises:
        MigrationError: 遷移失敗
    """
    import yaml

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            if file_path.suffix == ".yaml":
                data = yaml.safe_load(f)
            else:
                data = json.load(f)

        if not isinstance(data, dict):
            raise MigrationError(f"檔案內容不是字典: {file_path}")

        # 依據 from_version 和 to_version 執行特定遷移邏輯
        if from_version == "1.1" and to_version == "1.2":
            data = _migrate_1_1_to_1_2(data, file_path)

        # 更新 schema_version
        data["schema_version"] = to_version

        return data

    except MigrationError:
        raise
    except Exception as e:
        raise MigrationError(f"遷移檔案失敗 ({file_path}): {e}")


def write_migrated_file(file_path: Path, data: dict) -> None:
    """原子寫入遷移後的檔案

    Args:
        file_path: 目標路徑
        data: 資料字典

    Raises:
        MigrationError: 寫入失敗
    """
    import yaml

    # 使用臨時檔案進行原子寫入
    fd, tmp_path = tempfile.mkstemp(
        suffix=file_path.suffix,
        prefix=".tmp_migrate_",
        dir=file_path.parent,
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            if file_path.suffix == ".yaml":
                yaml.dump(
                    data,
                    f,
                    default_flow_style=False,
                    allow_unicode=True,
                    sort_keys=False,
                )
            else:
                json.dump(data, f, indent=2, ensure_ascii=False)

        # 原子重命名
        os.replace(tmp_path, file_path)
    except Exception as e:
        # 清理臨時檔案
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise MigrationError(f"寫入遷移檔案失敗 ({file_path}): {e}")


def run_migration(
    data_dir: Path,
    target_version: Optional[str] = None,
    dry_run: bool = False,
    actor: str = "system",
) -> MigrationEntry:
    """執行 schema 遷移

    Args:
        data_dir: 資料目錄根路徑
        target_version: 目標版本（預設為 CURRENT_SCHEMA_VERSION）
        dry_run: 是否只模擬執行
        actor: 執行者

    Returns:
        MigrationEntry 遷移結果

    Raises:
        MigrationError: 遷移失敗
    """
    if target_version is None:
        target_version = CURRENT_SCHEMA_VERSION

    # 檢查是否需要遷移
    needs, reason, outdated_files = needs_migration(data_dir)

    if not needs:
        return MigrationEntry(
            from_version="N/A",
            to_version=target_version,
            status="completed",
            actor=actor,
            completed_at=datetime.now(),
        )

    # 取得原始版本
    version_map = check_schema_version(data_dir)
    from_versions = sorted(set(version_map.keys()) - {target_version, "unknown"})
    from_version = from_versions[0] if from_versions else "unknown"

    # 建立遷移條目
    entry = MigrationEntry(
        from_version=from_version,
        to_version=target_version,
        files_migrated=[str(f.relative_to(data_dir)) for f in outdated_files],
        backup_path="",
        actor=actor,
    )

    if dry_run:
        entry.status = "dry_run"
        entry.completed_at = datetime.now()
        return entry

    try:
        # 建立備份
        backup_path = create_backup(data_dir, entry.migration_id)
        entry.backup_path = str(backup_path)

        # 記錄遷移開始
        append_migration_log(entry, data_dir)

        # 執行遷移
        for file_path in outdated_files:
            file_version = _extract_schema_version(file_path)
            if file_version != target_version:
                migrated_data = migrate_file(file_path, file_version, target_version)
                write_migrated_file(file_path, migrated_data)

        # 更新遷移狀態
        entry.status = "completed"
        entry.completed_at = datetime.now()
        append_migration_log(entry, data_dir)

        return entry

    except Exception as e:
        # 遷移失敗，嘗試還原
        entry.status = "failed"
        entry.error_message = str(e)
        entry.completed_at = datetime.now()

        if entry.backup_path:
            try:
                restore_backup(Path(entry.backup_path), data_dir)
                entry.status = "rolled_back"
            except Exception as restore_error:
                entry.error_message += f" | 還原失敗: {restore_error}"

        append_migration_log(entry, data_dir)
        raise MigrationError(f"遷移失敗: {e}")


def get_migration_status(data_dir: Path) -> dict:
    """取得遷移狀態摘要

    Args:
        data_dir: 資料目錄根路徑

    Returns:
        狀態摘要字典
    """
    version_map = check_schema_version(data_dir)
    needs, reason, outdated_files = needs_migration(data_dir)
    log_entries = read_migration_log(data_dir)

    return {
        "current_schema_version": CURRENT_SCHEMA_VERSION,
        "data_layout_version": DATA_LAYOUT_VERSION,
        "version_distribution": {
            v: len(files) for v, files in version_map.items()
        },
        "needs_migration": needs,
        "migration_reason": reason,
        "outdated_file_count": len(outdated_files),
        "total_migrations": len(log_entries),
        "last_migration": log_entries[-1].model_dump() if log_entries else None,
    }
