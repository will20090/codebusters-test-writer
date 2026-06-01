import os, json, psycopg2
from psycopg2.extras import RealDictCursor
from cryptography.fernet import Fernet

DATABASE_URL = os.environ['DATABASE_URL']
ENCRYPTION_KEY = os.environ['ENCRYPTION_KEY']
f = Fernet(ENCRYPTION_KEY.encode())

conn = psycopg2.connect(DATABASE_URL, sslmode='require')
conn.autocommit = True
cur = conn.cursor(cursor_factory=RealDictCursor)

cur.execute('SELECT id, questions FROM tests WHERE questions_encrypted IS NULL')
rows = cur.fetchall()
print(f'Migrating {len(rows)} tests...')

cur2 = conn.cursor()
for row in rows:
    questions = row['questions'] or []
    encrypted = f.encrypt(json.dumps(questions).encode()).decode()
    cur2.execute('UPDATE tests SET questions_encrypted = %s WHERE id = %s', (encrypted, row['id']))
    print(f'  Encrypted test {row["id"]}')

cur.close(); cur2.close(); conn.close()
print('Done.')