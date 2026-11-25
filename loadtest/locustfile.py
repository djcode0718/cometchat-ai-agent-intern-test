"""Locust load test script simulating customer support interactions with weighted user journeys."""

import random
from locust import HttpUser, between, task


class CustomerSupportUser(HttpUser):
    """Simulates customer support user traffic across knowledge, order, and multi-turn inquiries."""

    wait_time = between(0.1, 0.5)

    def on_start(self) -> None:
        """Initialize user session."""
        self.session_id = f"locust-user-{random.randint(10000, 99999)}"

    @task(4)
    def ask_knowledge_question(self) -> None:
        """Weighted task (40%): Common knowledge inquiries."""
        queries = [
            "What is your return policy?",
            "How long do TrailPlus members have to return items?",
            "What is the warranty period for backpacks?",
            "How much is standard domestic shipping?",
            "Do you ship internationally to Canada?",
            "How do I clean my Breeze Tumbler?",
        ]
        q = random.choice(queries)
        self.client.post(
            "/chat",
            json={"session_id": self.session_id, "message": q},
            name="/chat [knowledge]",
        )

    @task(3)
    def lookup_order_status(self) -> None:
        """Weighted task (30%): Order status inquiries."""
        order_ids = ["ORD-1001", "ORD-1002", "ORD-1003", "ORD-1005", "ORD-1007"]
        order_id = random.choice(order_ids)
        self.client.post(
            "/chat",
            json={"session_id": self.session_id, "message": f"Where is my order {order_id}?"},
            name="/chat [order_lookup]",
        )

    @task(2)
    def multi_turn_followup(self) -> None:
        """Weighted task (20%): Contextual follow-up queries."""
        # 1. Order lookup
        self.client.post(
            "/chat",
            json={"session_id": self.session_id, "message": "Can you check ORD-1007?"},
            name="/chat [multiturn_turn1]",
        )
        # 2. Follow-up inquiry
        self.client.post(
            "/chat",
            json={"session_id": self.session_id, "message": "Can I cancel it?"},
            name="/chat [multiturn_turn2]",
        )

    @task(1)
    def unknown_order_or_unanswerable(self) -> None:
        """Weighted task (10%): Unknown order or unanswerable question triggering safe handoff."""
        queries = [
            "What is the status of ORD-9999?",
            "Do you sell vegan leather jackets?",
        ]
        q = random.choice(queries)
        self.client.post(
            "/chat",
            json={"session_id": self.session_id, "message": q},
            name="/chat [edge_cases]",
        )
