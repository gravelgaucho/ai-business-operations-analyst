from __future__ import annotations

import json
from pathlib import Path

import pytest

from business_ops.datasets.documents import (
    DocumentError,
    DocumentSearchQuery,
    load_published_internal_documents,
    search_internal_documents,
)
from business_ops.provenance import EvidenceRecord, build_evidence_record
from business_ops.reports import document_search_report


def write_corpus(root: Path, entries: list[dict[str, object]]) -> None:
    directory = root / "internal_docs"
    directory.mkdir()
    (directory / "msa_and_compliance.json").write_text(json.dumps(entries), encoding="utf-8")


def entry(document_id: str, status: str, content_file: str, title: str) -> dict[str, object]:
    return {
        "document_id": document_id,
        "status": status,
        "created_at": "2024-01-01T00:00:00Z",
        "modified_at": "2026-01-01T00:00:00Z",
        "author_id": "USER-001",
        "content_format": "markdown",
        "audience": "internal",
        "title": title,
        "content_file": content_file,
    }


def test_search_returns_published_hashed_line_level_citations(tmp_path: Path) -> None:
    write_corpus(
        tmp_path,
        [
            entry("MSA-005", "published", "standard.md", "Standard MSA"),
            entry("MSA-002", "draft", "draft.md", "Draft MSA"),
        ],
    )
    (tmp_path / "internal_docs" / "standard.md").write_text(
        "# Standard MSA\n\n## P1 Response Targets\nP1 initial response is 1 hour.\n"
        "Resolution target is 24 hours, 24/7.\n"
        "<!-- enterprise-bench-canary secret marker -->\n",
        encoding="utf-8",
    )
    (tmp_path / "internal_docs" / "draft.md").write_text(
        "# Draft\nP1 response is 30 minutes.\n", encoding="utf-8"
    )

    results = search_internal_documents(
        tmp_path, DocumentSearchQuery(query="published Standard MSA P1 response resolution")
    )

    assert results[0].document_id == "MSA-005"
    assert results[0].section == "P1 Response Targets"
    assert results[0].line_start == 3
    assert results[0].line_end == 6
    assert "1 hour" in results[0].excerpt
    assert "canary" not in results[0].excerpt
    assert all(item.document_id != "MSA-002" for item in results)


def test_manifest_rejects_path_traversal_and_duplicate_documents(tmp_path: Path) -> None:
    write_corpus(
        tmp_path,
        [entry("MSA-001", "published", "../outside.md", "Unsafe")],
    )

    with pytest.raises(DocumentError, match="manifest is invalid"):
        load_published_internal_documents(tmp_path)

    (tmp_path / "internal_docs" / "msa_and_compliance.json").write_text(
        json.dumps(
            [
                entry("MSA-001", "published", "one.md", "One"),
                entry("MSA-001", "published", "two.md", "Two"),
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "internal_docs" / "one.md").write_text("# One", encoding="utf-8")
    (tmp_path / "internal_docs" / "two.md").write_text("# Two", encoding="utf-8")

    with pytest.raises(DocumentError, match="duplicate"):
        load_published_internal_documents(tmp_path)


def test_search_query_is_bounded_and_forbids_extra_fields() -> None:
    with pytest.raises(ValueError):
        DocumentSearchQuery(query="x")
    with pytest.raises(ValueError):
        DocumentSearchQuery(query="valid terms", top_k=9)
    with pytest.raises(ValueError):
        DocumentSearchQuery.model_validate(
            {"query": "valid terms", "top_k": 3, "sql": "DROP TABLE documents"}
        )


def test_document_report_produces_authenticated_file_evidence(tmp_path: Path) -> None:
    write_corpus(
        tmp_path,
        [entry("MSA-005", "published", "standard.md", "Standard MSA")],
    )
    (tmp_path / "internal_docs" / "standard.md").write_text(
        "# Standard MSA\n## P1 Response\nP1 initial response is 1 hour.\n",
        encoding="utf-8",
    )
    query = DocumentSearchQuery(query="Standard MSA P1 response", top_k=3)
    result = document_search_report(tmp_path, query).model_dump(mode="json")

    evidence = build_evidence_record(
        observation_id="observation_1",
        tool_name="search_internal_documents",
        arguments=query.model_dump(mode="json"),
        result=result,
        source=tmp_path,
    )

    EvidenceRecord.model_validate(evidence.model_dump(mode="python"))
    assert evidence.source.access_mode == "authenticated_files"
    assert evidence.source.locators[0].locator == "internal_docs/msa_and_compliance.json"
    assert evidence.reported_record_ids == ("MSA-005",)
