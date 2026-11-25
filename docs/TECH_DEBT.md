# Aster & Row — Technical Debt & Static Analysis Audit

This document catalogs findings identified by static analysis tools (`ruff` and `mypy`) across `src/` and `tests/`. In accordance with project engineering principles, trivial formatting was safely resolved, while non-trivial typing, syntax migrations, and import restructurings are logged here rather than silently modified.

---

## 1. Mypy Type Checking Findings (16 Errors across 7 Files)

Mypy configuration: `python_version = "3.11"`, `disallow_untyped_defs = false`, `ignore_missing_imports = true`.

| File | Line | Error Code | Description / Analysis |
| :--- | :--- | :--- | :--- |
| `src/core/config.py` | 108 | `[assignment]` | Incompatible types in assignment: `os.getenv("GEMINI_LLM_MODEL")` evaluates to `str | None`, whereas Pydantic field expects `str`. Default fallback logic should coalesce explicitly with empty string or default model. |
| `src/core/config.py` | 114 | `[assignment]` | Incompatible types in assignment: `os.getenv("GROQ_LLM_MODEL")` evaluates to `str | None`. |
| `src/core/config.py` | 117 | `[assignment]` | Incompatible types in assignment: `os.getenv("GROQ_FALLBACK_MODEL")` evaluates to `str | None`. |
| `src/core/config.py` | 120 | `[assignment]` | Incompatible types in assignment: `os.getenv("GROQ_BASE_URL")` evaluates to `str | None`. |
| `src/llm/provider.py` | 24 | `[assignment]` | Incompatible types in assignment: `api_key` can be `None`. |
| `src/llm/provider.py` | 56 | `[union-attr]` | Item `None` of `str | None` has no attribute `rstrip` on base URL normalization. |
| `src/llm/openrouter.py` | 43 | `[assignment]` | Incompatible types in assignment: `base_url` parameter typed as `str` but default can be `None`. |
| `src/llm/openrouter.py` | 49 | `[union-attr]` | Item `None` of `str | None` has no attribute `rstrip`. |
| `src/llm/grok.py` | 29 | `[assignment]` | Incompatible types in assignment: `base_url` can receive `None`. |
| `src/llm/grok.py` | 40 | `[union-attr]` | Item `None` of `str | None` has no attribute `rstrip`. |
| `src/llm/gemini.py` | 29 | `[assignment]` | Incompatible types in assignment: `base_url` can receive `None`. |
| `src/llm/gemini.py` | 39 | `[union-attr]` | Item `None` of `str | None` has no attribute `rstrip`. |
| `src/llm/gemini.py` | 48 | `[union-attr]` | Item `None` of `str | None` has no attribute `removeprefix`. |
| `src/llm/gemini.py` | 61 | `[union-attr]` | Item `None` of `str | None` has no attribute `startswith`. |
| `src/llm/openrouter_chain.py` | 85 | `[arg-type]` | Argument 1 to `append` has incompatible type `tuple[str, BaseLLMProvider, Any | str]`; expected `tuple[str, OpenRouterLLMProvider, str]`. |
| `src/llm/factory.py` | 29 | `[union-attr]` | Item `None` of `str | None` has no attribute `lower` on `provider_name`. |

---

## 2. Ruff Linter Findings (Non-Trivial Backlog)

| Rule Category | Count | Description / Recommendation |
| :--- | :--- | :--- |
| `UP045` (`non-pep604-annotation-optional`) | 157 | Migrate `Optional[X]` to Python 3.10+ `X | None`. (Retained for backwards compatibility across Pydantic v2 schemas). |
| `UP006` (`non-pep585-annotation`) | 143 | Migrate `typing.List` / `typing.Dict` to built-in `list` / `dict`. |
| `UP035` (`deprecated-import`) | 61 | Deprecated `typing` imports to be modernized gradually. |
| `F401` (`unused-import`) | 64 | Unused imports in test suites and factory dispatchers. |
| `I001` (`unsorted-imports`) | 33 | Import ordering across modules; should be run with automated isort pass during scheduled refactoring. |
| `E402` (`module-import-not-at-top-of-file`) | 12 | Late imports in `api.py` and test harnesses used intentionally to load `dotenv` and monkeypatch environments before module initialization. |
| `B905` (`zip-without-explicit-strict`) | 8 | `zip()` calls without `strict=True`. |
| `UP042` (`replace-str-enum`) | 4 | Migrate legacy `(str, Enum)` inheritance to `StrEnum`. |
