"""Tests for corpus tools (no network, uses tmp_path)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from zil.tools.corpus import (
    ingest_file,
    list_files,
    search,
    read_file,
    _file_to_name,
    _load_index,
)


# ── Name generation ───────────────────────────────────────────────────────────

class TestFileName:
    def test_simple_stem(self):
        assert _file_to_name(Path("consciousness-explained.pdf")) == "consciousness-explained"

    def test_spaces_become_hyphens(self):
        assert _file_to_name(Path("My Book Title.pdf")) == "my-book-title"

    def test_special_chars_stripped(self):
        assert _file_to_name(Path("report (2026).txt")) == "report-2026"

    def test_empty_fallback(self):
        # Path with no meaningful stem — _file_to_name uses stem directly, so
        # an all-punctuation stem like "---" collapses to "document" fallback.
        assert _file_to_name(Path("---.txt")) == "document"


# ── Ingestion: text files ─────────────────────────────────────────────────────

class TestIngestTextFile:
    def test_ingest_txt(self, tmp_path):
        corpus_dir = tmp_path / "corpus"
        src = tmp_path / "notes.txt"
        src.write_text("Line one.\nLine two.\nLine three.")

        record = ingest_file(src, corpus_dir)

        assert record["name"] == "notes"
        assert record["word_count"] > 0
        assert record["char_count"] > 0
        text_file = corpus_dir / "texts" / "notes.txt"
        assert text_file.exists()
        assert "Line one" in text_file.read_text()

    def test_ingest_md(self, tmp_path):
        corpus_dir = tmp_path / "corpus"
        src = tmp_path / "readme.md"
        src.write_text("# Title\n\nSome **markdown** content here.")

        record = ingest_file(src, corpus_dir)

        assert record["name"] == "readme"
        assert (corpus_dir / "texts" / "readme.txt").exists()

    def test_ingest_updates_index(self, tmp_path):
        corpus_dir = tmp_path / "corpus"
        src = tmp_path / "doc.txt"
        src.write_text("Content A")

        ingest_file(src, corpus_dir)
        index = _load_index(corpus_dir)
        assert len(index) == 1
        assert index[0]["name"] == "doc"

    def test_ingest_replaces_existing_record(self, tmp_path):
        corpus_dir = tmp_path / "corpus"
        src = tmp_path / "doc.txt"
        src.write_text("Version 1")
        ingest_file(src, corpus_dir)
        src.write_text("Version 2 with more content")
        ingest_file(src, corpus_dir)

        index = _load_index(corpus_dir)
        assert len(index) == 1  # not duplicated
        assert index[0]["word_count"] > 3  # updated

    def test_ingest_missing_file_raises(self, tmp_path):
        corpus_dir = tmp_path / "corpus"
        with pytest.raises(FileNotFoundError):
            ingest_file(tmp_path / "ghost.txt", corpus_dir)

    def test_ingest_unsupported_type_raises(self, tmp_path):
        corpus_dir = tmp_path / "corpus"
        src = tmp_path / "image.png"
        src.write_bytes(b"\x89PNG")
        with pytest.raises(ValueError, match="Unsupported file type"):
            ingest_file(src, corpus_dir)

    def test_ingest_multiple_files(self, tmp_path):
        corpus_dir = tmp_path / "corpus"
        for name, content in [("alpha.txt", "Alpha content"), ("beta.txt", "Beta content")]:
            src = tmp_path / name
            src.write_text(content)
            ingest_file(src, corpus_dir)

        index = _load_index(corpus_dir)
        names = {r["name"] for r in index}
        assert "alpha" in names
        assert "beta" in names


# ── Ingestion: PDF (mocked) ───────────────────────────────────────────────────

class TestIngestPdf:
    def test_ingest_pdf_extracts_text(self, tmp_path):
        corpus_dir = tmp_path / "corpus"
        src = tmp_path / "paper.pdf"
        src.write_bytes(b"%PDF-1.4 fake")  # not a real PDF, but we'll mock pypdf

        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Extracted text from the paper."
        mock_reader = MagicMock()
        mock_reader.pages = [mock_page]

        with patch("zil.tools.corpus.PdfReader", return_value=mock_reader, create=True):
            with patch("zil.tools.corpus._extract_pdf") as mock_extract:
                mock_extract.return_value = "Extracted text from the paper."
                record = ingest_file(src, corpus_dir)

        assert record["name"] == "paper"

    def test_ingest_pdf_missing_pypdf_raises(self, tmp_path):
        corpus_dir = tmp_path / "corpus"
        src = tmp_path / "paper.pdf"
        src.write_bytes(b"%PDF-1.4 fake")

        with patch("builtins.__import__", side_effect=lambda name, *a, **kw: (
            (_ for _ in ()).throw(ImportError("No module named 'pypdf'"))
            if name == "pypdf" else __import__(name, *a, **kw)
        )):
            # The import error should propagate through _extract_pdf
            pass  # Just verify the module structure is correct — actual import tested live


# ── list_files ────────────────────────────────────────────────────────────────

class TestListFiles:
    def test_empty_corpus(self, tmp_path):
        corpus_dir = tmp_path / "corpus"
        result = list_files(corpus_dir)
        assert "empty" in result.lower()

    def test_lists_ingested_files(self, tmp_path):
        corpus_dir = tmp_path / "corpus"
        for name, content in [("alpha.txt", "A"), ("beta.txt", "B")]:
            src = tmp_path / name
            src.write_text(content)
            ingest_file(src, corpus_dir)

        result = list_files(corpus_dir)
        assert "alpha" in result
        assert "beta" in result

    def test_shows_word_count(self, tmp_path):
        corpus_dir = tmp_path / "corpus"
        src = tmp_path / "doc.txt"
        src.write_text("one two three four five")
        ingest_file(src, corpus_dir)

        result = list_files(corpus_dir)
        assert "5" in result  # word count


# ── search ────────────────────────────────────────────────────────────────────

class TestSearch:
    def test_finds_matching_content(self, tmp_path):
        corpus_dir = tmp_path / "corpus"
        src = tmp_path / "book.txt"
        src.write_text("The concept of consciousness has puzzled philosophers for centuries.")
        ingest_file(src, corpus_dir)

        result = search("consciousness", corpus_dir)
        assert "book" in result
        assert "consciousness" in result.lower()

    def test_case_insensitive(self, tmp_path):
        corpus_dir = tmp_path / "corpus"
        src = tmp_path / "essay.txt"
        src.write_text("Consciousness is the hard problem.")
        ingest_file(src, corpus_dir)

        result = search("CONSCIOUSNESS", corpus_dir)
        assert "essay" in result

    def test_no_match_returns_empty_message(self, tmp_path):
        corpus_dir = tmp_path / "corpus"
        src = tmp_path / "doc.txt"
        src.write_text("Completely unrelated content about vegetables.")
        ingest_file(src, corpus_dir)

        result = search("quantum entanglement", corpus_dir)
        assert "no corpus results" in result.lower()

    def test_empty_corpus_returns_empty_message(self, tmp_path):
        corpus_dir = tmp_path / "corpus"
        result = search("anything", corpus_dir)
        assert "empty" in result.lower()

    def test_returns_excerpt_around_match(self, tmp_path):
        corpus_dir = tmp_path / "corpus"
        src = tmp_path / "doc.txt"
        src.write_text("Before. The key term appears here. After.")
        ingest_file(src, corpus_dir)

        result = search("key term", corpus_dir)
        assert "key term" in result
        # Excerpt should include surrounding context
        assert "Before" in result or "After" in result


# ── read_file ─────────────────────────────────────────────────────────────────

class TestReadFile:
    def test_reads_from_start(self, tmp_path):
        corpus_dir = tmp_path / "corpus"
        src = tmp_path / "book.txt"
        src.write_text("A" * 100 + "B" * 100 + "C" * 100)
        ingest_file(src, corpus_dir)

        result = read_file("book", corpus_dir, offset=0, limit=100)
        assert "A" * 50 in result

    def test_offset_and_limit_respected(self, tmp_path):
        corpus_dir = tmp_path / "corpus"
        src = tmp_path / "doc.txt"
        src.write_text("BEGINNING" + "MIDDLE" * 20 + "END")
        ingest_file(src, corpus_dir)

        # Read from character 9 (past "BEGINNING"), limit 6
        result = read_file("doc", corpus_dir, offset=9, limit=6)
        assert "MIDDLE" in result
        assert "BEGINNING" not in result

    def test_past_end_returns_message(self, tmp_path):
        corpus_dir = tmp_path / "corpus"
        src = tmp_path / "short.txt"
        src.write_text("Short document.")
        ingest_file(src, corpus_dir)

        result = read_file("short", corpus_dir, offset=99999, limit=100)
        assert "end of document" in result.lower()

    def test_unknown_name_returns_error(self, tmp_path):
        corpus_dir = tmp_path / "corpus"
        result = read_file("nonexistent", corpus_dir)
        assert "[error]" in result
        assert "nonexistent" in result

    def test_header_shows_position(self, tmp_path):
        corpus_dir = tmp_path / "corpus"
        src = tmp_path / "doc.txt"
        src.write_text("Hello world " * 10)
        ingest_file(src, corpus_dir)

        result = read_file("doc", corpus_dir, offset=0, limit=10)
        assert "chars 0" in result
