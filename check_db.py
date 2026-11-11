import sqlite3
c=sqlite3.connect('storage/smartclear.db')
print([r[0] for r in c.execute("select name from sqlite_master where type='table'").fetchall()])
for t in ['cases']:
    print(t, [r[1] for r in c.execute(f'pragma table_info({t})').fetchall()])
print('count', c.execute('select count(*) from cases').fetchone())
rows = c.execute('select id, filename from cases').fetchall()
print('first', rows[:3])
print('ids sample', [r[0] for r in rows[:5]])
