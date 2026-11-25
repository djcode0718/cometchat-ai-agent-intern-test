# Architecture and End-to-End Data Flow Specification

**Evaluation Artifact**: `evaluation/complete_customer_journey_2026_11_26/ARCHITECTURE_AND_DATA_FLOW.md`  
**System**: Aster & Row Customer Support System  
**Commit**: `663f5bbf50e42b90b497240ec466b4e74b19ec8a`

---

## 1. High-Level System Architecture

Aster & Row implements a deterministic-first customer service architecture. The generative LLM is restricted to phrasing policy answers and summarizing factual evidence. Business policies, state transitions, authentication, and database mutations are strictly decoupled and governed by Python state machines.

```mermaid
graph TD
    subgraph Frontend [React 18 / TypeScript / Vite]
        CV["Customer View (/)\nrole='log', aria-live, status card"]
        RC["Reviewer Console (/reviewer)\nFocus Trap, X-Reviewer-Key in memory"]
    end

    subgraph API [FastAPI Gateway]
        MW["Middleware\n(Correlation ID, RateLimiter, RequestSizeLimit)"]
        ChatEP["POST /chat"]
        PollEP["GET /sessions/{id}/proposal"]
        RevListEP["GET /reviewer/proposals"]
        RevDetailEP["GET /reviewer/proposals/{id}"]
        RevApprEP["POST /reviewer/proposals/{id}/approve"]
        RevRejEP["POST /reviewer/proposals/{id}/reject"]
        AuditEP["GET /reviewer/audit"]
        TraceEP["GET /sessions/{id}/trace"]
        PromEP["GET /metrics"]
    end

    subgraph Agent [Orchestrator & Intelligence Pipeline]
        SG["Pre-Retrieval Input Guard\n(Regex pattern neutralization)"]
        Router["Deterministic Regex Router\n(KNOWLEDGE, ORDER, ACTION, UNSUPPORTED)"]
        Retriever["Policy Retriever\n(SentenceTransformers MiniLM-L6)"]
        Resolver["Knowledge Resolver\n(Grounding & Chunk Selection)"]
        LLM["LLM Generation Layer\n(Mock / Ollama llama3.1:8b / Groq)"]
        Validator["OutputValidator\n(PII scrubbing, citation check, mutation claims)"]
    end

    subgraph Core [Transactional Approvals & Authority]
        ApprService["ApprovalService\n(State Machine, Optimistic Concurrency, Revalidation)"]
        OrderRepo["SqlOrderRepository\n(OrderModel, 30-min window check)"]
        AuditRepo["AuditRepository\n(Append-only chronological audit logging)"]
    end

    subgraph Storage [Relational Persistence]
        DB[(SQLite / PostgreSQL DB)]
    end

    CV -->|Chat turn / Poll| MW
    RC -->|Reviewer actions with X-Reviewer-Key| MW
    MW --> ChatEP & PollEP & RevListEP & RevDetailEP & RevApprEP & RevRejEP & AuditEP & TraceEP & PromEP

    ChatEP --> SG
    SG -->|If Clean| Router
    Router -->|KNOWLEDGE| Retriever --> Resolver --> LLM
    Router -->|ORDER / ACTION| OrderRepo
    LLM --> Validator
    Router -->|Eligible Cancellation| ApprService

    RevApprEP & RevRejEP --> ApprService
    ApprService -->|Lock & Revalidate| OrderRepo
    ApprService -->|Record transition| AuditRepo
    OrderRepo & AuditRepo & ApprService --> DB
```

---

## 2. End-to-End Action Lifecycle Sequence Diagram

The complete sequence diagram below depicts the execution lifecycle of a customer cancellation request, illustrating the separation between proposal creation, human approval, state revalidation, and single-execution mutation.

```mermaid
sequenceDiagram
    autonumber
    actor Customer as Customer
    participant UI_Cust as Customer Chat UI
    participant API as FastAPI Gateway
    participant Guard as Security Guard
    participant Router as Intent Router
    participant Engine as Approval Service
    participant DB as Relational Database
    actor Reviewer as Support Reviewer
    participant UI_Rev as Reviewer Console

    Note over Customer,DB: Phase 1: Request Interpretation & Proposal Creation
    Customer->>UI_Cust: Types: "Please cancel my order ORD-1001"
    UI_Cust->>API: POST /chat {"message": "...", "session_id": "sess_1"} [X-Request-ID: req_1]
    API->>Guard: evaluate_input_guard(message)
    Guard-->>API: Clean (no injection)
    API->>Router: route(message, session)
    Router->>DB: lookup_order("ORD-1001")
    DB-->>Router: Status="pending", placed_at="11:00:00Z"
    Router->>Router: Check eligibility: now (11:15:00Z) <= placed_at + 30m -> TRUE
    Router->>Engine: create_proposal(order_id="ORD-1001", action="CANCELLATION")
    Engine->>DB: INSERT ProposedAction (id="prop_1", status="PENDING_APPROVAL", v=1)
    Engine->>DB: INSERT AuditEvent (action="create_proposal", req_id="req_1")
    DB-->>Engine: Committed (Order ORD-1001 status remains "pending")
    Engine-->>API: Proposal created (id="prop_1")
    API-->>UI_Cust: HTTP 200 {"supported_action": "cancellation_request_submitted", "proposal": {"id": "prop_1", "status": "PENDING_APPROVAL"}}
    UI_Cust->>UI_Cust: Render status card: "Submitted for Review"

    Note over UI_Cust,API: Phase 2: Live Polling
    loop Poll Interval (2s)
        UI_Cust->>API: GET /sessions/sess_1/proposal
        API->>DB: SELECT proposal WHERE session_id="sess_1"
        DB-->>API: Status="PENDING_APPROVAL", v=1
        API-->>UI_Cust: HTTP 200 {"id": "prop_1", "status": "PENDING_APPROVAL"}
    end

    Note over Reviewer,DB: Phase 3: Reviewer Inspection & Decision
    Reviewer->>UI_Rev: Opens Reviewer Console (/reviewer)
    UI_Rev->>API: GET /reviewer/proposals [Header: X-Reviewer-Key]
    API->>DB: SELECT proposals WHERE status="PENDING_APPROVAL"
    DB-->>API: Returns prop_1
    API-->>UI_Rev: HTTP 200 [proposals list]
    Reviewer->>UI_Rev: Clicks "Approve" (enters reason)
    UI_Rev->>API: POST /reviewer/proposals/prop_1/approve {"version": 1, "note": "Approved"} [X-Request-ID: req_2]

    Note over API,DB: Phase 4: Atomic Execution & Revalidation
    API->>Engine: approve(proposal_id="prop_1", reviewer="admin", expected_version=1)
    Engine->>DB: SELECT proposal WHERE id="prop_1" FOR UPDATE
    Engine->>Engine: Verify expected_version == proposal.version (1 == 1)
    Engine->>Engine: Transition PENDING_APPROVAL -> APPROVED (v=2)
    Engine->>DB: SELECT order WHERE id="ORD-1001" FOR UPDATE
    Engine->>Engine: Revalidate order state: status == "pending" -> TRUE
    Engine->>DB: UPDATE orders SET status="cancelled" WHERE id="ORD-1001"
    Engine->>Engine: Transition APPROVED -> EXECUTED (v=3)
    Engine->>DB: INSERT AuditEvent (action="approve", req_id="req_2")
    Engine->>DB: INSERT AuditEvent (action="execute_success", req_id="req_2")
    DB-->>Engine: Atomic Transaction Committed
    Engine-->>API: Proposal EXECUTED (v=3)
    API-->>UI_Rev: HTTP 200 {"status": "EXECUTED", "version": 3}

    Note over Customer,API: Phase 5: Customer Card Updates
    UI_Cust->>API: GET /sessions/sess_1/proposal
    API-->>UI_Cust: HTTP 200 {"status": "EXECUTED", "version": 3}
    UI_Cust->>UI_Cust: Polite live announcement: "Proposal EXECUTED: Your order has been cancelled"
```

---

## 3. Finite State Machine Formal Specification

The proposed action lifecycle is implemented in `src/approvals/state_machine.py` as an explicit finite state machine with strict transition guards.

```mermaid
stateDiagram-v2
    [*] --> PENDING_APPROVAL: create_proposal() [v=1]

    PENDING_APPROVAL --> APPROVED: APPROVE event [v=2]\n(Authorized Reviewer)
    PENDING_APPROVAL --> REJECTED: REJECT event [v=2]\n(Requires Reason >= 10 chars)
    PENDING_APPROVAL --> EXPIRED: EXPIRE event [v=2]\n(Clock > expires_at TTL)

    APPROVED --> EXECUTED: EXECUTE_SUCCESS event [v=3]\n(Order Revalidation Passes)
    APPROVED --> FAILED: EXECUTE_FAILURE event [v=3]\n(Stale Order / Warehouse Shipped)

    REJECTED --> [*]: Terminal State
    EXPIRED --> [*]: Terminal State
    EXECUTED --> [*]: Terminal State (Idempotent 200 on retry)
    FAILED --> [*]: Terminal State
```

### State Machine Transition Rules Table

| Current State | Event Trigger | Next State | Version Change | Pre-Conditions & Invariants |
|---|---|---|---|---|
| *(None)* | `CREATE` | `PENDING_APPROVAL` | `version = 1` | Order exists, status is `pending`, now <= placed_at + 30m. |
| `PENDING_APPROVAL` | `APPROVE` | `APPROVED` | `version += 1` | `expected_version == current_version`, caller is authenticated reviewer. |
| `APPROVED` | `EXECUTE_SUCCESS` | `EXECUTED` | `version += 1` | Database row revalidated; order status atomically updated to `cancelled`. |
| `APPROVED` | `EXECUTE_FAILURE` | `FAILED` | `version += 1` | Order revalidation failed (e.g. order was shipped by warehouse). |
| `PENDING_APPROVAL` | `REJECT` | `REJECTED` | `version += 1` | Rejection reason length is between 10 and 500 characters. |
| `PENDING_APPROVAL` | `EXPIRE` | `EXPIRED` | `version += 1` | System clock > proposal `expires_at` timestamp. |
| `EXECUTED` | `APPROVE` (Retry) | `EXECUTED` | `None` | **Idempotent No-Op**: Returns current state without second mutation. |

---

## 4. Formal Data Contracts

### A. Customer Chat Request (`ChatRequest`)
```json
{
  "message": "Please cancel my order ORD-1001 right now.",
  "session_id": "journey-cust-e32d4ba1"
}
```

### B. Public Agent Response (`ChatResponse`)
Customer responses contain only sanitized, customer-safe fields. Sensitive internal attributes (fraud scores, credit card tokens, warehouse notes) are stripped prior to response delivery.
```json
{
  "session_id": "journey-cust-e32d4ba1",
  "turn_id": 1,
  "message": "Your cancellation request for order ORD-1001 has been submitted for human review (reference: prop_f2a9f4e05b56).",
  "decision_state": "ANSWER",
  "citations": [
    "01-cancellation-policy.md > Standard Order Cancellation"
  ],
  "handoff_recommended": false,
  "handoff_reason": null,
  "supported_action": "cancellation_request_submitted",
  "is_fallback": false,
  "fallback_reason": null,
  "safe_order": {
    "order_id": "ORD-1001",
    "customer_id": "CUST-401",
    "status": "pending",
    "item_count": 2,
    "items_summary": "1x Horizon Daypack, 1x Breeze Tumbler",
    "tracking_number": null,
    "estimated_delivery": null
  },
  "proposal": {
    "id": "prop_f2a9f4e05b56",
    "order_id": "ORD-1001",
    "action_type": "CANCELLATION",
    "status": "PENDING_APPROVAL",
    "created_at": "2026-11-25T21:07:14.500985Z",
    "expires_at": "2026-11-26T21:07:14.500985Z",
    "version": 1
  }
}
```

### C. Reviewer Decision Payload (`ApproveProposalRequest` / `RejectProposalRequest`)
```json
{
  "version": 1,
  "note": "Customer submitted cancellation within 30-minute window. Order verified pending."
}
```

### D. Audit Event Entity (`AuditEventResponse`)
All transitions generate permanent, append-only audit records.
```json
{
  "id": "evt_91f4b2a8",
  "proposal_id": "prop_f2a9f4e05b56",
  "order_id": "ORD-1001",
  "action": "execute_success",
  "actor": "admin",
  "actor_type": "human_reviewer",
  "previous_status": "APPROVED",
  "new_status": "EXECUTED",
  "version": 3,
  "timestamp": "2026-11-25T21:07:14.510277Z",
  "request_id": "req-rev-appr-77403d25",
  "details": {
    "order_id": "ORD-1001",
    "previous_order_status": "pending",
    "new_order_status": "cancelled",
    "mutation_executed_at": "2026-03-01T11:15:00Z"
  }
}
```
