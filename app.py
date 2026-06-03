import re
from flask import Flask, request, jsonify, send_file, session, render_template
import subprocess, tempfile, os, json, traceback, shutil, sys, datetime, uuid
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
from psycopg2.extras import RealDictCursor
from cryptography.fernet import Fernet

sys.path.insert(0, os.path.dirname(__file__))
import ciphers

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'codebusters-secret-key-change-this')
app.config['PERMANENT_SESSION_LIFETIME'] = datetime.timedelta(days=3650)
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = True

BASE = os.path.dirname(__file__)

# -- Database --

def get_db():
    conn = psycopg2.connect(
        os.environ['DATABASE_URL'],
        sslmode='require',
        connect_timeout=10
    )
    conn.autocommit = True
    return conn

def nid(): return uuid.uuid4().hex[:12]

def get_fernet():
    key = os.environ.get('ENCRYPTION_KEY')
    if not key:
        raise RuntimeError('ENCRYPTION_KEY not set')
    return Fernet(key.encode())

def encrypt_questions(questions_list):
    f = get_fernet()
    return f.encrypt(json.dumps(questions_list).encode()).decode()

def decrypt_questions(encrypted_str):
    if not encrypted_str:
        return []
    f = get_fernet()
    return json.loads(f.decrypt(encrypted_str.encode()).decode())

def log_history(tid, action, detail='', before=None, after=None):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            'INSERT INTO test_history (test_id, user_id, username, action, detail, before_data, after_data) VALUES (%s, %s, %s, %s, %s, %s, %s)',
            (tid, session.get('uid'), session.get('username'), action, detail,
             json.dumps(before) if before else None,
             json.dumps(after) if after else None)
        )
        cur.close(); conn.close()
    except Exception as e:
        print(f'[history] {e}')

def current_user():
    return session.get('uid')

def require_login():
    if not current_user():
        return jsonify({'error': 'Not logged in'}), 401
    return None

# -- Auth routes --

@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username','').strip().lower()
    password = data.get('password','').strip()
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    if len(username) < 3:
        return jsonify({'error': 'Username must be at least 3 characters'}), 400
    if len(password) < 4:
        return jsonify({'error': 'Password must be at least 4 characters'}), 400
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT id FROM users WHERE username = %s', (username,))
    if cur.fetchone():
        cur.close(); conn.close()
        return jsonify({'error': 'Username already taken'}), 400
    uid = nid()
    cur.execute(
        'INSERT INTO users (id, username, password, created) VALUES (%s, %s, %s, %s)',
        (uid, username, generate_password_hash(password), datetime.datetime.now().isoformat())
    )
    cur.close(); conn.close()
    session.permanent = True
    session['uid'] = uid
    session['username'] = username
    return jsonify({'ok': True, 'username': username})

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username','').strip().lower()
    password = data.get('password','').strip()
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('SELECT * FROM users WHERE username = %s', (username,))
    user = cur.fetchone()
    cur.close(); conn.close()
    if not user or not check_password_hash(user['password'], password):
        return jsonify({'error': 'Invalid username or password'}), 400
    session.permanent = True
    session['uid'] = user['id']
    session['username'] = user['username']
    return jsonify({'ok': True, 'username': user['username']})

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'ok': True})

@app.route('/api/me', methods=['GET'])
def me():
    if current_user():
        return jsonify({'uid': current_user(), 'username': session.get('username')})
    return jsonify({'uid': None, 'username': None})

# -- Test routes --

@app.route('/api/tests', methods=['GET'])
def get_tests():
    err = require_login()
    if err: return err
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(
        'SELECT id, name, created, modified, questions_encrypted, settings, true as owned FROM tests WHERE user_id = %s',
        (current_user(),)
    )
    owned = cur.fetchall()
    # Add question count from encrypted field
    owned_list = []
    for t in owned:
        t = dict(t)
        try:
            qs = decrypt_questions(t.get('questions_encrypted',''))
            t['count'] = len(qs)
        except:
            t['count'] = 0
        t.pop('questions_encrypted', None)
        settings = t.get('settings') or {}
        if isinstance(settings, str):
            try: settings = json.loads(settings)
            except: settings = {}
        t['is_practice'] = bool(settings.get('is_practice', False))
        t.pop('settings', None)
        owned_list.append(t)
    cur.execute(
        '''SELECT t.id, t.name, t.created, t.modified, t.questions_encrypted, t.settings, false as owned
           FROM tests t JOIN test_shares ts ON ts.test_id = t.id
           WHERE ts.user_id = %s ORDER BY t.modified DESC''',
        (current_user(),)
    )
    shared = cur.fetchall()
    shared_list = []
    for t in shared:
        t = dict(t)
        try:
            qs = decrypt_questions(t.get('questions_encrypted',''))
            t['count'] = len(qs)
        except:
            t['count'] = 0
        t.pop('questions_encrypted', None)
        settings = t.get('settings') or {}
        if isinstance(settings, str):
            try: settings = json.loads(settings)
            except: settings = {}
        t['is_practice'] = bool(settings.get('is_practice', False))
        t.pop('settings', None)
        shared_list.append(t)
    cur.close(); conn.close()
    return jsonify(owned_list + shared_list)

@app.route('/api/tests', methods=['POST'])
def create_test():
    err = require_login()
    if err: return err
    data = request.get_json()
    name = data.get('name','').strip()
    if not name: return jsonify({'error': 'Test name required'}), 400
    is_practice = bool(data.get('is_practice', False))
    tid = nid()
    now = datetime.datetime.now().isoformat()
    initial_settings = {'is_practice': True} if is_practice else {}
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        'INSERT INTO tests (id, user_id, name, created, modified, settings, questions_encrypted) VALUES (%s, %s, %s, %s, %s, %s, %s)',
        (tid, current_user(), name, now, now, json.dumps(initial_settings), encrypt_questions([]))
    )
    cur.close(); conn.close()
    log_history(tid, 'Created test', name)
    return jsonify({'id': tid, 'name': name, 'created': now, 'modified': now, 'settings': initial_settings, 'questions': []})

@app.route('/api/tests/<tid>', methods=['GET'])
def get_test(tid):
    err = require_login()
    if err: return err
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('''SELECT t.*, u.username as owner_username 
                   FROM tests t JOIN users u ON u.id = t.user_id
                   WHERE t.id = %s AND (t.user_id = %s OR t.id IN (SELECT test_id FROM test_shares WHERE user_id = %s))''', 
                (tid, current_user(), current_user()))
    t = cur.fetchone()
    cur.close(); conn.close()
    if not t: return jsonify({'error': 'Not found'}), 404
    t = dict(t)
    if t.get('questions_encrypted'):
        t['questions'] = decrypt_questions(t['questions_encrypted'])
    t.pop('questions_encrypted', None)
    return jsonify(t)

@app.route('/api/tests/<tid>', methods=['PUT'])
def update_test(tid):
    err = require_login()
    if err: return err
    data = request.get_json()
    now = datetime.datetime.now().isoformat()
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('SELECT settings, questions_encrypted FROM tests WHERE id = %s AND (user_id = %s OR id IN (SELECT test_id FROM test_shares WHERE user_id = %s))', (tid, current_user(), current_user()))    
    old = cur.fetchone()
    new_settings = data.get('settings', {})
    new_questions = data.get('questions', [])
    if old:
        old_settings = old['settings'] or {}
        old_questions = decrypt_questions(old['questions_encrypted'])
        if old_settings != new_settings:
            log_history(tid, 'Changed tournament settings', '', old_settings, new_settings)
        if len(old_questions) < len(new_questions):
            for i in range(len(old_questions), len(new_questions)):
                q = new_questions[i]
                log_history(tid, 'Added question', f"Q{i+1}: {q.get('cipher','')} — {q.get('plaintext','')}", None, q)
        elif len(old_questions) > len(new_questions):
            for i in range(len(new_questions), len(old_questions)):
                q = old_questions[i]
                log_history(tid, 'Deleted question', f"Q{i+1}: {q.get('cipher','')} — {q.get('plaintext','')}", q, None)
        elif len(old_questions) == len(new_questions) and len(old_questions) > 0:
            old_plaintexts = [q.get('plaintext','') for q in old_questions]
            new_plaintexts = [q.get('plaintext','') for q in new_questions]
            old_set = sorted(old_plaintexts)
            new_set = sorted(new_plaintexts)
            if old_set == new_set and old_plaintexts != new_plaintexts:
                # Pure reorder — find what moved
                moves = []
                for i, (op, np) in enumerate(zip(old_plaintexts, new_plaintexts)):
                    if op != np:
                        new_pos = new_plaintexts.index(op)
                        moves.append(f"Q{i+1} → Q{new_pos+1}")
                detail = ', '.join(moves)
                # Build before/after as ordered list of cipher+plaintext
                before_order = [{'pos': i+1, 'cipher': q.get('cipher',''), 'plaintext': q.get('plaintext','')} for i, q in enumerate(old_questions)]
                after_order  = [{'pos': i+1, 'cipher': q.get('cipher',''), 'plaintext': q.get('plaintext','')} for i, q in enumerate(new_questions)]
                log_history(tid, 'Reordered questions', detail, before_order, after_order)
            else:
                # Same count, not a pure reorder — check for edits
                for i, (oq, nq) in enumerate(zip(old_questions, new_questions)):
                    if oq.get('payload') != nq.get('payload') or oq.get('qtext') != nq.get('qtext'):
                        log_history(tid, 'Edited question', f"Q{i+1}: {nq.get('cipher','')} — {nq.get('plaintext','')}", oq, nq)
    cur2 = conn.cursor()
    cur2.execute(
        'UPDATE tests SET settings = %s, questions_encrypted = %s, modified = %s WHERE id = %s AND (user_id = %s OR id IN (SELECT test_id FROM test_shares WHERE user_id = %s))',
        (json.dumps(new_settings), encrypt_questions(new_questions), now, tid, current_user(), current_user())
    )
    cur2.close(); cur.close(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/tests/<tid>', methods=['DELETE'])
def del_test(tid):
    err = require_login()
    if err: return err
    conn = get_db()
    cur = conn.cursor()
    cur.execute('DELETE FROM tests WHERE id = %s AND user_id = %s', (tid, current_user()))
    cur.close(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/tests/<tid>/rename', methods=['POST'])
def rename_test(tid):
    err = require_login()
    if err: return err
    name = request.get_json().get('name','').strip()
    if not name: return jsonify({'error': 'Name required'}), 400
    conn = get_db()
    cur = conn.cursor()
    cur.execute('UPDATE tests SET name = %s WHERE id = %s AND user_id = %s', (name, tid, current_user()))
    cur.close(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/tests/<tid>/history', methods=['GET'])
def get_history(tid):
    err = require_login()
    if err: return err
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(
        'SELECT * FROM test_history WHERE test_id = %s ORDER BY created DESC LIMIT 200',
        (tid,)
    )
    rows = cur.fetchall()
    cur.close(); conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/tests/<tid>/history', methods=['POST'])
def add_history(tid):
    err = require_login()
    if err: return err
    d = request.get_json()
    log_history(tid, d.get('action',''), d.get('detail',''), d.get('before'), d.get('after'))
    return jsonify({'ok': True})

@app.route('/api/tests/<tid>/share', methods=['POST'])
def share_test(tid):
    err = require_login()
    if err: return err
    data = request.get_json()
    username = data.get('username','').strip().lower()
    if not username: return jsonify({'error': 'Username required'}), 400
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    # check target user exists
    cur.execute('SELECT id FROM users WHERE username = %s', (username,))
    target = cur.fetchone()
    if not target: cur.close(); conn.close(); return jsonify({'error': 'User not found'}), 404
    if target['id'] == current_user(): cur.close(); conn.close(); return jsonify({'error': 'Cannot share with yourself'}), 400
    # check test belongs to current user
    cur.execute('SELECT id FROM tests WHERE id = %s AND user_id = %s', (tid, current_user()))
    if not cur.fetchone(): cur.close(); conn.close(); return jsonify({'error': 'Not found'}), 404
    # insert share record (ignore if already exists)
    cur.execute('INSERT INTO test_shares (test_id, user_id) VALUES (%s, %s) ON CONFLICT DO NOTHING', (tid, target['id']))
    cur.close(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/tests/<tid>/shares', methods=['GET'])
def get_shares(tid):
    err = require_login()
    if err: return err
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('SELECT id FROM tests WHERE id = %s AND (user_id = %s OR id IN (SELECT test_id FROM test_shares WHERE user_id = %s))', (tid, current_user(), current_user()))
    if not cur.fetchone(): cur.close(); conn.close(); return jsonify({'error': 'Not found'}), 404
    cur.execute('SELECT u.username FROM test_shares ts JOIN users u ON u.id = ts.user_id WHERE ts.test_id = %s', (tid,))
    shares = [r['username'] for r in cur.fetchall()]
    cur.close(); conn.close()
    return jsonify(shares)

@app.route('/api/tests/<tid>/share/<username>', methods=['DELETE'])
def unshare_test(tid, username):
    err = require_login()
    if err: return err
    conn = get_db()
    cur = conn.cursor()
    cur.execute('DELETE FROM test_shares WHERE test_id = %s AND user_id = (SELECT id FROM users WHERE username = %s)', (tid, username))
    cur.close(); conn.close()
    return jsonify({'ok': True})

KEYWORD_CIPHERS = {'ARISTOCRAT', 'PATRISTOCRAT', 'XENOCRYPT'}

def latex_escape(s):
    return (str(s)
            .replace('\\', r'\textbackslash{}')
            .replace('&',  r'\&')
            .replace('%',  r'\%')
            .replace('$',  r'\$')
            .replace('#',  r'\#')
            .replace('^',  r'\^{}')
            .replace('_',  r'\_')
            .replace('{',  r'\{')
            .replace('}',  r'\}')
            .replace('~',  r'\textasciitilde{}'))

def make_answer_line(q_num, answer, bold, keyword=None, value=None, bonus=False):
    pts = f'({value} pts.) ' if value else ''
    star = r'$\bigstar$ ' if bonus else ''
    if keyword is not None and keyword != '':
        safe_kw = latex_escape(str(keyword))
        safe_pt = latex_escape(str(answer))
        return rf'\question {pts}{star}\textbf{{{safe_kw}}}: {safe_pt}' + '\n'
    safe = latex_escape(str(answer))
    return rf'\question {pts}{star}{safe}' + '\n'

def dispatch(row):
    cipher    = row.get('cipher','').upper()
    pt        = row.get('plaintext','')
    value     = row.get('value', 5)
    hint_type = row.get('hint_type','None')
    hint      = row.get('hint','')
    bonus     = bool(row.get('bonus', False))
    key1      = row.get('key1','')
    key2      = row.get('key2','')
    key3      = row.get('key3','')   # block size for nihilist/porta/affine/checkerboard
    key4      = row.get('key4','')   # crib plaintext for nihilist/porta/affine/checkerboard (CRIB type)
    rtype     = row.get('type','DECODE')
    extract   = (rtype == 'EXTRACT')

    if cipher == 'ARISTOCRAT':
        return ciphers.monoalph_creator(pt, value, 'Aristocrat', hint_type, hint,
                                        key3, key1, int(key2) if key2 else 0, extract)
    elif cipher == 'PATRISTOCRAT':
        return ciphers.monoalph_creator(pt, value, 'Patristocrat', hint_type, hint,
                                        key3, key1, int(key2) if key2 else 0, extract)
    elif cipher == 'ATBASH':
        return ciphers.atbash_encoder(pt, int(key3) if key3 else 5, value)
    elif cipher == 'BACONIAN':
        if rtype == 'WORDS':
            return ciphers.baconianWordsFormatter(pt, key1, key3, value, hint_type, bonus)
        else:
            btype = rtype if rtype != 'DECODE' else 'LETTERS'
            return ciphers.baconianLetters(pt, key1, key2, 55, value, btype, hint_type, hint, bonus)
    elif cipher == 'CAESAR':
        return ciphers.caesar_formatter(pt, int(key1), value, bonus)
    elif cipher == 'COLUMNAR':
        return ciphers.columnarFormatter(pt, int(key1), key2, value, bonus)
    elif cipher == 'CRYPTARITHM':
        return ciphers.cryptarithm_formatter(value, key1, key2, key3, bonus)
    elif cipher == 'FRACMORSE':
        return ciphers.fractionatedFormatter(pt, key1, key2, value, hint_type, hint, bonus)
    elif cipher == 'HILL':
        return ciphers.hillCreater(pt, key1, value, bonus)
    elif cipher == 'NIHILIST':
        # key1=keyword, key2=polybius key, key3=block size (always), key4=crib plaintext (CRIB only)
        bs_val = int(key3) if key3 != '' else 5
        crib_val = key4 if rtype == 'CRIB' else ''
        return ciphers.nihilistFormatter(pt, key1, key2, bs_val, value, rtype, hint_type, crib_val, bonus)
    elif cipher == 'PORTA':
        # key1=keyword, key3=block size (always), key4=crib plaintext (CRIB only)
        bs_val = int(key3) if key3 != '' else 5
        crib_val = key4 if rtype == 'CRIB' else ''
        return ciphers.porta_formatter(pt, key1, bs_val, value, rtype, hint_type, crib_val, bonus)
    elif cipher == 'XENOCRYPT':
        return ciphers.xeno_creator(pt, value, 'Aristocrat', hint_type, hint,
                                    key3, key1, int(key2) if key2 else 0, extract)
    elif cipher == 'AFFINE':
        # key1=a, key2=b, key3=block size (always), key4=crib plaintext (CRIB only)
        bs_val = int(key3) if key3 != '' else 5
        crib_val = key4 if rtype == 'CRIB' else ''
        return ciphers.affine_formatter(pt, key1, key2, bs_val, value, rtype, crib_val, bonus)
    elif cipher == 'CHECKERBOARD':
        # key1=hkey, key2=vkey, key3=polybius keyword, key5=block size... wait
        # Original: key1=H-key, key2=V-key, key3=Polybius keyword, hint=crib
        # New:      key1=H-key, key2=V-key, key3=Polybius keyword, key4=block size, key5=crib
        # But we only have key1-key4. Re-map: key1=hkey, key2=vkey, key3=pk, key4=block size
        # crib comes from hint field (kept as before for checkerboard)
        bs_val = int(key4) if key4 != '' else 5
        if rtype == 'DECODE':
            return ciphers.checkerboarddecode(pt, key1, key2, key3, bs_val, value, bonus)
        elif rtype == 'CRIB':
            return ciphers.checkerboardcrib(pt, key1, key2, key3, hint, bs_val, value, bonus)
    elif cipher == 'HOMOPHONIC':
        crib_val = key4 if rtype == 'CRIB' else ''
        return ciphers.homophonic_formatter(pt, key1, value, hint_type, hint, crib_val, bonus)
    else:
        raise ValueError(f"Unknown cipher: {cipher}")

@app.route('/api/generate', methods=['POST'])
def generate():
    err = require_login()
    if err: return err
    try:
        data   = request.get_json()
        latex  = dispatch(data)
        cipher = data.get('cipher','').upper()
        rtype  = data.get('type','DECODE')
        pt     = data.get('plaintext','')
        key1   = data.get('key1','')
        key2   = data.get('key2','')

        if rtype == 'EXTRACT' and cipher in KEYWORD_CIPHERS:
            answer      = pt
            answer_bold = True
            keyword     = key1
        elif cipher == 'CRYPTARITHM':
            answer      = key2 if key2 else pt
            answer_bold = False
            keyword     = None
        else:
            answer      = pt if pt else (key1 if key1 else '???')
            answer_bold = False
            keyword     = None

        return jsonify({
            'success': True, 'latex': latex,
            'answer': answer, 'answer_bold': answer_bold,
            'keyword': keyword, 'cipher': cipher, 'type': rtype,
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e), 'trace': traceback.format_exc()})


def build_latex(settings, questions_data, is_key=False):
    tournament   = settings.get('tournament', 'Tournament Name')
    division     = settings.get('division', 'Division')
    compdate     = settings.get('compdate', 'Date')
    tqvalue      = settings.get('tqvalue', '250')
    tqphrase     = settings.get('tqphrase', 'raise your hand')
    tqplaintext  = settings.get('tqcipher', 'PLAINTEXT HERE')
    writers      = settings.get('writers', 'INSERT WRITERS')
    bonus_nums   = settings.get('bonus_nums', 'INSERT BONUS QUESTION NUMBERS')
    cover_image  = settings.get('cover_image', '')
    exam_or_key  = 'KEY' if is_key else 'EXAM'
    printanswers = '%\\printanswers'

    import re as _re
    tq_clean = _re.sub(r'[^a-zA-Z ]', '', tqplaintext).upper()
    try:
        tq_encoded_raw = ciphers.aristo_letter_replacement(tqplaintext.upper())
        tqcipher = ciphers.aristo_format_sentence(tq_encoded_raw)
        tq_letters_only = _re.sub(r'[^A-Z]', '', tq_encoded_raw)
        tq_freq_row = '&'.join(str(tq_letters_only.count(chr(i+65))) for i in range(26))
    except Exception:
        tqcipher = tqplaintext.upper()
        tq_freq_row = '&'.join([''] * 26)

    img_latex = r'\fbox{\parbox[c][6cm][c]{10cm}{\centering\small xcoverart.png}}'
    if cover_image and cover_image.startswith('data:image'):
        import base64
        hdr, b64data = cover_image.split(',', 1)
        ext = 'png' if 'png' in hdr else 'jpg'
        img_tmp = os.path.join(tempfile.gettempdir(), f'cbcover.{ext}')
        with open(img_tmp, 'wb') as f:
            f.write(base64.b64decode(b64data))
        img_latex = rf'\includegraphics[width=10cm,height=6cm,keepaspectratio]{{{img_tmp}}}'

    compdate_line = rf'{{\large {compdate}}} \\[1.2em]' if compdate else ''
    if is_key:
        cover = rf"""
\begin{{center}}
{{\Large \textbf{{Codebusters {division} KEY}}}} \\[0.4em]
{{\large {tournament}}} \\[0.2em]
{compdate_line}
{img_latex}
\end{{center}}
\vspace{{2em}}
\begin{{mdframed}}
\textbf{{Grading Instructions:}}
\begin{{itemize}}[leftmargin=1.4em,itemsep=2pt,topsep=4pt]
  \item \textbf{{DO NOT SHOW THIS TO ANY COMPETITOR BEFORE, DURING, OR AFTER THE TEST}}
  \item For the timed question: competitors are allowed up to two errors in their deciphered plaintext to still be awarded full points, as well as eligibility for the Timed Bonus (2$\cdot{{}}$(600-time taken in seconds))
  \item The Timed Bonus is to be added to the points already existing for the Timed Question.
  \item There are two types of questions: ones that require a deciphered quote, and ones that require a deciphered keyword/keyphrase
  \item For questions requiring a deciphered quote, up to two errors may be in the quote for it to be considered correct. An error can be: an added letter, an incorrect letter, or a missing letter.
  \item For each succeeding error, 100 points will be taken off the question's points until it reaches 0.
  \item For questions requiring a deciphered keyword/phrase, the required phrase is at the beginning of the problem, in \textbf{{bold}}. The quote does not have to be solved.
  \item Zero errors are allowed in order for the question to be correct. For each succeeding error, deduct 100 points from the question's points until it reaches 0.
  \item The three Special Bonus questions are marked with a star. A team must solve a question correctly in order to have bonus points awarded for it.
  \item For each Special Bonus question answered correctly, award 150, 400, or 750 extra points for 1, 2, and 3 questions, respectively.
\end{{itemize}}
\end{{mdframed}}
\vspace{{1em}}
\begin{{center}}
\textbf{{\underline{{Written By:}}}} \\[0.4em]
{writers}
\end{{center}}
"""
    else:
        cover = rf"""
\begin{{center}}
{{\Large \textbf{{Codebusters {division}}}}} \\[0.4em]
{{\large {tournament}}} \\[0.2em]
{{\large {compdate}}} \\[1.2em]
{img_latex}
\end{{center}}
\vspace{{0.8em}}
\begin{{mdframed}}
\textbf{{Instructions:}}
\begin{{itemize}}[leftmargin=1.4em, itemsep=2pt, topsep=4pt]
  \item You will have \textbf{{50 minutes}} to complete this test.
  \item You may bring up to \textbf{{three (3)}} Class I or II calculators, as well as any writing utensils. Three copies of the reference materials will be provided.
  \item You may use the space on the exam as scratch paper, but please make sure that your answers are clear. Either write your answers separately and \fbox{{box}} them, or write them directly over/under the ciphertext.
  \item You may take apart the test as you wish, however you should write your team number \textbf{{on top of every page}} and a \textbf{{250 point deduction}} will be taken if the pages are \textbf{{not}} put back in the correct order.
  \item The first question on the exam is \textbf{{Timed}}. If you believe you have solved the question in the first 10 minutes, signal to the event supervisor who will come over to check it. If you are correct, your time will be recorded and a bonus issued; if you have more than 2 errors you will be notified and allowed to retry for a bonus throughout the first 10 minutes.
  \item If you successfully complete the timed question after 10 minutes, you may still get the base points for the question however it will not be checked and no bonus will be awarded.
  \item There are 3 questions marked for \textbf{{Special Bonus}}: {bonus_nums}
  \item This test is printed \textbf{{single-sided}}. Page 2 contains scoring information. \textbf{{Do not write anything on the scoring page apart from your team number}}. Page 3 is the \textbf{{Timed Question}}.
  \item Ties will be broken according to questions in ascending order (starting with timed), with each question evaluated according to the criteria in the rules.
\end{{itemize}}
\end{{mdframed}}
\vspace{{1em}}
Team Name: \underline{{\hspace{{12cm}}}} \\[1.2em]
Team Number: \underline{{\hspace{{3cm}}}}
\vspace{{1.5em}}
\begin{{center}}
\textbf{{\underline{{Written By:}}}} \\[0.4em]
{writers}
\end{{center}}
"""

    import re as _re2

    def get_latex(q):
        if not isinstance(q, dict):
            return q
        latex = q['latex']
        qtext = q.get('qtext', '').strip()
        if not qtext:
            return latex
        import re as _re
        # Replace the \question line's text with the custom qtext
        latex = _re.sub(
            r'(\\normalsize \\question\[\d+\] )(.*?)(\n)',
            lambda m: m.group(1) + qtext + m.group(3),
            latex,
            count=1,
            flags=_re.DOTALL
        )
        return latex
    
    def estimate_question_height(q):
        latex = get_latex(q) if isinstance(q, dict) else q
        height = 3.0
        verbatim_match = re.findall(r'\\begin\{verbatim\}(.*?)\\end\{verbatim\}', latex, re.DOTALL)
        for block in verbatim_match:
            lines = [l for l in block.strip().split('\n') if l.strip()]
            height += len(lines) * 0.8
        if '\\begin{tabular}' in latex:
            height += 2.5
        if '\\begin{pmatrix}' in latex:
            height += 2.0
        if '\\begin{flushleft}' in latex:
            height += 1.5
        if 'arraystretch' in latex:
            height += 3.5
        if 'newmoon' in latex:
            height += 2.5
        return min(height, 22.0)

    def make_col_rows(qs_indexed):
        rows = ''
        for i, q in qs_indexed:
            m = _re2.search(r'\\question\[(\d+)\]', get_latex(q))
            pts = int(m.group(1)) if m else 0
            rows += rf"Q{i+1} & {pts} & \\" + "\n" + r"\hline" + "\n"
        return rows

    def total_points():
        t = 0
        for q in questions_data:
            m = _re2.search(r'\\question\[(\d+)\]', get_latex(q))
            if m: t += int(m.group(1))
        return t

    n = len(questions_data)
    col_size = max(1, -(-n // 3))
    col1_qs = [(i, questions_data[i]) for i in range(0,            min(col_size,     n))]
    col2_qs = [(i, questions_data[i]) for i in range(col_size,     min(col_size * 2, n))]
    col3_qs = [(i, questions_data[i]) for i in range(col_size * 2, n)]
    col1_rows = make_col_rows(col1_qs)
    col2_rows = make_col_rows(col2_qs)
    col3_rows = make_col_rows(col3_qs)
    total = total_points()

    scoring_page = rf"""
\newpage
\thispagestyle{{headandfoot}}
\runningheader{{\textbf{{Codebusters {division} - {tournament}}}}}{{}}{{Team \#}}

\textbf{{\Large Scoring Table}}

\vspace{{0.8em}}
\textbf{{Exam Score}}

\vspace{{0.5em}}
\begin{{tabular}}{{|p{{1.6cm}}|p{{1.2cm}}|p{{1.2cm}}|}}
\hline
\textbf{{Question}} & \textbf{{Points}} & \textbf{{Score}} \\
\hline
{col1_rows}
\end{{tabular}}
\hspace{{0.8cm}}
\begin{{tabular}}{{|p{{1.6cm}}|p{{1.2cm}}|p{{1.2cm}}|}}
\hline
\textbf{{Question}} & \textbf{{Points}} & \textbf{{Score}} \\
\hline
{col2_rows}
\end{{tabular}}
\hspace{{0.8cm}}
\begin{{tabular}}{{|p{{1.6cm}}|p{{1.2cm}}|p{{1.2cm}}|}}
\hline
\textbf{{Question}} & \textbf{{Points}} & \textbf{{Score}} \\
\hline
{col3_rows}Total: & {total} & \\
\hline
\end{{tabular}}

\vspace{{1.4em}}
\textbf{{Timed Question}}

\vspace{{0.4em}}
Question Score: Circle one: \textbf{{{tqvalue}}} \hspace{{1cm}} 0

\vspace{{1em}}
Time: \tline{{minutes : seconds}}{{4cm}}

\vspace{{1em}}
Timed Bonus: $(600 -$ \tline{{time in seconds}}{{4cm}}$) \times 2 =$ \tline{{timed bonus}}{{4cm}}

\vspace{{1em}}
Total TQ Score: \tline{{question score}}{{3.5cm}} $+$ \tline{{timed bonus}}{{3.5cm}} $=$ \tline{{total TQ score}}{{3.5cm}}

\vspace{{1.4em}}
\textbf{{Special Bonus}}

\vspace{{0.4em}}
Circle one. Special bonus is only awarded for solving the question for full score. Special bonus questions: \textbf{{{bonus_nums}}}.
\begin{{itemize}}
  \item $1\ \text{{Correct}} = 150$
  \item $2\ \text{{Correct}} = 400$
  \item $3\ \text{{Correct}} = 750$
  \item $0\ \text{{Correct}} = 0$
\end{{itemize}}

\vspace{{1.4em}}
\textbf{{Total}}

\vspace{{0.4em}}
Final Score $=$ \tline{{Exam Score Total}}{{3cm}} $+$ \tline{{TQ Total}}{{3cm}} $+$ \tline{{Special Bonus}}{{3cm}} $=$ \tline{{}}{{4cm}}

\vspace{{1.2em}}
Rank: \underline{{\hspace{{1.5cm}}}}
"""

    if is_key:
        tq_answer = latex_escape(tq_clean)
        answer_lines = []
        for i, q in enumerate(questions_data):
            if isinstance(q, dict):
                answer  = q.get('answer', '')
                bold    = q.get('answer_bold', False)
                keyword = q.get('keyword') or None
                value   = q.get('payload', {}).get('value') if isinstance(q.get('payload'), dict) else None
                bonus   = bool(q.get('bonus', False))
                answer_lines.append(make_answer_line(i+1, answer, bold, keyword, value, bonus))
            else:
                answer_lines.append(r'\question ???' + '\n')
        middle_section = rf"""
\newpage
\thispagestyle{{headandfoot}}
\textbf{{Timed Question.}} ({tqvalue}~Points) \quad {tq_answer}

\vspace{{0.6em}}
\begin{{questions}}
{"".join(answer_lines)}\end{{questions}}
""" 
    else:
        questions_latex_list = []
        page_used = 0.0
        PAGE_HEIGHT = 22.0
        for idx, q in enumerate(questions_data):
            qh = estimate_question_height(q)
            if idx == 0:
                questions_latex_list.append(get_latex(q))
                page_used = qh
            else:
                if page_used + qh > PAGE_HEIGHT:
                    questions_latex_list.append('\n\\clearpage\n')
                    questions_latex_list.append(get_latex(q))
                    page_used = qh
                else:
                    questions_latex_list.append(f'\n\\Needspace{{{qh:.1f}cm}}\n')
                    questions_latex_list.append(get_latex(q))
                    page_used += qh
                if page_used > PAGE_HEIGHT / 2 and idx % 2 == 1:
                    page_used = 0.0
        middle_section = rf"""
{scoring_page}
\newpage
\setlength\extrarowheight{{2pt}}
\setlength{{\tabcolsep}}{{3pt}}

\textbf{{Timed Question.}} ({tqvalue}~Points) Solve this \textbf{{Aristocrat}}. When you have finished, \textbf{{{tqphrase}}} so your answer can be checked and time recorded.

\vspace{{0.6em}}
\Large{{
\begin{{verbatim}}
{tqcipher}
\end{{verbatim}}}}
\parskip 1cm
{{\normalsize
\begin{{center}}
\begin{{tabular}}{{|m{{2cm}}|m{{9.675pt}}|m{{9.675pt}}|m{{9.675pt}}|m{{9.675pt}}|m{{9.675pt}}|m{{9.675pt}}|m{{9.675pt}}|m{{9.675pt}}|m{{9.675pt}}|m{{9.675pt}}|m{{9.675pt}}|m{{9.675pt}}|m{{9.675pt}}|m{{9.675pt}}|m{{9.675pt}}|m{{9.675pt}}|m{{9.675pt}}|m{{9.675pt}}|m{{9.675pt}}|m{{9.675pt}}|m{{9.675pt}}|m{{9.675pt}}|m{{9.675pt}}|m{{9.675pt}}|m{{9.675pt}}|m{{9.675pt}}|m{{9.675pt}}|}}
\hline
&A&B&C&D&E&F&G&H&I&J&K&L&M&N&O&P&Q&R&S&T&U&V&W&X&Y&Z\\
\hline
Frequency&{tq_freq_row}\\
\hline
Replacement&&&&&&&&&&&&&&&&&&&&&&&&&&\\
\hline
\end{{tabular}}
\end{{center}}}}
\newpage

\begin{{questions}}
{"".join(questions_latex_list)}
\end{{questions}}
"""
    col_type = r'\newcolumntype{Z}[1]{>{\centering\arraybackslash}p{#1}}'
    return rf"""\documentclass[addpoints]{{exam}}
\usepackage[english]{{babel}}
\usepackage[utf8]{{inputenc}}
\usepackage{{amsmath,amsfonts,amssymb}}
\usepackage{{graphicx}}
\usepackage{{array}}
\usepackage{{longtable}}
\usepackage[margin=.7in]{{geometry}}
\usepackage{{parskip}}
\usepackage{{multicol}}
\usepackage{{hyperref}}
\usepackage{{wasysym}}
\usepackage[nodisplayskipstretch]{{setspace}}
\usepackage{{lastpage}}
\usepackage[table]{{xcolor}}
\usepackage{{bm}}
\usepackage{{enumitem}}
\usepackage{{mdframed}}
\usepackage{{needspace}}


{col_type}
\renewcommand{{\questionshook}}{{\setlength{{\leftmargin}}{{20pt}}}}
\renewcommand{{\choiceshook}}{{\setlength{{\leftmargin}}{{30pt}}}}
\hypersetup{{colorlinks=true,linkcolor=teal,filecolor=teal,urlcolor=teal}}
\setlength{{\parindent}}{{0.0in}}
\setlength{{\parskip}}{{2mm}}
\bonuspointpoints{{bonus point}}{{bonus points}}
\newcommand\tline[2]{{$\underset{{\text{{#1}}}}{{\text{{\underline{{\hspace{{#2}}}}}}}}$}}
{printanswers}

\header{{\textbf{{Codebusters {division}}}}}{{{exam_or_key}}}{{{tournament}}}
\runningheadrule

\begin{{document}}
\sffamily
\thispagestyle{{empty}}
{cover}
{middle_section}
\end{{document}}
"""


@app.route('/api/practice/preview', methods=['POST'])
def practice_preview():
    err = require_login()
    if err: return err
    try:
        d = request.get_json()
        practice_settings = {
            'tournament': 'Practice Test',
            'division': '',
            'compdate': '',
            'tqvalue': '250',
            'tqphrase': 'raise your hand',
            'tqcipher': '',
            'writers': '',
            'bonus_nums': 'None',
            'cover_image': '',
        }
        latex = build_latex(practice_settings, d.get('questions', []), d.get('is_key', False))
        return send_file(compile_pdf(latex), mimetype='application/pdf')
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/practice/download', methods=['POST'])
def practice_download():
    err = require_login()
    if err: return err
    try:
        d = request.get_json()
        is_key = d.get('is_key', False)
        test_name = re.sub(r'[^a-zA-Z0-9 ]', '', d.get('test_name', 'Practice Test')).strip()
        suffix = 'KEY' if is_key else 'TEST'
        name = f'{test_name} {suffix}.pdf'
        practice_settings = {
            'tournament': test_name,
            'division': '',
            'compdate': '',
            'tqvalue': '250',
            'tqphrase': 'raise your hand',
            'tqcipher': '',
            'writers': '',
            'bonus_nums': 'None',
            'cover_image': '',
        }
        latex = build_latex(practice_settings, d.get('questions', []), is_key)
        return send_file(compile_pdf(latex), mimetype='application/pdf',
                         as_attachment=True, download_name=name)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

def compile_pdf(latex_str):
    tmpdir = tempfile.mkdtemp()
    tex = os.path.join(tmpdir, 'test.tex')
    pdf = os.path.join(tmpdir, 'test.pdf')
    with open(tex, 'w', encoding='utf-8') as f: f.write(latex_str)
    words_src = os.path.join(BASE, 'sgb-words.txt')
    if os.path.exists(words_src): shutil.copy(words_src, tmpdir)
    r = None
    for _ in range(2):
        r = subprocess.run(['pdflatex', '-interaction=nonstopmode', '-output-directory', tmpdir, tex],
                           capture_output=True, text=True, timeout=60)
    if not os.path.exists(pdf):
        log = os.path.join(tmpdir, 'test.log')
        msg = open(log).read()[-4000:] if os.path.exists(log) else (r.stdout if r else '')[-4000:]
        raise RuntimeError(msg)
    return pdf

@app.route('/api/preview', methods=['POST'])
def preview():
    err = require_login()
    if err: return err
    try:
        d = request.get_json()
        latex = build_latex(d.get('settings',{}), d.get('questions',[]), d.get('is_key',False))
        return send_file(compile_pdf(latex), mimetype='application/pdf')
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/download', methods=['POST'])
def download():
    err = require_login()
    if err: return err
    try:
        d = request.get_json()
        latex = build_latex(d.get('settings',{}), d.get('questions',[]), d.get('is_key',False))
        settings = d.get('settings', {})
        tournament = re.sub(r'[^a-zA-Z0-9 ]', '', settings.get('tournament', 'Tournament')).strip()
        division = settings.get('division', '')
        compdate = settings.get('compdate', '')
        year = compdate.split('/')[-1] if compdate else ''
        suffix = 'KEY' if d.get('is_key') else 'TEST'
        parts = [p for p in [year, tournament, 'CODEBUSTERS', division, suffix] if p]
        name = ' '.join(parts).replace(' ', '_') + '.pdf'
        return send_file(compile_pdf(latex), mimetype='application/pdf', as_attachment=True, download_name=name)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    
@app.route('/api/practice/keywords', methods=['GET'])
def get_keywords():
    err = require_login()
    if err: return err
    path = os.path.join(BASE, 'keywords.txt')
    if not os.path.exists(path):
        return jsonify([])
    with open(path, encoding='utf-8') as f:
        lines = [l.strip().upper() for l in f if l.strip()]
    return jsonify(lines)

@app.route('/api/practice/quotes', methods=['GET'])
def get_quotes():
    err = require_login()
    if err: return err
    quotes_path = os.path.join(BASE, 'quotes.txt')
    if not os.path.exists(quotes_path):
        return jsonify([])
    with open(quotes_path, encoding='utf-8') as f:
        lines = [l.strip() for l in f if l.strip()]
    return jsonify(lines)

@app.route('/api/practice/checkkw', methods=['GET'])
def get_checkkw():
    err = require_login()
    if err: return err
    path = os.path.join(BASE, 'checkkw.txt')
    if not os.path.exists(path):
        return jsonify([])
    with open(path, encoding='utf-8') as f:
        lines = [l.strip().upper() for l in f if l.strip()]
    return jsonify([w for w in lines if len(w) == 5])

@app.route('/api/practice/homokw', methods=['GET'])
def get_homokw():
    err = require_login()
    if err: return err
    path = os.path.join(BASE, 'homokw.txt')
    if not os.path.exists(path):
        return jsonify([])
    with open(path, encoding='utf-8') as f:
        lines = [l.strip().upper() for l in f if l.strip()]
    return jsonify([w for w in lines if len(w) == 4])

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/builder')
def builder():
    return render_template('builder.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/security')
def security():
    return render_template('security.html')

@app.route('/practice')
def practice():
    return render_template('practicebuilder.html')



if __name__ == '__main__':
    app.run(debug=True, port=5000)