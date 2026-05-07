"""Raw 資料處理模組

提供不可變寫入機制，用於 raw/imports 和 raw/manual 目錄。
所有寫入的檔案自動設為 read-only (chmod 444)。

Phase 1 V4.1: 新增 raw_manifest.json 生成與驗證功能，
用於機器驗證 raw/ 的不可變性（sha256 比對）。
"""

import hashlib
import json
import os
import stat
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Optional
from uuid import uuid4

import yaml
from pydantic import BaseModel

from life_capital.io.errors import CSVError, RawFileExistsError, RawHandlerError
from life_capital.io.registry import RAW_DIR, RAW_IMPORTS_DIR, RAW_MANIFEST_FILE, RAW_MANUAL_DIR
from life_capital.models.operation import Provenance

# 重新導出供向後相容
__all__ = [
    "RawHandlerError",
    "RawFileExistsError",
    "write_raw",
    "read_raw",
    "list_raw_files",
]


RawType = Literal["imports", "manual"]
FileFormat = Literal["yaml", "json", "csv"]


def _generate_filename(format: FileFormat) -> str:
    """生成 raw 檔案名稱

    格式: {timestamp}_{uuid}.{ext}

    Args:
        format: 檔案格式

    Returns:
        檔案名稱，如 "20250127_120530_abc123.yaml"
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = str(uuid4())[:8]
    return f"{timestamp}_{unique_id}.{format}"


def _set_readonly(path: Path) -> None:
    """將檔案設為 read-only (chmod 444)

    Args:
        path: 檔案路徑
    """
    os.chmod(path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)


def _embed_provenance_yaml(data: dict[str, Any], provenance: Provenance) -> dict[str, Any]:
    """將 Provenance 資訊嵌入 YAML 資料

    使用 _provenance 欄位（front-matter style）

    Args:
        data: 原始資料
        provenance: 來源追溯資訊

    Returns:
        包含 _provenance 的資料
    """
    result = {"_provenance": provenance.model_dump(mode="json")}
    result.update(data)
    return result


def _embed_provenance_json(data: dict[str, Any], provenance: Provenance) -> dict[str, Any]:
    """將 Provenance 資訊嵌入 JSON 資料

    使用 _provenance 欄位

    Args:
        data: 原始資料
        provenance: 來源追溯資訊

    Returns:
        包含 _provenance 的資料
    """
    result = {"_provenance": provenance.model_dump(mode="json")}
    result.update(data)
    return result


def _extract_provenance_from_dict(data: dict[str, Any]) -> Optional[Provenance]:
    """從字典中提取 Provenance 資訊

    Args:
        data: 資料字典

    Returns:
        Provenance 實例或 None
    """
    if "_provenance" in data:
        try:
            return Provenance.model_validate(data["_provenance"])
        except Exception:
            return None
    return None


def write_raw(
    data: "BaseModel | dict[str, Any]",
    target: RawType,
    provenance: Provenance,
    format: FileFormat = "yaml",
    base_dir: Optional[Path] = None,
) -> Path:
    """寫入 raw 資料（不可變寫入）

    寫入後檔案自動設為 read-only (chmod 444)，
    且記錄 Provenance 資訊。

    Args:
        data: 要寫入的資料（BaseModel 或 dict）
        target: 目標目錄類型 (imports 或 manual)
        provenance: 來源追溯資訊
        format: 檔案格式 (yaml, json, csv)
        base_dir: 資料目錄根路徑（預設使用環境變數）

    Returns:
        寫入的檔案路徑

    Raises:
        RawFileExistsError: 檔案已存在
        RawHandlerError: 寫入失敗
        ValueError: 不支援的格式
    """
    if base_dir is None:
        from life_capital.utils.path_resolver import resolve_data_dir

        base_dir = resolve_data_dir()

    # 確定目標目錄
    if target == "imports":
        target_dir = base_dir / RAW_IMPORTS_DIR
    else:
        target_dir = base_dir / RAW_MANUAL_DIR

    target_dir.mkdir(parents=True, exist_ok=True)

    # 生成檔案名稱
    filename = _generate_filename(format)
    file_path = target_dir / filename

    # 檢查檔案是否已存在（理論上不應該，但保險起見）
    if file_path.exists():
        raise RawFileExistsError(file_path)

    # 準備資料
    if isinstance(data, BaseModel):
        data_dict = data.model_dump(mode="json")
    else:
        data_dict = data

    # 檢查格式
    if format not in ("yaml", "json", "csv"):
        raise ValueError(f"不支援的格式: {format}")

    # 根據格式寫入
    try:
        if format == "yaml":
            # 嵌入 Provenance
            data_with_provenance = _embed_provenance_yaml(data_dict, provenance)

            # 使用臨時檔案 + rename 確保原子性
            fd, tmp_path = tempfile.mkstemp(
                suffix=".yaml", prefix=".tmp_", dir=target_dir
            )

            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    yaml.dump(
                        data_with_provenance,
                        f,
                        default_flow_style=False,
                        allow_unicode=True,
                        sort_keys=False,
                    )

                # 原子重命名
                os.replace(tmp_path, file_path)

            except Exception as e:
                # 清理臨時檔案
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise RawHandlerError(f"YAML 寫入失敗: {e}")

        elif format == "json":
            # 嵌入 Provenance
            data_with_provenance = _embed_provenance_json(data_dict, provenance)

            # 使用臨時檔案 + rename
            fd, tmp_path = tempfile.mkstemp(
                suffix=".json", prefix=".tmp_", dir=target_dir
            )

            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(data_with_provenance, f, ensure_ascii=False, indent=2)

                os.replace(tmp_path, file_path)

            except Exception as e:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise RawHandlerError(f"JSON 寫入失敗: {e}")

        elif format == "csv":
            # CSV 格式使用註解記錄 Provenance
            fd, tmp_path = tempfile.mkstemp(
                suffix=".csv", prefix=".tmp_", dir=target_dir
            )

            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    # 寫入 Provenance 註解
                    f.write(f"# Provenance: {provenance.model_dump_json()}\n")

                    # 寫入實際資料（假設 data_dict 包含 'rows' 和 'headers'）
                    if "headers" in data_dict and "rows" in data_dict:
                        import csv

                        writer = csv.DictWriter(f, fieldnames=data_dict["headers"])
                        writer.writeheader()
                        writer.writerows(data_dict["rows"])
                    else:
                        raise ValueError("CSV 格式需要包含 'headers' 和 'rows' 欄位")

                os.replace(tmp_path, file_path)

            except Exception as e:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise RawHandlerError(f"CSV 寫入失敗: {e}")

        # 設為 read-only
        _set_readonly(file_path)

        return file_path

    except RawFileExistsError:
        raise
    except Exception as e:
        raise RawHandlerError(f"寫入失敗 ({file_path}): {e}")


def read_raw(
    file_path: Path,
    model_class: Optional[type[BaseModel]] = None,
) -> "tuple[dict[str, Any] | BaseModel, Optional[Provenance]]":
    """讀取 raw 資料

    自動偵測檔案格式（YAML/JSON/CSV）並解析。

    Args:
        file_path: 檔案路徑
        model_class: Pydantic 模型類別（可選，若提供則驗證資料）

    Returns:
        (解析後的資料, Provenance 資訊)
        若 model_class 為 None，返回 dict；否則返回 model_class 實例

    Raises:
        FileNotFoundError: 檔案不存在
        RawHandlerError: 讀取失敗
    """
    if not file_path.exists():
        raise FileNotFoundError(f"檔案不存在: {file_path}")

    suffix = file_path.suffix.lower()

    try:
        if suffix in [".yaml", ".yml"]:
            with open(file_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if data is None:
                data = {}

            # 提取 Provenance
            provenance = _extract_provenance_from_dict(data)

            # 移除 _provenance 欄位
            if "_provenance" in data:
                data = {k: v for k, v in data.items() if k != "_provenance"}

        elif suffix == ".json":
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 提取 Provenance
            provenance = _extract_provenance_from_dict(data)

            # 移除 _provenance 欄位
            if "_provenance" in data:
                data = {k: v for k, v in data.items() if k != "_provenance"}

        elif suffix == ".csv":
            # CSV 格式從註解中提取 Provenance
            import csv

            provenance = None
            rows = []

            with open(file_path, "r", encoding="utf-8") as f:
                # 讀取第一行檢查 Provenance
                first_line = f.readline()
                if first_line.startswith("# Provenance:"):
                    try:
                        prov_json = first_line.replace("# Provenance:", "").strip()
                        provenance = Provenance.model_validate_json(prov_json)
                    except Exception:
                        pass
                else:
                    # 重置檔案指標
                    f.seek(0)

                reader = csv.DictReader(f)
                if reader.fieldnames is None:
                    raise CSVError("CSV 檔案為空或無表頭")

                rows = list(reader)

            data = {"headers": list(reader.fieldnames), "rows": rows}

        else:
            raise ValueError(f"不支援的檔案格式: {suffix}")

        # 若提供 model_class，進行驗證
        if model_class is not None:
            validated_data = model_class.model_validate(data)
            return validated_data, provenance

        return data, provenance

    except Exception as e:
        raise RawHandlerError(f"讀取失敗 ({file_path}): {e}")


def list_raw_files(
    raw_type: RawType,
    since: Optional[datetime] = None,
    base_dir: Optional[Path] = None,
) -> list[Path]:
    """列出 raw 目錄檔案

    Args:
        raw_type: 目錄類型 (imports 或 manual)
        since: 篩選時間（僅返回此時間之後的檔案）
        base_dir: 資料目錄根路徑（預設使用環境變數）

    Returns:
        檔案路徑列表（按時間戳排序）
    """
    if base_dir is None:
        from life_capital.utils.path_resolver import resolve_data_dir

        base_dir = resolve_data_dir()

    # 確定目標目錄
    if raw_type == "imports":
        target_dir = base_dir / RAW_IMPORTS_DIR
    else:
        target_dir = base_dir / RAW_MANUAL_DIR

    if not target_dir.exists():
        return []

    # 列出所有檔案
    files = [f for f in target_dir.iterdir() if f.is_file() and not f.name.startswith(".")]

    # 篩選時間
    if since is not None:
        files = [f for f in files if datetime.fromtimestamp(f.stat().st_mtime) >= since]

    # 按檔案名稱排序（檔案名稱包含時間戳）
    files.sort()

    return files


# === Phase 1 V4.1: raw_manifest.json 相關函式 ===


def _compute_file_sha256(file_path: Path) -> str:
    """計算檔案的 SHA-256 hash

    Args:
        file_path: 檔案路徑

    Returns:
        64 字元的 hex hash
    """
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        # 分塊讀取以處理大檔案
        for chunk in iter(lambda: f.read(8192), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


def generate_raw_manifest(base_dir: Optional[Path] = None) -> dict[str, Any]:
    """生成 raw/ 目錄的 manifest

    掃描 raw/ 目錄下所有檔案，記錄路徑、大小、修改時間、SHA-256 hash。

    Args:
        base_dir: 資料目錄根路徑（預設使用環境變數）

    Returns:
        manifest 字典，包含 generated_at 和 files 陣列

    Raises:
        RawHandlerError: 生成失敗
    """
    if base_dir is None:
        from life_capital.utils.path_resolver import resolve_data_dir

        base_dir = resolve_data_dir()

    raw_dir = base_dir / RAW_DIR

    if not raw_dir.exists():
        return {
            "generated_at": datetime.now().isoformat(),
            "files": [],
        }

    files_info: list[dict[str, Any]] = []

    try:
        # 遞迴掃描 raw/ 目錄
        for file_path in sorted(raw_dir.rglob("*")):
            # 跳過目錄和隱藏檔案
            if file_path.is_dir() or file_path.name.startswith("."):
                continue

            # 跳過 raw_manifest.json 自身（避免循環參考）
            if file_path.name == "raw_manifest.json":
                continue

            # 計算相對路徑（相對於 raw/）
            relative_path = file_path.relative_to(raw_dir)

            # 取得檔案資訊
            stat_info = file_path.stat()

            files_info.append(
                {
                    "path": str(relative_path),
                    "size": stat_info.st_size,
                    "mtime": datetime.fromtimestamp(stat_info.st_mtime).isoformat(),
                    "sha256": _compute_file_sha256(file_path),
                }
            )

        manifest = {
            "generated_at": datetime.now().isoformat(),
            "files": files_info,
        }

        return manifest

    except Exception as e:
        raise RawHandlerError(f"生成 raw_manifest 失敗: {e}")


def save_raw_manifest(base_dir: Optional[Path] = None) -> Path:
    """生成並儲存 raw_manifest.json

    Args:
        base_dir: 資料目錄根路徑（預設使用環境變數）

    Returns:
        manifest 檔案路徑

    Raises:
        RawHandlerError: 儲存失敗
    """
    if base_dir is None:
        from life_capital.utils.path_resolver import resolve_data_dir

        base_dir = resolve_data_dir()

    manifest = generate_raw_manifest(base_dir)
    manifest_path = base_dir / RAW_MANIFEST_FILE

    # 確保父目錄存在
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        # 若檔案已存在且為 read-only，先暫時設為可寫
        if manifest_path.exists():
            current_mode = manifest_path.stat().st_mode
            if not (current_mode & stat.S_IWUSR):  # 沒有 user write 權限
                os.chmod(manifest_path, current_mode | stat.S_IWUSR)

        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        # 設為 read-only（與其他 raw/ 檔案一致）
        _set_readonly(manifest_path)

        return manifest_path

    except Exception as e:
        raise RawHandlerError(f"儲存 raw_manifest 失敗: {e}")


def load_raw_manifest(base_dir: Optional[Path] = None) -> Optional[dict[str, Any]]:
    """讀取 raw_manifest.json

    Args:
        base_dir: 資料目錄根路徑（預設使用環境變數）

    Returns:
        manifest 字典，若檔案不存在則返回 None

    Raises:
        RawHandlerError: 讀取或解析失敗
    """
    if base_dir is None:
        from life_capital.utils.path_resolver import resolve_data_dir

        base_dir = resolve_data_dir()

    manifest_path = base_dir / RAW_MANIFEST_FILE

    if not manifest_path.exists():
        return None

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)

    except Exception as e:
        raise RawHandlerError(f"讀取 raw_manifest 失敗: {e}")


class RawManifestCheckResult:
    """raw_manifest 驗證結果"""

    def __init__(
        self,
        passed: bool,
        message: str,
        modified_files: Optional[list[str]] = None,
        missing_files: Optional[list[str]] = None,
        new_files: Optional[list[str]] = None,
    ):
        self.passed = passed
        self.message = message
        self.modified_files = modified_files or []
        self.missing_files = missing_files or []
        self.new_files = new_files or []


class DuplicateImportResult:
    """重複匯入檢查結果"""

    def __init__(
        self,
        is_duplicate: bool,
        existing_file: Optional[str] = None,
        existing_hash: Optional[str] = None,
    ):
        self.is_duplicate = is_duplicate
        self.existing_file = existing_file
        self.existing_hash = existing_hash


def check_duplicate_import(
    csv_path: Path,
    base_dir: Optional[Path] = None,
) -> DuplicateImportResult:
    """檢查 CSV 是否已匯入過

    透過 SHA-256 hash 比對 raw/imports/ 中檔案的 Provenance.source_hash，
    偵測重複匯入。

    Args:
        csv_path: 要匯入的 CSV 檔案路徑
        base_dir: 資料目錄根路徑（預設使用環境變數）

    Returns:
        DuplicateImportResult 實例

    Raises:
        FileNotFoundError: CSV 檔案不存在
        RawHandlerError: 檢查失敗
    """
    if not csv_path.exists():
        raise FileNotFoundError(f"檔案不存在: {csv_path}")

    if base_dir is None:
        from life_capital.utils.path_resolver import resolve_data_dir

        base_dir = resolve_data_dir()

    try:
        # 計算輸入檔案的 hash
        input_hash = _compute_file_sha256(csv_path)

        # 檢查 raw/imports/ 目錄中的檔案，比對 Provenance.source_hash
        imports_dir = base_dir / RAW_IMPORTS_DIR
        if imports_dir.exists():
            for existing_file in imports_dir.iterdir():
                if existing_file.is_file() and existing_file.suffix == ".csv":
                    # 讀取檔案並提取 Provenance
                    try:
                        _, provenance = read_raw(existing_file)
                        if provenance and provenance.source_hash == input_hash:
                            return DuplicateImportResult(
                                is_duplicate=True,
                                existing_file=f"imports/{existing_file.name}",
                                existing_hash=input_hash,
                            )
                    except Exception:
                        # 無法解析的檔案跳過
                        continue

        return DuplicateImportResult(is_duplicate=False)

    except FileNotFoundError:
        raise
    except Exception as e:
        raise RawHandlerError(f"檢查重複匯入失敗: {e}")


def verify_raw_manifest(base_dir: Optional[Path] = None) -> RawManifestCheckResult:
    """驗證 raw/ 目錄與 manifest 的一致性

    透過 SHA-256 比對驗證 raw/ 內容是否被修改。

    Args:
        base_dir: 資料目錄根路徑（預設使用環境變數）

    Returns:
        RawManifestCheckResult 實例

    Raises:
        RawHandlerError: 驗證過程失敗
    """
    if base_dir is None:
        from life_capital.utils.path_resolver import resolve_data_dir

        base_dir = resolve_data_dir()

    # 讀取現有 manifest
    manifest = load_raw_manifest(base_dir)

    if manifest is None:
        return RawManifestCheckResult(
            passed=False,
            message="raw_manifest.json 不存在",
        )

    raw_dir = base_dir / RAW_DIR

    if not raw_dir.exists():
        return RawManifestCheckResult(
            passed=False,
            message="raw/ 目錄不存在",
        )

    # 建立 manifest 中檔案的 hash 對照表
    manifest_files: dict[str, str] = {
        entry["path"]: entry["sha256"] for entry in manifest.get("files", [])
    }

    modified_files: list[str] = []
    missing_files: list[str] = []
    new_files: list[str] = []

    try:
        # 檢查現有檔案
        current_files: set[str] = set()

        for file_path in raw_dir.rglob("*"):
            # 跳過目錄和隱藏檔案
            if file_path.is_dir() or file_path.name.startswith("."):
                continue

            relative_path = str(file_path.relative_to(raw_dir))

            # 跳過 raw_manifest.json 自身（它會在匯入時更新，不應被視為違規）
            if file_path.name == "raw_manifest.json":
                continue

            current_files.add(relative_path)

            if relative_path not in manifest_files:
                # 新增的檔案（不在 manifest 中）
                new_files.append(relative_path)
            else:
                # 比對 hash
                current_hash = _compute_file_sha256(file_path)
                if current_hash != manifest_files[relative_path]:
                    modified_files.append(relative_path)

        # 檢查遺失的檔案（排除 raw_manifest.json）
        for path in manifest_files:
            if path == "raw_manifest.json":
                continue
            if path not in current_files:
                missing_files.append(path)

        # 判定結果
        if modified_files or missing_files:
            # 有修改或遺失 → HARD_FAIL
            issues = []
            if modified_files:
                issues.append(f"已修改: {', '.join(modified_files)}")
            if missing_files:
                issues.append(f"已遺失: {', '.join(missing_files)}")

            return RawManifestCheckResult(
                passed=False,
                message=f"raw/ 內容不一致: {'; '.join(issues)}",
                modified_files=modified_files,
                missing_files=missing_files,
                new_files=new_files,
            )

        if new_files:
            # 有新增檔案 → 警告（但通過）
            return RawManifestCheckResult(
                passed=True,
                message=f"raw/ 有新增檔案（建議更新 manifest）: {', '.join(new_files)}",
                new_files=new_files,
            )

        return RawManifestCheckResult(
            passed=True,
            message="raw/ 內容與 manifest 一致",
        )

    except Exception as e:
        raise RawHandlerError(f"驗證 raw_manifest 失敗: {e}")
