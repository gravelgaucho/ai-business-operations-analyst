from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from business_ops.catalog import DEFAULT_CATALOG, DataClassification, catalog_digest
from business_ops.datasets.download import ENTERPRISE_BENCH, verify_dataset


class TestbedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CoverageStatus(StrEnum):
    ACTIVE = "active_capability"
    AVAILABLE = "available_not_onboarded"
    PLANNED = "planned_extension"


class ScenarioReadiness(StrEnum):
    QUALIFIED = "qualified"
    PARTIAL = "partial"
    BLOCKED = "blocked_on_planned_data"


class CanonicalEntityDefinition(TestbedModel):
    entity_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    display_name: str
    description: str
    identifiers: tuple[str, ...] = Field(min_length=1)
    status: CoverageStatus


class SourceAssetDefinition(TestbedModel):
    asset_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    display_name: str
    description: str
    business_system: str
    modality: Literal["structured", "unstructured"]
    primary_locator: str
    entity_ids: tuple[str, ...] = Field(min_length=1)
    status: CoverageStatus
    record_label: str
    eligibility_field: str | None = None
    eligibility_value: str | None = None

    @model_validator(mode="after")
    def eligibility_filter_is_complete(self) -> SourceAssetDefinition:
        if (self.eligibility_field is None) != (self.eligibility_value is None):
            raise ValueError("eligibility field and value must be supplied together")
        return self


class RelationshipDefinition(TestbedModel):
    relationship_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    left_entity_id: str
    right_entity_id: str
    join_fields: tuple[str, ...] = Field(min_length=1)
    status: CoverageStatus
    interpretation_boundary: str


class MetricRequirement(TestbedModel):
    metric_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    display_name: str
    description: str
    entity_ids: tuple[str, ...] = Field(min_length=1)
    source_asset_ids: tuple[str, ...] = Field(min_length=1)
    status: CoverageStatus
    semantic_boundary: str


class FlagshipScenarioDefinition(TestbedModel):
    scenario_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    question: str
    purpose: str
    required_metric_ids: tuple[str, ...] = Field(min_length=1)


class BusinessEvidenceTestbed(TestbedModel):
    schema_version: Literal["1.0"] = "1.0"
    testbed_version: str = Field(pattern=r"^stage-[1-9][0-9]*-v[1-9][0-9]*$")
    testbed_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    source_name: str
    source_commit: str
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_license: str
    source_classification: DataClassification
    entities: tuple[CanonicalEntityDefinition, ...] = Field(min_length=1)
    assets: tuple[SourceAssetDefinition, ...] = Field(min_length=1)
    relationships: tuple[RelationshipDefinition, ...] = Field(min_length=1)
    metrics: tuple[MetricRequirement, ...] = Field(min_length=1)
    scenarios: tuple[FlagshipScenarioDefinition, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def references_and_digest_are_valid(self) -> BusinessEvidenceTestbed:
        groups = {
            "entity": [item.entity_id for item in self.entities],
            "asset": [item.asset_id for item in self.assets],
            "relationship": [item.relationship_id for item in self.relationships],
            "metric": [item.metric_id for item in self.metrics],
            "scenario": [item.scenario_id for item in self.scenarios],
        }
        for label, identifiers in groups.items():
            if len(identifiers) != len(set(identifiers)):
                raise ValueError(f"{label} testbed identifiers must be unique")

        entity_ids = set(groups["entity"])
        asset_ids = set(groups["asset"])
        metric_ids = set(groups["metric"])
        for asset in self.assets:
            if missing := set(asset.entity_ids) - entity_ids:
                raise ValueError(f"asset references unknown entities: {sorted(missing)}")
        for relationship in self.relationships:
            if relationship.left_entity_id not in entity_ids:
                raise ValueError("relationship references an unknown left entity")
            if relationship.right_entity_id not in entity_ids:
                raise ValueError("relationship references an unknown right entity")
        for metric in self.metrics:
            if missing := set(metric.entity_ids) - entity_ids:
                raise ValueError(f"metric references unknown entities: {sorted(missing)}")
            if missing := set(metric.source_asset_ids) - asset_ids:
                raise ValueError(f"metric references unknown assets: {sorted(missing)}")
            asset_statuses = {
                next(asset.status for asset in self.assets if asset.asset_id == asset_id)
                for asset_id in metric.source_asset_ids
            }
            if metric.status == CoverageStatus.ACTIVE and asset_statuses != {
                CoverageStatus.ACTIVE
            }:
                raise ValueError("active metrics may reference only active assets")
            if (
                metric.status == CoverageStatus.AVAILABLE
                and CoverageStatus.PLANNED in asset_statuses
            ):
                raise ValueError("available metrics may not depend on planned assets")
        for scenario in self.scenarios:
            if missing := set(scenario.required_metric_ids) - metric_ids:
                raise ValueError(f"scenario references unknown metrics: {sorted(missing)}")

        expected = catalog_digest(self.model_dump(mode="json", exclude={"testbed_digest"}))
        if self.testbed_digest != expected:
            raise ValueError("testbed digest does not match its definitions")
        return self

    def metric(self, metric_id: str) -> MetricRequirement:
        for metric in self.metrics:
            if metric.metric_id == metric_id:
                return metric
        raise KeyError(f"Unknown testbed metric: {metric_id}")

    def scenario_readiness(self, scenario: FlagshipScenarioDefinition) -> ScenarioReadiness:
        statuses = {self.metric(metric_id).status for metric_id in scenario.required_metric_ids}
        if CoverageStatus.PLANNED in statuses:
            return ScenarioReadiness.BLOCKED
        if CoverageStatus.AVAILABLE in statuses:
            return ScenarioReadiness.PARTIAL
        return ScenarioReadiness.QUALIFIED


class AssetInventory(TestbedModel):
    asset_id: str
    status: CoverageStatus
    primary_locator: str
    present: bool
    record_count: int | None = Field(default=None, ge=0)
    eligible_record_count: int | None = Field(default=None, ge=0)
    content_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class CoverageSummary(TestbedModel):
    total_assets: int = Field(ge=1)
    active_assets: int = Field(ge=0)
    available_assets: int = Field(ge=0)
    planned_assets: int = Field(ge=0)
    present_source_records: int = Field(ge=0)


class ScenarioInventory(TestbedModel):
    scenario_id: str
    question: str
    readiness: ScenarioReadiness
    blocking_metrics: tuple[str, ...] = ()


class IntegrityCheck(TestbedModel):
    check_id: str
    passed: bool
    orphan_count: int = Field(ge=0)


class TestbedInventoryReport(TestbedModel):
    testbed_version: str
    testbed_digest: str
    source_verified: Literal[True] = True
    source_commit: str
    source_sha256: str
    summary: CoverageSummary
    assets: tuple[AssetInventory, ...]
    relationship_checks: tuple[IntegrityCheck, ...]
    scenarios: tuple[ScenarioInventory, ...]


def _canonical_entities() -> tuple[CanonicalEntityDefinition, ...]:
    active = CoverageStatus.ACTIVE
    available = CoverageStatus.AVAILABLE
    planned = CoverageStatus.PLANNED
    return (
        CanonicalEntityDefinition(
            entity_id="account",
            display_name="Account",
            description="Customer organization forming the primary cross-system entity spine.",
            identifiers=("account_id",),
            status=active,
        ),
        CanonicalEntityDefinition(
            entity_id="person",
            display_name="Person",
            description=(
                "Synthetic employee or customer participant referenced by business records."
            ),
            identifiers=("user_id",),
            status=available,
        ),
        CanonicalEntityDefinition(
            entity_id="opportunity",
            display_name="Opportunity",
            description="CRM sales opportunity associated with an account.",
            identifiers=("opportunity_id",),
            status=active,
        ),
        CanonicalEntityDefinition(
            entity_id="support_ticket",
            display_name="Support ticket",
            description="Customer support case associated with an account and product components.",
            identifiers=("ticket_id",),
            status=active,
        ),
        CanonicalEntityDefinition(
            entity_id="product_part",
            display_name="Product part",
            description="Product or component shared by support and product-management records.",
            identifiers=("part_id",),
            status=active,
        ),
        CanonicalEntityDefinition(
            entity_id="product_issue",
            display_name="Product issue",
            description="Product-management issue associated with components and conversations.",
            identifiers=("issue_id",),
            status=available,
        ),
        CanonicalEntityDefinition(
            entity_id="conversation",
            display_name="Conversation",
            description="Conversation container referenced by tickets or product issues.",
            identifiers=("conversation_id",),
            status=available,
        ),
        CanonicalEntityDefinition(
            entity_id="knowledge_article",
            display_name="Knowledge article",
            description="Published product or operating guidance with a governed content file.",
            identifiers=("article_id",),
            status=available,
        ),
        CanonicalEntityDefinition(
            entity_id="internal_document",
            display_name="Internal document",
            description="Manifest-listed internal policy, agreement, or technical document.",
            identifiers=("document_id",),
            status=active,
        ),
        CanonicalEntityDefinition(
            entity_id="transcript",
            display_name="Transcript",
            description="Account interaction transcript linked to CRM entities where supplied.",
            identifiers=("transcript_id",),
            status=available,
        ),
        CanonicalEntityDefinition(
            entity_id="executed_contract",
            display_name="Executed contract",
            description="Account-specific governing agreement and commercial terms.",
            identifiers=("contract_id",),
            status=planned,
        ),
        CanonicalEntityDefinition(
            entity_id="booking",
            display_name="Booking",
            description="Signed order or committed commercial value at the booking date.",
            identifiers=("booking_id",),
            status=planned,
        ),
        CanonicalEntityDefinition(
            entity_id="subscription",
            display_name="Subscription",
            description="Service entitlement connecting a booking to billing and delivery.",
            identifiers=("subscription_id",),
            status=planned,
        ),
        CanonicalEntityDefinition(
            entity_id="invoice",
            display_name="Invoice",
            description="Customer billing record associated with a subscription or order.",
            identifiers=("invoice_id",),
            status=planned,
        ),
        CanonicalEntityDefinition(
            entity_id="revenue_event",
            display_name="Revenue event",
            description="Period-specific recognized revenue under an explicit schedule.",
            identifiers=("revenue_event_id",),
            status=planned,
        ),
        CanonicalEntityDefinition(
            entity_id="payment",
            display_name="Payment",
            description="Cash collection or reversal associated with an invoice.",
            identifiers=("payment_id",),
            status=planned,
        ),
        CanonicalEntityDefinition(
            entity_id="implementation_milestone",
            display_name="Implementation milestone",
            description="Planned and actual delivery events affecting service activation.",
            identifiers=("milestone_id",),
            status=planned,
        ),
        CanonicalEntityDefinition(
            entity_id="usage_event",
            display_name="Usage event",
            description="Aggregated product-adoption observation for an account and product.",
            identifiers=("usage_event_id",),
            status=planned,
        ),
        CanonicalEntityDefinition(
            entity_id="cost_record",
            display_name="Cost record",
            description="Attributed service or operating cost used for margin analysis.",
            identifiers=("cost_record_id",),
            status=planned,
        ),
    )


def _source_assets() -> tuple[SourceAssetDefinition, ...]:
    active = CoverageStatus.ACTIVE
    available = CoverageStatus.AVAILABLE
    planned = CoverageStatus.PLANNED
    return (
        SourceAssetDefinition(
            asset_id="crm_accounts",
            display_name="CRM accounts",
            description="Customer identity, region, tier, ARR, MRR, and contract dates.",
            business_system="crm",
            modality="structured",
            primary_locator="crm_json_data/accounts.json",
            entity_ids=("account",),
            status=active,
            record_label="accounts",
        ),
        SourceAssetDefinition(
            asset_id="crm_opportunities",
            display_name="CRM opportunities",
            description="Sales opportunity stages, ACV, currency, ownership, and close dates.",
            business_system="crm",
            modality="structured",
            primary_locator="crm_json_data/opportunities.json",
            entity_ids=("account", "opportunity", "person"),
            status=active,
            record_label="opportunities",
        ),
        SourceAssetDefinition(
            asset_id="crm_tickets",
            display_name="Support tickets",
            description="Support priority, status, account, component, and conversation links.",
            business_system="support",
            modality="structured",
            primary_locator="crm_json_data/tickets.json",
            entity_ids=("account", "support_ticket", "product_part", "conversation", "person"),
            status=active,
            record_label="tickets",
        ),
        SourceAssetDefinition(
            asset_id="product_parts",
            display_name="Product parts",
            description="Product and component hierarchy used by support and product work.",
            business_system="product_management",
            modality="structured",
            primary_locator="pm_json_data/maple_parts.json",
            entity_ids=("product_part",),
            status=active,
            record_label="product parts",
        ),
        SourceAssetDefinition(
            asset_id="internal_documents",
            display_name="Internal documents",
            description="Manifest-governed agreements, specifications, and risk documentation.",
            business_system="internal_document_repository",
            modality="unstructured",
            primary_locator="internal_docs/msa_and_compliance.json",
            entity_ids=("internal_document", "person"),
            status=active,
            record_label="document manifest entries",
            eligibility_field="status",
            eligibility_value="published",
        ),
        SourceAssetDefinition(
            asset_id="crm_users",
            display_name="CRM users",
            description="Synthetic people, roles, departments, and employment status.",
            business_system="crm",
            modality="structured",
            primary_locator="crm_json_data/users.json",
            entity_ids=("person",),
            status=available,
            record_label="users",
        ),
        SourceAssetDefinition(
            asset_id="product_users",
            display_name="Product-management users",
            description="Synthetic product staff referenced by issues and comments.",
            business_system="product_management",
            modality="structured",
            primary_locator="pm_json_data/users.json",
            entity_ids=("person",),
            status=available,
            record_label="product users",
        ),
        SourceAssetDefinition(
            asset_id="product_issues",
            display_name="Product issues",
            description="Product work, priority, status, components, story points, and dates.",
            business_system="product_management",
            modality="structured",
            primary_locator="pm_json_data/issues.json",
            entity_ids=("product_issue", "product_part", "conversation", "person"),
            status=available,
            record_label="product issues",
        ),
        SourceAssetDefinition(
            asset_id="product_conversations",
            display_name="Product conversations",
            description="Conversation containers linked to product work or other records.",
            business_system="product_management",
            modality="structured",
            primary_locator="pm_json_data/conversations.json",
            entity_ids=("conversation",),
            status=available,
            record_label="conversations",
        ),
        SourceAssetDefinition(
            asset_id="product_comments",
            display_name="Product comments",
            description="Timestamped conversation comments with authors and visibility.",
            business_system="product_management",
            modality="unstructured",
            primary_locator="pm_json_data/comments.json",
            entity_ids=("conversation", "person"),
            status=available,
            record_label="comments",
        ),
        SourceAssetDefinition(
            asset_id="knowledge_articles",
            display_name="Knowledge-base articles",
            description="Published product, policy, pricing, and operating guidance.",
            business_system="knowledge_base",
            modality="unstructured",
            primary_locator="maple_kb/articles.json",
            entity_ids=("knowledge_article", "person"),
            status=available,
            record_label="article manifest entries",
            eligibility_field="status",
            eligibility_value="published",
        ),
        SourceAssetDefinition(
            asset_id="account_transcripts",
            display_name="Account transcripts",
            description="Business reviews, account check-ins, and onboarding conversations.",
            business_system="meeting_repository",
            modality="unstructured",
            primary_locator="transcripts/transcripts.json",
            entity_ids=("transcript", "account", "opportunity", "person"),
            status=available,
            record_label="transcript manifest entries",
        ),
        SourceAssetDefinition(
            asset_id="contract_assignments",
            display_name="Account contract assignments",
            description="Account-specific link to the executed agreement, tier, and amendments.",
            business_system="contract_lifecycle_management",
            modality="structured",
            primary_locator="maple_finance_extension/contract_assignments.json",
            entity_ids=("account", "executed_contract", "opportunity"),
            status=planned,
            record_label="contract assignments",
        ),
        SourceAssetDefinition(
            asset_id="bookings",
            display_name="Bookings and order lines",
            description="Signed commercial value, products, quantities, pricing, and discounts.",
            business_system="order_management",
            modality="structured",
            primary_locator="maple_finance_extension/bookings.json",
            entity_ids=("booking", "account", "opportunity", "executed_contract", "product_part"),
            status=planned,
            record_label="booking lines",
        ),
        SourceAssetDefinition(
            asset_id="subscriptions",
            display_name="Subscriptions",
            description="Service terms, activation, entitlement, and renewal state.",
            business_system="billing",
            modality="structured",
            primary_locator="maple_finance_extension/subscriptions.json",
            entity_ids=("subscription", "booking", "account", "product_part"),
            status=planned,
            record_label="subscriptions",
        ),
        SourceAssetDefinition(
            asset_id="invoices",
            display_name="Invoices",
            description="Billed amounts, dates, due dates, status, and subscription links.",
            business_system="billing",
            modality="structured",
            primary_locator="maple_finance_extension/invoices.json",
            entity_ids=("invoice", "subscription", "account"),
            status=planned,
            record_label="invoices",
        ),
        SourceAssetDefinition(
            asset_id="revenue_schedule",
            display_name="Revenue schedule",
            description="Period-specific recognized revenue with governing schedule references.",
            business_system="erp_finance",
            modality="structured",
            primary_locator="maple_finance_extension/revenue_schedule.json",
            entity_ids=("revenue_event", "invoice", "subscription", "booking", "account"),
            status=planned,
            record_label="revenue events",
        ),
        SourceAssetDefinition(
            asset_id="payments",
            display_name="Payments and collections",
            description="Cash receipts, failures, reversals, and invoice applications.",
            business_system="payments_ledger",
            modality="structured",
            primary_locator="maple_finance_extension/payments.json",
            entity_ids=("payment", "invoice", "account"),
            status=planned,
            record_label="payment events",
        ),
        SourceAssetDefinition(
            asset_id="implementation_milestones",
            display_name="Implementation milestones",
            description="Planned and actual delivery milestones associated with new business.",
            business_system="professional_services",
            modality="structured",
            primary_locator="maple_finance_extension/implementation_milestones.json",
            entity_ids=("implementation_milestone", "booking", "account"),
            status=planned,
            record_label="implementation milestones",
        ),
        SourceAssetDefinition(
            asset_id="product_usage",
            display_name="Product usage",
            description="Monthly account and product adoption observations.",
            business_system="product_analytics",
            modality="structured",
            primary_locator="maple_finance_extension/product_usage.json",
            entity_ids=("usage_event", "account", "product_part"),
            status=planned,
            record_label="usage observations",
        ),
        SourceAssetDefinition(
            asset_id="cost_ledger",
            display_name="Cost ledger",
            description="Attributed service delivery and operating costs for margin analysis.",
            business_system="erp_finance",
            modality="structured",
            primary_locator="maple_finance_extension/cost_ledger.json",
            entity_ids=("cost_record", "account", "product_part"),
            status=planned,
            record_label="cost records",
        ),
    )


def _relationships() -> tuple[RelationshipDefinition, ...]:
    active = CoverageStatus.ACTIVE
    available = CoverageStatus.AVAILABLE
    planned = CoverageStatus.PLANNED
    return (
        RelationshipDefinition(
            relationship_id="opportunity_account",
            left_entity_id="opportunity",
            right_entity_id="account",
            join_fields=("account_id",),
            status=active,
            interpretation_boundary="Current opportunity stage is not stage history.",
        ),
        RelationshipDefinition(
            relationship_id="ticket_account",
            left_entity_id="support_ticket",
            right_entity_id="account",
            join_fields=("account_id",),
            status=active,
            interpretation_boundary="A linked ticket does not establish account-level impact.",
        ),
        RelationshipDefinition(
            relationship_id="ticket_product_part",
            left_entity_id="support_ticket",
            right_entity_id="product_part",
            join_fields=("components[]", "part_id"),
            status=active,
            interpretation_boundary="Component association does not prove product causation.",
        ),
        RelationshipDefinition(
            relationship_id="issue_product_part",
            left_entity_id="product_issue",
            right_entity_id="product_part",
            join_fields=("components[]", "part_id"),
            status=available,
            interpretation_boundary="Product issue linkage must be onboarded and tested.",
        ),
        RelationshipDefinition(
            relationship_id="ticket_conversation",
            left_entity_id="support_ticket",
            right_entity_id="conversation",
            join_fields=("conversation_id",),
            status=available,
            interpretation_boundary="Only tickets with an explicit conversation ID are linked.",
        ),
        RelationshipDefinition(
            relationship_id="issue_conversation",
            left_entity_id="product_issue",
            right_entity_id="conversation",
            join_fields=("conversation_id",),
            status=available,
            interpretation_boundary="Only issues with an explicit conversation ID are linked.",
        ),
        RelationshipDefinition(
            relationship_id="comment_conversation",
            left_entity_id="conversation",
            right_entity_id="person",
            join_fields=("conversation_id", "author_id"),
            status=available,
            interpretation_boundary="Comment authorship does not validate comment content.",
        ),
        RelationshipDefinition(
            relationship_id="transcript_account",
            left_entity_id="transcript",
            right_entity_id="account",
            join_fields=("account_id",),
            status=available,
            interpretation_boundary="Statements are attributed evidence, not verified facts.",
        ),
        RelationshipDefinition(
            relationship_id="transcript_opportunity",
            left_entity_id="transcript",
            right_entity_id="opportunity",
            join_fields=("opportunity_id",),
            status=available,
            interpretation_boundary="Three transcripts provide sparse, nonrepresentative coverage.",
        ),
        RelationshipDefinition(
            relationship_id="contract_account",
            left_entity_id="executed_contract",
            right_entity_id="account",
            join_fields=("account_id", "contract_id"),
            status=planned,
            interpretation_boundary="Template or tier similarity is not an executed agreement.",
        ),
        RelationshipDefinition(
            relationship_id="booking_commercial_chain",
            left_entity_id="booking",
            right_entity_id="executed_contract",
            join_fields=("contract_id",),
            status=planned,
            interpretation_boundary="Bookings require a signed-date and cancellation policy.",
        ),
        RelationshipDefinition(
            relationship_id="subscription_booking",
            left_entity_id="subscription",
            right_entity_id="booking",
            join_fields=("booking_id",),
            status=planned,
            interpretation_boundary="Entitlement dates must remain distinct from booking dates.",
        ),
        RelationshipDefinition(
            relationship_id="invoice_subscription",
            left_entity_id="invoice",
            right_entity_id="subscription",
            join_fields=("subscription_id",),
            status=planned,
            interpretation_boundary="Billing is not equivalent to revenue recognition.",
        ),
        RelationshipDefinition(
            relationship_id="revenue_invoice",
            left_entity_id="revenue_event",
            right_entity_id="invoice",
            join_fields=("invoice_id",),
            status=planned,
            interpretation_boundary="Recognition policy and period must be explicit.",
        ),
        RelationshipDefinition(
            relationship_id="payment_invoice",
            left_entity_id="payment",
            right_entity_id="invoice",
            join_fields=("invoice_id",),
            status=planned,
            interpretation_boundary="Cash collection is not recognized revenue.",
        ),
        RelationshipDefinition(
            relationship_id="implementation_booking",
            left_entity_id="implementation_milestone",
            right_entity_id="booking",
            join_fields=("booking_id",),
            status=planned,
            interpretation_boundary=(
                "Timing association alone does not establish revenue treatment."
            ),
        ),
    )


def _metrics() -> tuple[MetricRequirement, ...]:
    active = CoverageStatus.ACTIVE
    available = CoverageStatus.AVAILABLE
    planned = CoverageStatus.PLANNED
    return (
        MetricRequirement(
            metric_id="account_arr",
            display_name="Account ARR",
            description="Annual recurring revenue stored on the current account record.",
            entity_ids=("account",),
            source_asset_ids=("crm_accounts",),
            status=active,
            semantic_boundary="Current account ARR is not recognized period revenue.",
        ),
        MetricRequirement(
            metric_id="closed_won_opportunity_acv",
            display_name="Closed-won opportunity ACV",
            description="Opportunity ACV grouped by target close date and current final stage.",
            entity_ids=("opportunity", "account"),
            source_asset_ids=("crm_opportunities", "crm_accounts"),
            status=active,
            semantic_boundary="This is a sales-pipeline measure, not bookings or revenue.",
        ),
        MetricRequirement(
            metric_id="support_exposure",
            display_name="Support exposure",
            description="Account ARR and ticket counts associated with open support cases.",
            entity_ids=("support_ticket", "account", "product_part"),
            source_asset_ids=("crm_tickets", "crm_accounts", "product_parts"),
            status=active,
            semantic_boundary="Exposure is not impact, loss, or causation.",
        ),
        MetricRequirement(
            metric_id="published_document_evidence",
            display_name="Published document evidence",
            description="Hashed line-level passages from governed published documents.",
            entity_ids=("internal_document",),
            source_asset_ids=("internal_documents",),
            status=active,
            semantic_boundary="Retrieval relevance does not establish applicability or authority.",
        ),
        MetricRequirement(
            metric_id="product_issue_backlog",
            display_name="Product issue backlog",
            description="Issue count and effort segmented by priority, status, and product part.",
            entity_ids=("product_issue", "product_part"),
            source_asset_ids=("product_issues", "product_parts"),
            status=available,
            semantic_boundary="Story points are an effort estimate, not elapsed time or impact.",
        ),
        MetricRequirement(
            metric_id="transcript_evidence",
            display_name="Account transcript evidence",
            description="Attributed statements from account-linked conversations.",
            entity_ids=("transcript", "account", "opportunity"),
            source_asset_ids=("account_transcripts",),
            status=available,
            semantic_boundary=(
                "Statements may be incomplete, subjective, or contradicted elsewhere."
            ),
        ),
        MetricRequirement(
            metric_id="knowledge_evidence",
            display_name="Knowledge-base evidence",
            description="Published product and operating guidance retrieved with citations.",
            entity_ids=("knowledge_article",),
            source_asset_ids=("knowledge_articles",),
            status=available,
            semantic_boundary="Published guidance may be outdated or inapplicable to an account.",
        ),
        MetricRequirement(
            metric_id="bookings",
            display_name="Bookings",
            description="Signed commercial value attributed to an explicit booking date.",
            entity_ids=("booking", "account", "opportunity", "executed_contract"),
            source_asset_ids=("bookings", "contract_assignments"),
            status=planned,
            semantic_boundary="Bookings are not billings, recognized revenue, or cash.",
        ),
        MetricRequirement(
            metric_id="recognized_revenue",
            display_name="Recognized revenue",
            description="Revenue recognized in a period under an explicit schedule.",
            entity_ids=("revenue_event", "invoice", "subscription", "account"),
            source_asset_ids=("revenue_schedule", "invoices", "subscriptions"),
            status=planned,
            semantic_boundary=(
                "Recognition dates and policy must be preserved separately from billing."
            ),
        ),
        MetricRequirement(
            metric_id="billing_and_collections",
            display_name="Billing and collections",
            description="Invoiced value, aging, cash receipts, failures, and reversals.",
            entity_ids=("invoice", "payment", "account"),
            source_asset_ids=("invoices", "payments"),
            status=planned,
            semantic_boundary="Invoices and cash movements are not recognized revenue.",
        ),
        MetricRequirement(
            metric_id="price_and_discount",
            display_name="Price and discount",
            description="List price, contracted price, quantity, and discount at order-line level.",
            entity_ids=("booking", "product_part", "account"),
            source_asset_ids=("bookings",),
            status=planned,
            semantic_boundary="Mix and quantity changes must be separated from price changes.",
        ),
        MetricRequirement(
            metric_id="implementation_timing",
            display_name="Implementation timing",
            description="Planned versus actual milestones, activation lag, and backlog.",
            entity_ids=("implementation_milestone", "booking", "account"),
            source_asset_ids=("implementation_milestones",),
            status=planned,
            semantic_boundary="Operational delay does not itself determine accounting treatment.",
        ),
        MetricRequirement(
            metric_id="product_adoption",
            display_name="Product adoption",
            description="Account and product usage over explicit periods.",
            entity_ids=("usage_event", "account", "product_part"),
            source_asset_ids=("product_usage",),
            status=planned,
            semantic_boundary="Usage is an activity measure and not proof of realized value.",
        ),
        MetricRequirement(
            metric_id="gross_margin",
            display_name="Gross margin",
            description="Recognized revenue less governed attributable service costs.",
            entity_ids=("revenue_event", "cost_record", "account", "product_part"),
            source_asset_ids=("revenue_schedule", "cost_ledger"),
            status=planned,
            semantic_boundary="Allocation policy must accompany any attributed cost or margin.",
        ),
    )


def _scenarios() -> tuple[FlagshipScenarioDefinition, ...]:
    return (
        FlagshipScenarioDefinition(
            scenario_id="support_pipeline_causal_screen",
            question="Did open P1 issues explain the Q1 closed-won ACV decline?",
            purpose="Preserve causal restraint while reconciling support and CRM evidence.",
            required_metric_ids=("closed_won_opportunity_acv", "support_exposure"),
        ),
        FlagshipScenarioDefinition(
            scenario_id="document_grounded_support_review",
            question=(
                "Which accounts have P1 exposure, and what does the published Standard MSA say?"
            ),
            purpose="Combine structured prioritization with exact document citations.",
            required_metric_ids=("support_exposure", "published_document_evidence"),
        ),
        FlagshipScenarioDefinition(
            scenario_id="product_issue_customer_impact",
            question="Which product issues are most likely to affect high-value accounts?",
            purpose="Connect product delivery evidence to account and support exposure.",
            required_metric_ids=("product_issue_backlog", "support_exposure"),
        ),
        FlagshipScenarioDefinition(
            scenario_id="bookings_revenue_divergence",
            question="Bookings are up, but revenue is flat. Figure out why.",
            purpose=(
                "Prove finance, sales, implementation, pricing, and segment reconciliation."
            ),
            required_metric_ids=(
                "bookings",
                "recognized_revenue",
                "price_and_discount",
                "implementation_timing",
            ),
        ),
        FlagshipScenarioDefinition(
            scenario_id="transaction_contract_pricing_review",
            question=(
                "Review this transaction for contract, order, invoice, and pricing exceptions."
            ),
            purpose="Preserve transaction review as a benchmark domain and potential vertical.",
            required_metric_ids=(
                "bookings",
                "billing_and_collections",
                "price_and_discount",
                "published_document_evidence",
            ),
        ),
    )


def _build_default_testbed() -> BusinessEvidenceTestbed:
    payload = {
        "schema_version": "1.0",
        "testbed_version": "stage-12-v1",
        "source_name": ENTERPRISE_BENCH.name,
        "source_commit": ENTERPRISE_BENCH.source_commit,
        "source_sha256": ENTERPRISE_BENCH.sha256,
        "source_license": ENTERPRISE_BENCH.license,
        "source_classification": DataClassification.PUBLIC_SYNTHETIC,
        "entities": [item.model_dump(mode="json") for item in _canonical_entities()],
        "assets": [item.model_dump(mode="json") for item in _source_assets()],
        "relationships": [item.model_dump(mode="json") for item in _relationships()],
        "metrics": [item.model_dump(mode="json") for item in _metrics()],
        "scenarios": [item.model_dump(mode="json") for item in _scenarios()],
    }
    return BusinessEvidenceTestbed(**payload, testbed_digest=catalog_digest(payload))


DEFAULT_TESTBED = _build_default_testbed()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _record_counts(path: Path, asset: SourceAssetDefinition) -> tuple[int, int]:
    value: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError(f"Testbed asset must contain a JSON list: {asset.primary_locator}")
    if not all(isinstance(item, dict) for item in value):
        raise ValueError(f"Testbed asset contains a non-object record: {asset.primary_locator}")
    if asset.eligibility_field is None:
        return len(value), len(value)
    eligible = sum(
        item.get(asset.eligibility_field) == asset.eligibility_value for item in value
    )
    return len(value), eligible


def _load_records(root: Path, locator: str) -> list[dict[str, Any]]:
    value = json.loads((root / locator).read_text(encoding="utf-8"))
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"Expected a JSON object list: {locator}")
    return value


def _orphan_count(values: set[str], valid: set[str]) -> int:
    return len(values - valid)


def _relationship_checks(root: Path) -> tuple[IntegrityCheck, ...]:
    accounts = _load_records(root, "crm_json_data/accounts.json")
    opportunities = _load_records(root, "crm_json_data/opportunities.json")
    tickets = _load_records(root, "crm_json_data/tickets.json")
    crm_users = _load_records(root, "crm_json_data/users.json")
    parts = _load_records(root, "pm_json_data/maple_parts.json")
    issues = _load_records(root, "pm_json_data/issues.json")
    conversations = _load_records(root, "pm_json_data/conversations.json")
    comments = _load_records(root, "pm_json_data/comments.json")
    product_users = _load_records(root, "pm_json_data/users.json")
    articles = _load_records(root, "maple_kb/articles.json")
    documents = _load_records(root, "internal_docs/msa_and_compliance.json")
    transcripts = _load_records(root, "transcripts/transcripts.json")

    account_ids = {item["account_id"] for item in accounts}
    opportunity_ids = {item["opportunity_id"] for item in opportunities}
    ticket_ids = {item["ticket_id"] for item in tickets}
    issue_ids = {item["issue_id"] for item in issues}
    part_ids = {item["part_id"] for item in parts}
    conversation_ids = {item["conversation_id"] for item in conversations}
    user_ids = {item["user_id"] for item in (*crm_users, *product_users)}

    counts = {
        "opportunity_account": _orphan_count(
            {item["account_id"] for item in opportunities}, account_ids
        ),
        "ticket_account": _orphan_count({item["account_id"] for item in tickets}, account_ids),
        "ticket_product_part": _orphan_count(
            {part_id for item in tickets for part_id in item.get("components", [])}, part_ids
        ),
        "ticket_conversation": _orphan_count(
            {item["conversation_id"] for item in tickets if item.get("conversation_id")},
            conversation_ids,
        ),
        "issue_product_part": _orphan_count(
            {part_id for item in issues for part_id in item.get("components", [])}, part_ids
        ),
        "issue_conversation": _orphan_count(
            {item["conversation_id"] for item in issues if item.get("conversation_id")},
            conversation_ids,
        ),
        "comment_conversation": _orphan_count(
            {item["conversation_id"] for item in comments}, conversation_ids
        ),
        "transcript_account": _orphan_count(
            {item["account_id"] for item in transcripts}, account_ids
        ),
        "transcript_opportunity": _orphan_count(
            {item["opportunity_id"] for item in transcripts}, opportunity_ids
        ),
    }
    parent_orphans = 0
    for conversation in conversations:
        valid_ids = issue_ids if conversation["parent_type"] == "issue" else ticket_ids
        parent_orphans += conversation["parent_id"] not in valid_ids
    counts["conversation_parent"] = parent_orphans

    person_values: set[str] = set()
    for records, fields in (
        (opportunities, ("created_by_id", "owner_id")),
        (tickets, ("assignee_id", "creator_id", "modified_by_id", "reporter_id")),
        (issues, ("assignee_id", "creator_id", "modified_by_id", "reporter_id")),
        (comments, ("author_id",)),
        (articles, ("author_id",)),
        (documents, ("author_id",)),
        (transcripts, ("organizer_id",)),
    ):
        person_values.update(
            value for item in records for field in fields if (value := item.get(field))
        )
    person_values.update(
        participant["user_id"]
        for transcript in transcripts
        for participant in transcript.get("participants", [])
    )
    counts["person_references"] = _orphan_count(person_values, user_ids)

    return tuple(
        IntegrityCheck(check_id=check_id, passed=orphan_count == 0, orphan_count=orphan_count)
        for check_id, orphan_count in counts.items()
    )


def inventory_testbed(
    root: Path,
    *,
    testbed: BusinessEvidenceTestbed = DEFAULT_TESTBED,
    check_relationships: bool = True,
) -> TestbedInventoryReport:
    verified_root = verify_dataset(root, spec=ENTERPRISE_BENCH)
    inventory: list[AssetInventory] = []
    present_records = 0
    for asset in testbed.assets:
        path = verified_root / asset.primary_locator
        present = path.is_file()
        count: int | None = None
        eligible: int | None = None
        digest: str | None = None
        if present:
            count, eligible = _record_counts(path, asset)
            digest = _sha256(path)
            present_records += count
        elif asset.status != CoverageStatus.PLANNED:
            raise ValueError(f"Approved source asset is missing: {asset.primary_locator}")
        inventory.append(
            AssetInventory(
                asset_id=asset.asset_id,
                status=asset.status,
                primary_locator=asset.primary_locator,
                present=present,
                record_count=count,
                eligible_record_count=eligible,
                content_sha256=digest,
            )
        )

    scenarios = []
    for scenario in testbed.scenarios:
        blocking = tuple(
            metric_id
            for metric_id in scenario.required_metric_ids
            if testbed.metric(metric_id).status != CoverageStatus.ACTIVE
        )
        scenarios.append(
            ScenarioInventory(
                scenario_id=scenario.scenario_id,
                question=scenario.question,
                readiness=testbed.scenario_readiness(scenario),
                blocking_metrics=blocking,
            )
        )

    statuses = [asset.status for asset in testbed.assets]
    return TestbedInventoryReport(
        testbed_version=testbed.testbed_version,
        testbed_digest=testbed.testbed_digest,
        source_verified=True,
        source_commit=testbed.source_commit,
        source_sha256=testbed.source_sha256,
        summary=CoverageSummary(
            total_assets=len(testbed.assets),
            active_assets=statuses.count(CoverageStatus.ACTIVE),
            available_assets=statuses.count(CoverageStatus.AVAILABLE),
            planned_assets=statuses.count(CoverageStatus.PLANNED),
            present_source_records=present_records,
        ),
        assets=tuple(inventory),
        relationship_checks=(
            _relationship_checks(verified_root) if check_relationships else tuple()
        ),
        scenarios=tuple(scenarios),
    )


def active_asset_locators() -> frozenset[str]:
    """Return source locators that already back executable catalog capabilities."""

    return frozenset(
        locator
        for capability in DEFAULT_CATALOG.capabilities
        for locator in (*capability.json_files, *capability.document_files)
    )
