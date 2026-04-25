from pathlib import Path

from PyPDF2 import PdfReader


def parse_file(file_path: Path) -> list[dict]:
    """Parse a file and return a list of {text, page} dicts."""
    suffix = file_path.suffix.lower()

    if suffix == ".pdf":
        return _parse_pdf(file_path)
    elif suffix in (".txt", ".md"):
        return _parse_text(file_path)
    else:
        raise ValueError(f"Unsupported file type: {suffix}")


def _parse_pdf(file_path: Path) -> list[dict]:
    reader = PdfReader(str(file_path))
    pages = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if text.strip():
            pages.append({"text": text, "page": i + 1})
    return pages


def _parse_text(file_path: Path) -> list[dict]:
    text = file_path.read_text(encoding="utf-8", errors="replace")
    return [{"text": text, "page": None}]
