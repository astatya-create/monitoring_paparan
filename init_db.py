import sqlite3

conn = sqlite3.connect("monitoring.db")
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    judul TEXT,
    unit TEXT,
    pic TEXT,
    wa_pic TEXT,
    deadline TEXT,
    progress INTEGER DEFAULT 0,
    status TEXT,
    instruksi TEXT,
    instruksi_file TEXT,
    output_file TEXT,
    catatan TEXT,
    update_terakhir TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    password TEXT,
    role TEXT
)
""")

conn.commit()
conn.close()

print("Database berhasil dibuat: monitoring.db")
