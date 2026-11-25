# Dataset Audit Report: Stage 3 Standard 50-Question Answerable Benchmark

**Audit Date**: 2026-11-25  
**Target Dataset**: [`evaluation/answer_quality_v1/stage3_standard_50_answerable.json`](file:///Users/sj/Documents/cometchat-ai-agent-intern-test/evaluation/answer_quality_v1/stage3_standard_50_answerable.json)  
**Curated Cases**: 50  
**Baseline Git Commit**: `a4cfc0d54665d567d0a1be7158190769db1562e7`  
**Audit Status**: **PASSED (100% Validated)**

---

## 1. Executive Summary

This audit validates the newly curated **Standard 50-Question Answerable Benchmark** (`stage3_standard_50_answerable.json`) for the Aster & Row AI Customer Support Agent.

While the existing difficult benchmark (`stage3_difficult_50_answerable.json`) assesses edge cases, multi-policy conflicts, and applied calendar calculations, this standard benchmark is designed to evaluate core agent performance on common, straightforward, and clearly answerable inquiries that customer support agents handle on a daily basis.

### Headline Audit Findings:
- **Total Questions**: Exactly 50 unique questions (`STD50-001` through `STD50-050`).
- **Answerability**: 100% (50/50) are classified as `answerable`.
- **Target Category Distribution**: Perfectly conforms to the required 15 / 10 / 10 / 10 / 5 distribution.
- **Single-Document Focus**: 100% of scenarios (50/50) are supported by a single authoritative source document and 1–2 specific evidence chunks, eliminating cross-document ranking displacement.
- **Total Required Atomic Claims**: 82 claims (average 1.64 claims per scenario; range 1–3 claims).
- **Zero Superseded or Draft Contamination**: All cited chunks map to active, official policies. Zero references to `02-returns-policy-legacy.md` or `14-internal-content-migration-notes.md`.
- **Zero Overlap with Difficult Benchmark**: Verified 0 duplicate or near-duplicate queries between the standard and difficult benchmarks.

---

## 2. Category Distribution

The 50 questions are distributed across five distinct question categories:

| Category | Target Count | Actual Count | Percentage | Required Claims | Avg Claims / Query |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `straightforward_factual` | 15 | 15 | 30.0% | 23 | 1.53 |
| `simple_policy` | 10 | 10 | 20.0% | 16 | 1.60 |
| `basic_procedural` | 10 | 10 | 20.0% | 22 | 2.20 |
| `simple_eligibility` | 10 | 10 | 20.0% | 14 | 1.40 |
| `common_clarification` | 5 | 5 | 10.0% | 7 | 1.40 |
| **Total** | **50** | **50** | **100.0%** | **82** | **1.64** |

---

## 3. Document Coverage & Sourcing Structure

Every question in the benchmark is tied to a single authoritative document from the Aster & Row official knowledge base:

| Source Document | Document ID | Status | Authority | Questions Mapped | Question IDs |
| :--- | :---: | :---: | :---: | :---: | :--- |
| `01-returns-policy-current.md` | `RET-2026-01` | active | official | 7 | STD50-001, 013, 017, 033, 036, 037, 045 |
| `07-warranty.md` | `WAR-2026-01` | active | official | 7 | STD50-002, 003, 020, 021, 032, 039, 050 |
| `05-domestic-shipping.md` | `SHIP-2026-US` | active | official | 6 | STD50-004, 005, 006, 007, 015, 025 |
| `10-gift-cards-and-price-adjustments.md` | `PAY-2026-03` | active | official | 6 | STD50-010, 022, 035, 042, 047, 049 |
| `06-international-shipping.md` | `SHIP-2026-INTL` | active | official | 5 | STD50-008, 009, 018, 019, 024 |
| `11-product-care.md` | `CARE-2026-01` | active | official | 4 | STD50-026, 027, 028, 044 |
| `04-damaged-or-wrong-items.md` | `OPS-2026-04` | active | official | 4 | STD50-029, 034, 040, 048 |
| `08-order-changes-and-cancellations.md` | `ORD-2026-01` | active | official | 4 | STD50-030, 031, 038, 046 |
| `03-final-sale-and-promotions.md` | `RET-2026-02` | active | official | 3 | STD50-014, 016, 023 |
| `12-breeze-tumbler-product-card.md` | `PROD-BREEZE-20` | active | official | 2 | STD50-011, 012 |
| `09-trailplus-membership.md` | `MEM-2026-01` | active | official | 2 | STD50-041, 043 |
| **Total** | — | — | — | **50** | **STD50-001 through STD50-050** |

### Single-Document vs Multi-Document Complexity:
- **Questions Requiring 1 Document**: **50 / 50 (100.0%)**
- **Questions Requiring Multiple Documents**: **0 / 50 (0.0%)**

---

## 4. Answer Key & Evidence Grounding Verification

A full automated verification audit was executed against the Aster & Row `KnowledgeIngestionService` index:
1. **Chunk Existence**:
   - Total evidence chunks referenced: 34 unique chunks.
   - All 34 chunks exist in the parsed knowledge base index.
   - Missing chunks: **0**.
2. **Authority and Status Check**:
   - Chunks from superseded documents (`02-returns-policy-legacy.md`): **0**.
   - Chunks from draft / internal documents (`14-internal-content-migration-notes.md`): **0**.
   - Valid, active, official chunks: **100% (34/34)**.
3. **Atomic Claim Verifiability**:
   - All 82 required factual claims were cross-referenced against the chunk texts.
   - 100% of claims are direct factual statements or simple explicit policy rules (e.g., "$6.95 return shipping fee", "30 calendar days from delivery", "2 years for backpacks", "1–2 business days processing").
   - Zero claims require unstated assumptions or calendar date math.

---

## 5. Duplicate and Benchmark Isolation Checks

1. **Internal Duplication**:
   - Unique queries: 50 / 50.
   - Zero duplicated or near-duplicate prompts within `stage3_standard_50_answerable.json`.
2. **Comparison with Difficult Benchmark (`stage3_difficult_50_answerable.json`)**:
   - Query text overlap: **0 / 50 (0.0%)**.
   - The difficult benchmark focuses on multi-policy friction (e.g., final sale items arriving defective with fee waivers, applied warranty date calculations, cancellation button vs warehouse processing thresholds).
   - In contrast, the standard benchmark tests direct retrieval of explicit single-policy answers (e.g., "Do gift cards expire?", "What is the warranty period for backpacks?").

---

## 6. Audit Verdict

**STATUS: APPROVED FOR BENCHMARK EVALUATION**

The standard 50-question benchmark meets all criteria:
- Complete compliance with schema and validation rules.
- Fully answerable from active, official documentation.
- Representative of high-frequency, real-world customer service inquiries.
- Fully isolated from the existing 50-question difficult benchmark.
