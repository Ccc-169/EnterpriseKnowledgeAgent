"""
data/file_parser.py — 上传附件内容提取

支持格式：.txt .md .py .csv .json .yaml .log .docx .pdf .xlsx
对不支持或解析失败的格式返回友好提示。
"""

import io
from pathlib import Path


def extract_file_content(uploaded_file, max_chars: int = 8000) -> str:
    """从 Streamlit UploadedFile 中提取文本内容。

    Args:
        uploaded_file: st.file_uploader 返回的文件对象
        max_chars: 最大返回字符数，超出截断

    Returns:
        提取的文本内容字符串；失败时返回错误提示。
    """
    name = uploaded_file.name
    ext = Path(name).suffix.lower()
    content = uploaded_file.getvalue()

    text = _extract_by_extension(name, ext, content)

    if text.startswith("[无法解析"):
        return text

    if len(text) > max_chars:
        text = text[:max_chars] + f"\n\n...（内容过长，已截断，共 {len(text)} 字符）"

    return text


def _extract_by_extension(name: str, ext: str, content: bytes) -> str:
    """根据扩展名分派到对应解析器。"""
    if ext in (".txt", ".md", ".py", ".csv", ".json", ".yaml", ".yml", ".log"):
        return _read_text(content, name)

    elif ext == ".docx":
        return _read_docx(content, name)

    elif ext == ".pdf":
        return _read_pdf(content, name)

    elif ext in (".xlsx", ".xls"):
        return _read_xlsx(content, name)

    else:
        return f"[不支持的文件格式 {ext}：{name}]"


# ── 文本类 ─────────────────────────────────────────────────────────────

def _read_text(content: bytes, name: str) -> str:
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return content.decode("gbk", errors="ignore")


# ── Word ───────────────────────────────────────────────────────────────

def _read_docx(content: bytes, name: str) -> str:
    try:
        from docx import Document
        doc = Document(io.BytesIO(content))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except ImportError:
        return f"[无法解析 {name}：请安装 python-docx]"
    except Exception as e:
        return f"[无法解析 {name}：{e}]"


# ── PDF ────────────────────────────────────────────────────────────────

def _read_pdf(content: bytes, name: str) -> str:
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(io.BytesIO(content))
        return "\n".join(
            (page.extract_text() or "") for page in reader.pages
        )
    except ImportError:
        return f"[无法解析 {name}：请安装 PyPDF2]"
    except Exception as e:
        return f"[无法解析 {name}：{e}]"


# ── Excel ──────────────────────────────────────────────────────────────

def _read_xlsx(content: bytes, name: str) -> str:
    try:
        import pandas as pd
        xls = pd.ExcelFile(io.BytesIO(content))
        sheets_text = []
        for sheet in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=sheet)
            sheets_text.append(f"【Sheet: {sheet}】\n{df.to_string(index=False)}")
        return "\n\n".join(sheets_text)
    except ImportError:
        return f"[无法解析 {name}：请安装 openpyxl]"
    except Exception as e:
        return f"[无法解析 {name}：{e}]"
