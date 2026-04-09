from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import settings


def get_text_splitter() -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )


def split_pages(pages: list[dict]) -> list[dict]:
    """Split parsed pages into chunks, preserving page metadata."""
    splitter = get_text_splitter()
    chunks = []
    for page_data in pages:
        texts = splitter.split_text(page_data["text"])
        for text in texts:
            chunks.append({"text": text, "page": page_data["page"]})
    return chunks
