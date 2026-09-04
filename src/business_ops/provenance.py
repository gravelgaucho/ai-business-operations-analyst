from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from business_ops.catalog import DEFAULT_CATALOG, CapabilityCatalog


class ProvenanceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ClaimType(StrEnum):
    VERIFIED_FACT = "verified_fact"
    ANALYTICAL_FINDING = "analytical_finding"
    HYPOTHESIS_ASSESSMENT = "hypothesis_assessment"
    BUSINESS_IMPLICATION = "business_implication"
    RECOMMENDATION = "recommendation"


class SourceLocator(ProvenanceModel):
    kind: Literal["file", "table"]
    locator: str = Field(min_length=1)


class EvidenceSource(ProvenanceModel):
    source_id: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    dataset: str
    source_repository: str
    source_commit: str
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    license: str
    synthetic: bool
    access_mode: Literal["authenticated_json", "read_only_sqlite"]
    locators: tuple[SourceLocator, ...] = Field(min_length=1)


class EvidenceMethod(ProvenanceModel):
    tool_name: str = Field(min_length=1)
    implementation: str = Field(min_length=1)
    method_version: str = Field(min_length=1)
    arguments: dict[str, Any]
    calculation: str | None = None
    metric_definition: str | None = None


class EvidenceRecord(ProvenanceModel):
    evidence_id: str = Field(pattern=r"^EV-[0-9a-f]{16}$")
    observation_id: str = Field(pattern=r"^observation_[1-9][0-9]*$")
    source: EvidenceSource
    method: EvidenceMethod
    reported_record_ids: tuple[str, ...] = ()
    result_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    result: Any

    @model_validator(mode="after")
    def content_address_is_valid(self) -> EvidenceRecord:
        expected_digest = result_digest(self.result)
        if self.result_digest != expected_digest:
            raise ValueError("evidence result digest does not match its result")
        expected_id = evidence_id(
            observation_id=self.observation_id,
            source=self.source,
            method=self.method,
            result_digest_value=self.result_digest,
        )
        if self.evidence_id != expected_id:
            raise ValueError("evidence ID does not match the immutable evidence content")
        return self


class EvidenceLedger(ProvenanceModel):
    schema_version: Literal["1.0"] = "1.0"
    records: tuple[EvidenceRecord, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def records_are_unique(self) -> EvidenceLedger:
        evidence_ids = [record.evidence_id for record in self.records]
        observation_ids = [record.observation_id for record in self.records]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("evidence IDs must be unique")
        if len(observation_ids) != len(set(observation_ids)):
            raise ValueError("each observation must have exactly one evidence record")
        return self

    @property
    def evidence_ids(self) -> frozenset[str]:
        return frozenset(record.evidence_id for record in self.records)


class AuditClaim(ProvenanceModel):
    claim_id: str
    claim_type: ClaimType
    statement: str
    evidence_ids: tuple[str, ...] = Field(min_length=1)


class AuditBundle(ProvenanceModel):
    schema_version: Literal["1.0"] = "1.0"
    investigation_id: str = Field(pattern=r"^INV-[0-9a-f]{16}$")
    question: str
    capability_catalog: CapabilityCatalog
    investigation_plan: dict[str, Any]
    controller_corrections: tuple[dict[str, Any], ...] = ()
    source_snapshots: tuple[EvidenceSource, ...] = Field(min_length=1)
    evidence_ledger: EvidenceLedger
    claims: tuple[AuditClaim, ...] = Field(min_length=1)
    execution_trace: tuple[dict[str, Any], ...] = Field(min_length=1)
    conclusion: dict[str, Any]

    @model_validator(mode="after")
    def claims_only_reference_present_evidence(self) -> AuditBundle:
        claim_ids = [claim.claim_id for claim in self.claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("audit claim IDs must be unique")
        cited = {
            evidence_id_value for claim in self.claims for evidence_id_value in claim.evidence_ids
        }
        missing = cited - self.evidence_ledger.evidence_ids
        if missing:
            raise ValueError(f"audit claims cite unknown evidence IDs: {sorted(missing)}")

        planned_capabilities = {
            str(step.get("analysis"))
            for step in self.investigation_plan.get("steps", [])
            if isinstance(step, dict)
        }
        unknown_planned = planned_capabilities - self.capability_catalog.capability_ids
        if unknown_planned:
            raise ValueError(
                f"audit plan references unknown capabilities: {sorted(unknown_planned)}"
            )
        for evidence_record in self.evidence_ledger.records:
            try:
                capability = self.capability_catalog.capability(
                    evidence_record.method.tool_name
                )
                source = self.capability_catalog.source(capability.source_ids[0])
            except KeyError as exc:
                raise ValueError("audit evidence references an unknown catalog entry") from exc
            expected_locators = (
                capability.json_files
                if evidence_record.source.access_mode == "authenticated_json"
                else capability.sqlite_tables
            )
            if (
                evidence_record.method.implementation != capability.implementation
                or evidence_record.method.method_version != capability.method_version
                or evidence_record.source.source_id != source.source_id
                or evidence_record.source.source_commit != source.source_commit
                or evidence_record.source.snapshot_sha256 != source.snapshot_sha256
                or tuple(item.locator for item in evidence_record.source.locators)
                != expected_locators
            ):
                raise ValueError("audit evidence does not match the embedded capability catalog")
        identity_payload = {
            "question": self.question,
            "capability_catalog_digest": self.capability_catalog.catalog_digest,
            "investigation_plan": self.investigation_plan,
            "controller_corrections": self.controller_corrections,
            "evidence_ids": [
                record.evidence_id for record in self.evidence_ledger.records
            ],
            "claims": [claim.model_dump(mode="json") for claim in self.claims],
            "execution_trace": self.execution_trace,
            "conclusion": self.conclusion,
        }
        if self.investigation_id != investigation_id(identity_payload):
            raise ValueError("investigation ID does not match the audit bundle content")
        return self


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def result_digest(result: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(result)).hexdigest()


def evidence_id(
    *,
    observation_id: str,
    source: EvidenceSource,
    method: EvidenceMethod,
    result_digest_value: str,
) -> str:
    identity = {
        "observation_id": observation_id,
        "source": source.model_dump(mode="json"),
        "method": method.model_dump(mode="json"),
        "result_digest": result_digest_value,
    }
    return "EV-" + hashlib.sha256(_canonical_json(identity)).hexdigest()[:16]


def _reported_record_ids(value: Any) -> tuple[str, ...]:
    found: set[str] = set()

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                if key.endswith("_id") and isinstance(child, str) and child:
                    found.add(child)
                else:
                    visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    return tuple(sorted(found))


def build_evidence_record(
    *,
    observation_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    result: dict[str, Any],
    source: Path | object,
    catalog: CapabilityCatalog = DEFAULT_CATALOG,
) -> EvidenceRecord:
    """Create one tamper-evident evidence record from a deterministic report."""

    access_mode: Literal["authenticated_json", "read_only_sqlite"] = (
        "authenticated_json" if isinstance(source, Path) else "read_only_sqlite"
    )
    source_kind: Literal["file", "table"] = (
        "file" if access_mode == "authenticated_json" else "table"
    )
    capability = catalog.capability(tool_name)
    source_definition = catalog.source(capability.source_ids[0])
    locator_values = (
        capability.json_files
        if access_mode == "authenticated_json"
        else capability.sqlite_tables
    )
    source_metadata = result.get("source", {})
    evidence_source = EvidenceSource(
        source_id=source_definition.source_id,
        dataset=str(source_metadata.get("dataset", source_definition.display_name)),
        source_repository=source_definition.source_repository,
        source_commit=str(source_metadata.get("source_commit", source_definition.source_commit)),
        snapshot_sha256=source_definition.snapshot_sha256,
        license=str(source_metadata.get("license", source_definition.license)),
        synthetic=bool(source_metadata.get("synthetic", source_definition.synthetic)),
        access_mode=access_mode,
        locators=tuple(SourceLocator(kind=source_kind, locator=value) for value in locator_values),
    )
    method = EvidenceMethod(
        tool_name=tool_name,
        implementation=capability.implementation,
        method_version=capability.method_version,
        arguments=arguments,
        calculation=result.get("calculation"),
        metric_definition=result.get("metric_definition"),
    )
    digest = result_digest(result)
    return EvidenceRecord(
        evidence_id=evidence_id(
            observation_id=observation_id,
            source=evidence_source,
            method=method,
            result_digest_value=digest,
        ),
        observation_id=observation_id,
        source=evidence_source,
        method=method,
        reported_record_ids=_reported_record_ids(result),
        result_digest=digest,
        result=result,
    )


def investigation_id(payload: dict[str, Any]) -> str:
    return "INV-" + hashlib.sha256(_canonical_json(payload)).hexdigest()[:16]
