# import os
# import json
# from langchain_core.messages import HumanMessage, AIMessage
# from build_index import build_index
# from drive_loader.google_drive_loader import fetch_files_from_folder
# from agent.orchestrator import graph

# FOLDER_ID = "1OQVILYMdPwOSU7Pj_4yxbp5DEsDQmI0x"

# # ─────────────────────────────────────────────
# # INDEX MANAGEMENT
# # ─────────────────────────────────────────────
# def is_drive_updated() -> bool:
#     if not os.path.exists("index_meta.json"):
#         return True
#     try:
#         with open("index_meta.json", "r") as f:
#             old_ids = set(json.load(f))
#         docs    = fetch_files_from_folder(FOLDER_ID)
#         new_ids = set(doc["file_id"] for doc in docs)
#         return old_ids != new_ids
#     except Exception as e:
#         print("⚠️  Error checking Drive updates:", e)
#         return True


# def ensure_index():
#     if not os.path.exists("faiss_index"):
#         print("\n⚡ No index found. Building index...")
#         build_index()
#     elif is_drive_updated():
#         print("\n🔄 Drive updated. Rebuilding index...")
#         build_index()
#     else:
#         print("\n✅ Index is up-to-date")


# # ─────────────────────────────────────────────
# # STREAM RUNNER
# # ─────────────────────────────────────────────
# def stream_graph(initial_state: dict) -> dict:
#     """
#     Streams the graph from start to END.
#     Prints assistant response as soon as hr_agent / email_agent node finishes.
#     No interrupts — evaluation goes straight to END (or retry on fail).
#     """
#     final_state = {}

#     for chunk in graph.stream(initial_state, stream_mode="updates"):
#         for node_name, node_output in chunk.items():
#             if isinstance(node_output, dict):
#                 final_state = {**final_state, **node_output}

#                 if node_name in ("hr_agent", "email_agent"):
#                     messages = node_output.get("messages", [])
#                     if messages and isinstance(messages[-1], AIMessage):
#                         print(f"\nAssistant: {messages[-1].content}\n")

#     return final_state


# # ─────────────────────────────────────────────
# # MAIN LOOP
# # ─────────────────────────────────────────────
# def run_assistant():
#     print("\n" + "=" * 50)
#     print("HR Assistant Running...")
#     print("=" * 50 + "\n")

#     chat_history          = []
#     pending_email_draft   = None
#     cancelled_email_draft = None

#     while True:
#         try:
#             query = input("You: ").strip()
#             if not query:
#                 continue
#             if query.lower() in ["exit", "quit"]:
#                 print("\nExiting Assistant...")
#                 break

#             chat_history.append(HumanMessage(content=query))

#             initial_state = {
#                 "messages":                  chat_history,
#                 "last_agent":                "",
#                 "needs_input":               False,
#                 "route":                     None,
#                 "pending_email_draft":       pending_email_draft,
#                 "cancelled_email_draft":     cancelled_email_draft,
#                 "last_eval":                 None,
#                 "db_ground_truth":           None,
#                 # agent feedback loop
#                 "eval_feedback":             None,
#                 "retry_count":               0,
#                 "retry_agent":               None,
#                 # orchestrator feedback loop
#                 "orchestrator_feedback":     None,
#                 "orchestrator_retry_count":  0,
#             }

#             final_state = stream_graph(initial_state)

#             # Persist the last AI message into chat history
#             all_messages = final_state.get("messages", [])
#             ai_msgs      = [m for m in all_messages if isinstance(m, AIMessage)]
#             if ai_msgs:
#                 last_ai = ai_msgs[-1]
#                 if not chat_history or not isinstance(chat_history[-1], AIMessage):
#                     chat_history.append(last_ai)
#                 elif chat_history[-1].content != last_ai.content:
#                     chat_history.append(last_ai)

#             pending_email_draft   = final_state.get("pending_email_draft")
#             cancelled_email_draft = final_state.get("cancelled_email_draft")

#         except KeyboardInterrupt:
#             print("\n\nInterrupted. Exiting...")
#             break
#         except Exception as e:
#             import traceback
#             print(f"\nError: {e}")
#             traceback.print_exc()


# if __name__ == "__main__":
#     # ensure_index()
#     run_assistant()
