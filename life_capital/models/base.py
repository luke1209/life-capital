"""基礎資料模型

提供版本化模型基底類別。
"""

from pydantic import BaseModel, ConfigDict

from life_capital.io.registry import CURRENT_SCHEMA_VERSION


class VersionedModel(BaseModel):
    """帶有 schema_version 的基底模型

    所有需要版本控制的資料模型都應繼承此類別。
    """

    model_config = ConfigDict(
        # 允許額外欄位（向前相容）
        extra="ignore",
        # 驗證賦值
        validate_assignment=True,
    )

    schema_version: str = CURRENT_SCHEMA_VERSION

    def is_current_version(self) -> bool:
        """檢查是否為當前版本"""
        return self.schema_version == CURRENT_SCHEMA_VERSION

    def validate_version(self) -> None:
        """驗證 schema 版本

        Raises:
            ValueError: 版本不匹配
        """
        if not self.is_current_version():
            raise ValueError(
                f"Schema 版本不匹配: {self.schema_version} != {CURRENT_SCHEMA_VERSION}\n"
                f"請執行: lc migrate"
            )
