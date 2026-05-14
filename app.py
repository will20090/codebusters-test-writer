from flask import Flask, request, jsonify, send_file, session, render_template
import subprocess, tempfile, os, json, traceback, shutil, sys, datetime, uuid
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
from psycopg2.extras import RealDictCursor

sys.path.insert(0, os.path.dirname(__file__))
import ciphers

app = Flask(__name__)
app.secret_key = 'codebusters-secret-key-change-this'

BASE = os.path.dirname(__file__)

# ── Database ──────────────────────────────────────────────────────────────────

def get_db():
    conn = psycopg2.connect(os.environ['DATABASE_URL'], sslmode='require')
    conn.autocommit = True
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            created TEXT NOT NULL
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS tests (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            created TEXT NOT NULL,
            modified TEXT NOT NULL DEFAULT '',
            settings JSONB NOT NULL DEFAULT '{}',
            questions JSONB NOT NULL DEFAULT '[]'
        )
    ''')
    conn.commit()
    cur.close()
    conn.close()

def nid(): return uuid.uuid4().hex[:12]

def current_user():
    return session.get('uid')

def require_login():
    if not current_user():
        return jsonify({'error': 'Not logged in'}), 401
    return None

# ── Auth routes ───────────────────────────────────────────────────────────────

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
    try:
        conn.commit()
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    cur.close(); conn.close()
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

# ── Test routes ───────────────────────────────────────────────────────────────

@app.route('/api/tests', methods=['GET'])
def get_tests():
    err = require_login()
    if err: return err
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(
        'SELECT id, name, created, modified, jsonb_array_length(questions) as count FROM tests WHERE user_id = %s ORDER BY modified DESC',
        (current_user(),)
    )
    tests = cur.fetchall()
    cur.close(); conn.close()
    return jsonify([dict(t) for t in tests])

@app.route('/api/tests', methods=['POST'])
def create_test():
    err = require_login()
    if err: return err
    data = request.get_json()
    name = data.get('name','').strip()
    if not name: return jsonify({'error': 'Test name required'}), 400
    tid = nid()
    now = datetime.datetime.now().isoformat()
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        'INSERT INTO tests (id, user_id, name, created, modified, settings, questions) VALUES (%s, %s, %s, %s, %s, %s, %s)',
        (tid, current_user(), name, now, now, json.dumps({}), json.dumps([]))
    )
    conn.commit(); cur.close(); conn.close()
    return jsonify({'id': tid, 'name': name, 'created': now, 'modified': now, 'settings': {}, 'questions': []})

@app.route('/api/tests/<tid>', methods=['GET'])
def get_test(tid):
    err = require_login()
    if err: return err
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('SELECT * FROM tests WHERE id = %s AND user_id = %s', (tid, current_user()))
    t = cur.fetchone()
    cur.close(); conn.close()
    if not t: return jsonify({'error': 'Not found'}), 404
    return jsonify(dict(t))

@app.route('/api/tests/<tid>', methods=['PUT'])
def update_test(tid):
    err = require_login()
    if err: return err
    data = request.get_json()
    now = datetime.datetime.now().isoformat()
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        'UPDATE tests SET settings = %s, questions = %s, modified = %s WHERE id = %s AND user_id = %s',
        (json.dumps(data.get('settings', {})), json.dumps(data.get('questions', [])), now, tid, current_user())
    )
    conn.commit(); cur.close(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/tests/<tid>', methods=['DELETE'])
def del_test(tid):
    err = require_login()
    if err: return err
    conn = get_db()
    cur = conn.cursor()
    cur.execute('DELETE FROM tests WHERE id = %s AND user_id = %s', (tid, current_user()))
    conn.commit(); cur.close(); conn.close()
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
    conn.commit(); cur.close(); conn.close()
    return jsonify({'ok': True})

# ── Cipher dispatcher ─────────────────────────────────────────────────────────

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

def make_answer_line(q_num, answer, bold, keyword=None):
    if keyword is not None and keyword != '':
        safe_kw = latex_escape(str(keyword))
        safe_pt = latex_escape(str(answer))
        return rf'\question \textbf{{{safe_kw}}}: {safe_pt}' + '\n'
    safe = latex_escape(str(answer))
    return rf'\question {safe}' + '\n'

def dispatch(row):
    cipher    = row.get('cipher','').upper()
    pt        = row.get('plaintext','')
    value     = row.get('value', 5)
    hint_type = row.get('hint_type','None')
    hint      = row.get('hint','')
    bonus     = bool(row.get('bonus', False))
    key1      = row.get('key1','')
    key2      = row.get('key2','')
    key3      = row.get('key3','')
    key4      = row.get('key4','')
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
        bs_val = key3 if rtype == 'CRIB' else (int(key3) if key3 else 5)
        return ciphers.nihilistFormatter(pt, key1, key2, bs_val, value, rtype, hint_type, hint, bonus)
    elif cipher == 'PORTA':
        bs_val = key3 if rtype == 'CRIB' else (int(key3) if key3 else 5)
        return ciphers.porta_formatter(pt, key1, bs_val, value, rtype, hint_type, hint, bonus)
    elif cipher == 'XENOCRYPT':
        return ciphers.xeno_creator(pt, value, 'Aristocrat', hint_type, hint,
                                    key3, key1, int(key2) if key2 else 0, extract)
    elif cipher == 'AFFINE':
        return ciphers.affine_formatter(pt, key1, key2, key3, value, rtype, hint or key4, bonus)
    elif cipher == 'CHECKERBOARD':
        if rtype == 'DECODE':
            return ciphers.checkerboarddecode(pt, key1, key2, key3, 5, value, bonus)
        elif rtype == 'CRIB':
            return ciphers.checkerboardcrib(pt, key1, key2, key3, hint, value, bonus)
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
        tq_encoded_raw = ciphers.aristo_letter_replacement(tq_clean)
        tqcipher = ciphers.aristo_format_sentence(tq_encoded_raw)
        tq_letters_only = _re.sub(r'[^A-Z]', '', tq_encoded_raw)
        tq_freq_row = '&'.join(str(tq_letters_only.count(chr(i+65))) for i in range(26))
    except Exception:
        tqcipher = tq_clean
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

    if is_key:
        cover = rf"""
\begin{{center}}
{{\Large \textbf{{Codebusters {division} KEY}}}} \\[0.4em]
{{\large {tournament}}} \\[0.2em]
{{\large {compdate}}} \\[1.2em]
{img_latex}
\end{{center}}
\vspace{{2em}}
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
        return q['latex'] if isinstance(q, dict) else q

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
                answer_lines.append(make_answer_line(i+1, answer, bold, keyword))
            else:
                answer_lines.append(r'\question ???' + '\n')
        middle_section = rf"""
\newpage
\thispagestyle{{headandfoot}}
\textbf{{Timed Question.}} ({tqvalue}~Points) \quad \textbf{{Answer:}} {tq_answer}

\vspace{{0.6em}}
\begin{{questions}}
{"".join(answer_lines)}\end{{questions}}
"""
    else:
        questions_latex_list = [get_latex(q) for q in questions_data]
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

\newcolumntype{{C}}[1]{{>{{centering\arraybackslash}}p{{#1}}}}
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
        name = 'key.pdf' if d.get('is_key') else 'test.pdf'
        return send_file(compile_pdf(latex), mimetype='application/pdf', as_attachment=True, download_name=name)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/builder')
def builder():
    return render_template('builder.html')

init_db()

if __name__ == '__main__':
    app.run(debug=True, port=5000)

@app.route('/api/dbtest')
def dbtest():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("INSERT INTO users (id, username, password, created) VALUES ('rendertest', 'rendertest', 'x', '2026-01-01')")
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}) 