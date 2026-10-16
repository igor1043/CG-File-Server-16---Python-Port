from core import connect
db=connect()
for row in db.execute('PRAGMA index_list(mappings)'):print(tuple(row),flush=True)
for sql in ("SELECT c.key,c.topic,c.transcript,c.wav,c.status,s.path FROM clips c LEFT JOIN mappings m ON m.clip=c.key AND m.profile=? LEFT JOIN sources s ON s.key=m.source",):
    for row in db.execute('EXPLAIN QUERY PLAN '+sql,('Vilani',)):print(tuple(row),flush=True)
print('Counts',db.execute('SELECT count(*) FROM clips').fetchone()[0],db.execute('SELECT count(*) FROM mappings').fetchone()[0],flush=True)
db.close()
