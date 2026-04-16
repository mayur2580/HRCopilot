import re
from langchain_core.tools import tool
from rag.rag_pipeline import hr_policy_tool
from database.db_access import db_query
from langsmith import traceable


# ─────────────────────────────────────────────
# TOOL: RAG SEARCH
# ─────────────────────────────────────────────
@tool
@traceable(run_type="tool", tool_name="rag_search")
def rag_search(query: str) -> str:
    """Search HR policy documents for company rules, guidelines, and procedures.

    Use this tool for questions about:
    - Leave policies (sick leave, casual leave, annual leave, maternity, paternity)
    - Company rules, procedures, and guidelines
    - Employee benefits and entitlements
    - HR policies of any kind
    - Working hours, dress code, code of conduct

    Args:
        query: A natural language search query describing the policy topic.

    Returns:
        Relevant policy text extracted from HR documents.
    """
    result = hr_policy_tool(query)
    if not result:
        return "No relevant policy documents found."
    # Strip sources section — agent only needs the content
    return result.split("\n\n📄 Sources:")[0].split("\n\nSources:")[0].strip()


# ─────────────────────────────────────────────
# TOOL: DB QUERY
# ─────────────────────────────────────────────
@tool
@traceable(run_type="tool", tool_name="db_query_tool")
def db_query_tool(sql: str) -> str:
    """Run a SQL SELECT query against the HR database to fetch employee records.

    Use this tool for questions about:
    - Specific employee details (name, email, role, department, contact, address)
    - Leave balances (total_leaves, taken_leaves, pending_leaves)
    - Attendance records for a specific employee
    - Leave history (leave type, dates, status)
    - Manager information for an employee
    - Finding who holds a specific role or position in the company
   Example: SELECT full_name, email FROM employees WHERE role = 'CEO'

    Available tables and columns:
        employees:
            employee_id, full_name, email, role, department,
            date_of_joining, tenure_years, contact_no, gender, address,
            total_leaves, taken_leaves, pending_leaves,
            manager_id, manager_name

        attendance:
            employee_id, date, status

        leaves:
            employee_id, leave_type, start_date, end_date, days, status

    Args:
        sql: A valid SQL SELECT statement. Always use WHERE to filter by employee_id.

    Returns:
        Pipe-formatted query results, or a "no results" message if nothing is found.

    Examples:
        - "SELECT * FROM employees WHERE employee_id = 'EMP0418'"
        - "SELECT leave_type, days, status FROM leaves WHERE employee_id = 'EMP0418'"
        - "SELECT date, status FROM attendance WHERE employee_id = 'EMP0418'"
    """
    result = db_query(sql)
    return result if result else "No results found."


# ─────────────────────────────────────────────
# TOOL: FETCH EMPLOYEE  (used by email_agent)
# ─────────────────────────────────────────────
@tool
def fetch_employee_tool(emp_id: str) -> str:
    """Fetch core employee contact details needed for drafting emails.

    Returns the employee's full_name, email, role, department,
    manager_id, and manager_name.

    Use this whenever you need to look up who to send an email to,
    or need to find the manager of a given employee.

    Args:
        emp_id: The employee ID string, e.g. 'EMP0418'.

    Returns:
        Pipe-formatted employee record, or an error message if not found.
    """
    emp_id = emp_id.strip().upper()
    result = db_query(
        f"SELECT employee_id, full_name, email, role, department, "
        f"manager_id, manager_name FROM employees WHERE employee_id = '{emp_id}'"
    )
    if not result or "|" not in result:
        return f"Employee {emp_id} not found in database."
    return result


# ─────────────────────────────────────────────
# EXPORTS
# ─────────────────────────────────────────────
HR_TOOLS    = [rag_search, db_query_tool]        # used by hr_agent
EMAIL_TOOLS = [fetch_employee_tool]              # used by email_agent (DB lookups only)
ALL_TOOLS   = [rag_search, db_query_tool, fetch_employee_tool]


# ─────────────────────────────────────────────
# SHARED HELPER — used by hr_agent after tool calls
# ─────────────────────────────────────────────
_NO_ROWS_PATTERNS = re.compile(
    r"(no rows|no results|0 rows|not found|does not exist|empty result|no data)",
    re.IGNORECASE,
)

def db_returned_data(db_output: str) -> bool:
    """Returns True if the DB output contains actual data rows."""
    if not db_output or not db_output.strip():
        return False
    stripped = db_output.strip()
    if _NO_ROWS_PATTERNS.fullmatch(stripped):
        return False
    if "|" in db_output:
        return True
    if _NO_ROWS_PATTERNS.search(stripped) and len(stripped) < 60:
        return False
    return True