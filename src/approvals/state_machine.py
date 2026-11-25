"""State machine specification and pure function transition table for HITL proposals."""

from enum import Enum
from typing import Dict, Set, Tuple

from src.approvals.models import ProposalStatus


class InvalidTransition(Exception):
    """Raised when an illegal state transition is attempted."""

    def __init__(self, from_state: ProposalStatus, to_state: ProposalStatus, reason: str = ""):
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(
            f"Invalid transition from {from_state.value} to {to_state.value}"
            + (f": {reason}" if reason else "")
        )


class ProposalEvent(str, Enum):
    """Events driving state machine transitions."""
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    EXPIRE = "EXPIRE"
    EXECUTE_SUCCESS = "EXECUTE_SUCCESS"
    EXECUTE_FAIL = "EXECUTE_FAIL"


# Pure transition mapping: (Current Status, Event) -> Target Status
TRANSITIONS: Dict[Tuple[ProposalStatus, ProposalEvent], ProposalStatus] = {
    (ProposalStatus.PENDING_APPROVAL, ProposalEvent.APPROVE): ProposalStatus.APPROVED,
    (ProposalStatus.PENDING_APPROVAL, ProposalEvent.REJECT): ProposalStatus.REJECTED,
    (ProposalStatus.PENDING_APPROVAL, ProposalEvent.EXPIRE): ProposalStatus.EXPIRED,
    (ProposalStatus.APPROVED, ProposalEvent.EXECUTE_SUCCESS): ProposalStatus.EXECUTED,
    (ProposalStatus.APPROVED, ProposalEvent.EXECUTE_FAIL): ProposalStatus.FAILED,
}

# Terminal states where no further events may be applied
TERMINAL_STATES: Set[ProposalStatus] = {
    ProposalStatus.REJECTED,
    ProposalStatus.EXPIRED,
    ProposalStatus.EXECUTED,
    ProposalStatus.FAILED,
}


def transition(current_status: ProposalStatus, event: ProposalEvent) -> ProposalStatus:
    """Pure transition function evaluating (current_status, event) -> next_status.

    Raises InvalidTransition if the transition is illegal or if current_status is terminal.
    """
    key = (current_status, event)
    if key in TRANSITIONS:
        return TRANSITIONS[key]

    raise InvalidTransition(
        from_state=current_status,
        to_state=ProposalStatus(event.value) if event.value in ProposalStatus._value2member_map_ else ProposalStatus.FAILED,
        reason=f"Event {event.value} is not permitted from state {current_status.value}",
    )


def is_terminal(status: ProposalStatus) -> bool:
    """Return True if status is a terminal state."""
    return status in TERMINAL_STATES
