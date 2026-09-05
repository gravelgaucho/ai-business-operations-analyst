from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

MANIFEST_PATH = "internal_docs/msa_and_compliance.json"
MAX_DOCUMENT_BYTES = 2_000_000
MAX_CHUNK_CHARACTERS = 2_400
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_TOKEN = re.compile(r"[a-z0-9]+(?:[.-][a-z0-9]+)*", re.IGNORECASE)


class DocumentError(RuntimeError):
    """Raised when the governed document corpus is invalid or unsafe."""


class DocumentModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class InternalDocumentManifestEntry(DocumentModel):
    document_id: str = Field(pattern=r"^[A-Z]+-[0-9]{3}$")
    status: Literal["published", "draft"]
    created_at: datetime
    modified_at: datetime
    author_id: str = Field(pattern=r"^USER-[0-9]{3}$")
    content_format: Literal["markdown"]
    audience: Literal["internal"]
    title: str = Field(min_length=1, max_length=200)
    content_file: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def content_file_is_a_local_markdown_name(self) -> InternalDocumentManifestEntry:
        relative = PurePosixPath(self.content_file)
        if (
            relative.is_absolute()
            or len(relative.parts) != 1
            or relative.suffix.lower() != ".md"
        ):
            raise ValueError("document content_file must be one local Markdown filename")
        return self


class DocumentSearchQuery(DocumentModel):
    query: str = Field(min_length=3, max_length=500)
    top_k: int = Field(default=5, ge=1, le=8)


class DocumentCitation(DocumentModel):
    document_id: str
    title: str
    status: Literal["published"]
    modified_at: datetime
    locator: str
    section: str
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    chunk_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    relevance_score: float = Field(ge=0)
    excerpt: str = Field(min_length=1, max_length=MAX_CHUNK_CHARACTERS)

    @model_validator(mode="after")
    def line_range_and_digest_are_valid(self) -> DocumentCitation:
        if self.line_start > self.line_end:
            raise ValueError("document citation line_start must not exceed line_end")
        expected = "sha256:" + hashlib.sha256(self.excerpt.encode("utf-8")).hexdigest()
        if self.chunk_sha256 != expected:
            raise ValueError("document citation digest does not match its excerpt")
        return self


class _DocumentChunk(DocumentModel):
    document: InternalDocumentManifestEntry
    locator: str
    section: str
    line_start: int
    line_end: int
    text: str


def _strip_html_comments_preserving_lines(text: str) -> str:
    return _HTML_COMMENT.sub(lambda match: "\n" * match.group(0).count("\n"), text)


def _safe_document_path(root: Path, entry: InternalDocumentManifestEntry) -> Path:
    directory = (root / "internal_docs").resolve()
    candidate = (directory / entry.content_file).resolve()
    if candidate.parent != directory or candidate.is_symlink():
        raise DocumentError(f"Unsafe document path in manifest: {entry.content_file}")
    if not candidate.is_file():
        raise DocumentError(f"Manifest document is missing: {entry.content_file}")
    if candidate.stat().st_size > MAX_DOCUMENT_BYTES:
        raise DocumentError(f"Manifest document exceeds the size limit: {entry.content_file}")
    return candidate


def load_published_internal_documents(root: Path) -> tuple[InternalDocumentManifestEntry, ...]:
    """Load only published, manifest-listed internal Markdown documents."""

    manifest = (root.resolve() / MANIFEST_PATH).resolve()
    expected_parent = (root.resolve() / "internal_docs").resolve()
    if manifest.parent != expected_parent or not manifest.is_file() or manifest.is_symlink():
        raise DocumentError("The governed internal-document manifest is missing or unsafe.")
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        entries = TypeAdapter(list[InternalDocumentManifestEntry]).validate_python(payload)
    except (OSError, ValueError) as exc:
        raise DocumentError(f"The internal-document manifest is invalid: {exc}") from exc
    ids = [entry.document_id for entry in entries]
    files = [entry.content_file for entry in entries]
    if len(ids) != len(set(ids)) or len(files) != len(set(files)):
        raise DocumentError("The internal-document manifest contains duplicate IDs or files.")
    published = tuple(entry for entry in entries if entry.status == "published")
    if not published:
        raise DocumentError("The internal-document manifest has no published documents.")
    for entry in published:
        _safe_document_path(root.resolve(), entry)
    return published


def _bounded_sections(lines: list[str]) -> list[tuple[str, int, int, str]]:
    headings = [
        (index, match.group(2).strip())
        for index, line in enumerate(lines)
        if (match := _HEADING.match(line))
    ]
    if not headings:
        headings = [(0, "Document")]
    sections: list[tuple[str, int, int, str]] = []
    for heading_index, (start, title) in enumerate(headings):
        end = headings[heading_index + 1][0] if heading_index + 1 < len(headings) else len(lines)
        cursor = start
        while cursor < end:
            segment_end = cursor
            characters = 0
            while segment_end < end:
                added = len(lines[segment_end]) + 1
                if segment_end > cursor and characters + added > MAX_CHUNK_CHARACTERS:
                    break
                characters += added
                segment_end += 1
            excerpt = "\n".join(lines[cursor:segment_end]).strip()
            if excerpt:
                section = title if cursor == start else f"{title} (continued)"
                sections.append((section, cursor + 1, segment_end, excerpt))
            cursor = max(segment_end, cursor + 1)
    return sections


def _load_chunks(root: Path) -> list[_DocumentChunk]:
    chunks: list[_DocumentChunk] = []
    for entry in load_published_internal_documents(root):
        path = _safe_document_path(root.resolve(), entry)
        try:
            content = _strip_html_comments_preserving_lines(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError) as exc:
            raise DocumentError(
                f"Could not read governed document {entry.content_file}: {exc}"
            ) from exc
        locator = f"internal_docs/{entry.content_file}"
        for section, line_start, line_end, excerpt in _bounded_sections(content.splitlines()):
            chunks.append(
                _DocumentChunk(
                    document=entry,
                    locator=locator,
                    section=section,
                    line_start=line_start,
                    line_end=line_end,
                    text=excerpt,
                )
            )
    if not chunks:
        raise DocumentError("The governed document corpus produced no searchable passages.")
    return chunks


def _tokens(value: str) -> list[str]:
    return [match.group(0).lower() for match in _TOKEN.finditer(value)]


def search_internal_documents(
    root: Path, query: DocumentSearchQuery
) -> list[DocumentCitation]:
    """Rank bounded passages from manifest-approved published internal documents."""

    chunks = _load_chunks(root.resolve())
    query_terms = tuple(dict.fromkeys(_tokens(query.query)))
    if not query_terms:
        return []
    weighted_tokens = [
        _tokens(
            f"{chunk.document.title} {chunk.document.title} {chunk.document.title} "
            f"{chunk.section} {chunk.section} {chunk.text}"
        )
        for chunk in chunks
    ]
    lengths = [len(tokens) for tokens in weighted_tokens]
    average_length = sum(lengths) / len(lengths)
    document_frequency = {
        term: sum(term in set(tokens) for tokens in weighted_tokens) for term in query_terms
    }
    scored: list[tuple[float, _DocumentChunk]] = []
    for chunk, tokens, length in zip(chunks, weighted_tokens, lengths, strict=True):
        counts = Counter(tokens)
        score = 0.0
        for term in query_terms:
            frequency = counts[term]
            if frequency == 0:
                continue
            frequency_weight = frequency * 2.2
            denominator = frequency + 1.2 * (0.25 + 0.75 * length / average_length)
            inverse_frequency = math.log(
                1 + (len(chunks) - document_frequency[term] + 0.5)
                / (document_frequency[term] + 0.5)
            )
            score += inverse_frequency * frequency_weight / denominator
        if score > 0:
            scored.append((score, chunk))
    ranked = sorted(
        scored,
        key=lambda item: (
            -item[0],
            item[1].document.document_id,
            item[1].line_start,
        ),
    )[: query.top_k]
    return [
        DocumentCitation(
            document_id=chunk.document.document_id,
            title=chunk.document.title,
            status="published",
            modified_at=chunk.document.modified_at,
            locator=chunk.locator,
            section=chunk.section,
            line_start=chunk.line_start,
            line_end=chunk.line_end,
            chunk_sha256=(
                "sha256:" + hashlib.sha256(chunk.text.encode("utf-8")).hexdigest()
            ),
            relevance_score=round(score, 6),
            excerpt=chunk.text,
        )
        for score, chunk in ranked
    ]
