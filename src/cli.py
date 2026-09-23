"""Interactive command-line interface for the Aster & Row AI support agent."""

import json
import os
import sys
import uuid
from typing import Any, Callable, Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()

from src.agent.orchestrator import AgentOrchestrator
from src.agent.state import PublicAgentResponse
from src.core.config import get_settings


class SupportCLI:
    """Production-quality interactive terminal interface for customer support."""

    def __init__(
        self,
        orchestrator: Optional[AgentOrchestrator] = None,
        input_fn: Callable[[str], str] = input,
        print_fn: Callable[..., None] = print,
    ) -> None:
        self.orchestrator = orchestrator or AgentOrchestrator()
        self.input_fn = input_fn
        self.print_fn = print_fn
        self.session_id = self._generate_session_id()
        self.last_trace: Optional[Dict[str, Any]] = None
        self.running = False

    @staticmethod
    def _generate_session_id() -> str:
        return f"cli-{uuid.uuid4().hex[:8]}"

    def print_banner(self) -> None:
        """Display clean startup banner and configuration summary."""
        settings = get_settings()
        primary_model = settings.groq_llm_model
        fallback_model = settings.groq_fallback_model

        self.print_fn("\n" + "=" * 62)
        self.print_fn(" Aster & Row — AI Customer Support Assistant")
        self.print_fn("=" * 62)
        self.print_fn(f"Session:        {self.session_id}")
        self.print_fn(f"Provider Chain: Groq ({primary_model}) → Groq ({fallback_model}) → Safe Fallback")
        self.print_fn("-" * 62)
        self.print_fn("Type your inquiry below or use slash commands:")
        self.print_fn("  /help   - View help & supported topics")
        self.print_fn("  /reset  - Start a new isolated conversation session")
        self.print_fn("  /trace  - Inspect safe observability trace of last turn")
        self.print_fn("  /exit   - Exit the CLI (also 'exit', 'quit', ':q')")
        self.print_fn("=" * 62 + "\n")

    def handle_help(self) -> None:
        """Display help information and operational capabilities."""
        self.print_fn("\n" + "-" * 50)
        self.print_fn("ASTER & ROW SUPPORT CLI — HELP")
        self.print_fn("-" * 50)
        self.print_fn("You can ask questions about:")
        self.print_fn("  • Return Policies (Standard 30-day window, TrailPlus 60-day window)")
        self.print_fn("  • Damaged / Defective Items & Final Sale Exceptions")
        self.print_fn("  • Warranty Coverage (Bags: 2 yrs, Drinkware: 1 yr)")
        self.print_fn("  • Shipping Destinations, Delivery Estimates & Fees")
        self.print_fn("  • Product Care & Material Guidelines")
        self.print_fn("  • Order Inquiries (e.g., 'Where is ORD-1001?', 'Can I cancel it?')")
        self.print_fn("\nAvailable Commands:")
        self.print_fn("  /help   - Show this help message")
        self.print_fn("  /reset  - Start a fresh session with cleared history")
        self.print_fn("  /trace  - View safe audit trace of previous response")
        self.print_fn("  /exit   - Quit the assistant")
        self.print_fn("-" * 50 + "\n")

    def handle_reset(self) -> None:
        """Reset session state and generate a fresh isolated session ID."""
        self.session_id = self._generate_session_id()
        self.last_trace = None
        self.print_fn(f"\n[Session reset. Started fresh isolated session: {self.session_id}]\n")

    def handle_trace(self) -> None:
        """Display the sanitized observability audit trace for the last turn."""
        if not self.last_trace:
            self.print_fn("\n[No trace available yet. Ask a question first to generate a trace.]\n")
            return

        self.print_fn("\n" + "-" * 50)
        self.print_fn("LAST TURN OBSERVABILITY TRACE (Sanitized Audit View)")
        self.print_fn("-" * 50)
        # Render clean indented JSON without PII or internal keys
        safe_trace_str = json.dumps(self.last_trace, indent=2)
        self.print_fn(safe_trace_str)
        self.print_fn("-" * 50 + "\n")

    def format_response(self, public_resp: PublicAgentResponse, safe_order: Optional[Dict[str, Any]]) -> str:
        """Format the public agent response for clean terminal rendering."""
        lines: List[str] = []

        # 1. Main assistant message
        lines.append(f"\nAssistant:\n{public_resp.message}")

        # 2. Customer-Safe Order Details if applicable
        if safe_order:
            lines.append("\nOrder Details:")
            lines.append(f"  • Order ID:           {safe_order.get('order_id')}")
            lines.append(f"  • Status:             {str(safe_order.get('status')).capitalize()}")
            if safe_order.get("carrier"):
                lines.append(f"  • Carrier:            {safe_order.get('carrier')}")
            if safe_order.get("tracking_number"):
                lines.append(f"  • Tracking Number:    {safe_order.get('tracking_number')}")
            if safe_order.get("estimated_delivery"):
                lines.append(f"  • Estimated Delivery: {safe_order.get('estimated_delivery')}")
            else:
                lines.append("  • Estimated Delivery: Unavailable")
            cancellable_str = "Eligible" if safe_order.get("is_cancellable") else "Ineligible"
            lines.append(f"  • Cancellation:       {cancellable_str}")

        # 3. Approved Citations if present
        if public_resp.citations:
            lines.append("\nSources:")
            for cit in public_resp.citations:
                lines.append(f"  • {cit}")

        # 4. Status Footer
        decision_str = public_resp.decision_state.value
        handoff_str = "Yes" if public_resp.handoff_recommended else "No"
        footer = f"\n[Decision: {decision_str} | Handoff: {handoff_str}"
        if public_resp.supported_action:
            footer += f" | Action: {public_resp.supported_action}"
        if public_resp.is_fallback:
            footer += " | Safe Fallback Used"
        footer += "]"
        lines.append(footer)

        if public_resp.handoff_recommended and public_resp.handoff_reason:
            lines.append(f"Handoff Reason: {public_resp.handoff_reason}")

        return "\n".join(lines) + "\n"

    def process_input(self, user_input: str) -> bool:
        """Process a single line of user input. Returns False if CLI should exit."""
        trimmed = user_input.strip()
        if not trimmed:
            return True

        # Check exit commands
        if trimmed.lower() in ("exit", "quit", ":q", "/exit"):
            self.print_fn("\nThank you for contacting Aster & Row. Goodbye!\n")
            return False

        # Check slash commands
        if trimmed.startswith("/"):
            cmd = trimmed.split()[0].lower()
            if cmd == "/help":
                self.handle_help()
            elif cmd == "/reset":
                self.handle_reset()
            elif cmd == "/trace":
                self.handle_trace()
            else:
                self.print_fn(f"\n[Unknown command '{cmd}'. Type /help for available commands.]\n")
            return True

        # Regular user query -> pass to orchestrator
        try:
            state = self.orchestrator.process_turn(self.session_id, trimmed)
            self.last_trace = state.trace
            public_resp = state.to_public_response()
            safe_order = state.trace.get("safe_order") if state.trace else None
            rendered = self.format_response(public_resp, safe_order)
            self.print_fn(rendered)
        except Exception:
            self.print_fn(
                "\nAssistant:\nSorry, I encountered an unexpected issue while processing your request. "
                "Please try again or contact customer support.\n"
            )

        return True

    def run(self) -> None:
        """Run interactive read-eval-print loop."""
        self.print_banner()
        self.running = True
        while self.running:
            try:
                user_input = self.input_fn("You: ")
                should_continue = self.process_input(user_input)
                if not should_continue:
                    self.running = False
            except (KeyboardInterrupt, EOFError):
                self.print_fn("\n\nSession terminated. Goodbye!\n")
                self.running = False


def main() -> None:
    """Main CLI entrypoint."""
    cli = SupportCLI()
    cli.run()


if __name__ == "__main__":
    main()
