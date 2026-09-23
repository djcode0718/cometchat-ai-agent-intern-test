"""Exceptions for order lookup, normalization, and data processing."""


class OrderError(Exception):
    """Base exception for all order-related errors."""


class OrderNotFoundError(OrderError):
    """Raised when an order ID is not found in the repository."""

    def __init__(self, order_id: str) -> None:
        super().__init__(f"Order not found: {order_id}")
        self.order_id = order_id


class InvalidOrderIDError(OrderError):
    """Raised when a candidate order ID fails validation."""

    def __init__(self, raw_input: str) -> None:
        super().__init__(f"Invalid order ID format: {raw_input!r}")
        self.raw_input = raw_input


class OrderDataError(OrderError):
    """Raised when order data file cannot be read or is malformed."""
