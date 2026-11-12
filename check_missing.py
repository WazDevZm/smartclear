import sqlite3, os, glob
c=sqlite3.connect('storage/smartclear.db')
rows = {r[1] for r in c.execute('select id, filename from cases').fetchall()}
expected = {os.path.basename(p) for p in glob.glob('data/synthetic_nrc/*.pdf')}
missing = sorted(expected - rows)
print('missing count', len(missing))
print(missing)
