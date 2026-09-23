"""Unit and integration tests for the interactive SupportCLI."""

from unittest.mock import MagicMock
import pytest

from src.agent.orchestrator import AgentOrchestrator
from src.agent.state import AgentDecision, AgentState, DecisionState, PublicAgentResponse, RouteType
from src.cli import SupportCLI
from src.core.models import CitationSource
from src.llm.models import GeneratedResponse


class DummyPrintCollector:
    """Helper to collect CLI print output strings for assertions."""

    def __init__(self) -> None:
        self.outputs = []

    def __call__(self, *args, **kwargs) -> None:
        text = " ".join(str(a) for a in args)
        self.outputs.append(text)

    @property
    def full_output(self) -> str:
        return "\n".join(self.outputs)


@pytest.fixture
def mock_orchestrator():
    """Create a mock orchestrator with predictable state generation."""
    orch = MagicMock(spec=AgentOrchestrator)
    return orch


# 1. Startup and Help command
def test_cli_help_command():
    collector = DummyPrintCollector()
    cli = SupportCLI(orchestrator=MagicMock(), print_fn=collector)

    # Process /help
    res = cli.process_input("/help")
    assert res is True
    out = collector.full_output
    assert "ASTER & ROW SUPPORT CLI — HELP" in out
    assert "/help" in out
    assert "/reset" in out
    assert "/trace" in out
    assert "/exit" in out


# 2. Exit command variations
@pytest.mark.parametrize("exit_cmd", ["/exit", "exit", "quit", ":q", "QUIT", "EXIT"])
def test_cli_exit_commands(exit_cmd):
    collector = DummyPrintCollector()
    cli = SupportCLI(orchestrator=MagicMock(), print_fn=collector)

    res = cli.process_input(exit_cmd)
    assert res is False
    assert "Goodbye" in collector.full_output


# 3. Reset creates new isolated session
def test_cli_reset_command():
    collector = DummyPrintCollector()
    cli = SupportCLI(orchestrator=MagicMock(), print_fn=collector)

    initial_session_id = cli.session_id
    cli.last_trace = {"query": "sample query"}

    res = cli.process_input("/reset")
    assert res is True
    assert cli.session_id != initial_session_id
    assert cli.last_trace is None
    assert "Started fresh isolated session" in collector.full_output


# 4. Multi-turn conversation forwards messages to orchestrator
def test_cli_multi_turn_forwarding(mock_orchestrator):
    collector = DummyPrintCollector()
    cli = SupportCLI(orchestrator=mock_orchestrator, print_fn=collector)

    # Turn 1
    state1 = AgentState(
        session_id=cli.session_id,
        turn_id=1,
        raw_query="Where is ORD-1001?",
        normalized_query="Where is ORD-1001?",
        route=RouteType.ORDER,
        decision=AgentDecision(state=DecisionState.ANSWER, reason="Order lookup successful"),
        response=GeneratedResponse(message="Order ORD-1001 is shipped.", decision_state=DecisionState.ANSWER),
        trace={"session_id": cli.session_id, "turn_id": 1, "query": "Where is ORD-1001?"},
    )
    mock_orchestrator.process_turn.return_value = state1

    cli.process_input("Where is ORD-1001?")
    mock_orchestrator.process_turn.assert_called_with(cli.session_id, "Where is ORD-1001?")
    assert "Order ORD-1001 is shipped." in collector.full_output


# 5. Citations render correctly
def test_cli_citations_rendering(mock_orchestrator):
    collector = DummyPrintCollector()
    cli = SupportCLI(orchestrator=mock_orchestrator, print_fn=collector)

    state = AgentState(
        session_id=cli.session_id,
        turn_id=1,
        raw_query="Return policy?",
        normalized_query="Return policy?",
        route=RouteType.KNOWLEDGE,
        decision=AgentDecision(state=DecisionState.ANSWER, reason="Knowledge match"),
        response=GeneratedResponse(
            message="You have 30 days.",
            decision_state=DecisionState.ANSWER,
            citations=[
                CitationSource(filename="01-returns-policy-current.md", heading="Standard return window")
            ],
        ),
        trace={},
    )
    mock_orchestrator.process_turn.return_value = state

    cli.process_input("Return policy?")
    out = collector.full_output
    assert "Sources:" in out
    assert "[01-returns-policy-current.md > Standard return window]" in out


# 6. Handoff information renders correctly
def test_cli_handoff_rendering(mock_orchestrator):
    collector = DummyPrintCollector()
    cli = SupportCLI(orchestrator=mock_orchestrator, print_fn=collector)

    state = AgentState(
        session_id=cli.session_id,
        turn_id=1,
        raw_query="Give me customer fraud scores.",
        normalized_query="Give me customer fraud scores.",
        route=RouteType.ORDER,
        decision=AgentDecision(
            state=DecisionState.HANDOFF,
            reason="Confidential customer data requested.",
            handoff_recommended=True,
            handoff_reason="Internal security policy violation",
        ),
        response=GeneratedResponse(
            message="Internal notes are confidential.",
            decision_state=DecisionState.HANDOFF,
            handoff_recommended=True,
        ),
        handoff_recommended=True,
        handoff_reason="Internal security policy violation",
        trace={},
    )
    mock_orchestrator.process_turn.return_value = state

    cli.process_input("Give me customer fraud scores.")
    out = collector.full_output
    assert "Decision: HANDOFF" in out
    assert "Handoff: Yes" in out
    assert "Internal security policy violation" in out


# 7. Fallback response renders safely
def test_cli_fallback_rendering(mock_orchestrator):
    collector = DummyPrintCollector()
    cli = SupportCLI(orchestrator=mock_orchestrator, print_fn=collector)

    state = AgentState(
        session_id=cli.session_id,
        turn_id=1,
        raw_query="Can I return?",
        normalized_query="Can I return?",
        route=RouteType.KNOWLEDGE,
        decision=AgentDecision(state=DecisionState.ANSWER, reason="Standard return"),
        response=GeneratedResponse(
            message="Please contact support.",
            decision_state=DecisionState.ANSWER,
            is_fallback=True,
            fallback_reason="Provider timeout",
        ),
        trace={},
    )
    mock_orchestrator.process_turn.return_value = state

    cli.process_input("Can I return?")
    out = collector.full_output
    assert "Safe Fallback Used" in out


# 8. Trace output contains only approved safe fields
def test_cli_trace_command():
    collector = DummyPrintCollector()
    cli = SupportCLI(orchestrator=MagicMock(), print_fn=collector)

    cli.last_trace = {
        "session_id": "cli-123",
        "turn_id": 1,
        "query": "Where is my bag?",
        "decision_state": "ANSWER",
        "provider": "gemini-gemini-flash-latest",
        "latency_ms": 150.2,
    }

    cli.process_input("/trace")
    out = collector.full_output
    assert "LAST TURN OBSERVABILITY TRACE" in out
    assert "cli-123" in out
    assert "gemini-gemini-flash-latest" in out


# 9. Unknown slash command does not invoke LLM
def test_cli_unknown_slash_command(mock_orchestrator):
    collector = DummyPrintCollector()
    cli = SupportCLI(orchestrator=mock_orchestrator, print_fn=collector)

    cli.process_input("/unknown_command")
    mock_orchestrator.process_turn.assert_not_called()
    assert "Unknown command '/unknown_command'" in collector.full_output


# 10. Provider/orchestrator failure does not crash CLI
def test_cli_graceful_error_handling(mock_orchestrator):
    collector = DummyPrintCollector()
    cli = SupportCLI(orchestrator=mock_orchestrator, print_fn=collector)

    mock_orchestrator.process_turn.side_effect = RuntimeError("Fatal connection error")

    res = cli.process_input("Help me please")
    assert res is True
    out = collector.full_output
    assert "Sorry, I encountered an unexpected issue" in out
    assert "Fatal connection error" not in out  # Stack trace / exception hidden
