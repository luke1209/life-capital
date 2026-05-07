"""I/O 層共用例外類別

此模組定義 I/O 層的基礎例外類別，
用於避免模組間循環導入問題。
"""


class IOError(Exception):
    """I/O 層基礎例外"""

    pass


class CSVError(IOError):
    """CSV 處理錯誤基類"""

    pass


class CSVParseError(CSVError):
    """CSV 解析錯誤"""

    def __init__(self, path, line: int, message: str):
        self.path = path
        self.line = line
        super().__init__(f"解析 CSV 失敗 ({path}, 第 {line} 行): {message}")


class YAMLError(IOError):
    """YAML 處理錯誤基類"""

    pass


class YAMLParseError(YAMLError):
    """YAML 解析錯誤"""

    def __init__(self, path, message: str):
        self.path = path
        super().__init__(f"解析 YAML 失敗 ({path}): {message}")


class YAMLValidationError(YAMLError):
    """YAML 驗證錯誤"""

    def __init__(self, path, errors: list):
        self.path = path
        self.errors = errors
        error_list = "\n  - ".join(errors)
        super().__init__(f"驗證失敗 ({path}):\n  - {error_list}")


class RawHandlerError(IOError):
    """Raw handler 錯誤基類"""

    pass


class RawFileExistsError(RawHandlerError):
    """Raw 檔案已存在錯誤"""

    def __init__(self, path):
        self.path = path
        super().__init__(f"Raw 檔案已存在且不可覆寫: {path}")


class PathSecurityError(IOError):
    """路徑安全驗證錯誤

    當檔案路徑不符合安全規則時拋出，防止 path traversal 攻擊。
    """

    def __init__(self, message: str):
        super().__init__(f"路徑安全驗證失敗: {message}")
