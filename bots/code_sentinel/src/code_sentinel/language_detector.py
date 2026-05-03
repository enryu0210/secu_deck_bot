"""파일 확장자 → 언어 매핑."""
from __future__ import annotations


_EXT_TO_LANG = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".c": "c",
    ".cpp": "cpp",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".sh": "bash",
    ".sql": "sql",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
}


def detect_language(filename: str | None, code_hint: str = "") -> str:
    """파일명 우선, 없으면 코드 휴리스틱.

    이건 LLM 호출 전 '대략적' 분류라 정확하지 않아도 OK.
    """
    if filename:
        lower = filename.lower()
        for ext, lang in _EXT_TO_LANG.items():
            if lower.endswith(ext):
                return lang

    # 코드 휴리스틱 — 첫 200자만 검사
    sample = code_hint[:500].lower()
    if "def " in sample or "import " in sample and "from " in sample:
        return "python"
    if "function " in sample or "const " in sample or "=>" in sample:
        return "javascript"
    if "interface " in sample and "type " in sample:
        return "typescript"
    if "package main" in sample or "func " in sample:
        return "go"

    return "text"
