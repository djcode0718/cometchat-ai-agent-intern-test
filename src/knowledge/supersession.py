"""Supersession graph and resolution for knowledge-base documents."""

from typing import Dict, List, Optional, Set, Tuple

from src.core.models import DocumentMetadata, KnowledgeChunk
from src.knowledge.evidence import ExcludedEvidence, ExclusionReason
from src.retrieval.models import RetrievalResult


class SupersessionResolver:
    """Detects and resolves superseded documents in retrieved candidate sets."""

    @staticmethod
    def is_superseded(metadata: DocumentMetadata) -> bool:
        """Check whether a document's metadata indicates it is superseded."""
        return metadata.status == "superseded" or bool(metadata.superseded_by)

    @classmethod
    def resolve(
        cls, candidates: List[RetrievalResult]
    ) -> Tuple[List[RetrievalResult], List[ExcludedEvidence]]:
        """Separate candidate retrieval results into non-superseded candidates and superseded excluded evidence.

        A candidate is excluded as superseded if:
        1. Its document metadata explicitly marks status == 'superseded'.
        2. Its document metadata has a 'superseded_by' field.
        3. Another active candidate in the retrieval set declares that it supersedes this candidate's document_id.
        """
        # Identify all document IDs that are explicitly superseded by an active document in the set
        superseded_doc_ids: Set[str] = set()
        active_superseders: Dict[str, str] = {}  # superseded_id -> active_doc_id

        for res in candidates:
            meta = res.metadata
            if meta.status == "active" and meta.supersedes:
                superseded_doc_ids.add(meta.supersedes)
                active_superseders[meta.supersedes] = meta.document_id

        kept_candidates: List[RetrievalResult] = []
        excluded_items: List[ExcludedEvidence] = []

        for res in candidates:
            meta = res.metadata
            doc_id = meta.document_id

            if cls.is_superseded(meta) or doc_id in superseded_doc_ids:
                superseder = meta.superseded_by or active_superseders.get(doc_id, "active version")
                excluded_items.append(
                    ExcludedEvidence(
                        chunk=res.chunk,
                        reason=ExclusionReason.SUPERSEDED,
                        details=f"Document {doc_id} is superseded by {superseder}.",
                        retrieval_score=res.score,
                        retrieval_rank=res.rank,
                        retrieval_strategy=res.strategy,
                    )
                )
            else:
                kept_candidates.append(res)

        return kept_candidates, excluded_items
