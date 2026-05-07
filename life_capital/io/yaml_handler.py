"""YAML 讀寫模組

提供原子寫入功能，確保資料一致性。
"""

import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

import yaml
from pydantic import BaseModel

from life_capital.io.errors import YAMLError, YAMLParseError, YAMLValidationError

if TYPE_CHECKING:
    from life_capital.models.base import VersionedModel

T = TypeVar("T", bound=BaseModel)


# 重新導出供向後相容
__all__ = [
    "YAMLError",
    "YAMLParseError",
    "YAMLValidationError",
    "load_yaml",
    "save_yaml",
    "load_model",
    "save_model",
    "validate_version",
]


def load_yaml(path: Path) -> dict[str, Any]:
    """讀取 YAML 檔案

    Args:
        path: YAML 檔案路徑

    Returns:
        解析後的字典

    Raises:
        FileNotFoundError: 檔案不存在
        YAMLParseError: YAML 解析失敗
    """
    if not path.exists():
        raise FileNotFoundError(f"檔案不存在: {path}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data if data is not None else {}
    except yaml.YAMLError as e:
        raise YAMLParseError(path, str(e))


def save_yaml(path: Path, data: dict[str, Any]) -> None:
    """原子寫入 YAML 檔案

    使用臨時檔案 + rename 確保寫入的原子性。

    Args:
        path: 目標路徑
        data: 要寫入的資料

    Raises:
        PermissionError: 無寫入權限
        YAMLError: 寫入失敗
    """
    # 確保父目錄存在
    path.parent.mkdir(parents=True, exist_ok=True)

    # 使用臨時檔案進行原子寫入
    fd, tmp_path = tempfile.mkstemp(
        suffix=".yaml", prefix=".tmp_", dir=path.parent
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            yaml.dump(
                data,
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )

        # 原子重命名
        os.replace(tmp_path, path)

    except Exception as e:
        # 清理臨時檔案
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise YAMLError(f"寫入失敗 ({path}): {e}")


def load_model(path: Path, model_class: type[T]) -> T:
    """讀取 YAML 並解析為 Pydantic 模型

    Args:
        path: YAML 檔案路徑
        model_class: Pydantic 模型類別

    Returns:
        解析後的模型實例

    Raises:
        FileNotFoundError: 檔案不存在
        YAMLParseError: YAML 解析失敗
        YAMLValidationError: 模型驗證失敗
    """
    data = load_yaml(path)

    try:
        return model_class.model_validate(data)
    except Exception as e:
        # 提取 Pydantic 驗證錯誤
        errors = []
        if hasattr(e, "errors"):
            for err in e.errors():
                loc = ".".join(str(x) for x in err["loc"])
                msg = err["msg"]
                errors.append(f"{loc}: {msg}")
        else:
            errors.append(str(e))

        raise YAMLValidationError(path, errors)


def save_model(path: Path, model: BaseModel) -> None:
    """將 Pydantic 模型儲存為 YAML

    Args:
        path: 目標路徑
        model: Pydantic 模型實例
    """
    # 使用 model_dump 保留 enum 值為字串
    data = model.model_dump(mode="json")
    save_yaml(path, data)


def validate_version(path: Path, model: "VersionedModel") -> None:
    """驗證模型版本

    Args:
        path: 來源檔案路徑（用於錯誤訊息）
        model: 已載入的模型

    Raises:
        YAMLValidationError: 版本不匹配
    """
    if not model.is_current_version():
        raise YAMLValidationError(
            path,
            [
                f"Schema 版本不匹配: 檔案版本 {model.schema_version}",
                "請執行: lc migrate",
            ],
        )
