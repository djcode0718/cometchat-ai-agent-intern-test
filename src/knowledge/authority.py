"""Knowledge authority and customer-answerability filtering."""

from typing import List, Tuple

from src.core.models import DocumentMetadata
from src.knowledge.evidence import ExcludedEvidence, ExclusionReason
from src.retrieval.models import RetrievalResult


class AuthorityResolver:
    """Evaluates document metadata to enforce customer-answerability, policy authority, and audience boundaries."""

    @staticmethod
    def evaluate_chunk_eligibility(
        result: RetrievalResult,
    ) -> Tuple[bool, ExclusionReason, str]:
        """Evaluate if a retrieved chunk is eligible for approved customer-facing evidence.

        Returns:
            (is_eligible, reason, explanation_details)
        """
        meta: DocumentMetadata = result.metadata

        # 1. Hard customer-answering flag
        if not meta.customer_answering:
            return (
                False,
                ExclusionReason.CUSTOMER_ANSWERING_FALSE,
                f"Document {meta.document_id} has customer_answering=False (internal-only).",
            )

        # 2. Audience boundary
        if meta.audience == "internal":
            return (
                False,
                ExclusionReason.INTERNAL_AUDIENCE,
                f"Document {meta.document_id} has audience=internal (not customer-facing).",
            )

        # 3. Policy authority check
        if meta.policy_authority != "official":
            return (
                False,
                ExclusionReason.POLICY_AUTHORITY_NONE,
                f"Document {meta.document_id} policy_authority is {meta.policy_authority!r} (not official).",
            )

        # 4. Status checks
        if meta.status == "draft":
            return (
                False,
                ExclusionReason.DRAFT_STATUS,
                f"Document {meta.document_id} is in draft status.",
            )

        if meta.status != "active":
            return (
                False,
                ExclusionReason.INACTIVE_STATUS,
                f"Document {meta.document_id} status is {meta.status!r} (inactive).",
            )

        return (True, ExclusionReason.DUPLICATE, "Eligible customer-facing evidence.")

    @classmethod
    def filter_eligible_candidates(
        cls, candidates: List[RetrievalResult]
    ) -> Tuple[List[RetrievalResult], List[ExcludedEvidence]]:
        """Filter candidates into eligible active customer evidence and excluded items with explicit reasons."""
        eligible_candidates: List[RetrievalResult] = []
        excluded_items: List[ExcludedEvidence] = []

        for res in candidates:
            is_eligible, reason, details = cls.evaluate_chunk_eligibility(res)
            if is_eligible:
                eligible_candidates.append(res)
            else:
                excluded_items.append(
                    ExcludedEvidence(
                        chunk=res.chunk,
                        reason=reason,
                        details=details,
                        retrieval_score=res.score,
                        retrieval_rank=res.rank,
                        retrieval_strategy=res.strategy,
                    )
                )

        return eligible_candidates, excluded_items
