import os
import json
import re
from datetime import datetime
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from agent.state import AgentState


# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
llm = ChatGroq(
    groq_api_key=os.environ.get("GROQ_API_KEY"),
    model="openai/gpt-oss-120b",
    temperature=0.2
)

EVAL_LOG_FILE     = "evaluation_log.jsonl"
JSON_PATTERN      = re.compile(r"\{[\s\S]*\}", re.DOTALL)
MAX_AGENT_RETRIES = 2   # max regeneration attempts per agent per turn
MAX_ORCH_RETRIES  = 1   # max re-route attempts per turn

# Trivial turns that must skip evaluation entirely — no LLM call needed
TRIVIAL_PATTERNS = re.compile(
    r"^\s*(yes|no|ok|okay|confirm|cancel|send|stop|n|y|"
    r"yes send it|don'?t send|hi|hello|hey|thanks|thank you|"
    r"great|got it|sure|sounds good)\s*[.!]?\s*$",
    re.IGNORECASE,
)


# ─────────────────────────────────────────────
# EVALUATION PROMPTS
# ─────────────────────────────────────────────

HR_EVAL_PROMPT = """You are a strict QA evaluator for an HR assistant system.
You will be given a user query, the assistant's response, and optionally the raw DB output.

YOUR JOB: Decide if the response is good enough to show to the user.
Be strict. A score of 7+ means the response is acceptable as-is.
A score below 7 means it must be regenerated.

Score each dimension from 1-10:
- accuracy:     Are all facts correct? If DB ground truth is provided, every value in the
                response (name, email, role, leaves, manager, etc.) MUST match it exactly.
                Any mismatch = hallucination = score 1-3.
- relevance:    Does it directly and completely answer what was asked? Off-topic = low score.
- tone:         Professional, warm, appropriate for HR context?
- conciseness:  Not too long, not too short. Vague one-liners score low. Essays score low.
- completeness: Does it cover ALL parts of the user's question? Partial answers score low.

STRICT RULES:
- If DB ground truth is provided and ANY value in the response contradicts it → accuracy = 2,
  pass = false, list every mismatched field in issues.
- If the response says "I don't know" or "I couldn't find" when data WAS available → relevance = 2.
- If the response is a generic filler ("Please provide more details") when the query was clear → relevance = 3.
- Do NOT give high scores just because the response sounds professional. Content must be correct.

Return ONLY valid JSON, no markdown, no explanation:
{
  "scores": {
    "accuracy":     <1-10>,
    "relevance":    <1-10>,
    "tone":         <1-10>,
    "conciseness":  <1-10>,
    "completeness": <1-10>
  },
  "overall":            <average of the 5 scores rounded to 1 decimal>,
  "pass":               <true if overall >= 7.0, else false>,
  "issues":             ["specific problem 1", "specific problem 2"],
  "suggested_response": "<describe HOW to fix the response structurally — never invent names, emails, numbers, or any data values. If a value is missing, instruct the agent to query the database. null if pass is true>"
}"""


EMAIL_EVAL_PROMPT = """You are a strict QA evaluator for HR email drafts.
You will be given the original email request and the drafted email.

YOUR JOB: Decide if this email draft is ready to send. Be strict.
A score of 7+ means it is acceptable. Below 7 means it must be regenerated.

Score each dimension from 1-10:
- professionalism: Is the tone appropriate for a workplace email? No casual/sloppy language?
- clarity:         Is the message clear, unambiguous, and easy to understand?
- completeness:    Does the email body address the full intent of the original request?
- personalization: Does it greet the recipient by name? Does the sign-off match the sender?
- correctness:     Are to_email, to_name, sender_name, sender_id fields consistent with
                   the request? Subject line must match the body content.

STRICT RULES — evaluate each field independently, do not cascade errors:
- personalization: compare greeting name against to_name ONLY.
  "Dear Krishna" is correct if to_name is "Krishna Patil". Do NOT compare greeting to sender_name.
- correctness: compare sign-off name against sender_name ONLY.
  For employee→manager emails: to_email must be the MANAGER's email, not the employee's own email.
  If to_email is the same as sender_id, that is a correctness failure — flag it explicitly.
- If sign-off name does not match sender_name → correctness = 2.
- If subject has nothing to do with the body → correctness = 2.
- If body is a single generic sentence with no real content → completeness = 2.
- Do NOT cascade: a wrong to_email does not cause personalization to fail if the greeting is correct.
- Do NOT pass an email just because it looks formatted correctly. Content must match the request.

Return ONLY valid JSON, no markdown, no explanation:
{
  "scores": {
    "professionalism": <1-10>,
    "clarity":         <1-10>,
    "completeness":    <1-10>,
    "personalization": <1-10>,
    "correctness":     <1-10>
  },
  "overall":        <average of the 5 scores rounded to 1 decimal>,
  "pass":           <true if overall >= 7.0, else false>,
  "issues":         ["specific problem 1", "specific problem 2"],
  "suggested_body": "<an improved email body that fixes all issues, or null if pass is true>"
}"""


ROUTING_EVAL_PROMPT = """You are a QA evaluator for an AI orchestrator that routes user messages.

The orchestrator routes to either HR_AGENT or EMAIL_AGENT.

Routing rules:
- EMAIL_AGENT: user wants to send/draft/compose/write an email, notify someone,
               say things like "let him know", "inform her", "shoot a mail",
               or confirm/cancel a pending email draft (yes/no after seeing a draft).
- HR_AGENT:    HR policy questions, employee data lookups (details, leaves, attendance,
               salary), greetings, general conversation, follow-up HR questions.
               NOTE: questions containing the word "email" that are about policy
               (e.g. "what is the email policy?") still go to HR_AGENT.

Evaluate whether the routing decision was correct.

Return ONLY valid JSON, no markdown, no explanation:
{
  "expected_route":  "HR_AGENT or EMAIL_AGENT",
  "actual_route":    "HR_AGENT or EMAIL_AGENT",
  "correct":         <true or false>,
  "confidence":      <1-10, how confident you are in your judgment>,
  "reasoning":       "one sentence explaining why the routing was or was not correct",
  "correction_hint": "one sentence telling the orchestrator exactly what to do instead, or null if correct"
}"""


# ─────────────────────────────────────────────
# LOGGER
# ─────────────────────────────────────────────
def log_evaluation(eval_type: str, result: dict, context: dict) -> None:
    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "eval_type": eval_type,
        "result":    result,
        "context":   context,
    }
    try:
        with open(EVAL_LOG_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        print(f"[EVAL] Warning: could not write log — {e}")


# ─────────────────────────────────────────────
# JSON PARSER
# ─────────────────────────────────────────────
def _parse_json(text: str) -> dict | None:
    match = JSON_PATTERN.search(text)
    if not match:
        return None
    try:
        return json.loads(re.sub(r'```json|```', '', match.group(0)).strip())
    except json.JSONDecodeError:
        return None


# ─────────────────────────────────────────────
# TRIVIAL TURN GUARD
# ─────────────────────────────────────────────
def is_trivial_turn(user_query: str) -> bool:
    """
    Returns True for confirmations, cancellations, greetings, and other
    short turns that have no meaningful output to evaluate.
    Skipping these saves an LLM call and avoids false failures.
    """
    return bool(TRIVIAL_PATTERNS.match(user_query.strip()))


# ─────────────────────────────────────────────
# EVALUATORS
# ─────────────────────────────────────────────
def evaluate_hr_response(
    user_query: str,
    assistant_response: str,
    conversation_history: list = None,
    db_ground_truth: str = None,
) -> dict:
    history_text = ""
    if conversation_history:
        history_text = "\n".join(
            f"{'User' if isinstance(m, HumanMessage) else 'Assistant'}: {m.content[:200]}"
            for m in conversation_history[-4:]
        )

    # DB ground truth block — evaluator uses this to catch hallucinations
    ground_truth_block = ""
    if db_ground_truth:
        ground_truth_block = (
            f"\nDB GROUND TRUTH (raw database output — every value here is authoritative):\n"
            f"{db_ground_truth}\n\n"
            f"CRITICAL: Compare every fact in the assistant response against this ground truth. "
            f"Any field that differs (name, email, role, department, leave counts, manager, "
            f"contact, address, tenure) is a hallucination. Score accuracy 1-3 and list "
            f"every mismatched field explicitly in 'issues'.\n\n"
        )

    result = _parse_json(llm.invoke([
        SystemMessage(content=HR_EVAL_PROMPT),
        HumanMessage(content=(
            f"CONVERSATION HISTORY:\n{history_text}\n\n"
            f"USER QUERY:\n{user_query}\n\n"
            f"{ground_truth_block}"
            f"ASSISTANT RESPONSE TO EVALUATE:\n{assistant_response}"
        )),
    ]).content.strip())

    if not result:
        # Parse failure → default pass to avoid infinite retry loops
        print("[EVAL] ⚠️  HR eval JSON parse failed — defaulting to pass.")
        return {"overall": 7.0, "pass": True, "issues": [], "suggested_response": None}

    log_evaluation("hr_response", result, {
        "user_query":         user_query[:300],
        "assistant_response": assistant_response[:300],
    })
    return result


def evaluate_email_draft(email_draft: dict, original_request: str) -> dict:
    # Build CC line so evaluator can verify it was included
    cc_list = email_draft.get("cc", [])
    cc_line = ""
    if cc_list:
        cc_parts = [
            f"{p['full_name']} <{p['email']}>"
            for p in cc_list
            if isinstance(p, dict) and p.get("full_name") and p.get("email")
        ]
        if cc_parts:
            cc_line = f"CC:      {', '.join(cc_parts)}\n"

    draft_text = (
        f"From:    {email_draft.get('sender_name')} <{email_draft.get('sender_id')}>\n"
        f"To:      {email_draft.get('to_name')} <{email_draft.get('to_email')}>\n"
        f"{cc_line}"
        f"Subject: {email_draft.get('subject')}\n\n"
        f"Body:\n{email_draft.get('body')}"
    )

    # Inform the evaluator of the resolved names so it does not flag correct
    # DB-resolved names as wrong just because it cannot look up EMP IDs itself
    resolved_note = (
        f"\nNOTE: The recipient '{email_draft.get('to_name')}' and sender "
        f"'{email_draft.get('sender_name')}' were resolved from the HR database "
        f"and are authoritative — do NOT flag these names as incorrect.\n"
        f"If CC recipients are shown in the draft above, do NOT flag CC as missing.\n"
    )

    result = _parse_json(llm.invoke([
        SystemMessage(content=EMAIL_EVAL_PROMPT),
        HumanMessage(content=(
            f"ORIGINAL REQUEST:\n{original_request}\n"
            f"{resolved_note}\n"
            f"EMAIL DRAFT TO EVALUATE:\n{draft_text}"
        )),
    ]).content.strip())

    if not result:
        print("[EVAL] ⚠️  Email eval JSON parse failed — defaulting to pass.")
        return {"overall": 7.0, "pass": True, "issues": [], "suggested_body": None}

    log_evaluation("email_draft", result, {
        "original_request": original_request[:300],
        "to_email":         email_draft.get("to_email"),
        "subject":          email_draft.get("subject"),
    })
    return result


def evaluate_routing(
    user_message: str,
    actual_route: str,
    conversation_history: list = None,
) -> dict:
    history_text = ""
    if conversation_history:
        history_text = "\n".join(
            f"{'User' if isinstance(m, HumanMessage) else 'Assistant'}: {m.content[:200]}"
            for m in conversation_history[-4:]
        )
    route_label = "EMAIL_AGENT" if actual_route == "email" else "HR_AGENT"

    result = _parse_json(llm.invoke([
        SystemMessage(content=ROUTING_EVAL_PROMPT),
        HumanMessage(content=(
            f"CONVERSATION HISTORY:\n{history_text}\n\n"
            f"USER MESSAGE:\n{user_message}\n\n"
            f"ORCHESTRATOR ROUTED TO: {route_label}"
        )),
    ]).content.strip())

    if not result:
        print("[EVAL] ⚠️  Routing eval JSON parse failed — defaulting to correct.")
        return {"correct": True, "confidence": 5, "reasoning": "Parse failed", "correction_hint": None}

    log_evaluation("routing", result, {
        "user_message": user_message[:300],
        "actual_route": route_label,
    })
    return result


# ─────────────────────────────────────────────
# FEEDBACK BUILDERS
# ─────────────────────────────────────────────
def _build_hr_feedback(issues: list, suggested: str | None) -> str:
    # Sanitize — ensure every issue is a plain string, never a dict
    issues = [str(i) for i in (issues or []) if i]
    lines = [
        "Your previous response did not meet quality standards. Regenerate it.",
        "",
        "Issues found:",
    ]
    for issue in issues:
        lines.append(f"  - {issue}")
    if suggested:
        lines += [
            "",
            "Here is a suggested corrected response — use this as a reference and improve on it:",
            suggested,
        ]
    lines += [
        "",
        "Requirements for your new response:",
        "  - Fix every issue listed above",
        "  - Use ONLY data from the tool results — do not invent any values",
        "  - Be concise (4-6 lines), professional, and warm",
        "  - Do NOT mention tools, SQL, or any technical terms",
    ]
    return "\n".join(lines)


def _build_email_feedback(issues: list, suggested_body: str | None) -> str:
    # Sanitize — ensure every issue is a plain string, never a dict
    issues = [str(i) for i in (issues or []) if i]
    lines = [
        "The email draft did not meet quality standards. Regenerate it.",
        "",
        "Issues found:",
    ]
    for issue in issues:
        lines.append(f"  - {issue}")
    if suggested_body and isinstance(suggested_body, str):
        lines += [
            "",
            "Here is a suggested improved body — use this as a reference:",
            suggested_body,
            "",
            "Keep the same to_email, to_name, sender_name, sender_id, and subject.",
            "Only fix the body to address the issues above.",
        ]
    lines += [
        "",
        "Requirements for your new draft:",
        "  - Greeting must use the recipient's first name exactly as it appears in the data",
        "  - Sign-off must use the sender's name exactly as it appears in the data",
        "  - Subject must accurately reflect the email body content",
        "  - Body must fully address the original request",
    ]
    return "\n".join(lines)


def _build_orchestrator_feedback(
    correction_hint: str,
    actual_route: str,
    expected_route: str,
) -> str:
    return (
        f"You previously routed this request to {actual_route.upper()} — that was incorrect.\n\n"
        f"Correction: {correction_hint}\n\n"
        f"Please re-evaluate the user's message and route to {expected_route.upper()} instead.\n"
        f"Return ONLY the agent name: {expected_route.upper()}_AGENT"
    )


# ─────────────────────────────────────────────
# EVALUATION NODE
# ─────────────────────────────────────────────
def evaluation_agent_node(state: AgentState) -> AgentState:
    """
    Runs after every agent response.

    Priority order:
    1. Trivial turn guard  — skip all evaluation for confirmations/greetings
    2. Routing evaluation  — checked first; if wrong agent ran, re-route immediately
    3. HR response quality — retry hr_agent if score < 7 and retries remain
    4. Email draft quality — retry email_agent if score < 7 and retries remain
    """
    messages         = state["messages"]
    last_agent       = state.get("last_agent", "")
    route            = state.get("route", "")
    pending_draft    = state.get("pending_email_draft")
    retry_count      = state.get("retry_count", 0)
    orch_retry_count = state.get("orchestrator_retry_count", 0)

    human_msgs = [m for m in messages if isinstance(m, HumanMessage)]
    ai_msgs    = [m for m in messages if isinstance(m, AIMessage)]

    last_user_query      = human_msgs[-1].content if human_msgs else ""
    last_ai_response     = ai_msgs[-1].content    if ai_msgs    else ""
    conversation_history = messages[:-1]

    # ── 1. Trivial turn guard — skip evaluation entirely ──
    if is_trivial_turn(last_user_query):
        print(f"[EVAL] Trivial turn detected — skipping evaluation.")
        return {**state, "route": "done", "last_eval": {}}

    eval_results  = {}
    next_route    = "done"
    eval_feedback = None
    retry_agent   = None
    orch_feedback = None

    # ── 2. Routing evaluation — highest priority ──
    if route in ("hr", "email") and last_user_query:
        print(f"[EVAL] Evaluating routing decision...")
        routing_eval = evaluate_routing(
            user_message=last_user_query,
            actual_route=route,
            conversation_history=conversation_history,
        )
        eval_results["routing"] = routing_eval

        correct         = routing_eval.get("correct", True)
        confidence      = routing_eval.get("confidence", 10)
        reasoning       = routing_eval.get("reasoning", "")
        correction_hint = routing_eval.get("correction_hint")
        expected_route  = routing_eval.get("expected_route", "")

        print(f"[EVAL] Routing → {'✅ Correct' if correct else '❌ Wrong'} "
              f"(confidence {confidence}/10) | {reasoning}")

        if not correct and confidence >= 7 and orch_retry_count < MAX_ORCH_RETRIES:
            print(f"[EVAL] Wrong route — correcting orchestrator "
                  f"(retry {orch_retry_count + 1}/{MAX_ORCH_RETRIES})...")
            orch_feedback = _build_orchestrator_feedback(
                correction_hint or reasoning,
                actual_route=route,
                expected_route=expected_route.replace("_AGENT", "").lower(),
            )
            return {
                **state,
                "route":                    "retry_orchestrator",
                "last_eval":                eval_results,
                "orchestrator_feedback":    orch_feedback,
                "orchestrator_retry_count": orch_retry_count + 1,
                "retry_count":              0,
                "eval_feedback":            None,
                "retry_agent":              None,
            }
        elif not correct:
            print(f"[EVAL] ⚠️  Wrong route but max orch retries reached — proceeding.")

    # ── 3. HR response quality evaluation ──
    if last_agent == "hr_agent" and last_ai_response:
        print(f"[EVAL] Evaluating HR response "
              f"(attempt {retry_count + 1}/{MAX_AGENT_RETRIES + 1})...")

        hr_eval = evaluate_hr_response(
            user_query=last_user_query,
            assistant_response=last_ai_response,
            conversation_history=conversation_history,
            db_ground_truth=state.get("db_ground_truth"),
        )
        eval_results["hr_response"] = hr_eval

        overall = hr_eval.get("overall", 10)
        passed  = hr_eval.get("pass", True)
        issues  = [str(i) for i in hr_eval.get("issues", []) if i]

        print(f"[EVAL] HR Response → {overall}/10 | {'✅ PASS' if passed else '❌ FAIL'}")
        if issues:
            print(f"[EVAL] Issues: {'; '.join(issues)}")

        if not passed and retry_count < MAX_AGENT_RETRIES:
            print(f"[EVAL] Sending feedback to hr_agent "
                  f"(retry {retry_count + 1}/{MAX_AGENT_RETRIES})...")
            eval_feedback = _build_hr_feedback(issues, hr_eval.get("suggested_response"))
            next_route    = "retry_hr"
            retry_agent   = "hr_agent"
        elif not passed:
            print(f"[EVAL] ❌ Max retries reached — accepting HR response as-is.")

    # ── 4. Email draft quality evaluation ──
    if last_agent == "email_agent" and pending_draft:
        print(f"[EVAL] Evaluating email draft "
              f"(attempt {retry_count + 1}/{MAX_AGENT_RETRIES + 1})...")

        # Evaluate the first draft in a bulk list, or the single draft
        draft_to_eval = pending_draft[0] if isinstance(pending_draft, list) else pending_draft

        email_eval = evaluate_email_draft(
            email_draft=draft_to_eval,
            original_request=last_user_query,
        )
        eval_results["email_draft"] = email_eval

        overall = email_eval.get("overall", 10)
        passed  = email_eval.get("pass", True)
        issues  = [str(i) for i in email_eval.get("issues", []) if i]

        print(f"[EVAL] Email Draft → {overall}/10 | {'✅ PASS' if passed else '❌ FAIL'}")
        if issues:
            print(f"[EVAL] Issues: {'; '.join(issues)}")

        if not passed and retry_count < MAX_AGENT_RETRIES:
            print(f"[EVAL] Sending feedback to email_agent "
                  f"(retry {retry_count + 1}/{MAX_AGENT_RETRIES})...")
            suggested_body = email_eval.get("suggested_body")
            # Apply suggested body to the draft so email_agent has a starting point
            if suggested_body:
                if isinstance(pending_draft, list):
                    pending_draft = [{**pending_draft[0], "body": suggested_body}] + pending_draft[1:]
                else:
                    pending_draft = {**pending_draft, "body": suggested_body}
            eval_feedback = _build_email_feedback(issues, suggested_body)
            next_route    = "retry_email"
            retry_agent   = "email_agent"
        elif not passed:
            print(f"[EVAL] ❌ Max retries reached — accepting email draft as-is.")

    new_retry_count = (retry_count + 1) if next_route in ("retry_hr", "retry_email") else 0

    # No retry needed — end the turn

    return {
        **state,
        "route":                 next_route,
        "last_eval":             eval_results,
        "eval_feedback":         eval_feedback,
        "retry_agent":           retry_agent,
        "retry_count":           new_retry_count,
        "pending_email_draft":   pending_draft,
        "orchestrator_feedback": None,   # always clear after use
    }


# ─────────────────────────────────────────────
# ON-DEMAND EVALUATOR
# ─────────────────────────────────────────────
def run_manual_evaluation(
    eval_type: str,
    *,
    user_query: str = "",
    assistant_response: str = "",
    email_draft: dict = None,
    actual_route: str = "",
    conversation_history: list = None,
    db_ground_truth: str = None,
) -> dict:
    """
    Call this from outside the graph to evaluate any output on demand.
    eval_type: 'hr' | 'email' | 'routing'
    """
    if eval_type == "hr":
        return evaluate_hr_response(
            user_query, assistant_response,
            conversation_history or [], db_ground_truth,
        )
    elif eval_type == "email":
        if not email_draft:
            return {"error": "email_draft dict is required"}
        return evaluate_email_draft(email_draft, user_query)
    elif eval_type == "routing":
        if not actual_route:
            return {"error": "actual_route is required"}
        return evaluate_routing(user_query, actual_route, conversation_history or [])
    else:
        return {"error": f"Unknown eval_type '{eval_type}'. Use 'hr', 'email', or 'routing'."}


# ─────────────────────────────────────────────
# LOG READER
# ─────────────────────────────────────────────
def read_evaluation_log(last_n: int = 10) -> list[dict]:
    if not os.path.exists(EVAL_LOG_FILE):
        return []
    try:
        with open(EVAL_LOG_FILE, "r") as f:
            lines = f.readlines()
        return [json.loads(l) for l in lines if l.strip()][-last_n:]
    except Exception as e:
        print(f"[EVAL] Could not read log: {e}")
        return []