# import sqlite3

# DB_PATH = "database/hr.db"


# def db_query(query: str) -> str:
#     """
#     Direct SQLite Database Access

#     Tables:
#     - employees
#     - attendance   (NOT attendance_logs)
#     - leaves       (NOT leave_history)

#     Only SELECT queries allowed.
#     """

#     # Safety Check
#     dangerous_keywords = ["drop", "delete", "truncate", "insert", "update", "alter"]
#     if any(word in query.lower() for word in dangerous_keywords):
#         return "Only SELECT queries are allowed for safety."

#     conn = sqlite3.connect(DB_PATH)
#     cursor = conn.cursor()

#     try:
#         cursor.execute(query)

#         if query.strip().lower().startswith("select"):
#             rows = cursor.fetchall()

#             if not rows:
#                 return "No data found."

#             # Get column names for readable output
#             col_names = [desc[0] for desc in cursor.description]

#             # Format as readable table
#             lines = []
#             lines.append(" | ".join(col_names))
#             lines.append("-" * len(lines[0]))
#             for row in rows:
#                 lines.append(" | ".join(str(v) if v is not None else "-" for v in row))

#             return "\n".join(lines)

#         else:
#             return "Only SELECT queries are allowed."

#     except Exception as e:
#         return f"Database error: {str(e)}"

#     finally:
#         conn.close()

import sqlite3
from pathlib import Path
from langsmith import traceable
# database/db_access.py
# Project root = parent of the "database" folder
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "database" / "hr.db"

@traceable(run_type="tool", name="db_access")
def db_query(query: str) -> str:
    """
    Direct SQLite Database Access

    Tables:
    - employees
    - attendance
    - leaves

    Only SELECT queries allowed.
    """

    dangerous_keywords = ["drop", "delete", "truncate", "insert", "update", "alter"]
    if any(word in query.lower() for word in dangerous_keywords):
        return "Only SELECT queries are allowed for safety."

    if not DB_PATH.exists():
        return f"Database file not found at: {DB_PATH}"

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    try:
        cursor.execute(query)

        if query.strip().lower().startswith("select"):
            rows = cursor.fetchall()

            if not rows:
                return "No data found."

            col_names = [desc[0] for desc in cursor.description]

            lines = []
            lines.append(" | ".join(col_names))
            lines.append("-" * len(lines[0]))
            for row in rows:
                lines.append(" | ".join(str(v) if v is not None else "-" for v in row))

            return "\n".join(lines)

        return "Only SELECT queries are allowed."

    except Exception as e:
        return f"Database error: {str(e)}"

    finally:
        conn.close()