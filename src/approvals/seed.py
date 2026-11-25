"""Database seed script for populating demo orders from data/demo_orders.json."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path

from src.approvals import get_engine, get_session_factory
from src.approvals.models import Base, OrderModel


def seed_database(demo_file_path: str = "data/demo_orders.json") -> int:
    """Read demo_orders.json and insert or update order rows."""
    file_path = Path(demo_file_path).resolve()
    if not file_path.exists():
        raise FileNotFoundError(f"Seed file not found: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    session_factory = get_session_factory()
    count = 0
    with session_factory() as session:
        for order_dict in data.get("orders", []):
            order_id = order_dict["order_id"]
            existing = session.query(OrderModel).filter(OrderModel.order_id == order_id).first()
            if not existing:
                created_dt = datetime.fromisoformat(order_dict["created_at"].replace("Z", "+00:00"))
                updated_dt = datetime.fromisoformat(order_dict["updated_at"].replace("Z", "+00:00"))
                raw_dict = dict(order_dict.get("raw_data", {}))
                if "status_updated_at" not in raw_dict:
                    raw_dict["status_updated_at"] = order_dict["updated_at"]
                if "placed_at" not in raw_dict:
                    raw_dict["placed_at"] = order_dict["created_at"]
                order_row = OrderModel(
                    order_id=order_id,
                    customer_id=order_dict["customer_id"],
                    status=order_dict["status"],
                    created_at=created_dt,
                    updated_at=updated_dt,
                    items=order_dict.get("items", []),
                    shipping_address=order_dict.get("shipping_address", {}),
                    raw_data=raw_dict,
                )
                session.add(order_row)
                count += 1
            else:
                existing.status = order_dict["status"]
                existing.items = order_dict.get("items", [])
                existing.shipping_address = order_dict.get("shipping_address", {})
                raw_dict = dict(order_dict.get("raw_data", {}))
                raw_dict["status"] = order_dict["status"]
                if "status_updated_at" not in raw_dict:
                    raw_dict["status_updated_at"] = order_dict["updated_at"]
                if "placed_at" not in raw_dict:
                    raw_dict["placed_at"] = order_dict["created_at"]
                existing.raw_data = raw_dict
                count += 1
        session.commit()
    print(f"Successfully seeded {count} orders into database.")
    return count


if __name__ == "__main__":
    seed_database()
