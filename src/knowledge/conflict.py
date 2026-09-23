"""Deterministic conflict detection between active official knowledge-base sources."""

from typing import List, Optional, Tuple

from src.core.models import KnowledgeChunk
from src.knowledge.evidence import ApprovedEvidence
from src.retrieval.models import RetrievalResult


class ConflictRule:
    """A deterministic conflict detection rule defining incompatible assertions."""

    def __init__(
        self,
        name: str,
        doc_id_a: str,
        doc_id_b: str,
        topic_keywords: List[str],
        description: str,
        heading_a: Optional[str] = None,
        heading_b: Optional[str] = None,
    ) -> None:
        self.name = name
        self.doc_id_a = doc_id_a
        self.doc_id_b = doc_id_b
        self.topic_keywords = [k.lower() for k in topic_keywords]
        self.description = description
        self.heading_a = heading_a
        self.heading_b = heading_b

    def check(
        self, query: str, approved_evidence: List[ApprovedEvidence]
    ) -> Tuple[bool, List[ApprovedEvidence], str]:
        """Check if approved evidence triggers this conflict rule."""
        query_lower = query.lower()

        # Check if query or retrieved content matches the conflict topic
        matches_topic = any(kw in query_lower for kw in self.topic_keywords)

        chunks_a: List[ApprovedEvidence] = []
        chunks_b: List[ApprovedEvidence] = []

        for item in approved_evidence:
            if item.document_id == self.doc_id_a:
                if not self.heading_a or self.heading_a.lower() in item.heading.lower():
                    chunks_a.append(item)
            elif item.document_id == self.doc_id_b:
                if not self.heading_b or self.heading_b.lower() in item.heading.lower():
                    chunks_b.append(item)

        # If both incompatible sources are present (or query specifically targets the conflicting topic)
        if chunks_a and chunks_b:
            conflict_items = chunks_a + chunks_b
            return True, conflict_items, self.description

        # If query specifically asks about the conflicting topic and one source is present,
        # but the topic has a known contradiction across active official docs:
        if matches_topic and (chunks_a or chunks_b):
            conflict_items = chunks_a + chunks_b
            return True, conflict_items, self.description

        return False, [], ""


# Registry of known domain-level policy conflicts in Aster & Row corpus
BUILTIN_CONFLICT_RULES: List[ConflictRule] = [
    ConflictRule(
        name="breeze_tumbler_dishwasher_conflict",
        doc_id_a="CARE-2026-01",
        doc_id_b="PROD-BREEZE-20",
        heading_a="Breeze Tumbler",
        heading_b="Cleaning",
        topic_keywords=["dishwasher", "dish wash", "clean", "washing", "breeze tumbler"],
        description=(
            "Official sources conflict on Breeze Tumbler dishwashing safety: "
            "Product Care Guide (CARE-2026-01) states the stainless-steel body must be hand-washed, "
            "while Breeze Tumbler Product Information (PROD-BREEZE-20) states all components are dishwasher safe."
        ),
    )
]


class ConflictDetector:
    """Detects genuine contradictions between active official knowledge-base sources."""

    def __init__(self, rules: Optional[List[ConflictRule]] = None) -> None:
        self.rules = rules or BUILTIN_CONFLICT_RULES

    def detect_conflicts(
        self, query: str, approved_evidence: List[ApprovedEvidence]
    ) -> Tuple[bool, List[ApprovedEvidence], str]:
        """Evaluate approved evidence against registered conflict rules.

        Returns:
            (conflict_detected, conflicting_evidence_items, conflict_description)
        """
        for rule in self.rules:
            detected, items, desc = rule.check(query, approved_evidence)
            if detected:
                return True, items, desc

        return False, [], ""
