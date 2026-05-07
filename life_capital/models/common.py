"""共用常數與型別定義

此模組定義跨模型使用的常數，作為驗證層的唯一真相來源。
"""

# === 成員 ID 限制 ===
# 使用 set 而非 Literal，便於未來擴展（只需修改此處）
ALLOWED_MEMBER_IDS: set[str] = {"person_a", "person_b"}

# === 預設成員 ===
DEFAULT_PRIMARY_MEMBER: str = "person_a"
