"""SQL-backed OrderRepository conforming to the exact public interface of OrderRepository."""

import json
from typing import Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.approvals.models import OrderModel
from src.tools.exceptions import (
    InvalidOrderIDError,
    OrderNotFoundError,
)
from src.tools.normalizer import normalize_order_id
from src.tools.order_models import CustomerSafeOrder, RawOrder
from src.tools.reconciler import StatusReconciler


class SqlOrderRepository:
    """SQL-backed order repository matching OrderRepository interface."""

    def __init__(self, session_factory, snapshot_at: Optional[str] = None) -> None:
        self._session_factory = session_factory
        self._snapshot_at = snapshot_at or "2026-03-01T12:00:00Z"
        self._dataset_name = "sql_orders_store"

    @property
    def snapshot_at(self) -> str:
        return self._snapshot_at

    @property
    def dataset_name(self) -> str:
        return self._dataset_name

    def has_order(self, order_id_input: str) -> bool:
        canonical_id = normalize_order_id(order_id_input)
        if not canonical_id:
            return False
        with self._session_factory() as session:
            stmt = select(OrderModel.order_id).where(OrderModel.order_id == canonical_id)
            return session.scalar(stmt) is not None

    def list_order_ids(self) -> List[str]:
        with self._session_factory() as session:
            stmt = select(OrderModel.order_id).order_by(OrderModel.order_id)
            return list(session.scalars(stmt).all())

    def _get_raw_order(self, canonical_id: str) -> Optional[RawOrder]:
        with self._session_factory() as session:
            stmt = select(OrderModel).where(OrderModel.order_id == canonical_id)
            order_row = session.scalar(stmt)
            if not order_row:
                return None
            
            raw_dict = order_row.raw_data or {}
            # Ensure database fields are reflected
            raw_dict["order_id"] = order_row.order_id
            raw_dict["customer_id"] = order_row.customer_id
            raw_dict["status"] = order_row.status
            if order_row.items:
                raw_dict["items"] = order_row.items
            if order_row.shipping_address:
                raw_dict["shipping_address"] = order_row.shipping_address
            return RawOrder(**raw_dict)

    def lookup_order(self, query_or_id: str) -> Optional[CustomerSafeOrder]:
        canonical_id = normalize_order_id(query_or_id)
        if not canonical_id:
            return None
        raw_order = self._get_raw_order(canonical_id)
        if not raw_order:
            return None
        return StatusReconciler.reconcile(raw_order, snapshot_time_str=self._snapshot_at)

    def get_safe_order(self, order_id_input: str) -> CustomerSafeOrder:
        canonical_id = normalize_order_id(order_id_input)
        if not canonical_id:
            raise InvalidOrderIDError(order_id_input)
        raw_order = self._get_raw_order(canonical_id)
        if not raw_order:
            raise OrderNotFoundError(canonical_id)
        return StatusReconciler.reconcile(raw_order, snapshot_time_str=self._snapshot_at)
