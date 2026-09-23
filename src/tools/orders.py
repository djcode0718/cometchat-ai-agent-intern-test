"""Deterministic order repository for loading, looking up, and sanitizing order data."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Union

from src.core.config import Settings, get_settings
from src.tools.exceptions import (
    InvalidOrderIDError,
    OrderDataError,
    OrderNotFoundError,
)
from src.tools.normalizer import extract_candidate_order_id, normalize_order_id
from src.tools.order_models import (
    CustomerSafeOrder,
    OrderDatasetSnapshot,
    RawOrder,
)
from src.tools.reconciler import StatusReconciler


class OrderRepository:
    """In-memory repository managing orders and deterministic customer-safe lookups."""

    def __init__(self, data_file_path: Optional[Union[str, Path]] = None) -> None:
        if data_file_path is not None:
            self._file_path = Path(data_file_path).resolve()
        else:
            settings: Settings = get_settings()
            self._file_path = settings.orders_file_path

        self._dataset_name: str = ""
        self._snapshot_at: str = ""
        self._raw_orders: Dict[str, RawOrder] = {}
        self._load_dataset()

    @property
    def snapshot_at(self) -> str:
        """Timestamp when the dataset snapshot was generated."""
        return self._snapshot_at

    @property
    def dataset_name(self) -> str:
        """Name of the dataset snapshot."""
        return self._dataset_name

    def _load_dataset(self) -> None:
        """Load and parse orders JSON dataset into typed internal models."""
        if not self._file_path.exists() or not self._file_path.is_file():
            raise OrderDataError(f"Orders dataset file not found: {self._file_path}")

        try:
            content = self._file_path.read_text(encoding="utf-8")
            data = json.loads(content)
        except Exception as e:
            raise OrderDataError(f"Failed to read or parse orders JSON: {e}") from e

        try:
            snapshot = OrderDatasetSnapshot(**data)
            self._dataset_name = snapshot.dataset_name
            self._snapshot_at = snapshot.snapshot_at
            self._raw_orders = {order.order_id: order for order in snapshot.orders}
        except Exception as e:
            raise OrderDataError(f"Schema validation error in orders dataset: {e}") from e

    def has_order(self, order_id_input: str) -> bool:
        """Check if a candidate order ID exists in the repository."""
        canonical_id = normalize_order_id(order_id_input)
        if not canonical_id:
            return False
        return canonical_id in self._raw_orders

    def list_order_ids(self) -> List[str]:
        """Return a sorted list of all available order IDs."""
        return sorted(list(self._raw_orders.keys()))

    def lookup_order(self, query_or_id: str) -> Optional[CustomerSafeOrder]:
        """Look up an order by ID or text containing an ID.

        Returns a sanitized, reconciled CustomerSafeOrder instance, or None if:
        1. No valid order ID could be extracted/normalized.
        2. The order ID is not present in the dataset.
        """
        canonical_id = normalize_order_id(query_or_id)
        if not canonical_id or canonical_id not in self._raw_orders:
            return None

        raw_order = self._raw_orders[canonical_id]
        return StatusReconciler.reconcile(raw_order, snapshot_time_str=self._snapshot_at)

    def get_safe_order(self, order_id_input: str) -> CustomerSafeOrder:
        """Look up order and return CustomerSafeOrder, raising typed exceptions on error."""
        canonical_id = normalize_order_id(order_id_input)
        if not canonical_id:
            raise InvalidOrderIDError(order_id_input)

        if canonical_id not in self._raw_orders:
            raise OrderNotFoundError(canonical_id)

        raw_order = self._raw_orders[canonical_id]
        return StatusReconciler.reconcile(raw_order, snapshot_time_str=self._snapshot_at)


@lru_cache(maxsize=1)
def get_order_repository() -> OrderRepository:
    """Return cached singleton OrderRepository instance."""
    return OrderRepository()
