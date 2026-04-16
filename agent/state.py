from typing import TypedDict, List, Optional, Any
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    messages:              List[BaseMessage]
    last_agent:            str
    needs_input:           bool
    route:                 Optional[str]   # "hr" | "email" | "done" |
                                           # "retry_hr" | "retry_email" | "retry_orchestrator"
    pending_email_draft:   Optional[Any]   # holds draft dict while awaiting user confirmation
    cancelled_email_draft: Optional[Any]   # preserves cancelled draft for next-turn EMP ID recovery
    last_eval:             Optional[dict]  # latest evaluation results from evaluation_agent

    # ── Agent feedback loop ──
    db_ground_truth:       Optional[str]   # raw DB output from hr_agent; used by evaluator
    eval_feedback:         Optional[str]   # feedback injected into agent on retry
    retry_count:           int             # agent regeneration attempts this turn
    retry_agent:           Optional[str]   # "hr_agent" | "email_agent"

    # ── Orchestrator feedback loop ──
    orchestrator_feedback:    Optional[str]  # correction hint injected into orchestrator on re-route
    orchestrator_retry_count: int            # how many times orchestrator has been re-routed this turn