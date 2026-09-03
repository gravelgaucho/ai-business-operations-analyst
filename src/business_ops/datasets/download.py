from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tempfile
import urllib.request
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath


class DatasetImportError(RuntimeError):
    """Raised when a dataset fails source or archive safety checks."""


@dataclass(frozen=True)
class DatasetSpec:
    name: str
    source_repository: str
    source_commit: str
    archive_url: str
    sha256: str
    license: str
    synthetic: bool
    max_archive_bytes: int
    max_extracted_bytes: int
    allowed_roots: frozenset[str]
    allowed_root_files: frozenset[str]
    allowed_suffixes: frozenset[str]


ENTERPRISE_BENCH = DatasetSpec(
    name="DevRev Enterprise-Bench / Maple Payments",
    source_repository="https://github.com/devrev/enterprise-bench",
    source_commit="c921345cb64f8045d70f79a3f99717008d68f366",
    archive_url=(
        "https://raw.githubusercontent.com/devrev/enterprise-bench/"
        "c921345cb64f8045d70f79a3f99717008d68f366/artifacts/data.zip"
    ),
    sha256="24d6d134067ffc763c953fab8ec28022c98bb4da11aa0e4456798d7f9bb656bc",
    license="Apache-2.0",
    synthetic=True,
    max_archive_bytes=5_000_000,
    max_extracted_bytes=64_000_000,
    allowed_roots=frozenset(
        {
            "crm_json_data",
            "internal_docs",
            "maple_kb",
            "pm_json_data",
            "transcripts",
        }
    ),
    allowed_root_files=frozenset({"CANARY.md"}),
    allowed_suffixes=frozenset({".json", ".md", ".txt"}),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(spec: DatasetSpec, target: Path) -> None:
    request = urllib.request.Request(
        spec.archive_url,
        headers={"User-Agent": "ai-business-operations-analyst-dataset-importer"},
    )
    downloaded = 0
    try:
        with urllib.request.urlopen(request, timeout=60) as response, target.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                downloaded += len(chunk)
                if downloaded > spec.max_archive_bytes:
                    raise DatasetImportError("Dataset archive exceeds the configured size limit.")
                output.write(chunk)
    except DatasetImportError:
        raise
    except OSError as exc:
        raise DatasetImportError(f"Could not download the verified dataset: {exc}") from exc


def _validated_members(spec: DatasetSpec, archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    members: list[zipfile.ZipInfo] = []
    extracted_bytes = 0
    for member in archive.infolist():
        path = PurePosixPath(member.filename)
        mode = member.external_attr >> 16
        if member.is_dir():
            continue
        if path.is_absolute() or ".." in path.parts:
            raise DatasetImportError(f"Unsafe archive path: {member.filename}")
        is_approved_root_file = len(path.parts) == 1 and member.filename in spec.allowed_root_files
        if not is_approved_root_file and (
            len(path.parts) < 2 or path.parts[0] not in spec.allowed_roots
        ):
            raise DatasetImportError(f"Unexpected archive directory: {path.parts[0]}")
        if path.suffix.lower() not in spec.allowed_suffixes:
            raise DatasetImportError(f"Unexpected archive file type: {member.filename}")
        if stat.S_ISLNK(mode):
            raise DatasetImportError(f"Symbolic links are not allowed: {member.filename}")
        extracted_bytes += member.file_size
        if extracted_bytes > spec.max_extracted_bytes:
            raise DatasetImportError("Extracted dataset exceeds the configured size limit.")
        members.append(member)
    if not members:
        raise DatasetImportError("Dataset archive contains no approved files.")
    return members


def _extract(spec: DatasetSpec, archive_path: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="dataset-import-", dir=destination.parent) as temp_dir:
        temporary_destination = Path(temp_dir) / "verified"
        temporary_destination.mkdir()
        try:
            with zipfile.ZipFile(archive_path) as archive:
                for member in _validated_members(spec, archive):
                    target = temporary_destination.joinpath(*PurePosixPath(member.filename).parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(member) as source, target.open("xb") as output:
                        shutil.copyfileobj(source, output)
        except (OSError, zipfile.BadZipFile) as exc:
            raise DatasetImportError(f"Could not safely extract dataset: {exc}") from exc

        marker = asdict(spec)
        marker["allowed_roots"] = sorted(spec.allowed_roots)
        marker["allowed_root_files"] = sorted(spec.allowed_root_files)
        marker["allowed_suffixes"] = sorted(spec.allowed_suffixes)
        marker["files"] = {
            path.relative_to(temporary_destination).as_posix(): _sha256(path)
            for path in sorted(temporary_destination.rglob("*"))
            if path.is_file()
        }
        (temporary_destination / ".source.json").write_text(
            json.dumps(marker, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_destination.rename(destination)


def verify_dataset(destination: Path, *, spec: DatasetSpec = ENTERPRISE_BENCH) -> Path:
    """Verify the source marker, file inventory, and every extracted file digest."""

    destination = destination.resolve()
    marker_path = destination / ".source.json"
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DatasetImportError(
            f"Dataset source marker is missing or invalid: {destination}"
        ) from exc
    expected_metadata = {
        "source_commit": spec.source_commit,
        "sha256": spec.sha256,
        "license": spec.license,
        "synthetic": spec.synthetic,
    }
    if any(marker.get(key) != value for key, value in expected_metadata.items()):
        raise DatasetImportError(
            f"Dataset source marker does not match the approved release: {destination}"
        )
    expected_files = marker.get("files")
    if not isinstance(expected_files, dict) or not expected_files:
        raise DatasetImportError(f"Dataset file manifest is missing or invalid: {destination}")
    actual_files = {
        path.relative_to(destination).as_posix()
        for path in destination.rglob("*")
        if path.is_file() and path != marker_path
    }
    if actual_files != expected_files.keys():
        raise DatasetImportError(f"Dataset file inventory has changed: {destination}")
    for relative_path, expected_digest in expected_files.items():
        path = destination / relative_path
        if path.is_symlink() or _sha256(path) != expected_digest:
            raise DatasetImportError(f"Dataset file integrity check failed: {relative_path}")
    return destination


def import_dataset(
    destination: Path,
    *,
    spec: DatasetSpec = ENTERPRISE_BENCH,
    archive_path: Path | None = None,
) -> Path:
    """Download, authenticate, validate, and atomically extract a dataset."""

    destination = destination.resolve()
    if destination.exists():
        return verify_dataset(destination, spec=spec)

    if archive_path is not None:
        archive = archive_path.resolve()
        if not archive.is_file():
            raise DatasetImportError(f"Dataset archive does not exist: {archive}")
        if archive.stat().st_size > spec.max_archive_bytes:
            raise DatasetImportError("Dataset archive exceeds the configured size limit.")
        owned_archive = False
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix="dataset-download-", suffix=".zip", dir=destination.parent
        )
        archive = Path(temporary_name)
        owned_archive = True
        os.close(descriptor)

    try:
        if owned_archive:
            _download(spec, archive)
        actual_digest = _sha256(archive)
        if actual_digest != spec.sha256:
            raise DatasetImportError(
                f"Dataset checksum mismatch: expected {spec.sha256}, got {actual_digest}."
            )
        _extract(spec, archive, destination)
    finally:
        if owned_archive:
            archive.unlink(missing_ok=True)
    return destination
