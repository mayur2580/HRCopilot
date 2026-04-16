import os
import re
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_groq import ChatGroq
from langgraph.prebuilt import ToolNode
from langchain_openai import ChatOpenAI
from agent.state import AgentState
from tools.tools import HR_TOOLS, db_returned_data


# ─────────────────────────────────────────────
# LLM  (with tools bound)
# ─────────────────────────────────────────────
llm = ChatGroq(
    groq_api_key=os.environ.get("GROQ_API_KEY"),
    model="meta-llama/llama-4-scout-17b-16e-instruct",
    temperature=0.3
).bind_tools(HR_TOOLS)


tool_node = ToolNode(HR_TOOLS)


# ─────────────────────────────────────────────
# SYSTEM PROMPT
# ─────────────────────────────────────────────
HR_SYSTEM_PROMPT = """You are a professional HR assistant for employees and HR staff.
Your job is to ALWAYS attempt to answer the user's question — never deflect, never say
"I can't do that", and never ask for information you can try to find yourself.

═══════════════════════════════════════════════════════
TOOLS AVAILABLE
═══════════════════════════════════════════════════════

1. db_query_tool — query the HR database for any employee information.
   Tables and columns:
     employees  : employee_id, full_name, email, role, department,
                  date_of_joining, tenure_years, contact_no, gender, address,
                  total_leaves, taken_leaves, pending_leaves, manager_id, manager_name
     attendance : employee_id, date, status
     leaves     : employee_id, leave_type, start_date, end_date, days, status

2. rag_search — search HR policy documents for rules, guidelines, and procedures.

═══════════════════════════════════════════════════════
WHEN AND HOW TO USE TOOLS
═══════════════════════════════════════════════════════

EMPLOYEE LOOKUP — always try, never refuse:
  • User gives an employee ID      → SELECT * FROM employees WHERE employee_id = '<ID>'
  • User gives a name              → SELECT * FROM employees WHERE full_name ILIKE '%<n>%'
  • User says "my name is X"       → immediately search by that name, do not ask for an ID
  • Multiple matches found         → list them (name + role + department), ask user to confirm
  • User asks about a role/title   → SELECT * FROM employees WHERE role ILIKE '%<title>%'
  • User asks about leave balance  → query leaves / employees table using employee_id
  • User asks about attendance     → query attendance table using employee_id
  • User asks about their manager  → fetch manager_id then query that manager's record

HR POLICY LOOKUP — call rag_search immediately:
  • Any mention of: leave policy, sick leave, annual leave, casual leave, maternity,
    paternity, benefits, working hours, dress code, code of conduct, rules, procedures,
    guidelines, "tell me more", "more detail", "all policies"
  • NEVER ask what type of leave — just search broadly and return everything found

GENERAL / CONVERSATIONAL:
  • Greetings, thanks, small talk → answer directly, no tools needed

═══════════════════════════════════════════════════════
WHEN INFORMATION IS NOT FOUND — follow this exactly
═══════════════════════════════════════════════════════

If db_query_tool returns no results:
  1. Tell the user clearly what you searched for (the name, ID, or role they gave)
  2. Confirm that no matching record was found in the database
  3. Suggest concrete next steps — choose the most relevant:
       • "Could you double-check the spelling of your name?"
       • "Try providing your employee ID (e.g. EMP0123) for an exact match."
       • "Try a shorter version of your name (e.g. just first name)."
       • "If the issue persists, please contact HR directly for assistance."
  4. Stay warm and helpful — NEVER just say "not found" and stop

If rag_search returns no results:
  1. Tell the user the topic wasn't covered in the available policy documents
  2. Suggest they reach out to HR directly for clarification on that policy

═══════════════════════════════════════════════════════
GOLDEN RULES — NEVER BREAK THESE
═══════════════════════════════════════════════════════

✅ ALWAYS attempt to answer — use tools proactively, never wait for more info
✅ ALWAYS try a name-based search if no employee ID is given
✅ ALWAYS call rag_search for any policy question without asking for clarification first
✅ ONLY use values from tool results — never invent or guess any data
✅ When data is not found, explain clearly + suggest next steps (never just stop)

❌ NEVER say "I can only search by employee ID"
❌ NEVER say "I don't have access to that information"
❌ NEVER ask the user for information you can look up yourself
❌ NEVER truncate or summarise results unless explicitly asked to
❌ NEVER give a one-line "not found" reply — always guide the user forward

═══════════════════════════════════════════════════════
RESPONSE STYLE
═══════════════════════════════════════════════════════

- Warm, professional, and concise
- Use bullet points for lists; plain sentences for short answers
- Always complete your answer fully — do not cut off mid-response
"""


# ─────────────────────────────────────────────
# HR AGENT NODE
# ─────────────────────────────────────────────
def hr_agent_node(state: AgentState) -> AgentState:
    """
    HR agent with native LangGraph tool calling.

    Flow:
    1. Build message list with system prompt
    2. LLM decides whether to call tools (db_query_tool / rag_search)
    3. ToolNode executes the calls and returns ToolMessages
    4. DB guard: if employee queried but DB returned empty → inject not-found signal,
       let LLM craft a warm, helpful reply (no more hardcoded error messages)
    5. LLM synthesizes final answer from tool results
    6. Capture db_ground_truth for evaluator
    """
    # Find the last HumanMessage for user_query.
    # The eval wrapper may have injected a SystemMessage after the real user message,
    # so we cannot rely on state["messages"][-1] being a HumanMessage.
    user_query = ""
    for msg in reversed(state["messages"]):
        if isinstance(msg, HumanMessage):
            user_query = msg.content
            break

    # Separate internal eval-feedback SystemMessages (hidden from UI) from the
    # user-visible conversation messages (HumanMessage / AIMessage / ToolMessage).
    clean_messages = []  # stored back into state — these are user-visible
    internal_msgs  = []  # passed to LLM only — never returned in state["messages"]
    for msg in state["messages"]:
        if isinstance(msg, SystemMessage) and "[INTERNAL EVAL FEEDBACK" in msg.content:
            internal_msgs.append(msg)
        else:
            clean_messages.append(msg)

    # Build LLM context: HR system prompt + hidden eval hints + visible conversation
    lc_messages = [SystemMessage(content=HR_SYSTEM_PROMPT)] + internal_msgs + clean_messages

    db_ground_truth = None

    # ── Agentic tool loop ──
    while True:
        response = llm.invoke(lc_messages)
        lc_messages.append(response)

        # No tool calls → LLM is done, response is final
        if not response.tool_calls:
            break

        print(f"[HR_AGENT] Tool calls: {[tc['name'] for tc in response.tool_calls]}")

        # Execute all tool calls
        tool_results: dict = tool_node.invoke({"messages": lc_messages})
        tool_messages: list[ToolMessage] = tool_results["messages"]

        # ── DB guard: empty result → patch ToolMessage so LLM crafts a helpful reply ──
        # Instead of returning a hardcoded error, we inject a clear NO_RESULTS signal
        # into the tool result and let the LLM follow the system prompt's "not found" rules.
        for i, tm in enumerate(tool_messages):
            if tm.name == "db_query_tool" and not db_returned_data(tm.content):
                tool_messages[i] = tm.__class__(
                    content=(
                        "NO_RESULTS: The database returned no matching records for this query. "
                        "Do not invent any data. Follow the 'WHEN INFORMATION IS NOT FOUND' "
                        "section of your instructions: tell the user what was searched, confirm "
                        "no record was found, and suggest helpful next steps."
                    ),
                    name=tm.name,
                    tool_call_id=tm.tool_call_id,
                )

        # Capture raw DB output for evaluator ground-truth checking
        for tm in tool_messages:
            if tm.name == "db_query_tool":
                db_ground_truth = (db_ground_truth + "\n\n" + tm.content
                                   if db_ground_truth else tm.content)

        lc_messages.extend(tool_messages)

    # Final LLM response is the last message
    final_answer = lc_messages[-1].content.strip()

    return {
        **state,
        # Use clean_messages (no internal SystemMessages) so the UI stays clean
        "messages":        clean_messages + [AIMessage(content=final_answer)],
        "last_agent":      "hr_agent",
        "route":           "done",
        "db_ground_truth": db_ground_truth,
    }