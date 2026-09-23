"""Tests for order repository, order ID normalization, and lookup behavior."""

import pytest

from src.tools.exceptions import InvalidOrderIDError, OrderNotFoundError
from src.tools.normalizer import extract_candidate_order_id, normalize_order_id
from src.tools.order_models import CustomerSafeOrder
from src.tools.orders import OrderRepository, get_order_repository


def test_order_id_normalization_variations():
    # Canonical
    assert normalize_order_id("ORD-1001") == "ORD-1001"
    # Lowercase
    assert normalize_order_id("ord-1001") == "ORD-1001"
    # Mixed case and quotes
    assert normalize_order_id('"ord-1007"') == "ORD-1007"
    assert normalize_order_id("'ORD-1003'") == "ORD-1003"
    # Surrounded by whitespace and punctuation
    assert normalize_order_id("  ord-1005.  ") == "ORD-1005"
    assert normalize_order_id("ORD-1004!") == "ORD-1004"


def test_order_id_extraction_from_sentences():
    assert extract_candidate_order_id("Where is ORD-1007 and when should it arrive?") == "ORD-1007"
    assert extract_candidate_order_id("When will order ord-1004 arrive?") == "ORD-1004"
    assert extract_candidate_order_id("Please check ORD-9999.") == "ORD-9999"


def test_order_id_rejection_of_invalid_inputs():
    # Arbitrary raw numbers must not be treated as valid order IDs
    assert normalize_order_id("1001") is None
    assert normalize_order_id("order 1001") is None
    assert extract_candidate_order_id("1001") is None
    assert extract_candidate_order_id("Where is my order?") is None
    assert normalize_order_id("") is None
    assert normalize_order_id(None) is None


def test_order_lookup_valid():
    repo = get_order_repository()
    order = repo.lookup_order("ORD-1001")

    assert order is not None
    assert isinstance(order, CustomerSafeOrder)
    assert order.order_id == "ORD-1001"
    assert order.membership_tier == "standard"
    assert len(order.items) == 1
    assert order.items[0].name == "Ridge Daypack"


def test_order_lookup_case_insensitive_and_phrasing():
    repo = get_order_repository()

    order_lower = repo.lookup_order("ord-1007")
    assert order_lower is not None
    assert order_lower.order_id == "ORD-1007"

    order_sentence = repo.lookup_order("Where is ord-1007 right now?")
    assert order_sentence is not None
    assert order_sentence.order_id == "ORD-1007"


def test_order_lookup_unknown_order():
    repo = get_order_repository()

    # lookup_order returns None for unknown
    assert repo.lookup_order("ORD-9999") is None
    assert repo.has_order("ORD-9999") is False

    # get_safe_order raises typed exception
    with pytest.raises(OrderNotFoundError) as exc_info:
        repo.get_safe_order("ORD-9999")
    assert exc_info.value.order_id == "ORD-9999"


def test_order_lookup_invalid_id_raises():
    repo = get_order_repository()
    with pytest.raises(InvalidOrderIDError):
        repo.get_safe_order("not_an_order")


def test_order_lookup_missing_or_empty():
    repo = get_order_repository()
    assert repo.lookup_order("") is None
    assert repo.lookup_order("Where is my order?") is None


def test_repository_dataset_metadata():
    repo = get_order_repository()
    assert "Aster & Row" in repo.dataset_name
    assert repo.snapshot_at == "2026-08-15T12:00:00Z"
    assert len(repo.list_order_ids()) == 12


def test_repository_isolation_from_mutations():
    repo = get_order_repository()
    order1 = repo.lookup_order("ORD-1001")
    assert order1 is not None

    # Mutate the returned object
    order1.membership_tier = "MUTATED_TIER"
    order1.items.clear()

    # Subsequent lookup should remain uncorrupted
    order2 = repo.lookup_order("ORD-1001")
    assert order2 is not None
    assert order2.membership_tier == "standard"
    assert len(order2.items) == 1


def test_order_lookup_determinism():
    repo = get_order_repository()
    order_a = repo.lookup_order("ORD-1007")
    order_b = repo.lookup_order("ORD-1007")

    assert order_a is not None and order_b is not None
    assert order_a.model_dump() == order_b.model_dump()
