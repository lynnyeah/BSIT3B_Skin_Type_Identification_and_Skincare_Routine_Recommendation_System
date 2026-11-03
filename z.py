import sqlite3; c=sqlite3.connect('db.sqlite3'); [print(r[0]) for r in c.execute(\
SELECT
name
FROM
sqlite_master
WHERE
type=table\)]; c.close()
