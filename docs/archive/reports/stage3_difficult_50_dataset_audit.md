# Stage 3 Benchmark Curation Audit Report: 50 Difficult, Fully Answerable Scenarios

**Dataset Name**: `stage3_difficult_50_answerable.json`  
**Location**: `evaluation/answer_quality_v1/stage3_difficult_50_answerable.json`  
**Dataset Version**: 1.0.0  
**Curated On**: 2026-11-25  
**Baseline Git Commit**: `a4cfc0d54665d567d0a1be7158190769db1562e7`  
**Evaluation Track**: Answer Quality, Groundedness, and Multi-Evidence Reasoning  

---

## 1. Executive Summary

This report documents the curation, structure, source attribution, and verification of the **Stage 3 50-Question Difficult Answerable Benchmark** (`stage3_difficult_50_answerable.json`). 

Unlike synthetic or simple single-sentence lookup evaluations, this curated benchmark contains **exactly 50 difficult customer inquiries** designed to evaluate whether the Aster & Row AI Customer Support Agent can synthesize cross-document evidence, resolve conditional rules and exceptions, navigate supersession boundaries, answer multi-part questions completely, and communicate precise factual answers grounded strictly in authoritative policy.

Every scenario in this benchmark satisfies two fundamental guarantees:
1. **Fully Answerable**: Every required fact, timeframe, threshold, condition, and exception exists verbatim or through deterministic deduction in the official Aster & Row knowledge base.
2. **Zero External/Live System Dependencies**: No question requires querying a live order database, checking real-time warehouse inventory, issuing refunds, modifying live customer accounts, or making unstated assumptions.

---

## 2. Benchmark Composition & Category Distribution

The dataset strictly adheres to the requested distribution of 50 unique scenarios across 6 specialized evaluation categories:

| Category Code | Description | Target Count | Actual Count | Share |
| :--- | :--- | :---: | :---: | :---: |
| `multi_policy_or_document` | Requires cross-referencing 2 or more distinct policy documents | 10 | **10** | 20.0% |
| `exception_eligibility_conditional` | Tests complex edge cases, exclusions, and conditional eligibility rules | 10 | **10** | 20.0% |
| `date_sensitive_or_supersession` | Hinge on order dates, effective dates, elapsed days/months, or policy supersession | 8 | **8** | 16.0% |
| `multi_part_factual` | Inquiries containing 2 to 4 distinct factual queries requiring complete answers | 8 | **8** | 16.0% |
| `distinguishing_similar_policies` | Contrasts closely related policies (e.g., transit damage vs warranty; cancel vs return) | 7 | **7** | 14.0% |
| `difficult_precise_factual` | Inquiries requiring exact numbers, specific thresholds, and strict appliance/care rules | 7 | **7** | 14.0% |
| **Total** | | **50** | **50** | **100.0%** |

### Structural Complexity Metrics:
- **Total Benchmark Cases**: 50
- **Total Atomic Factual Claims Evaluated**: 204 claims (mean: 4.08 claims per case)
- **Total Forbidden / Negative Constraint Claims**: 150 claims (mean: 3.00 claims per case)
- **Scenarios Requiring Multiple Documents**: 21 / 50 (42.0%)
- **Scenarios Requiring Multiple Evidence Chunks**: 32 / 50 (64.0%)
- **Scenarios Requiring Date or Eligibility Reasoning**: 26 / 50 (52.0%)
- **Scenarios Requiring Multi-Part Answers**: 16 / 50 (32.0%)

---

## 3. Knowledge Base Source Documents Used

The benchmark draws evidence strictly from authoritative, active documents in `knowledge-base/` (plus the legacy returns policy strictly for pre-April 1, 2026 historical queries):

| Document Filename | Title | Status & Authority | Chunks Used | Scenarios Referencing |
| :--- | :--- | :---: | :---: | :---: |
| `01-returns-policy-current.md` | Returns Policy | Active / Official | 4 / 4 | 18 |
| `02-returns-policy-legacy.md` | Returns Policy — Legacy Version | Superseded / Official | 4 / 4 | 2 |
| `03-final-sale-and-promotions.md` | Final Sale and Promotional Purchases | Active / Official | 4 / 4 | 6 |
| `04-damaged-or-wrong-items.md` | Damaged, Defective, or Wrong Items | Active / Official | 4 / 4 | 9 |
| `05-domestic-shipping.md` | Domestic Shipping | Active / Official | 3 / 4 | 5 |
| `06-international-shipping.md` | International Shipping | Active / Official | 3 / 4 | 4 |
| `07-warranty.md` | Limited Product Warranty | Active / Official | 5 / 5 | 8 |
| `08-order-changes-and-cancellations.md` | Order Changes and Cancellations | Active / Official | 3 / 4 | 5 |
| `09-trailplus-membership.md` | TrailPlus Membership Benefits | Active / Official | 3 / 3 | 6 |
| `10-gift-cards-and-price-adjustments.md` | Gift Cards and Price Adjustments | Active / Official | 2 / 2 | 7 |
| `11-product-care.md` | Product Care Guide | Active / Official | 4 / 4 | 3 |
| `12-breeze-tumbler-product-card.md` | Breeze Tumbler — Product Information | Active / Official | 1 / 3 | 1 |
| **Total Official Sources** | | | **40 / 46** | **50** |

### Excluded Documents & Rationale:
1. `13-support-escalation.md` (Internal Support Escalation and Handoff Rules):
   - *Metadata*: `audience: internal`, `customer_answering: false`.
   - *Exclusion Reason*: Internal procedural instructions for human agents. Per Aster & Row authority rules (`AuthorityResolver`), internal-audience documents must not be cited as customer-facing evidence.
2. `14-internal-content-migration-notes.md` (Content Migration Scratchpad):
   - *Metadata*: `status: draft`, `policy_authority: none`, `customer_answering: false`.
   - *Exclusion Reason*: Contains draft unapproved copy (e.g., fictitious 60-day return claims) and vendor prompt-injection test probes. Strictly excluded from authoritative answer keys.

---

## 4. Question Exclusions and Replacements During Curation

During the curation process, candidate questions were screened and filtered out if they violated answerability or created unresolvable ambiguity:

1. **Unanswerable / Order Data Dependencies (Excluded)**:
   - *Candidate*: "Where is my order ORD-2041 right now and why is tracking delayed?"
   - *Reason for Exclusion*: Requires live tool execution (`order_lookup`) against real-time shipping carrier telemetry. Excluded to ensure benchmark evaluates knowledge retrieval and synthesis exclusively.
2. **Ambiguous Source Conflicts (Excluded from Answerable Benchmark)**:
   - *Candidate*: "Can I wash the stainless-steel body of the Breeze Tumbler in my dishwasher?"
   - *Reason for Exclusion*: Documented contradiction between `11-product-care.md` (hand-wash body only) and `12-breeze-tumbler-product-card.md` (all components dishwasher safe). Under Aster & Row governance, active official source conflicts require human escalation, not definitive answering. Replaced with temperature and appliance limitations (`AQ50-047`), which have unanimous cross-document consensus.
3. **Hypothetical Store Credit Expirations (Excluded)**:
   - *Candidate*: "Do Aster & Row store credits expire after 12 months?"
   - *Reason for Exclusion*: The knowledge base documents gift card rules ("gift cards do not expire"), but does not specify a separate policy for standalone store credits. Excluded to prevent requiring speculation or ungrounded assumptions.
4. **Trivial Single-Sentence Lookups (Excluded)**:
   - *Candidate*: "How long do I have to return an item?"
   - *Reason for Exclusion*: Too simplistic. Replaced with conditional, multi-policy, or date-sensitive variants (e.g. `AQ50-002`, `AQ50-023`) requiring cross-checking membership status, fees, and post-inspection refund schedules.

---

## 5. Dataset Validation Checklist & Results

Every scenario underwent programmatic and semantic verification against the codebase using `scratch/curate_stage3_difficult_50.py`:

| Validation Criterion | Requirement | Verification Result | Status |
| :--- | :--- | :--- | :---: |
| **Scenario Count** | Exactly 50 scenarios | 50 scenarios generated | **PASS** |
| **ID Uniqueness** | `AQ50-001` to `AQ50-050` with no collisions | 50 unique IDs | **PASS** |
| **Query Uniqueness** | Zero duplicate or near-duplicate queries | 50 distinct queries | **PASS** |
| **Category Allocation** | Exactly matches specified 10/10/8/8/7/7 distribution | 10 / 10 / 8 / 8 / 7 / 7 verified | **PASS** |
| **Answer Completeness** | Non-empty, comprehensive `expected_answer` | 100% populated (mean 412 chars) | **PASS** |
| **Atomic Claim Decomposition** | $\ge 2$ testable claims per scenario | 204 claims total (min 2, max 5, mean 4.08) | **PASS** |
| **Forbidden Claim Formulation** | $\ge 2$ explicit hallucination/error bounds | 150 claims total (min 2, max 4, mean 3.00) | **PASS** |
| **Evidence Reference Validity** | All chunk IDs exist in `ingest_knowledge_base()` | 100% of referenced chunk IDs valid (53 total) | **PASS** |
| **Citation Syntax Alignment** | Formatted as `[{filename} > {heading}]` | 100% structurally aligned with validator format | **PASS** |
| **Schema Compatibility** | Fully compatible with existing Stage 3 evaluator | Parsed and loaded by `evaluate_answer_quality_v1.py` | **PASS** |
| **Authority Boundary Safety** | No draft or unapproved sources cited | Zero references to `14-internal-content-migration-notes.md` | **PASS** |

---

## 6. Detailed 50-Scenario Summary Table

| ID | Category | Difficulty | Primary Supporting Documents | Claims Count | Core Evaluation Focus |
| :--- | :--- | :---: | :--- | :---: | :--- |
| `AQ50-001` | Multi-Policy | Hard | `01-returns`, `03-final-sale`, `04-damaged` | 5 | Defective arrival on final-sale item; fee waiver |
| `AQ50-002` | Multi-Policy | Hard | `01-returns`, `09-trailplus` | 5 | TrailPlus 45-day window vs outbound-only free shipping |
| `AQ50-003` | Multi-Policy | Hard | `03-final-sale`, `04-damaged` | 5 | Damaged bundle component exception to full bundle return |
| `AQ50-004` | Multi-Policy | Hard | `04-damaged`, `06-intl-shipping` | 4 | Canadian damaged item resolution; no direct exchanges |
| `AQ50-005` | Multi-Policy | Hard | `03-final-sale`, `07-warranty` | 4 | Final-sale items retain 2-year backpack defect warranty |
| `AQ50-006` | Multi-Policy | Hard | `01-returns`, `03-final-sale`, `10-gift-cards` | 4 | Gift cards cannot buy gift cards; non-refundable/no cash |
| `AQ50-007` | Multi-Policy | Hard | `07-warranty`, `11-product-care` | 5 | Machine washing prohibited; care guide conflict voids warranty |
| `AQ50-008` | Multi-Policy | Hard | `05-domestic-shipping` | 5 | Free shipping threshold ($75 after discounts); processing/delivery |
| `AQ50-009` | Multi-Policy | Hard | `08-order-changes` | 4 | Post-checkout item edit impossible; 30-min pending cancel |
| `AQ50-010` | Multi-Policy | Hard | `01-returns`, `10-gift-cards` | 5 | Price adjustment eligibility vs $6.95 return shipping deduction |
| `AQ50-011` | Conditional/Exception | Hard | `01-returns` | 4 | Indoor fit trial permitted; tags/condition requirements |
| `AQ50-012` | Conditional/Exception | Hard | `01-returns`, `03-final-sale` | 4 | Promotional discount code does not make item final sale |
| `AQ50-013` | Conditional/Exception | Hard | `04-damaged`, `07-warranty` | 4 | Reporting transit damage at 10 days exceeds 7-day limit |
| `AQ50-014` | Conditional/Exception | Hard | `01-returns`, `09-trailplus` | 3 | Joining TrailPlus after checkout does not extend past order window |
| `AQ50-015` | Conditional/Exception | Hard | `01-returns`, `04-damaged`, `09-trailplus` | 5 | Precise fee waiver conditions (wrong item / arrival defect only) |
| `AQ50-016` | Conditional/Exception | Hard | `10-gift-cards` | 4 | Flash sales explicitly excluded from 7-day price adjustments |
| `AQ50-017` | Conditional/Exception | Hard | `04-damaged` | 4 | Stockout handling on damaged items: refund/resolution without fee |
| `AQ50-018` | Conditional/Exception | Hard | `08-order-changes` | 4 | Address change requires both 30-min window AND pending status |
| `AQ50-019` | Conditional/Exception | Hard | `09-trailplus` | 4 | TrailPlus free shipping excludes expedited & Canadian delivery |
| `AQ50-020` | Conditional/Exception | Hard | `04-damaged` | 4 | Missing accessory qualifies as wrong/defective arrival within 7 days |
| `AQ50-021` | Date/Supersession | Very Hard | `02-returns-legacy` | 4 | Historical March 2026 order governed by legacy 45-day/free label |
| `AQ50-022` | Date/Supersession | Hard | `01-returns`, `02-returns-legacy` | 4 | Post-April 1, 2026 order rejects superseded legacy return rules |
| `AQ50-023` | Date/Supersession | Hard | `01-returns` | 4 | April 10 to May 8 = 28 days elapsed (within 30-day window) |
| `AQ50-024` | Date/Supersession | Hard | `07-warranty` | 4 | Backpack zipper failure at 22 months is within 2-year warranty |
| `AQ50-025` | Date/Supersession | Hard | `07-warranty` | 4 | Drinkware vacuum failure at 14 months exceeds 1-year warranty |
| `AQ50-026` | Date/Supersession | Hard | `01-returns` | 3 | Return window strictly begins on delivery date, not order date |
| `AQ50-027` | Date/Supersession | Hard | `10-gift-cards` | 3 | October 1 to October 10 = 9 days, exceeding 7-day adjustment limit |
| `AQ50-028` | Date/Supersession | Hard | `04-damaged` | 3 | Delivery on September 1 requires defect report by September 8 |
| `AQ50-029` | Multi-Part | Hard | `05-domestic-shipping` | 4 | Alaska shipping: $80 threshold (free), 1-2 days prep, 5-8 days transit |
| `AQ50-030` | Multi-Part | Hard | `01-returns`, `09-trailplus` | 4 | Standard vs TrailPlus windows (30 vs 45), fees ($6.95), refund (5-7d) |
| `AQ50-031` | Multi-Part | Hard | `07-warranty` | 4 | Durations for bags (2y), drinkware (1y), packing cubes (1y); no lifetime |
| `AQ50-032` | Multi-Part | Hard | `06-intl-shipping` | 4 | Canada orders: 1-2d processing, 5-9d transit, recipient pays duties |
| `AQ50-033` | Multi-Part | Hard | `08-order-changes` | 4 | Cancellation: 30 minutes, pending status only; quantity edit impossible |
| `AQ50-034` | Multi-Part | Hard | `11-product-care` | 5 | Cleaning: spot-clean bags, hand-wash cubes, top-rack dishwasher lid |
| `AQ50-035` | Multi-Part | Hard | `01-returns` | 4 | Item condition: unused, unwashed, resalable, original packaging/tags |
| `AQ50-036` | Multi-Part | Hard | `10-gift-cards` | 4 | Price adjustments: 7-day limit, 1 per purchase, clearance excluded |
| `AQ50-037` | Distinguishing Policies | Hard | `04-damaged`, `07-warranty` | 5 | Transit arrival damage (7 days, no fee) vs warranty (1-2y, defect only) |
| `AQ50-038` | Distinguishing Policies | Hard | `01-returns`, `08-order-changes` | 5 | Cancellation (30m, pending, $0) vs Return (30d, delivered, $6.95) |
| `AQ50-039` | Distinguishing Policies | Hard | `01-returns`, `06-intl-shipping` | 4 | Domestic return label ($6.95) vs Canadian return (customer pays carrier) |
| `AQ50-040` | Distinguishing Policies | Hard | `01-returns`, `03-final-sale` | 5 | Promotional coupon discount (returnable) vs Final Sale (non-returnable) |
| `AQ50-041` | Distinguishing Policies | Hard | `05-domestic-shipping`, `09-trailplus` | 3 | Domestic standard shipping: $75 spend for standard vs $0 for TrailPlus |
| `AQ50-042` | Distinguishing Policies | Hard | `01-returns`, `10-gift-cards` | 4 | Physical products (30d returnable) vs Gift Cards (final sale, no expiry) |
| `AQ50-043` | Distinguishing Policies | Hard | `08-order-changes` | 5 | Address change within 30m pending (support) vs post-dispatch (carrier) |
| `AQ50-044` | Precise Factual | Hard | `05-domestic-shipping` | 4 | US delivery estimates: contiguous (3-5d), AK/HI (5-8d), PO boxes (5-9d) |
| `AQ50-045` | Precise Factual | Hard | `01-returns` | 3 | Exact return shipping fee ($6.95) & post-inspection timeline (5-7d) |
| `AQ50-046` | Precise Factual | Hard | `05-domestic-shipping` | 3 | Free shipping threshold ($75): after discounts and before tax |
| `AQ50-047` | Precise Factual | Hard | `11-product-care`, `12-breeze-tumbler` | 5 | Breeze Tumbler limits: hot/cold only; no stove, oven, freezer, microwave |
| `AQ50-048` | Precise Factual | Hard | `07-warranty` | 5 | 8 specific exclusions from warranty (wear, accidents, improper care, etc.) |
| `AQ50-049` | Precise Factual | Hard | `06-intl-shipping` | 3 | Canadian exchange rules: direct exchanges prohibited; must return & reorder |
| `AQ50-050` | Precise Factual | Hard | `10-gift-cards` | 2 | Agent security restriction: must not ask for full gift card code in chat |

---

## 7. Remaining Limitations

1. **Deterministic Fallback Evaluation Constraint**: In fallback baseline mode, the local engine concatenates verbatim evidence passages up to 1,500 characters. Questions requiring synthesis of 3+ documents may experience chunk budget exhaustion if the retriever returns long context chunks.
2. **Date Parsing Dependency**: Scenarios testing elapsed time (e.g., `AQ50-023`, `AQ50-027`) require reasoning about calendar dates. Systems lacking arithmetic capabilities will struggle on elapsed day calculations even when the raw policy numbers (30 days, 7 days) are retrieved correctly.
3. **Retrieval Rank Sensitivity**: Because answers depend on multi-document cross-referencing (e.g. `AQ50-001` requiring `01-returns`, `03-final-sale`, and `04-damaged`), the evaluation depends heavily on hybrid retrieval ranking all relevant chunks in the top-k candidate set.
