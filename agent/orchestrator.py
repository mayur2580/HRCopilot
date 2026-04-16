import os
from langgraph.graph import StateGraph, END
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from agent.state import AgentState
from agent.hr_agent import hr_agent_node
from agent.email_agent import email_agent_node
from agent.evaluation_agent import evaluation_agent_node


# ─────────────────────────────────────────────
# LLM
# ─────────────────────────────────────────────
llm = ChatGroq(
    groq_api_key=os.environ.get("GROQ_API_KEY"),
    model="meta-llama/llama-4-scout-17b-16e-instruct",
    temperature=0
)


# ─────────────────────────────────────────────
# ORCHESTRATOR PROMPT
# ─────────────────────────────────────────────
ORCHESTRATOR_PROMPT = """You are an intelligent orchestrator for an HR assistant system.

You have two specialized agents available:

1. HR_AGENT    — handles all HR questions, policies, employee data, leave, attendance, payroll
2. EMAIL_AGENT — handles drafting, previewing, and sending emails to employees

Your job is to read the user's latest message and conversation history, then decide which agent should handle it.

ROUTING RULES:

Route to EMAIL_AGENT if the user wants to:
- Send, draft, write, or compose an email to someone
- Notify an employee via email
- Confirm or cancel a pending email (yes/no responses when an email draft is shown)
- Say things like "let him know", "inform her", "shoot him a mail"

Route to HR_AGENT for everything else:
- HR policy questions
- Employee data lookups (leaves, attendance, salary, details)
- General greetings and conversation
- Follow-up questions about HR topics
- Questions that contain the word "email" but are about policy (e.g. "what is the email policy?")

- If the latest message is casual (e.g. "my name is...", "hi", "hello", "thanks"),
  ALWAYS route to HR_AGENT even if previous message was about email

CONVERSATION HISTORY:
{history}

LATEST USER MESSAGE:
{query}

{correction}

Return ONLY one word:
HR_AGENT
EMAIL_AGENT

No explanation. No punctuation. Just the agent name."""


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def get_conversation_summary(messages: list) -> str:
    recent = messages[-6:] if len(messages) > 6 else messages
    lines  = []
    for msg in recent:
        role = "User" if isinstance(msg, HumanMessage) else "Assistant"
        lines.append(f"{role}: {msg.content[:120]}")
    return "\n".join(lines)


# ─────────────────────────────────────────────
# ORCHESTRATOR NODE
# ─────────────────────────────────────────────
def orchestrator_node(state: AgentState) -> AgentState:
    """
    Routes the user message to hr_agent or email_agent.
    Injects evaluator correction when present.
    """
    if state.get("pending_email_draft"):
        return {
            **state,
            "route":                 "email",
            "retry_count":           0,
            "eval_feedback":         None,
            "orchestrator_feedback": None,
        }

    orch_feedback    = state.get("orchestrator_feedback") or ""
    orch_retry_count = state.get("orchestrator_retry_count", 0)

    correction_block = ""
    if orch_feedback:
        correction_block = f"CORRECTION FROM EVALUATOR:\n{orch_feedback}"
        print(f"[ORCHESTRATOR] Re-routing with eval correction (orch retry {orch_retry_count})...")

    query   = state["messages"][-1].content
    history = get_conversation_summary(state["messages"][:-1])
    prompt  = ORCHESTRATOR_PROMPT.format(
        history=history,
        query=query,
        correction=correction_block,
    )

    decision = llm.invoke(prompt).content.strip().upper()
    route    = "email" if "EMAIL" in decision else "hr"

    print(f"[ORCHESTRATOR] -> {decision}")

    return {
        **state,
        "route":                 route,
        "retry_count":           0,
        "eval_feedback":         None,
        "orchestrator_feedback": None,
    }


# ─────────────────────────────────────────────
# FEEDBACK-AWARE AGENT WRAPPERS
# ─────────────────────────────────────────────
def hr_agent_with_feedback(state: AgentState) -> AgentState:
    eval_feedback = state.get("eval_feedback")

    if eval_feedback:
        # Evaluator-triggered retry — inject eval correction as a hidden SystemMessage
        # so it is never visible in the user-facing conversation history.
        print(f"[HR_AGENT] Regenerating with eval feedback (retry {state.get('retry_count', 1)})...")

        # Strip the bad previous AIMessage so it doesn't appear in the UI.
        # Walk back from the end and remove the last AIMessage (the failed response).
        messages = list(state["messages"])
        for i in range(len(messages) - 1, -1, -1):
            if isinstance(messages[i], AIMessage):
                messages.pop(i)
                break

        feedback_msg = SystemMessage(content=(
            f"[INTERNAL EVAL FEEDBACK — regenerate your previous response]\n\n"
            f"{eval_feedback}\n\n"
            f"Do NOT mention this feedback to the user. Just produce an improved response."
        ))
        # Insert the hidden feedback before the last user message.
        state = {
            **state,
            "messages": messages[:-1] + [feedback_msg, messages[-1]],
            "eval_feedback": None,
        }

    result = hr_agent_node(state)
    return {**result, "eval_feedback": None}


def email_agent_with_feedback(state: AgentState) -> AgentState:
    eval_feedback = state.get("eval_feedback")

    if eval_feedback:
        # Evaluator-triggered retry — inject eval correction as a hidden SystemMessage
        # so it is never visible in the user-facing conversation history.
        print(f"[EMAIL_AGENT] Regenerating with eval feedback (retry {state.get('retry_count', 1)})...")

        # Strip the bad previous AIMessage so it doesn't appear in the UI.
        messages = list(state["messages"])
        for i in range(len(messages) - 1, -1, -1):
            if isinstance(messages[i], AIMessage):
                messages.pop(i)
                break

        feedback_msg = SystemMessage(content=(
            f"[INTERNAL EVAL FEEDBACK — regenerate the email draft]\n\n"
            f"{eval_feedback}\n\n"
            f"Do NOT mention this feedback to the user. Just produce an improved response."
        ))
        # Insert the hidden feedback before the last user message.
        state = {
            **state,
            "messages": messages[:-1] + [feedback_msg, messages[-1]],
            "eval_feedback": None,
        }

    result = email_agent_node(state)
    return {**result, "eval_feedback": None}


# ─────────────────────────────────────────────
# ROUTE SELECTORS
# ─────────────────────────────────────────────
def route_selector(state: AgentState) -> str:
    return state.get("route", "hr")


def eval_route_selector(state: AgentState) -> str:
    route = state.get("route", "done")
    # print(f"[EVAL ROUTER] -> {route}")
    return route


# ─────────────────────────────────────────────
# GRAPH
# ─────────────────────────────────────────────
builder = StateGraph(AgentState)

builder.add_node("orchestrator",     orchestrator_node)
builder.add_node("hr_agent",         hr_agent_with_feedback)
builder.add_node("email_agent",      email_agent_with_feedback)
builder.add_node("evaluation_agent", evaluation_agent_node)

builder.set_entry_point("orchestrator")

# Orchestrator -> agents
builder.add_conditional_edges("orchestrator", route_selector, {
    "hr":    "hr_agent",
    "email": "email_agent",
})

# Agents -> evaluation
builder.add_edge("hr_agent",    "evaluation_agent")
builder.add_edge("email_agent", "evaluation_agent")

# Evaluation -> retry or END (no human review step)
builder.add_conditional_edges("evaluation_agent", eval_route_selector, {
    "retry_orchestrator": "orchestrator",
    "retry_hr":           "hr_agent",
    "retry_email":        "email_agent",
    "done":               END,
})

graph = builder.compile()