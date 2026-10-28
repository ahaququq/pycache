import sqlite3

conn = sqlite3.connect("/app/app/data/cache_server.db")
rows = conn.execute("SELECT local_path, exists_upstream, unavailable, unavailable_reason FROM files WHERE local_path = ?", ("gradle/8.5/gradle-8.5-bin.zip",)).fetchall()
print("Rows found:", len(rows))
for r in rows:
    print(dict(zip(["local_path", "exists_upstream", "unavailable", "unavailable_reason"], r)))