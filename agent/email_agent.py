import os
import re
import json
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_groq import ChatGroq

from agent.state import AgentState
from agent.email_service import dispatch_email
from tools.tools import fetch_employee_tool
from database.db_access import db_query
from langsmith import traceable

# ─────────────────────────────────────────────
# LLM
# ─────────────────────────────────────────────
llm = ChatGroq(
    groq_api_key=os.environ.get("GROQ_API_KEY"),
    model="meta-llama/llama-4-scout-17b-16e-instruct",
    # model="qwen/qwen3-32b",
    temperature=0.3
)

HR_SENDER_NAME  = "HR Department"
HR_SENDER_EMAIL = "hr@dhurandharai.com"


# ─────────────────────────────────────────────
# SYSTEM PROMPT
# ─────────────────────────────────────────────
EMAIL_SYSTEM_PROMPT = """You are an HR email drafting assistant.

You will be given REAL DATA already fetched from the database.
Use it exactly — NEVER invent or guess any email address or name.

The data block will contain:
  SENDER:    who is sending the email
  RECIPIENT: who is receiving the email

Return ONLY a valid JSON object, no markdown, no extra text:

{
  "to_email":    "recipient's exact email from the RECIPIENT block",
  "to_name":     "recipient's exact full_name from the RECIPIENT block",
  "subject":     "email subject line matching the body content",
  "body":        "full professional email body",
  "sender_name": "exact name from the SENDER block",
  "sender_id":   "exact email from the SENDER block"
}

STRICT RULES:
- to_email and to_name MUST come from the RECIPIENT block — never from SENDER
- sender_name and sender_id MUST come from the SENDER block — never from RECIPIENT
- Body greeting: "Dear <RECIPIENT first name>," — use RECIPIENT's first name only
- Body sign-off: use SENDER's full name exactly as given
- Subject must accurately reflect the body content
- Write a professional, warm, and concise email body
- Return ONLY the JSON, no explanation
"""


# ─────────────────────────────────────────────
# CONSTANTS & PATTERNS
# ─────────────────────────────────────────────
JSON_PATTERN = re.compile(r"\{[\s\S]*\}", re.DOTALL)

EMPLOYEE_SENDER_PHRASES = [
    "my manager", "to my manager", "to manager",
    "mail my manager", "email my manager",
    "inform my manager", "notify my manager",
    "write to my manager", "send to my manager",
]

HR_SENDER_PHRASES = [
    "send email to emp", "send mail to emp",
    "draft email to emp", "write email to emp",
    "email emp", "notify emp", "inform emp",
    "send him", "send her", "send them",
    "drop a mail to emp", "remind emp",
    "warn emp", "alert emp",
]

REDIRECT_PHRASES = [
    r"send\s+(this|it|the\s+mail|the\s+email)\s+to",
    r"forward\s+(this|it)\s+to",
    r"mail\s+to\s+\w+",
    r"send\s+to\s+\w+'?s?\s+manager",
    r"\w+'?s?\s+manager",
]

CC_PATTERNS = [
    r'\bcc\b', r"\bcc'?d\b", r'\bin\s+cc\b', r'\badd.*\bcc\b', r'\bcc.*to\b',
    r'\bcopy\s+to\b', r'\bkeep.*in\s+loop\b', r'\bloop\s+in\b', r'\bcarbon\s+copy\b',
]

BULK_PHRASES = [
    r'same\s+(mail|email|message)\s+to',
    r'send\s+(it|this|same)\s+to',
    r'also\s+send\s+to',
    r'forward\s+to',
]


# ─────────────────────────────────────────────
# INTENT DETECTION
# ─────────────────────────────────────────────
def detect_sender_type(user_request: str, conversation_history: list) -> str:
    text = user_request.lower()
    if any(phrase in text for phrase in EMPLOYEE_SENDER_PHRASES):
        return "employee"
    if any(phrase in text for phrase in HR_SENDER_PHRASES):
        return "hr"
    for msg in reversed(conversation_history[-4:]):
        if any(phrase in msg.content.lower() for phrase in EMPLOYEE_SENDER_PHRASES):
            return "employee"
    return "hr"


def is_manager_recipient(user_request: str) -> bool:
    return any(phrase in user_request.lower() for phrase in EMPLOYEE_SENDER_PHRASES)


def is_manager_redirect(user_request: str) -> bool:
    """True when user redirects a cancelled draft to a manager."""
    text = user_request.lower()
    return "manager" in text and any(re.search(p, text) for p in REDIRECT_PHRASES)


def is_cc_request(user_request: str) -> bool:
    return any(re.search(p, user_request.lower()) for p in CC_PATTERNS)


def is_bulk_request(user_request: str) -> bool:
    if len(re.findall(r'\bEMP\d+\b', user_request, re.IGNORECASE)) > 1:
        return True
    return any(re.search(p, user_request.lower()) for p in BULK_PHRASES)


# ─────────────────────────────────────────────
# EMP ID HELPERS
# ─────────────────────────────────────────────
def resolve_emp_ids(user_request: str) -> list[str]:
    return [e.upper() for e in re.findall(r'\bEMP\d+\b', user_request, re.IGNORECASE)]


def resolve_emp_id_from_history(conversation_history: list) -> str | None:
    for msg in reversed(conversation_history):
        ids = re.findall(r'\bEMP\d+\b', msg.content, re.IGNORECASE)
        if ids:
            return ids[-1].upper()
    return None


def resolve_emp_id_from_cancelled_draft(cancelled_draft: dict | None) -> str | None:
    """
    Recover EMP ID from a cancelled draft's sender email.
    Used when user cancels then redirects without repeating the EMP ID.
    """
    if not cancelled_draft:
        return None
    sender_email = cancelled_draft.get("sender_id", "")
    if not sender_email or sender_email == HR_SENDER_EMAIL:
        return None
    result = db_query(
        f"SELECT employee_id FROM employees WHERE email = '{sender_email}'"
    )
    if not result or "|" not in result:
        return None
    for line in result.strip().split("\n"):
        line = line.strip()
        if "|" in line and "---" not in line and "employee_id" not in line.lower():
            emp_id = line.split("|")[0].strip()
            if emp_id.upper().startswith("EMP"):
                return emp_id.upper()
    return None


# ─────────────────────────────────────────────
# DB HELPERS
# ─────────────────────────────────────────────
def extract_field(db_output: str, field: str) -> str | None:
    """Parse a column value from pipe-formatted db output."""
    lines    = [l.strip() for l in db_output.strip().split("\n") if l.strip()]
    header   = None
    data_row = None
    for line in lines:
        if "|" in line and "---" not in line:
            if header is None:
                header = [c.strip().lower() for c in line.split("|")]
            else:
                data_row = [c.strip() for c in line.split("|")]
                break
    if not header or not data_row:
        return None
    if field.lower() in header:
        idx = header.index(field.lower())
        val = data_row[idx] if idx < len(data_row) else None
        return val if val and val != "-" else None
    return None


def fetch_employee(emp_id: str) -> dict | None:
    """Fetch employee data via fetch_employee_tool."""
    raw = fetch_employee_tool.invoke({"emp_id": emp_id})
    if not raw or "|" not in raw or "not found" in raw.lower():
        return None
    name  = extract_field(raw, "full_name")
    email = extract_field(raw, "email")
    if not name or not email:
        return None
    return {"emp_id": emp_id, "full_name": name, "email": email, "raw": raw}


def fetch_manager(employee_raw: str) -> dict | None:
    """Fetch the manager of an employee using their raw DB record."""
    manager_id = extract_field(employee_raw, "manager_id")
    if not manager_id or "EMP" not in manager_id.upper():
        return None
    raw = db_query(
        f"SELECT full_name, email FROM employees WHERE employee_id = '{manager_id}'"
    )
    if not raw or "|" not in raw:
        return None
    name  = extract_field(raw, "full_name")
    email = extract_field(raw, "email")
    if not name or not email:
        return None
    return {"full_name": name, "email": email}


# ─────────────────────────────────────────────
# HISTORY HELPERS
# ─────────────────────────────────────────────
def get_last_email_body(conversation_history: list) -> str | None:
    for msg in reversed(conversation_history):
        if isinstance(msg, AIMessage) and "Type 'yes' to send or 'no' to cancel." in msg.content:
            lines      = msg.content.split("\n")
            body_lines = []
            in_body    = False
            for line in lines:
                if line.startswith("Subject:"):
                    in_body = True
                    continue
                if "Type 'yes' to send or 'no' to cancel." in line:
                    break
                if in_body:
                    body_lines.append(line)
            body = "\n".join(body_lines).strip()
            if body:
                return body
    return None


def get_last_email_subject(conversation_history: list) -> str | None:
    for msg in reversed(conversation_history):
        if isinstance(msg, AIMessage) and "Subject:" in msg.content:
            for line in msg.content.split("\n"):
                if line.startswith("Subject:"):
                    return line.replace("Subject:", "").strip()
    return None


# ─────────────────────────────────────────────
# CC RESOLVER
# ─────────────────────────────────────────────
def resolve_cc_list(user_request: str, exclude_emp_ids: list[str] = None) -> list[dict]:
    exclude    = set(e.upper() for e in (exclude_emp_ids or []))
    cc_ids     = []
    cc_pattern = re.compile(
        r'(?:cc|copy|loop\s+in|keep.*in\s+loop)\s+((?:\bEMP\d+\b[\s,and]*)+)',
        re.IGNORECASE
    )
    match = cc_pattern.search(user_request)
    if match:
        cc_ids = re.findall(r'\bEMP\d+\b', match.group(1), re.IGNORECASE)

    cc_list = []
    for emp_id in cc_ids:
        emp_id = emp_id.upper()
        if emp_id in exclude:
            continue
        data = fetch_employee(emp_id)
        if data:
            cc_list.append({"full_name": data["full_name"], "email": data["email"]})
    return cc_list


# ─────────────────────────────────────────────
# DRAFT EMAIL (single recipient)
# ─────────────────────────────────────────────
def draft_email(
    user_request: str,
    conversation_history: list,
    sender_type: str,
    recipient_emp_id: str | None = None,
    reuse_body: str | None = None,
    reuse_subject: str | None = None,
    cc_list: list[dict] | None = None,
    cancelled_draft: dict | None = None,
) -> dict | None:
    """
    Draft a single email.

    FIX: Sender and recipient are assigned in clearly separated blocks.
    For employee→manager flow, sender (employee) is locked first,
    then recipient (manager) is resolved independently — they never overlap.
    """
    # ── Resolve employee EMP ID ──
    emp_id = recipient_emp_id
    if not emp_id:
        ids    = resolve_emp_ids(user_request)
        emp_id = ids[0] if ids else resolve_emp_id_from_history(conversation_history)
    if not emp_id:
        emp_id = resolve_emp_id_from_cancelled_draft(cancelled_draft)

    employee_data = fetch_employee(emp_id) if emp_id else None

    # ── FIX: Assign sender and recipient in separate, non-overlapping blocks ──
    if sender_type == "hr":
        # HR → Employee
        sender_name     = HR_SENDER_NAME
        sender_email    = HR_SENDER_EMAIL
        recipient_name  = employee_data["full_name"] if employee_data else None
        recipient_email = employee_data["email"]     if employee_data else None

    else:
        # Employee → Manager  (or Employee → Employee as fallback)
        # Step 1: Lock sender as the employee — never overwrite this
        sender_name  = employee_data["full_name"] if employee_data else None
        sender_email = employee_data["email"]     if employee_data else None

        # Step 2: Determine recipient independently
        if is_manager_recipient(user_request) or is_manager_redirect(user_request):
            manager = fetch_manager(employee_data["raw"]) if employee_data else None
            if manager:
                recipient_name  = manager["full_name"]
                recipient_email = manager["email"]
            else:
                print("[EMAIL_AGENT] ⚠️  Manager not found — cannot draft email.")
                return None
        else:
            recipient_name  = employee_data["full_name"] if employee_data else None
            recipient_email = employee_data["email"]     if employee_data else None

    # Guard: cannot draft without recipient
    if not recipient_email or not recipient_name:
        return None

    # ── Reuse path: adapt greeting only, skip LLM ──
    if reuse_body and recipient_name:
        adapted_body = re.sub(
            r'^(Dear\s+)\S+[,]?',
            f'Dear {recipient_name.split()[0]},',
            reuse_body,
            count=1,
            flags=re.MULTILINE,
        )
        return {
            "to_email":    recipient_email,
            "to_name":     recipient_name,
            "subject":     reuse_subject or "HR Communication",
            "body":        adapted_body,
            "sender_name": sender_name,
            "sender_id":   sender_email,
            "cc":          cc_list or [],
        }

    # ── LLM path ──
    context = (
        f"SENDER:\n  Name:  {sender_name}\n  Email: {sender_email}\n\n"
        f"RECIPIENT:\n  Name:  {recipient_name}\n  Email: {recipient_email}\n"
    )
    if employee_data:
        context += f"\nEMPLOYEE DETAILS:\n{employee_data['raw']}\n"
    if cc_list:
        cc_names = ", ".join(p["full_name"] for p in cc_list)
        context += f"\nCC: {cc_names}\n"

    lc_messages = [SystemMessage(content=EMAIL_SYSTEM_PROMPT)] + conversation_history
    lc_messages.append(HumanMessage(
        content=f"Draft an email for: {user_request}\n\nData:\n{context}"
    ))

    response_text = llm.invoke(lc_messages).content.strip()
    json_match    = JSON_PATTERN.search(response_text)
    if not json_match:
        return None

    try:
        email_dict = json.loads(re.sub(r'```json|```', '', json_match.group(0)).strip())
    except json.JSONDecodeError:
        return None

    # Hard-override all fields from DB — LLM must not invent any of these
    email_dict["to_email"]    = recipient_email
    email_dict["to_name"]     = recipient_name
    email_dict["sender_name"] = sender_name
    email_dict["sender_id"]   = sender_email
    email_dict["cc"]          = cc_list or []
    return email_dict


# ─────────────────────────────────────────────
# PREVIEW BUILDERS
# ─────────────────────────────────────────────
def _build_preview(email_draft: dict) -> str:
    cc_list = email_draft.get("cc", [])
    cc_line = ""
    if cc_list:
        cc_str  = ", ".join(f"{p['full_name']} <{p['email']}>" for p in cc_list)
        cc_line = f"CC:      {cc_str}\n"
    return (
        f"Here is the email draft:\n\n"
        f"From:    {email_draft.get('sender_name', '')} <{email_draft.get('sender_id', '')}>\n"
        f"To:      {email_draft.get('to_name', '')} <{email_draft.get('to_email', '')}>\n"
        f"{cc_line}"
        f"Subject: {email_draft.get('subject', '')}\n\n"
        f"{email_draft.get('body', '')}"
    )


def _build_bulk_preview(drafts: list[dict]) -> str:
    lines = [f"The same email will be sent to {len(drafts)} recipients:\n"]
    for i, d in enumerate(drafts, 1):
        cc_list = d.get("cc", [])
        cc_str  = ""
        if cc_list:
            cc_str = "  CC: " + ", ".join(f"{p['full_name']} <{p['email']}>" for p in cc_list) + "\n"
        lines.append(f"  {i}. To: {d['to_name']} <{d['to_email']}>\n{cc_str}")
    lines.append(f"\nSubject: {drafts[0].get('subject', '')}\n")
    lines.append(f"{drafts[0].get('body', '')}\n")
    return "\n".join(lines)

# ─────────────────────────────────────────────
# EMAIL AGENT NODE
# ─────────────────────────────────────────────
@traceable(run_type="chain", name="email_agent_node")
def email_agent_node(state: AgentState) -> AgentState:
    messages        = state["messages"]
    last_message    = messages[-1].content.strip()
    last_lower      = last_message.lower()
    pending_draft   = state.get("pending_email_draft")
    cancelled_draft = state.get("cancelled_email_draft")

    # ── Confirm send ──
    if pending_draft and last_lower in ["yes", "confirm", "send", "ok", "y", "yes send it"]:

        if isinstance(pending_draft, list):
            results = []
            for draft in pending_draft:
                success, msg = dispatch_email(
                    to_email=draft["to_email"],
                    to_name =draft["to_name"],
                    subject =draft["subject"],
                    body    =draft["body"],
                    cc_list =draft.get("cc", []),
                )
                results.append((draft["to_name"], draft["to_email"], success, msg))
            sent   = [r for r in results if r[2]]
            failed = [r for r in results if not r[2]]
            parts  = []
            if sent:
                parts.append("Emails successfully sent to: " +
                             ", ".join(f"{n} ({e})" for n, e, _, _ in sent) + ".")
            if failed:
                parts.append("Failed to send to: " +
                             ", ".join(f"{n} ({e}): {m}" for n, e, _, m in failed) + ".")
            reply = " ".join(parts)
        else:
            success, result_msg = dispatch_email(
                to_email=pending_draft["to_email"],
                to_name =pending_draft["to_name"],
                subject =pending_draft["subject"],
                body    =pending_draft["body"],
                cc_list =pending_draft.get("cc", []),
            )
            reply = (
                f"Email successfully sent to {pending_draft['to_name']} ({pending_draft['to_email']})."
                if success else f"Failed to send email: {result_msg}"
            )

        return {
            **state,
            "messages":              messages + [AIMessage(content=reply)],
            "last_agent":            "email_agent",
            "route":                 "done",
            "pending_email_draft":   None,
            "cancelled_email_draft": None,
        }

    # ── Cancel — FIX: preserve draft so next turn can recover EMP ID ──
    if pending_draft and last_lower in ["no", "cancel", "n", "don't send", "stop"]:
        return {
            **state,
            "messages":              messages + [AIMessage(content="Email cancelled. Let me know if you'd like to make changes or draft a new one.")],
            "last_agent":            "email_agent",
            "route":                 "done",
            "pending_email_draft":   None,
            "cancelled_email_draft": pending_draft,   # ← preserved for redirect recovery
        }

    # ── New email request ──
    conversation_history = [
        msg for msg in messages[:-1]
        if isinstance(msg, (HumanMessage, AIMessage))
    ]
    user_request = last_message
    sender_type  = detect_sender_type(user_request, conversation_history)

    cc_list       = resolve_cc_list(user_request) if is_cc_request(user_request) else []
    recipient_ids = resolve_emp_ids(user_request)

    if cc_list:
        cc_pattern = re.compile(
            r'(?:cc|copy|loop\s+in|keep.*in\s+loop)\s+((?:\bEMP\d+\b[\s,and]*)+)',
            re.IGNORECASE
        )
        m = cc_pattern.search(user_request)
        if m:
            cc_emp_set    = {e.upper() for e in re.findall(r'\bEMP\d+\b', m.group(1), re.IGNORECASE)}
            recipient_ids = [e for e in recipient_ids if e not in cc_emp_set]

    # ── Bulk send ──
    if is_bulk_request(user_request) and len(recipient_ids) > 1:
        reuse_body    = get_last_email_body(conversation_history)
        reuse_subject = get_last_email_subject(conversation_history)
        drafts        = []
        failed_ids    = []
        for emp_id in recipient_ids:
            draft = draft_email(
                user_request=user_request,
                conversation_history=conversation_history,
                sender_type=sender_type,
                recipient_emp_id=emp_id,
                reuse_body=reuse_body,
                reuse_subject=reuse_subject,
                cc_list=cc_list,
                cancelled_draft=cancelled_draft,
            )
            if draft:
                drafts.append(draft)
            else:
                failed_ids.append(emp_id)

        if not drafts:
            return {
                **state,
                "messages":   messages + [AIMessage(content="I wasn't able to find any of those employees. Please check the employee IDs.")],
                "last_agent": "email_agent",
                "route":      "done",
            }

        preview = _build_bulk_preview(drafts)
        if failed_ids:
            preview += f"\n\n⚠️  Could not find records for: {', '.join(failed_ids)} — they will be skipped."

        return {
            **state,
            "messages":              messages + [AIMessage(content=preview)],
            "last_agent":            "email_agent",
            "route":                 "done",
            "pending_email_draft":   drafts,
            "cancelled_email_draft": None,
        }

    # ── Single send ──
    email_draft = draft_email(
        user_request=user_request,
        conversation_history=conversation_history,
        sender_type=sender_type,
        cc_list=cc_list,
        cancelled_draft=cancelled_draft,
    )

    if not email_draft:
        return {
            **state,
            "messages":   messages + [AIMessage(content="I wasn't able to draft the email. Could you provide more details about who to send it to and what it should say?")],
            "last_agent": "email_agent",
            "route":      "done",
        }

    preview = _build_preview(email_draft)
    return {
        **state,
        "messages":              messages + [AIMessage(content=preview)],
        "last_agent":            "email_agent",
        "route":                 "done",
        "pending_email_draft":   email_draft,
        "cancelled_email_draft": None,
    }