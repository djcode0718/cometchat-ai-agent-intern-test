"""Tests for deterministic retrieval tokenizer."""

from src.retrieval.tokenizer import tokenize_text


def test_tokenizer_lowercasing_and_punctuation():
    tokens = tokenize_text("Returns Policy (2026 Edition): What is covered?")
    assert "returns" in tokens
    assert "policy" in tokens
    assert "2026" in tokens
    assert "covered" in tokens


def test_tokenizer_alphanumeric_identifiers():
    tokens = tokenize_text("Check order ORD-1007 and policy RET-2026-01.")
    assert "ord-1007" in tokens
    assert "ret-2026-01" in tokens


def test_tokenizer_hyphenated_terms():
    tokens = tokenize_text("Is this item final-sale or dishwasher-safe?")
    assert "final-sale" in tokens
    assert "final" in tokens
    assert "sale" in tokens
    assert "dishwasher-safe" in tokens
    assert "dishwasher" in tokens
    assert "safe" in tokens


def test_tokenizer_currency():
    tokens = tokenize_text("Free shipping on orders of $75 or more.")
    assert "$75" in tokens
    assert "shipping" in tokens


def test_tokenizer_empty_and_whitespace():
    assert tokenize_text("") == []
    assert tokenize_text("   \n\t  ") == []


def test_tokenizer_determinism():
    text = "TrailPlus membership return window is 45 calendar days."
    assert tokenize_text(text) == tokenize_text(text)
