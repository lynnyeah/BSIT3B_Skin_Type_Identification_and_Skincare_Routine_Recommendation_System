import sqlite3
c = sqlite3.connect("db.sqlite3")
cur = c.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type=\"table\" AND (name LIKE \"%core%\" OR name LIKE \"%skin%\" OR name LIKE \"%analysis%\" OR name LIKE \"%routine%\" OR name LIKE \"%profile%\") ORDER BY name")
for r in cur.fetchall():
    print(r[0])
c.close()
