import sqlite3
import pandas as pd
import os

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH  = os.path.join(BASE_DIR, "database", "hr.db")

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

conn = sqlite3.connect(DB_PATH)

# Load and import CSVs — table names must match db_access.py and hr_agent.py
pd.read_csv(os.path.join(DATA_DIR, "dhurandharai_employees.csv")).to_sql(
    "employees", conn, if_exists="replace", index=False
)
pd.read_csv(os.path.join(DATA_DIR, "leave_history.csv")).to_sql(
    "leaves", conn, if_exists="replace", index=False      # ← "leaves" not "leave_history"
)
pd.read_csv(os.path.join(DATA_DIR, "attendance_logs.csv")).to_sql(
    "attendance", conn, if_exists="replace", index=False  # ← "attendance" not "attendance_logs"
)

conn.close()
print("Data imported successfully!")
print("Tables: employees, leaves, attendance")