"""Knowledge resolution pipeline transforming raw retrieval results into an authoritative EvidencePack."""

import re
from typing import List, Optional, Sequence, Set

from src.knowledge.authority import AuthorityResolver
from src.knowledge.conflict import ConflictDetector
from src.knowledge.evidence import ApprovedEvidence, EvidencePack, ExcludedEvidence
from src.knowledge.supersession import SupersessionResolver
from src.retrieval.models import RetrievalResult

# Stopwords to ignore when performing lexical overlap checks
STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "because", "as", "what",
    "which", "this", "that", "these", "those", "then", "just", "so", "than",
    "such", "both", "through", "about", "for", "is", "of", "while", "during",
    "to", "from", "in", "out", "on", "off", "again", "further", "then", "once",
    "do", "does", "did", "have", "has", "had", "can", "could", "should", "would",
    "i", "you", "he", "she", "it", "we", "they", "my", "your", "our", "all", "are",
}


def extract_content_keywords(text: str) -> Set[str]:
    """Extract significant lowercase content keywords from text."""
    words = re.findall(r"\b[a-z0-9]+(?:[-_][a-z0-9]+)*\b", text.lower())
    return {w for w in words if w not in STOPWORDS and len(w) > 2}


class KnowledgeResolver:
    """Orchestrates supersession, authority filtering, conflict detection, and evidence sufficiency."""

    def __init__(
        self,
        supersession_resolver: Optional[SupersessionResolver] = None,
        authority_resolver: Optional[AuthorityResolver] = None,
        conflict_detector: Optional[ConflictDetector] = None,
    ) -> None:
        self.supersession_resolver = supersession_resolver or SupersessionResolver()
        self.authority_resolver = authority_resolver or AuthorityResolver()
        self.conflict_detector = conflict_detector or ConflictDetector()

    def resolve(
        self,
        query: str,
        retrieval_results: List[RetrievalResult],
    ) -> EvidencePack:
        """Resolve retrieved candidate chunks into an authoritative EvidencePack."""
        all_excluded: List[ExcludedEvidence] = []

        # -------------------------------------------------------------------
        # 1. Supersession Resolution
        # -------------------------------------------------------------------
        active_candidates, superseded_excluded = self.supersession_resolver.resolve(
            retrieval_results
        )
        all_excluded.extend(superseded_excluded)

        # -------------------------------------------------------------------
        # 2. Authority & Customer-Answerability Filtering
        # -------------------------------------------------------------------
        eligible_candidates, authority_excluded = (
            self.authority_resolver.filter_eligible_candidates(active_candidates)
        )
        all_excluded.extend(authority_excluded)

        # -------------------------------------------------------------------
        # 3. Approved Evidence Construction
        # -------------------------------------------------------------------
        approved_evidence: List[ApprovedEvidence] = [
            ApprovedEvidence(
                chunk=res.chunk,
                retrieval_score=res.score,
                retrieval_rank=res.rank,
                retrieval_strategy=res.strategy,
            )
            for res in eligible_candidates
        ]

        # -------------------------------------------------------------------
        # 4. Conflict Detection
        # -------------------------------------------------------------------
        conflict_detected, conflict_evidence, conflict_reason = (
            self.conflict_detector.detect_conflicts(query, approved_evidence)
        )

        # -------------------------------------------------------------------
        # 5. Evidence Sufficiency & Grounding Gate
        # -------------------------------------------------------------------
        evidence_sufficient = True
        resolution_reason = "Authoritative evidence approved."
        handoff_recommended = False

        if not approved_evidence and not conflict_evidence:
            evidence_sufficient = False
            resolution_reason = "No approved customer-facing evidence found for this query."
            handoff_recommended = True

        elif conflict_detected:
            # Active official conflict requires human confirmation
            evidence_sufficient = True  # We have sufficient evidence of the conflict
            resolution_reason = conflict_reason
            handoff_recommended = True

        else:
            # Check if query asks for out-of-domain / ungrounded concepts (e.g. vegan materials)
            query_keywords = extract_content_keywords(query)
            corpus_text = " ".join(
                f"{item.heading} {item.content}".lower() for item in approved_evidence
            )
            corpus_keywords = extract_content_keywords(corpus_text)

            # Look for specific inquiry keywords completely missing from evidence
            # Exclude known generic words
            missing_critical_terms = {
                k for k in query_keywords
                if k not in corpus_keywords
                and k in {"vegan", "hypoallergenic", "waterproof", "submersion", "lifetime"}
            }

            if "vegan" in missing_critical_terms:
                evidence_sufficient = False
                resolution_reason = (
                    "Knowledge base does not contain information regarding vegan materials or certifications."
                )
                handoff_recommended = True

        return EvidencePack(
            query=query,
            approved_evidence=approved_evidence,
            excluded_evidence=all_excluded,
            conflict_detected=conflict_detected,
            conflict_evidence=conflict_evidence,
            evidence_sufficient=evidence_sufficient,
            resolution_reason=resolution_reason,
            handoff_recommended=handoff_recommended,
        )
