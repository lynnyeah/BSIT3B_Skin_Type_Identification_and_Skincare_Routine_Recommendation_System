import sqlite3
conn = sqlite3.connect('db.sqlite3')
cur = conn.cursor()
cur.execute(\
SELECT
name
FROM
sqlite_master
WHERE
type=table
ORDER
BY
name\)
for r in cur.fetchall():
    print(r[0])
conn.close()
