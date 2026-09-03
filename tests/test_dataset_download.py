from __future__ import annotations

import hashlib
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

from business_ops.datasets.download import (
    ENTERPRISE_BENCH,
    DatasetImportError,
    import_dataset,
)


def make_archive(path: Path, member: str = "crm_json_data/accounts.json") -> str:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(member, "[]")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_imports_an_authenticated_approved_archive(tmp_path: Path) -> None:
    archive = tmp_path / "data.zip"
    digest = make_archive(archive)
    spec = replace(ENTERPRISE_BENCH, sha256=digest)

    destination = import_dataset(tmp_path / "data", spec=spec, archive_path=archive)

    assert (destination / "crm_json_data" / "accounts.json").read_text() == "[]"
    assert (destination / ".source.json").is_file()
    assert import_dataset(destination, spec=spec, archive_path=archive) == destination


def test_rejects_checksum_mismatch(tmp_path: Path) -> None:
    archive = tmp_path / "data.zip"
    make_archive(archive)

    with pytest.raises(DatasetImportError, match="checksum mismatch"):
        import_dataset(tmp_path / "data", archive_path=archive)


def test_rejects_a_modified_extracted_file(tmp_path: Path) -> None:
    archive = tmp_path / "data.zip"
    digest = make_archive(archive)
    spec = replace(ENTERPRISE_BENCH, sha256=digest)
    destination = import_dataset(tmp_path / "data", spec=spec, archive_path=archive)
    (destination / "crm_json_data" / "accounts.json").write_text("tampered")

    with pytest.raises(DatasetImportError, match="integrity check failed"):
        import_dataset(destination, spec=spec, archive_path=archive)


@pytest.mark.parametrize(
    "member",
    ["../escape.json", "/absolute.json", "unknown/data.json", "crm_json_data/run.sh"],
)
def test_rejects_unsafe_or_unexpected_members(tmp_path: Path, member: str) -> None:
    archive = tmp_path / "data.zip"
    digest = make_archive(archive, member)
    spec = replace(ENTERPRISE_BENCH, sha256=digest)

    with pytest.raises(DatasetImportError):
        import_dataset(tmp_path / "data", spec=spec, archive_path=archive)
