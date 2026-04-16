import sqlite3

conn = sqlite3.connect("database/hr.db")
cursor = conn.cursor()

cursor.execute("SELECT * FROM employees LIMIT 5")

for row in cursor.fetchall():
    print(row)

conn.close()