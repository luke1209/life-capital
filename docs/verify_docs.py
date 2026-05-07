#!/usr/bin/env python3
"""
文件驗證腳本

檢查 docs/ 目錄下的 Markdown 文件：
1. 引用的檔案是否存在
2. 程式碼區塊語法是否正確
3. 內部連結是否有效
4. 輸出驗證報告
"""

import re
import sys
from pathlib import Path
from typing import List, Tuple, Dict, Any

# 專案根目錄
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
DOCS_DIR = PROJECT_ROOT / "docs"


def find_all_markdown_files() -> List[Path]:
    """找出所有 Markdown 檔案"""
    return list(DOCS_DIR.rglob("*.md"))


def extract_file_references(content: str) -> List[str]:
    """
    從 Markdown 內容中抽取檔案引用

    支援格式：
    - 路徑: `path/to/file.py`
    - 連結: [text](path/to/file.md)
    - 程式碼註解: # See: path/to/file.py
    """
    references = []

    # Pattern 1: Markdown 連結
    link_pattern = r'\[.*?\]\(((?!http)[^)]+)\)'
    references.extend(re.findall(link_pattern, content))

    # Pattern 2: 反引號包裹的路徑（排除單字）
    backtick_pattern = r'`([a-zA-Z0-9_/\.\-]+\.(py|md|yaml|json|txt))`'
    references.extend([match[0] for match in re.findall(backtick_pattern, content)])

    # Pattern 3: 註解中的路徑
    comment_pattern = r'#\s*(?:See|Ref|路徑):\s*([a-zA-Z0-9_/\.\-]+)'
    references.extend(re.findall(comment_pattern, content))

    return list(set(references))  # 去重


def check_file_exists(file_path: str, base_dir: Path) -> Tuple[bool, str]:
    """
    檢查檔案是否存在

    回傳: (exists, resolved_path_or_error_message)
    """
    # 嘗試多種路徑解析方式
    possible_paths = [
        PROJECT_ROOT / file_path,
        base_dir / file_path,
        DOCS_DIR / file_path
    ]

    for path in possible_paths:
        if path.exists():
            return True, str(path.relative_to(PROJECT_ROOT))

    return False, f"找不到檔案: {file_path}"


def extract_code_blocks(content: str) -> List[Tuple[str, str]]:
    """
    抽取 Markdown 中的程式碼區塊

    回傳: [(language, code_content), ...]
    """
    pattern = r'```(\w+)?\n(.*?)\n```'
    matches = re.findall(pattern, content, re.DOTALL)
    return [(lang or "plaintext", code) for lang, code in matches]


def validate_code_block(language: str, code: str) -> Tuple[bool, str]:
    """
    驗證程式碼區塊語法（基本檢查）

    回傳: (is_valid, error_message)
    """
    # Python 語法檢查
    if language == "python":
        try:
            compile(code, "<string>", "exec")
            return True, ""
        except SyntaxError as e:
            return False, f"Python 語法錯誤: {e}"

    # YAML 檢查（需要 PyYAML）
    if language in ["yaml", "yml"]:
        try:
            import yaml
            yaml.safe_load(code)
            return True, ""
        except ImportError:
            return True, "跳過 YAML 驗證（缺少 PyYAML）"
        except Exception as e:
            return False, f"YAML 語法錯誤: {e}"

    # JSON 檢查
    if language == "json":
        try:
            import json
            json.loads(code)
            return True, ""
        except json.JSONDecodeError as e:
            return False, f"JSON 語法錯誤: {e}"

    # 其他語言不檢查（僅標記）
    return True, ""


def extract_internal_links(content: str) -> List[str]:
    """
    抽取 Markdown 內部連結（錨點）

    格式: [text](#section-anchor)
    """
    pattern = r'\[.*?\]\(#([a-zA-Z0-9\-_]+)\)'
    return re.findall(pattern, content)


def extract_section_anchors(content: str) -> List[str]:
    """
    抽取 Markdown 標題生成的錨點

    規則: ## Section Title → #section-title
    """
    pattern = r'^#{1,6}\s+(.+)$'
    titles = re.findall(pattern, content, re.MULTILINE)

    # 轉為錨點格式（小寫 + dash）
    anchors = []
    for title in titles:
        # 移除特殊字元，保留英數字與空白
        clean_title = re.sub(r'[^\w\s\-]', '', title)
        anchor = clean_title.lower().replace(' ', '-')
        anchors.append(anchor)

    return anchors


def verify_document(doc_path: Path) -> Dict[str, Any]:
    """
    驗證單一文件

    回傳: {
        "file": str,
        "errors": [],
        "warnings": [],
        "stats": {}
    }
    """
    result = {
        "file": str(doc_path.relative_to(PROJECT_ROOT)),
        "errors": [],
        "warnings": [],
        "stats": {
            "file_references": 0,
            "code_blocks": 0,
            "internal_links": 0
        }
    }

    try:
        content = doc_path.read_text(encoding="utf-8")
    except Exception as e:
        result["errors"].append(f"讀取檔案失敗: {e}")
        return result

    # Check 1: 檔案引用
    file_refs = extract_file_references(content)
    result["stats"]["file_references"] = len(file_refs)

    for ref in file_refs:
        # 跳過外部連結
        if ref.startswith("http"):
            continue

        exists, message = check_file_exists(ref, doc_path.parent)
        if not exists:
            result["warnings"].append(message)

    # Check 2: 程式碼區塊語法
    code_blocks = extract_code_blocks(content)
    result["stats"]["code_blocks"] = len(code_blocks)

    for idx, (lang, code) in enumerate(code_blocks, start=1):
        is_valid, error_msg = validate_code_block(lang, code)
        if not is_valid:
            result["errors"].append(f"程式碼區塊 {idx} ({lang}): {error_msg}")

    # Check 3: 內部連結
    internal_links = extract_internal_links(content)
    section_anchors = extract_section_anchors(content)
    result["stats"]["internal_links"] = len(internal_links)

    for link in internal_links:
        if link not in section_anchors:
            result["warnings"].append(f"錨點不存在: #{link}")

    return result


def print_report(results: List[Dict[str, Any]]) -> int:
    """
    輸出驗證報告

    回傳: exit_code (0=成功, 1=有警告, 2=有錯誤)
    """
    total_errors = sum(len(r["errors"]) for r in results)
    total_warnings = sum(len(r["warnings"]) for r in results)

    print("=" * 80)
    print("文件驗證報告")
    print("=" * 80)
    print(f"\n總共檢查: {len(results)} 個檔案")
    print(f"錯誤: {total_errors}")
    print(f"警告: {total_warnings}")
    print()

    # 顯示統計
    total_refs = sum(r["stats"]["file_references"] for r in results)
    total_code_blocks = sum(r["stats"]["code_blocks"] for r in results)
    total_links = sum(r["stats"]["internal_links"] for r in results)

    print("統計資訊:")
    print(f"  - 檔案引用: {total_refs}")
    print(f"  - 程式碼區塊: {total_code_blocks}")
    print(f"  - 內部連結: {total_links}")
    print()

    # 顯示問題明細
    if total_errors > 0:
        print("❌ 錯誤明細:")
        print("-" * 80)
        for result in results:
            if result["errors"]:
                print(f"\n📄 {result['file']}")
                for error in result["errors"]:
                    print(f"  ❌ {error}")
        print()

    if total_warnings > 0:
        print("⚠️  警告明細:")
        print("-" * 80)
        for result in results:
            if result["warnings"]:
                print(f"\n📄 {result['file']}")
                for warning in result["warnings"]:
                    print(f"  ⚠️  {warning}")
        print()

    # 成功的檔案
    success_count = sum(1 for r in results if not r["errors"] and not r["warnings"])
    if success_count > 0:
        print(f"✅ {success_count} 個檔案通過驗證")
        print()

    # 決定 exit code
    if total_errors > 0:
        print("🔴 驗證失敗（有錯誤）")
        return 2
    elif total_warnings > 0:
        print("🟡 驗證通過（有警告）")
        return 1
    else:
        print("🟢 驗證完全通過")
        return 0


def main():
    """主函式"""
    print(f"掃描目錄: {DOCS_DIR}")
    print()

    markdown_files = find_all_markdown_files()

    if not markdown_files:
        print("❌ 找不到任何 Markdown 檔案")
        sys.exit(2)

    print(f"找到 {len(markdown_files)} 個 Markdown 檔案")
    print()

    # 驗證所有檔案
    results = []
    for doc_path in sorted(markdown_files):
        print(f"檢查: {doc_path.relative_to(PROJECT_ROOT)}", end=" ... ")
        result = verify_document(doc_path)
        results.append(result)

        # 即時反饋
        if result["errors"]:
            print("❌")
        elif result["warnings"]:
            print("⚠️")
        else:
            print("✅")

    print()

    # 輸出報告
    exit_code = print_report(results)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
