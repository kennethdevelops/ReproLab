"""Status enums shared by the DB layer, API and workers."""

from __future__ import annotations

from enum import StrEnum


class IndexStatus(StrEnum):
    PENDING = "pending"
    FETCHING = "fetching"
    PARSING = "parsing"
    EMBEDDING = "embedding"
    READY = "ready"
    FAILED = "failed"
    CANCELLED = "cancelled"


class InvestigationStatus(StrEnum):
    QUEUED = "queued"
    PLANNING = "planning"
    RETRIEVING = "retrieving"
    BROWSING = "browsing"
    ANALYSING = "analysing"
    REPORTING = "reporting"
    # Terminal statuses.
    REPRODUCED = "reproduced"
    NOT_REPRODUCED = "not_reproduced"
    BLOCKED = "blocked"
    INCONCLUSIVE = "inconclusive"
    CANCELLED = "cancelled"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        return self in TERMINAL_INVESTIGATION_STATUSES


TERMINAL_INVESTIGATION_STATUSES = frozenset(
    {
        InvestigationStatus.REPRODUCED,
        InvestigationStatus.NOT_REPRODUCED,
        InvestigationStatus.BLOCKED,
        InvestigationStatus.INCONCLUSIVE,
        InvestigationStatus.CANCELLED,
        InvestigationStatus.FAILED,
    }
)


class RagMode(StrEnum):
    NONE = "none"
    LEXICAL = "lexical"
    VECTOR = "vector"
    HYBRID = "hybrid"
    HYBRID_RERANKED = "hybrid_reranked"


class TestValidation(StrEnum):
    __test__ = False  # not a pytest class

    NOT_ATTEMPTED = "not_attempted"
    PASSED_ORACLE = "passed_oracle"
    FAILED_ORACLE = "failed_oracle"
    UNSUPPORTED = "unsupported"
    EXECUTION_ERROR = "execution_error"


class FindingVerification(StrEnum):
    VERIFIED_OBSERVATION = "verified_observation"
    SUPPORTED_HYPOTHESIS = "supported_hypothesis"
    UNVERIFIED_HYPOTHESIS = "unverified_hypothesis"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class ProjectMode(StrEnum):
    DEMO = "demo"
    LOCAL = "local"
