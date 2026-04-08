"""Corpus tool implementations for ZIL⌀.

The corpus is an indexed collection of local documents (PDFs, text files, books)
that ZIL can search and read. Documents live in artifacts/library/. Extracted
text and the index live in vessel/state/zil/corpus/.

Index format (corpus/index.json):
  [
    {
      "name": "consciousness-explained",
      "source_path": "artifacts/library/consciousness-explained.pdf",
      "text_file": "consciousness-explained.txt",
      "ingested_at": "2026-04-06T12:00:00Z",
      "word_count": 125000,
      "char_count": 700000
    },
    ...
  ]

Text files live at corpus/texts/<name>.txt.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path


# ── Ingestion ─────────────────────────────────────────────────────────────────

def ingest_file(source_path: Path, corpus_dir: Path) -> dict:
    """Extract text from a file and add it to the corpus index.

    Supports PDF (.pdf) and plain text (.txt, .md, .rst, .text).
    Returns the index record for the newly ingested file.
    Raises ValueError if the file type is unsupported.
    Raises FileNotFoundError if source_path does not exist.
    """
    if not source_path.exists():
        raise FileNotFoundError(f"Source file not found: {source_path}")

    suffix = source_path.suffix.lower()
    if suffix == ".pdf":
        text = _extract_pdf(source_path)
    elif suffix in (".txt", ".md", ".rst", ".text", ".markdown"):
        text = source_path.read_text(encoding="utf-8", errors="replace")
    else:
        raise ValueError(
            f"Unsupported file type: {suffix!r}. "
            "Supported: .pdf, .txt, .md, .rst, .text, .markdown"
        )

    # Normalise whitespace but preserve paragraph structure
    text = re.sub(r"\r\n", "\n", text)
    text = re.sub(r"\r", "\n", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    text = text.strip()

    name = _file_to_name(source_path)
    texts_dir = corpus_dir / "texts"
    texts_dir.mkdir(parents=True, exist_ok=True)
    text_file = texts_dir / f"{name}.txt"
    text_file.write_text(text, encoding="utf-8")

    record = {
        "name": name,
        "source_path": str(source_path),
        "text_file": f"{name}.txt",
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "word_count": len(text.split()),
        "char_count": len(text),
    }

    # Update index
    index = _load_index(corpus_dir)
    # Replace existing record with same name if present
    index = [r for r in index if r["name"] != name]
    index.append(record)
    _save_index(corpus_dir, index)

    return record


def _extract_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ImportError(
            "pypdf is required for PDF ingestion. Run: pip install pypdf"
        )

    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        if page_text.strip():
            pages.append(page_text)
    return "\n\n".join(pages)


def _file_to_name(path: Path) -> str:
    """Convert a file path to a safe corpus name (lowercase, hyphenated)."""
    stem = path.stem
    # Replace non-alphanumeric with hyphens, collapse runs, strip edges
    name = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
    return name or "document"


# ── Index management ──────────────────────────────────────────────────────────

def _load_index(corpus_dir: Path) -> list[dict]:
    index_path = corpus_dir / "index.json"
    if not index_path.exists():
        return []
    try:
        return json.loads(index_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save_index(corpus_dir: Path, index: list[dict]) -> None:
    corpus_dir.mkdir(parents=True, exist_ok=True)
    index_path = corpus_dir / "index.json"
    index_path.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")


# ── Query operations ──────────────────────────────────────────────────────────

def list_files(corpus_dir: Path) -> str:
    """Return a formatted list of indexed corpus documents."""
    index = _load_index(corpus_dir)
    if not index:
        return "(corpus is empty — use ingest_corpus_file to add documents)"
    lines = []
    for r in sorted(index, key=lambda x: x["name"]):
        wc = r.get("word_count", 0)
        ingested = r.get("ingested_at", "")[:10]
        lines.append(f"{r['name']}  ({wc:,} words, ingested {ingested})")
    return "\n".join(lines)


def search(query: str, corpus_dir: Path, max_results: int = 8) -> str:
    """Search across all corpus texts for query. Returns excerpts."""
    index = _load_index(corpus_dir)
    if not index:
        return "(corpus is empty)"

    q = query.lower()
    texts_dir = corpus_dir / "texts"
    matches: list[tuple[str, str]] = []  # (name, excerpt)

    for record in index:
        text_path = texts_dir / record["text_file"]
        if not text_path.exists():
            continue
        try:
            text = text_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        text_lower = text.lower()
        pos = 0
        found_in_doc = 0
        while found_in_doc < 3:  # max 3 excerpts per document
            idx = text_lower.find(q, pos)
            if idx == -1:
                break
            start = max(0, idx - 120)
            end = min(len(text), idx + len(query) + 120)
            excerpt = text[start:end].replace("\n", " ").strip()
            if start > 0:
                excerpt = "..." + excerpt
            if end < len(text):
                excerpt = excerpt + "..."
            matches.append((record["name"], excerpt))
            pos = idx + len(query)
            found_in_doc += 1

        if len(matches) >= max_results:
            break

    if not matches:
        return f"(no corpus results for {query!r})"

    lines = [f"Corpus search: {query!r}\n"]
    for name, excerpt in matches[:max_results]:
        lines.append(f"[{name}]\n{excerpt}\n")
    return "\n".join(lines)


def read_file(name: str, corpus_dir: Path, offset: int = 0, limit: int = 4000) -> str:
    """Read a portion of a corpus document by name.

    offset and limit are character positions. Default page is 4000 chars (~600 words).
    """
    index = _load_index(corpus_dir)
    record = next((r for r in index if r["name"] == name), None)
    if record is None:
        available = ", ".join(r["name"] for r in index) or "(none)"
        return f"[error] Corpus document {name!r} not found. Available: {available}"

    texts_dir = corpus_dir / "texts"
    text_path = texts_dir / record["text_file"]
    if not text_path.exists():
        return f"[error] Text file missing for {name!r}. Re-ingest the document."

    text = text_path.read_text(encoding="utf-8", errors="replace")
    total = len(text)

    chunk = text[offset: offset + limit]
    if not chunk:
        return f"(end of document — {total:,} total characters)"

    header = f"[{name}] chars {offset}–{offset + len(chunk)} of {total:,}\n\n"
    return header + chunk
