import os
import json
import time
import streamlit as st
from langchain_core.messages import HumanMessage, AIMessage

from build_index import build_index
from drive_loader.google_drive_loader import fetch_files_from_folder
from agent.orchestrator import graph

# =========================================================
# CONFIG
# =========================================================
FOLDER_ID = "1OQVILYMdPwOSU7Pj_4yxbp5DEsDQmI0x"

st.set_page_config(
    page_title="HR Copilot",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =========================================================
# STYLES
# =========================================================
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    .stApp {
        background-color: #FFFFFF;
    }

    section[data-testid="stSidebar"] {
        background-color: #F8FAFC;
        border-right: 1px solid #E5E7EB;
    }

    .app-title {
        font-size: 28px;
        font-weight: 700;
        color: #0F172A;
        margin-bottom: 4px;
    }

    .app-subtitle {
        font-size: 14px;
        color: #64748B;
        margin-bottom: 16px;
    }

    .welcome-card {
        background: #FFFFFF;
        border: 1px solid #E5E7EB;
        border-radius: 20px;
        padding: 28px;
        box-shadow: 0 4px 18px rgba(15, 23, 42, 0.05);
        margin-top: 20px;
    }

    .suggestion-chip {
        display: inline-block;
        padding: 10px 14px;
        border-radius: 999px;
        background: #EFF6FF;
        color: #1D4ED8;
        font-size: 14px;
        font-weight: 500;
        margin: 6px 8px 0 0;
        border: 1px solid #DBEAFE;
    }

    .email-card {
        background: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 18px;
        padding: 16px;
        margin-top: 10px;
        box-shadow: 0 4px 14px rgba(15, 23, 42, 0.05);
    }

    .email-title {
        font-size: 18px;
        font-weight: 700;
        color: #0F172A;
        margin-bottom: 10px;
    }

    .email-label {
        color: #475569;
        font-weight: 600;
    }

    .small-muted {
        color: #64748B;
        font-size: 13px;
    }

    .history-item {
        padding: 10px 12px;
        border-radius: 12px;
        background: #FFFFFF;
        border: 1px solid #E5E7EB;
        margin-bottom: 8px;
    }

    .history-title {
        font-size: 14px;
        font-weight: 600;
        color: #0F172A;
        margin-bottom: 2px;
    }

    .history-time {
        font-size: 12px;
        color: #64748B;
    }

    .logout-box {
        padding: 12px;
        border-top: 1px solid #E5E7EB;
        margin-top: 18px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# =========================================================
# INDEX MANAGEMENT
# =========================================================
def is_drive_updated() -> bool:
    if not os.path.exists("index_meta.json"):
        return True
    try:
        with open("index_meta.json", "r", encoding="utf-8") as f:
            old_ids = set(json.load(f))
        docs = fetch_files_from_folder(FOLDER_ID)
        new_ids = set(doc["file_id"] for doc in docs)
        return old_ids != new_ids
    except Exception as e:
        st.warning(f"Error checking Drive updates: {e}")
        return True


def ensure_index():
    if not os.path.exists("faiss_index"):
        with st.spinner("No index found. Building index..."):
            build_index()
    elif is_drive_updated():
        with st.spinner("Drive updated. Rebuilding index..."):
            build_index()


# =========================================================
# SESSION STATE
# =========================================================
def init_session():
    defaults = {
        "logged_in": False,
        "auth_token": None,
        "user_email": "",
        "chat_sessions": [],
        "active_chat_id": None,
        "pending_email_draft": None,
        "cancelled_email_draft": None,
        "index_ready": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def create_new_chat():
    chat_id = str(int(time.time() * 1000))
    chat = {
        "id": chat_id,
        "title": "New Chat",
        "timestamp": time.strftime("%d %b %Y, %I:%M %p"),
        "messages": [],
    }
    st.session_state.chat_sessions.insert(0, chat)
    st.session_state.active_chat_id = chat_id


def get_active_chat():
    for chat in st.session_state.chat_sessions:
        if chat["id"] == st.session_state.active_chat_id:
            return chat
    return None


def update_chat_title(chat, user_query: str):
    if chat and (chat["title"] == "New Chat" or not chat["title"].strip()):
        chat["title"] = user_query[:40] + ("..." if len(user_query) > 40 else "")


# =========================================================
# HELPERS
# =========================================================
def serialize_messages_for_graph(messages):
    graph_messages = []
    for msg in messages:
        if msg["role"] == "user":
            graph_messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            graph_messages.append(AIMessage(content=msg["content"]))
    return graph_messages


def parse_email_draft(draft):
    """
    Tries to normalize pending_email_draft into a dict.
    Supports:
    - dict draft
    - plain string draft
    """
    if not draft:
        return None

    if isinstance(draft, dict):
        return {
            "to": draft.get("to", ""),
            "subject": draft.get("subject", ""),
            "body": draft.get("body", ""),
            "cc": draft.get("cc", ""),
            "bcc": draft.get("bcc", ""),
        }

    if isinstance(draft, str):
        return {
            "to": "",
            "subject": "Email Draft",
            "body": draft,
            "cc": "",
            "bcc": "",
        }

    return {
        "to": "",
        "subject": "Email Draft",
        "body": str(draft),
        "cc": "",
        "bcc": "",
    }


def run_graph_query(chat_messages):
    initial_state = {
        "messages": serialize_messages_for_graph(chat_messages),
        "last_agent": "",
        "needs_input": False,
        "route": None,
        "pending_email_draft": st.session_state.pending_email_draft,
        "cancelled_email_draft": st.session_state.cancelled_email_draft,
        "last_eval": None,
        "db_ground_truth": None,
        "eval_feedback": None,
        "retry_count": 0,
        "retry_agent": None,
        "orchestrator_feedback": None,
        "orchestrator_retry_count": 0,
    }

    final_state = {}
    assistant_reply = None

    for chunk in graph.stream(initial_state, stream_mode="updates"):
        for node_name, node_output in chunk.items():
            if isinstance(node_output, dict):
                final_state = {**final_state, **node_output}

                if node_name in ("hr_agent", "email_agent"):
                    messages = node_output.get("messages", [])
                    if messages and isinstance(messages[-1], AIMessage):
                        assistant_reply = messages[-1].content

    if not assistant_reply:
        all_messages = final_state.get("messages", [])
        ai_msgs = [m for m in all_messages if isinstance(m, AIMessage)]
        if ai_msgs:
            assistant_reply = ai_msgs[-1].content

    st.session_state.pending_email_draft = final_state.get("pending_email_draft")
    st.session_state.cancelled_email_draft = final_state.get("cancelled_email_draft")

    return assistant_reply or "I could not generate a response."


# =========================================================
# LOGIN PAGE
# =========================================================
def login_page():
    col1, col2, col3 = st.columns([1, 1.1, 1])

    with col2:
        st.markdown("<div style='height: 8vh;'></div>", unsafe_allow_html=True)
        st.markdown(
            """
            <div class="welcome-card" style="max-width: 460px; margin: auto;">
                <div style="text-align:center; margin-bottom:20px;">
                    <div style="font-size:38px;">💼</div>
                    <div class="app-title">HR Copilot</div>
                    <div class="app-subtitle">Secure employee support and HR workflow assistant</div>
                </div>
            """,
            unsafe_allow_html=True,
        )

        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login", use_container_width=True)

            if submitted:
                if email and password:
                    st.session_state.logged_in = True
                    st.session_state.auth_token = "demo-token"
                    st.session_state.user_email = email

                    if not st.session_state.chat_sessions:
                        create_new_chat()

                    st.rerun()
                else:
                    st.error("Please enter both email and password.")

        st.markdown("</div>", unsafe_allow_html=True)


# =========================================================
# SIDEBAR
# =========================================================
def render_sidebar():
    with st.sidebar:

        if st.button("➕ New Chat", use_container_width=True):
            create_new_chat()
            st.rerun()

        search_term = st.text_input(
            "Search chat",
            placeholder="Search conversations..."
        )

        st.markdown("### Recent Chats")

        filtered_chats = st.session_state.chat_sessions
        if search_term.strip():
            filtered_chats = [
                c for c in st.session_state.chat_sessions
                if search_term.lower() in c["title"].lower()
            ]

        if not filtered_chats:
            st.caption("No chats found.")
        else:
            for chat in filtered_chats:
                is_active = chat["id"] == st.session_state.active_chat_id

                button_label = (
                    f"💬 {chat['title']}"
                )

                if st.button(
                    button_label,
                    key=f"chat_{chat['id']}",
                    use_container_width=True,
                    type="primary" if is_active else "secondary",
                ):
                    st.session_state.active_chat_id = chat["id"]
                    st.rerun()

        st.markdown("---")
        st.markdown(f"**👤 {st.session_state.user_email}**")

        if st.button("Logout", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.auth_token = None
            st.session_state.user_email = ""
            st.rerun()
# =========================================================
# EMAIL DRAFT CARD
# =========================================================
def render_email_draft_card():
    draft = parse_email_draft(st.session_state.pending_email_draft)
    if not draft:
        return

    st.markdown(
        f"""
        <div class="email-card">
            <div class="email-title">📧 Email Draft Preview</div>
            <div><span class="email-label">To:</span> {draft.get("to", "")}</div>
            <div><span class="email-label">CC:</span> {draft.get("cc", "")}</div>
            <div><span class="email-label">BCC:</span> {draft.get("bcc", "")}</div>
            <div><span class="email-label">Subject:</span> {draft.get("subject", "")}</div>
            <hr style="border:none; border-top:1px solid #E2E8F0; margin:12px 0;">
            <div style="white-space:pre-wrap; color:#0F172A;">{draft.get("body", "")}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns([1, 1, 4])

    with c1:
        if st.button("Confirm Send", type="primary", key="confirm_send_btn"):
            active_chat = get_active_chat()
            if active_chat:
                active_chat["messages"].append({
                    "role": "user",
                    "content": "yes"
                })

                with st.spinner("Sending email..."):
                    reply = run_graph_query(active_chat["messages"])

                active_chat["messages"].append({
                    "role": "assistant",
                    "content": reply
                })

            st.rerun()

    with c2:
        if st.button("Cancel", key="cancel_send_btn"):
            active_chat = get_active_chat()
            if active_chat:
                active_chat["messages"].append({
                    "role": "user",
                    "content": "no"
                })

                with st.spinner("Cancelling draft..."):
                    reply = run_graph_query(active_chat["messages"])

                active_chat["messages"].append({
                    "role": "assistant",
                    "content": reply
                })

            st.rerun()


# =========================================================
# MAIN CHAT UI
# =========================================================
def chat_page():
    render_sidebar()

    if not st.session_state.index_ready:
        ensure_index()
        st.session_state.index_ready = True

    active_chat = get_active_chat()
    if active_chat is None:
        create_new_chat()
        active_chat = get_active_chat()

    st.markdown("<div class='app-title'>HR Copilot</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='app-subtitle'>Ask employee, leave, HR policy, or email related questions.</div>",
        unsafe_allow_html=True,
    )

    if not active_chat["messages"]:
        # st.markdown(
        #     """
            
        #     </div>
        #     """,
        #     unsafe_allow_html=True,
        # )

        prompt_cols = st.columns(4)
        # suggestions = [
        #     "Find employee details for EMP0418",
        #     "Explain the leave policy",
        #     "Draft an email to my manager for planned leave",
        #     "Show attendance records for EMP0417",
        # ]
        # for idx, suggestion in enumerate(suggestions):
        #     with prompt_cols[idx]:
        #         if st.button(suggestion, key=f"suggestion_{idx}", use_container_width=True):
        #             active_chat["messages"].append({"role": "user", "content": suggestion})
        #             update_chat_title(active_chat, suggestion)

        #             with st.spinner("Thinking..."):
        #                 reply = run_graph_query(active_chat["messages"])

        #             active_chat["messages"].append({"role": "assistant", "content": reply})
        #             st.rerun()

    # Render chat
    for msg in active_chat["messages"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Render draft card if any
    render_email_draft_card()

    # Chat input
    user_query = st.chat_input("Ask something about HR, policies, employees, or email...")

    if user_query:
        active_chat["messages"].append({"role": "user", "content": user_query})
        update_chat_title(active_chat, user_query)

        with st.chat_message("user"):
            st.markdown(user_query)

        with st.chat_message("assistant"):
            with st.spinner("Typing..."):
                reply = run_graph_query(active_chat["messages"])
                st.markdown(reply)

        active_chat["messages"].append({"role": "assistant", "content": reply})
        st.rerun()


# =========================================================
# APP ENTRY
# =========================================================
def main():
    init_session()

    if not st.session_state.logged_in:
        login_page()
    else:
        chat_page()


if __name__ == "__main__":
    main()