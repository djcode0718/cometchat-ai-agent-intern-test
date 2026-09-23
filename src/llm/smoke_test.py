"""Manual smoke test utility for live LLM providers (Gemini & Grok).

Usage:
    python -m src.llm.smoke_test
    or
    python src/llm/smoke_test.py

This script only runs real API calls when explicit environment keys are provided.
It NEVER executes during automated pytest runs.
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

from src.core.config import get_settings
from src.core.models import CitationSource, DecisionState, DocumentMetadata, KnowledgeChunk
from src.knowledge.evidence import ApprovedEvidence
from src.llm.fallback import FallbackChainLLMProvider
from src.llm.gemini import GeminiLLMProvider
from src.llm.grok import GrokLLMProvider, GroqLLMProvider
from src.llm.models import GroundedGenerationRequest


def create_sample_request() -> GroundedGenerationRequest:
    """Construct a minimal sample generation request with approved policy evidence."""
    meta = DocumentMetadata(
        document_id="RET-2026-01",
        title="Standard Return Policy",
        status="active",
        effective_date="2026-01-01",
        audience="customer",
        policy_authority="official",
        customer_answering=True,
    )
    chunk = KnowledgeChunk(
        chunk_id="01-returns-policy-current-chunk-1",
        document_id="01-returns-policy-current.md",
        filename="01-returns-policy-current.md",
        heading="Standard return window",
        content="Customers on the standard plan may request a return within 30 calendar days of delivery.",
        metadata=meta,
    )
    sample_doc = ApprovedEvidence(
        chunk=chunk,
        retrieval_score=0.95,
        retrieval_rank=1,
        retrieval_strategy="hybrid",
    )
    return GroundedGenerationRequest(
        user_query="What is your return window for a backpack?",
        decision_state=DecisionState.ANSWER,
        decision_reason="Standard return policy query with authoritative active evidence.",
        approved_evidence=[sample_doc],
        citations=[CitationSource(filename="01-returns-policy-current.md", heading="Standard return window")],
    )


def run_smoke_test() -> None:
    print("=" * 60)
    print("ASTER & ROW — LLM PROVIDER LIVE SMOKE TEST")
    print("=" * 60)

    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    groq_key = os.getenv("GROQ_API_KEY") or os.getenv("GROK_API_KEY") or os.getenv("XAI_API_KEY")

    if not gemini_key and not groq_key:
        print("\n[INFO] Neither GEMINI_API_KEY nor GROQ_API_KEY is set.")
        print("To run live provider smoke tests, set keys in your environment:")
        print("  export GEMINI_API_KEY='your_key_here'")
        print("  export GROQ_API_KEY='your_key_here'")
        print("Skipping live network calls.\n")
        return

    req = create_sample_request()

    # 1. Test Gemini Primary if key available
    if gemini_key:
        print("\n[1] Testing Primary Provider: Gemini API...")
        try:
            gemini = GeminiLLMProvider()
            resp = gemini.generate(req)
            print(f"  ✓ Gemini Success ({gemini.provider_name})")
            print(f"  Latency: {gemini.last_latency_ms} ms")
            print(f"  Response: {resp.message}")
            print(f"  Citations: {resp.citation_strings}")
            print(f"  Fallback: {resp.is_fallback}")
        except Exception as e:
            print(f"  ✗ Gemini Failed: {type(e).__name__} - {e}")
    else:
        print("\n[1] Gemini API key not set — skipping Gemini live test.")

    # 2. Test Groq Fallback if key available
    if groq_key:
        print("\n[2] Testing Fallback Provider: Groq API...")
        try:
            groq = GroqLLMProvider()
            resp = groq.generate(req)
            print(f"  ✓ Groq Success ({groq.provider_name})")
            print(f"  Latency: {groq.last_latency_ms} ms")
            print(f"  Response: {resp.message}")
            print(f"  Citations: {resp.citation_strings}")
            print(f"  Fallback: {resp.is_fallback}")
        except Exception as e:
            print(f"  ✗ Groq Failed: {type(e).__name__} - {e}")
    else:
        print("\n[2] Groq API key not set — skipping Groq live test.")

    # 3. Test Fallback Chain (Gemini -> Groq -> Deterministic Fallback)
    print("\n[3] Testing Fallback Chain...")
    gemini = GeminiLLMProvider()
    groq = GroqLLMProvider()
    chain = FallbackChainLLMProvider(primary_provider=gemini, fallback_provider=groq, deterministic_fallback_on_error=True)
    try:
        resp = chain.generate(req)
        print(f"  ✓ Chain Execution Completed")
        print(f"  Telemetry: {chain.last_telemetry}")
        print(f"  Response: {resp.message}")
    except Exception as e:
        print(f"  ✗ Chain Failed: {type(e).__name__} - {e}")

    print("\n" + "=" * 60)
    print("SMOKE TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    run_smoke_test()
