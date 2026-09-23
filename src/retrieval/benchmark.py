"""Benchmark dataset and runner for evaluating and comparing retrieval strategies."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from src.retrieval.base import BaseRetriever
from src.retrieval.metrics import hit_at_k, precision_at_k, reciprocal_rank
from src.retrieval.models import RetrievalResult


class BenchmarkCase(BaseModel):
    """A single retrieval benchmark query with explicit ground truth target documents."""

    id: str = Field(..., description="Unique case identifier")
    query: str = Field(..., description="User search query")
    category: str = Field(..., description="Topic category")
    expected_targets: List[str] = Field(
        ..., description="List of expected relevant document filenames or IDs"
    )
    description: Optional[str] = Field(
        default=None, description="Explanation of what this case tests"
    )


# Curated benchmark dataset derived from Aster & Row knowledge base & requirements
DEFAULT_BENCHMARK_CASES: List[BenchmarkCase] = [
    BenchmarkCase(
        id="case_01_standard_return",
        query="How long do I have to return an unused backpack as a regular customer?",
        category="returns",
        expected_targets=["01-returns-policy-current.md", "RET-2026-01"],
        description="Standard 30-day return policy retrieval",
    ),
    BenchmarkCase(
        id="case_02_trailplus_returns",
        query="What is the return window for active TrailPlus members?",
        category="membership",
        expected_targets=["09-trailplus-membership.md", "MEM-2026-01"],
        description="TrailPlus 45-day member return policy",
    ),
    BenchmarkCase(
        id="case_03_final_sale_damage",
        query="Can I return a final sale item that arrived damaged?",
        category="final-sale",
        expected_targets=["03-final-sale-and-promotions.md", "04-damaged-or-wrong-items.md", "RET-2026-02", "OPS-2026-04"],
        description="Final sale damage exception",
    ),
    BenchmarkCase(
        id="case_04_us_shipping_rates",
        query="How much do I need to spend for free standard shipping in the US?",
        category="shipping",
        expected_targets=["05-domestic-shipping.md", "SHIP-2026-US"],
        description="Domestic free shipping threshold ($75)",
    ),
    BenchmarkCase(
        id="case_05_canada_shipping",
        query="Do you ship to Canada and how long does delivery take?",
        category="international",
        expected_targets=["06-international-shipping.md", "SHIP-2026-INTL"],
        description="Canada international shipping time (5-9 days)",
    ),
    BenchmarkCase(
        id="case_06_warranty_periods",
        query="What is the warranty coverage period on Aster & Row backpacks versus drinkware?",
        category="warranty",
        expected_targets=["07-warranty.md", "WAR-2026-01"],
        description="Warranty periods (2 years bags, 1 year drinkware)",
    ),
    BenchmarkCase(
        id="case_07_cancellation_window",
        query="Can I cancel my order within 30 minutes of placing it?",
        category="cancellations",
        expected_targets=["08-order-changes-and-cancellations.md", "ORD-2026-01"],
        description="30-minute cancellation rule for pending orders",
    ),
    BenchmarkCase(
        id="case_08_price_adjustment",
        query="Do you offer price adjustments if an item goes on sale after I bought it?",
        category="pricing",
        expected_targets=["10-gift-cards-and-price-adjustments.md", "PAY-2026-03"],
        description="7-day price adjustment policy",
    ),
    BenchmarkCase(
        id="case_09_tumbler_care",
        query="How should I clean my stainless steel Breeze Tumbler?",
        category="product-care",
        expected_targets=["11-product-care.md", "12-breeze-tumbler-product-card.md", "CARE-2026-01", "PROD-BREEZE-20"],
        description="Breeze tumbler cleaning and dishwasher instructions",
    ),
    BenchmarkCase(
        id="case_10_unsupported_germany",
        query="Can you ship an order to Germany or Europe?",
        category="international",
        expected_targets=["06-international-shipping.md", "SHIP-2026-INTL"],
        description="International shipping destinations (Canada only)",
    ),
    BenchmarkCase(
        id="case_11_damaged_arrival_window",
        query="How many days do I have to report an item that arrived broken?",
        category="damages",
        expected_targets=["04-damaged-or-wrong-items.md", "OPS-2026-04"],
        description="7-day damage reporting window",
    ),
    BenchmarkCase(
        id="case_12_gift_card_expiry",
        query="Do Aster & Row gift cards expire or can they be refunded?",
        category="gift-cards",
        expected_targets=["10-gift-cards-and-price-adjustments.md", "PAY-2026-03"],
        description="Gift card final sale and non-expiration policy",
    ),
]


class BenchmarkQueryResult(BaseModel):
    """Evaluation result of a single query under a specific retrieval strategy."""

    case_id: str
    query: str
    strategy: str
    hit_at_k: float
    reciprocal_rank: float
    precision_at_k: float
    top_results: List[RetrievalResult]


class StrategyBenchmarkMetrics(BaseModel):
    """Aggregated retrieval evaluation metrics for a single strategy."""

    strategy: str
    total_queries: int
    top_k: int
    hit_at_k: float = Field(..., description="Mean Hit@K (0.0 to 1.0)")
    mrr: float = Field(..., description="Mean Reciprocal Rank (0.0 to 1.0)")
    precision_at_k: float = Field(..., description="Mean Precision@K (0.0 to 1.0)")
    query_results: List[BenchmarkQueryResult] = Field(default_factory=list)

    def summary_row(self) -> Dict[str, Any]:
        return {
            "Strategy": self.strategy.upper(),
            "Queries": self.total_queries,
            "Top-K": self.top_k,
            f"Hit@{self.top_k}": f"{self.hit_at_k * 100:.1f}%",
            "MRR": f"{self.mrr:.4f}",
            f"Precision@{self.top_k}": f"{self.precision_at_k * 100:.1f}%",
        }


def evaluate_retriever(
    retriever: BaseRetriever,
    cases: List[BenchmarkCase],
    top_k: int = 5,
) -> StrategyBenchmarkMetrics:
    """Evaluate a single retriever against a list of benchmark cases."""
    if not cases:
        return StrategyBenchmarkMetrics(
            strategy=retriever.strategy_name,
            total_queries=0,
            top_k=top_k,
            hit_at_k=0.0,
            mrr=0.0,
            precision_at_k=0.0,
        )

    query_results: List[BenchmarkQueryResult] = []
    hit_scores: List[float] = []
    mrr_scores: List[float] = []
    precision_scores: List[float] = []

    for case in cases:
        results = retriever.retrieve(query=case.query, top_k=top_k)
        h_score = hit_at_k(results, case.expected_targets, k=top_k)
        rr_score = reciprocal_rank(results, case.expected_targets)
        p_score = precision_at_k(results, case.expected_targets, k=top_k)

        hit_scores.append(h_score)
        mrr_scores.append(rr_score)
        precision_scores.append(p_score)

        query_results.append(
            BenchmarkQueryResult(
                case_id=case.id,
                query=case.query,
                strategy=retriever.strategy_name,
                hit_at_k=h_score,
                reciprocal_rank=rr_score,
                precision_at_k=p_score,
                top_results=results,
            )
        )

    return StrategyBenchmarkMetrics(
        strategy=retriever.strategy_name,
        total_queries=len(cases),
        top_k=top_k,
        hit_at_k=sum(hit_scores) / len(hit_scores),
        mrr=sum(mrr_scores) / len(mrr_scores),
        precision_at_k=sum(precision_scores) / len(precision_scores),
        query_results=query_results,
    )


def run_retrieval_benchmark(
    retrievers: Dict[str, BaseRetriever],
    cases: Optional[List[BenchmarkCase]] = None,
    top_k: int = 5,
) -> Dict[str, StrategyBenchmarkMetrics]:
    """Execute evaluation across multiple retrieval strategies using the same benchmark cases."""
    benchmark_cases = cases or DEFAULT_BENCHMARK_CASES
    results: Dict[str, StrategyBenchmarkMetrics] = {}

    for name, retriever in retrievers.items():
        results[name] = evaluate_retriever(retriever, benchmark_cases, top_k=top_k)

    return results


def format_benchmark_table(metrics: Dict[str, StrategyBenchmarkMetrics]) -> str:
    """Format benchmark metrics into a clean markdown table."""
    header = "| Strategy | Queries | Top-K | Hit@K | MRR | Precision@K |\n|---|---:|---:|---:|---:|---:|"
    rows = []
    for metric in metrics.values():
        row = metric.summary_row()
        top_k_val = row["Top-K"]
        hit_val = row[f"Hit@{top_k_val}"]
        mrr_val = row["MRR"]
        prec_val = row[f"Precision@{top_k_val}"]
        rows.append(
            f"| {row['Strategy']} | {row['Queries']} | {top_k_val} | {hit_val} | {mrr_val} | {prec_val} |"
        )
    return "\n".join([header] + rows)
