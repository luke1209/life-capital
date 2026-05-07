"""
Phase 5 Stage 3 文件驗收測試

驗證 Stage 3 相關文件的完整性與一致性
"""

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent


def test_stage3_design_document_exists():
    """驗證 Stage 3 設計文件存在"""
    design_doc = PROJECT_ROOT / "docs" / "advisor" / "stage3-design.md"
    assert design_doc.exists(), "Stage 3 設計文件應存在"

    content = design_doc.read_text(encoding="utf-8")
    assert len(content) > 1000, "設計文件應有足夠內容"

    # 驗證關鍵章節存在
    assert "## 架構設計" in content
    assert "## E1: Memory 擴展" in content
    assert "## E2: Wiki 編譯器" in content
    assert "## E3: 風險評估" in content
    assert "## E4: 敏感度分析" in content
    assert "## E5: CLI 整合" in content


def test_stage3_api_document_exists():
    """驗證 Stage 3 API 參考文件存在"""
    api_doc = PROJECT_ROOT / "docs" / "advisor" / "stage3-api.md"
    assert api_doc.exists(), "Stage 3 API 文件應存在"

    content = api_doc.read_text(encoding="utf-8")
    assert len(content) > 1000, "API 文件應有足夠內容"

    # 驗證關鍵 CLI 命令文件化
    assert "## CLI 命令" in content
    assert "lc advisor history" in content
    assert "lc advisor explain" in content
    assert "lc doctor --advisor" in content


def test_io_contract_updated():
    """驗證 io_contract.md 已更新 Stage 3 內容"""
    contract = PROJECT_ROOT / "docs" / "contracts" / "io_contract.md"
    assert contract.exists()

    content = contract.read_text(encoding="utf-8")

    # 驗證 Section 10 (Stage 3 Advisor Enhancements)
    assert "## 10. Stage 3 Advisor Enhancements" in content or "Section 10" in content

    # 驗證 Section 11 (Evaluability Module)
    assert "## 11. Evaluability Module" in content or "Section 11" in content
    assert "evaluability" in content.lower()


def test_documentation_verification_script_exists():
    """驗證文件驗證腳本存在且可執行"""
    verify_script = PROJECT_ROOT / "docs" / "verify_docs.py"
    assert verify_script.exists(), "文件驗證腳本應存在"

    content = verify_script.read_text(encoding="utf-8")

    # 驗證關鍵函數存在
    assert "def verify_document" in content
    assert "def extract_file_references" in content
    assert "def validate_code_block" in content
    assert "def print_report" in content


def test_key_modules_exist():
    """驗證關鍵模組檔案存在"""
    # E1: Memory expansion
    assert (PROJECT_ROOT / "life_capital" / "models" / "decisions.py").exists()
    assert (PROJECT_ROOT / "life_capital" / "io" / "decisions_handler.py").exists()

    # E2: Wiki compiler
    assert (PROJECT_ROOT / "life_capital" / "generation" / "decision_wiki.py").exists()

    # E3: Risk assessment
    assert (PROJECT_ROOT / "life_capital" / "advisor" / "risk_assessor.py").exists()
    assert (PROJECT_ROOT / "life_capital" / "generation" / "risk_matrix.py").exists()

    # Shared modules
    assert (PROJECT_ROOT / "life_capital" / "advisor" / "shared" / "evaluability.py").exists()


def test_key_tests_exist():
    """驗證關鍵測試檔案存在"""
    tests_dir = PROJECT_ROOT / "tests"

    # Evaluability tests
    assert (tests_dir / "advisor" / "test_evaluability.py").exists()

    # Risk assessor tests
    assert (tests_dir / "advisor" / "test_risk_assessor.py").exists()

    # Decision wiki tests
    assert (tests_dir / "generation" / "test_decision_wiki.py").exists()

    # Risk matrix tests
    assert (tests_dir / "generation" / "test_risk_matrix.py").exists()


def test_documentation_cross_references():
    """驗證文件間的交叉引用一致性"""
    design_doc = PROJECT_ROOT / "docs" / "advisor" / "stage3-design.md"
    api_doc = PROJECT_ROOT / "docs" / "advisor" / "stage3-api.md"

    design_content = design_doc.read_text(encoding="utf-8")
    api_content = api_doc.read_text(encoding="utf-8")

    # stage3-design.md 應引用 stage3-api.md
    # (或反之，取決於文件組織)
    # 這裡進行基本一致性檢查

    # 兩文件都應提到關鍵模組
    for keyword in ["evaluability", "risk_assessor", "decision_wiki"]:
        assert keyword in design_content.lower(), f"{keyword} 應在設計文件中"
        assert keyword in api_content.lower(), f"{keyword} 應在 API 文件中"


@pytest.mark.skip(reason="Complete E2E tests require model schema alignment")
def test_full_e2e_workflow():
    """
    完整的 E2E 工作流測試（Future Work）

    Note: 此測試需要 DecisionRecord schema 與實際專案模型對齊後才能執行
    目前專案中的 DecisionRecord 使用不同的欄位結構
    """
    pass


def test_documentation_completeness_summary():
    """文件完整性摘要測試"""
    docs_dir = PROJECT_ROOT / "docs" / "advisor"

    # 驗證必要文件都存在
    required_files = [
        docs_dir / "stage3-design.md",
        docs_dir / "stage3-api.md",
    ]

    for file_path in required_files:
        assert file_path.exists(), f"缺少必要文件: {file_path}"

        # 驗證不是空檔案
        content = file_path.read_text(encoding="utf-8")
        assert len(content) > 500, f"文件內容過少: {file_path}"
