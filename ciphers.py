import random
import math
import os
import re
import unicodedata

# ── Helpers ───────────────────────────────────────────────────────────────────

def detect_hint_type(plaintext_clean, crib_clean):
    if crib_clean not in plaintext_clean:
        raise ValueError(f"Crib '{crib_clean}' not found in '{plaintext_clean}'")
    if plaintext_clean.startswith(crib_clean): return "Start Crib"
    if plaintext_clean.endswith(crib_clean):   return "End Crib"
    return "Middle Crib"

def ordinal(n):
    if 11 <= (n % 100) <= 13: return f"{n}th"
    return f"{n}{['th','st','nd','rd','th'][min(n % 10, 4)]}"

# ── Aristocrat / Patristocrat ─────────────────────────────────────────────────

def process_word(word, shift):
    seen = set()
    unique_letters = []
    word = word.lower().replace(" ", "")
    for char in word:
        if char not in seen:
            unique_letters.append(char); seen.add(char)
    unused = sorted(set('abcdefghijklmnopqrstuvwxyz') - seen)
    result = ''.join(unique_letters) + ''.join(unused)
    shift = shift % len(result)
    return result[-shift:] + result[:-shift]

def aristo_letter_replacement(s, keyword="", shift="", alph=""):
    def derangement(lst):
        while True:
            r = lst[:]
            random.shuffle(r)
            if all(x != y for x, y in zip(lst, r)): return r
    def rand_derange(alphabet):
        return ''.join(derangement(list(alphabet)))

    if alph == "":
        alphabet_upper = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        replacement_alphabet = rand_derange(alphabet_upper)
    elif alph == "K2":
        alphabet_upper = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        replacement_alphabet = process_word(keyword, shift).upper()
    elif alph == "K1":
        alphabet_upper = process_word(keyword, shift).upper()
        replacement_alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    else:
        alphabet_upper = process_word(keyword, 0).upper()
        replacement_alphabet = process_word(keyword, 26 - shift).upper()

    for i in range(26):
        if alphabet_upper[i] == replacement_alphabet[i]:
            raise ValueError("Cannot have a letter map to itself; check your keys")
    return s.upper().translate(str.maketrans(alphabet_upper, replacement_alphabet))

def aristo_format_sentence(s):
    words = s.split()
    out = ""; line = ""; length = 0
    for w in words:
        if length + len(w) + 1 > 52:
            out += line.rstrip() + "\n\n\n"; line = w + " "; length = len(w) + 1
        else:
            line += w + " "; length += len(w) + 1
    return out + line.rstrip() + "\n"

def pat_format_sentence(s):
    s = re.sub(r'[^a-zA-Z]', '', s)
    q = ""
    for i in range(len(s)):
        q += s[i]
        if i % 5 == 4: q += " "
    return aristo_format_sentence(q)

def aristo_frequency_table(ct, alph):
    if alph == "K2":
        o = "Replacement"
        for i in range(26): o += "&"
        o += "\\\\\n\\hline\nK2"
        for i in range(26): o += "&" + chr(i+65)
        o += "\\\\\n\\hline\nFrequency"
        for i in range(26): o += "&" + str(ct.count(chr(i+65)))
        o += "\\\\"
    else:
        o = f"{alph}"
        for i in range(26): o += "&" + chr(i+65)
        o += "\\\\\n\\hline\nFrequency"
        for i in range(26): o += "&" + str(ct.count(chr(i+65)))
        o += "\\\\\n\\hline\nReplacement"
        for i in range(26): o += "&"
        o += "\\\\"
    return o

def mono_table():
    return (
        "{\\normalsize\n\\begin{center}\n\\begin{tabular}\n"
        "{|m{2cm}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|}\n"
    )

def monoalph_creator(s, value, ctype, hint_type, hint, alph="", keyword="", shift="", extract=False):
    replaced = aristo_letter_replacement(s, keyword, shift, alph)
    if ctype == "Aristocrat":
        formatted = aristo_format_sentence(replaced)
    else:
        formatted = pat_format_sentence(replaced)
        replaced = re.sub(r'[^a-zA-Z]', '', replaced)
    table = aristo_frequency_table(replaced, alph)
    alph_label = alph + " " if alph else ""

    if not extract:
        v = f"\\normalsize \\question[{value}] Solve this \\textbf{{{alph_label}{ctype}}}"
    else:
        article = "an" if ctype == "Aristocrat" else "a"
        v = f"\\normalsize \\question[{value}] The following quote was encoded as {article} \\textbf{{{ctype}}} with a {alph_label}alphabet"

    if hint_type == "None" or not hint_type:
        v += ".\n"
    elif hint_type in ("Word", "Letters"):
        v += f". You are told that {hint}.\n"
    elif hint_type in ("Word + Subject", "Letters + Subject"):
        parts = hint.split(",", 1)
        v += f" about {parts[1].strip()}. You are told that {parts[0].strip()}.\n"
    elif hint_type == "Subject":
        v += f" about {hint}.\n"
    else:
        v += ".\n"

    if extract:
        v += f"You are told that the keyword used is {len(keyword)} letters long. What is the keyword? $\\boxed{{\\text{{Box}}}}$ your final answer."

    v += "\n\\Large{\n\\begin{verbatim}\n"
    v += formatted + "\n\\end{verbatim}}\n"
    v += mono_table()
    v += "\\hline\n" + table + "\n\\hline\n\\end{tabular}\n\\end{center}}\n\\vfill\n\\uplevel{\\hrulefill}\n"
    return v

# ── Atbash ────────────────────────────────────────────────────────────────────

def atbash_encoder(text, bs, value):
    text = re.sub(r'[^a-zA-Z]', '', text).upper()
    rev = {chr(i): chr(155-i) for i in range(65, 91)}
    t = ''.join(rev[c] for c in text)
    v = ""
    for i in range(len(t)):
        v += t[i]
        if i % bs == bs - 1: v += " "
    lines = []
    for i, w in enumerate(v.split()):
        lines.append(w)
    # reformat to 52 chars wide
    out = ""; line = ""; length = 0
    for w in v.split():
        if length + len(w) + 1 > 52:
            out += line.rstrip() + "\n\n\n"; line = w + " "; length = len(w)+1
        else:
            line += w + " "; length += len(w)+1
    out += line.rstrip()
    return (f"\\normalsize \\question[{value}] Decode this phrase that was encoded using the \\textbf{{Atbash}} cipher.\n"
            f"\n \\Large{{\n\\begin{{verbatim}}\n{out}\n\n\\end{{verbatim}}}}\n\\vfill\n\\uplevel{{\\hrulefill}}")

# ── Baconian Letters ──────────────────────────────────────────────────────────

BACON_ALPHA = {"A":"AAAAA","B":"AAAAB","C":"AAABA","D":"AAABB","E":"AABAA","F":"AABAB",
               "G":"AABBA","H":"AABBB","I":"ABAAA","J":"ABAAA","K":"ABAAB","L":"ABABA",
               "M":"ABABB","N":"ABBAA","O":"ABBAB","P":"ABBBA","Q":"ABBBB","R":"BAAAA",
               "S":"BAAAB","T":"BAABA","U":"BAABB","V":"BAABB","W":"BABAA","X":"BABAB",
               "Y":"BABBA","Z":"BABBB"}

def baconLetterEncoder(s, a, b, lw, btype):
    a = list(str(a)); b = list(str(b))
    s = re.sub(r'[^a-zA-Z]', '', s).upper()
    baconed = ''.join(BACON_ALPHA[c] for c in s)
    encoded = ""; xi = 0; yi = 0
    for bit in baconed:
        if btype == "LETTERS":
            if bit == "A": encoded += a[xi]; xi = (xi+1)%len(a)
            else:          encoded += b[yi]; yi = (yi+1)%len(b)
        elif btype == "RANDOM LETTERS":
            if bit == "A": encoded += a[random.randint(0,len(a)-1)]
            else:          encoded += b[random.randint(0,len(b)-1)]
        elif btype == "SEQUENCE":
            if bit == "A": encoded += a[xi]; xi = (xi+1)%len(a)
            else:          encoded += b[xi]; xi = (xi+1)%len(b)
    spaced = ""
    for i in range(len(encoded)):
        spaced += encoded[i]
        if i % lw == lw-1: spaced += "\n\n\n"
    return spaced

def baconianLetters(s, a, b, lw, value, btype, hint_type, hint, bonus):
    t = baconLetterEncoder(s, a, b, lw, btype)
    bonus_text = " \\emph{$\\bigstar$\\textbf{This question is a special bonus question.}}" if bonus else ""
    if hint_type == "Letters":
        q = f"\\normalsize \\question[{value}] Decode this phrase that was encoded using the \\textbf{{Baconian}} cipher. You are told that {hint}.{bonus_text}"
    else:
        q = f"\\normalsize \\question[{value}] Decode this phrase that was encoded using the \\textbf{{Baconian}} cipher.{bonus_text}"
    return q + f"\n\n \\Large{{\n\\begin{{verbatim}}\n{t}\n\n\\end{{verbatim}}}}\n\\vfill\n\\uplevel{{\\hrulefill}}"

# ── Baconian Words ────────────────────────────────────────────────────────────

def get_matching_words(f1, f2, f3, f4, f5):
    words_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sgb-words.txt")
    with open(words_file) as fh:
        words = fh.read().splitlines()
    f1,f2,f3,f4,f5 = f1.lower(),f2.lower(),f3.lower(),f4.lower(),f5.lower()
    return [w for w in words if w[0] in f1 and w[1] in f2 and w[2] in f3 and w[3] in f4 and w[4] in f5]

def words_format_sentence(s):
    words = s.split()
    out = ""; line = ""; length = 0
    for w in words:
        if length + len(w) + 1 > 58:
            out += line.rstrip() + "\n\n\n"; line = w + " "; length = len(w)+1
        else:
            line += w + " "; length += len(w)+1
    return out + line.rstrip()

def bacon_words_encode(s, alph):
    s = re.sub(r'[^a-zA-Z]', '', s).upper()
    alph = (alph.replace(" ","").upper() * 13)[:26]
    a = ''.join(chr(i+65) for i in range(26) if alph[i]=='A')
    b = ''.join(chr(i+65) for i in range(26) if alph[i]=='B')
    baconed = ''.join(BACON_ALPHA[c] for c in s)
    result = ""
    for i in range(0, len(baconed), 5):
        chunk = baconed[i:i+5]
        sets = [a if chunk[j]=="A" else b for j in range(5)]
        wlist = get_matching_words(*sets)
        result += random.choice(wlist) + " "
    return words_format_sentence(result.upper())

def baconianWordsFormatter(s, alph, crib, value, hint_type, bonus):
    s = re.sub(r'[^a-zA-Z]', '', s)
    t = bacon_words_encode(s, alph)
    bonus_text = " \\emph{$\\bigstar$\\textbf{This question is a special bonus question.}}" if bonus else ""
    pt = s.upper(); crib_c = re.sub(r'[^A-Z]','',crib.upper()) if crib else ""
    if crib_c:
        try: hint_type = detect_hint_type(pt, crib_c)
        except: pass
    if hint_type == "Start Crib":
        q = f"\\normalsize \\question[{value}] Decode this phrase that was encoded using the \\textbf{{Baconian}} cipher. You are told that the plaintext starts with \\textbf{{{crib_c}}}.{bonus_text}"
    elif hint_type == "End Crib":
        q = f"\\normalsize \\question[{value}] Decode this phrase that was encoded using the \\textbf{{Baconian}} cipher. You are told that the plaintext ends with \\textbf{{{crib_c}}}.{bonus_text}"
    elif hint_type == "Middle Crib" and crib_c:
        idx = pt.find(crib_c)
        all_words = t.split()
        crib_words = " ".join(all_words[idx:idx+len(crib_c)])
        q = (f"\\normalsize \\question[{value}] Decode this phrase that was encoded using the \\textbf{{Baconian}} cipher. "
             f"You are told that the plaintext contains \\textbf{{{crib_c}}}, encoding to \\textbf{{{crib_words}}}, "
             f"or characters {idx+1}-{idx+len(crib_c)}.{bonus_text}")
    else:
        q = f"\\normalsize \\question[{value}] Decode this phrase that was encoded using the \\textbf{{Baconian}} cipher.{bonus_text}"

    bacon_table = (
        "\n{\\normalsize\n\\begin{flushleft}\n\\begin{tabular}\n"
        "{|m{2cm}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|}\n"
        "\\hline\n&A&B&C&D&E&F&G&H&I&J&K&L&M&N&O&P&Q&R&S&T&U&V&W&X&Y&Z\\\\\n"
        "\\hline\nReplacement&&&&&&&&&&&&&&&&&&&&&&&&&&\\\\\n\\hline\n\\end{tabular}\n\\end{flushleft}}"
    )
    return q + f"\n\n \\Large{{\n\\begin{{verbatim}}\n{t}\n\n\\end{{verbatim}}}}\n{bacon_table}\n\\vfill\n\\uplevel{{\\hrulefill}}"

# ── Caesar ────────────────────────────────────────────────────────────────────

def caesar_formatter(s, shift, value, bonus):
    shift = int(shift)
    if shift % 26 == 0: raise ValueError("Shift cannot be 0 mod 26")
    s = re.sub(r'[^a-zA-Z]', '', s).upper()
    encoded = ''.join(chr((ord(c)-65+shift)%26+65) for c in s)
    spaced = ""
    for i in range(len(encoded)):
        spaced += encoded[i]
        if i % 5 == 4: spaced += " "
    out = ""; line = ""; length = 0
    for w in spaced.split():
        if length + len(w) + 1 > 52:
            out += line.rstrip() + "\n\n\n"; line = w + " "; length = len(w)+1
        else:
            line += w + " "; length += len(w)+1
    out += line.rstrip()
    bonus_text = " \\emph{$\\bigstar$\\textbf{This question is a special bonus question.}}" if bonus else ""
    return (f"\\normalsize \\question[{value}] Decode this phrase that was encoded using the \\textbf{{Caesar}} cipher.{bonus_text}\n"
            f"\n\\Large{{\n\\begin{{verbatim}}\n{out}\n\n\\end{{verbatim}}}}\n\\vfill\n\\uplevel{{\\hrulefill}}")

# ── Columnar ──────────────────────────────────────────────────────────────────

def columnarFormatter(s, columns, crib, value, bonus):
    s = re.sub(r'[^a-zA-Z]', '', s).upper()
    columns = int(columns)
    key = ''.join(random.sample([str(i) for i in range(columns)], columns))
    key_lst = sorted(list(key))
    col = len(key); row = math.ceil(len(s)/col)
    padded = list(s) + ['X'] * (row*col - len(s))
    matrix = [padded[i:i+col] for i in range(0, len(padded), col)]
    cipher = ''.join(''.join(r[key.index(key_lst[k])] for r in matrix) for k in range(col))
    spaced = ""
    for i in range(len(cipher)):
        spaced += cipher[i]
        if i % 5 == 4: spaced += " "
    out = ""; line = ""; length = 0
    for w in spaced.split():
        if length + len(w) + 1 > 52:
            out += line.rstrip() + "\n\n\n"; line = w + " "; length = len(w)+1
        else:
            line += w + " "; length += len(w)+1
    out += line.rstrip()
    bonus_text = " \\emph{$\\bigstar$\\textbf{This question is a special bonus question.}}" if bonus else ""
    return (f"\\normalsize \\question[{value}] Decode this phrase that was encoded using the \\textbf{{Complete Columnar}} cipher. "
            f"You are told that the plaintext contains \\textbf{{{crib.upper()}}}.{bonus_text}\n"
            f"\n \\Large{{\n\\begin{{verbatim}}\n{out}\n\n\\end{{verbatim}}}}\n\\vfill\n\\uplevel{{\\hrulefill}}")

# ── Cryptarithm ───────────────────────────────────────────────────────────────

def cryptarithm_formatter(value, problem_text, solution_numbers, operation, bonus):
    nums = str(solution_numbers)
    math_nums = r'\:'.join(nums.split())
    bonus_text = r" \emph{$\bigstar$\textbf{This question is a special bonus question.}}" if bonus else ""
    op_label = operation if operation else "Addition"
    header_lines = "Base 10 " + op_label + "\nAnswer: " + nums
    q_text = (r"\normalsize \question[" + str(value) + r"] Solve this \textbf{" + op_label + r" Cryptarithm} for $" + math_nums + r"$. "
              r"Write out your final answer and $\boxed{\text{box}}$ it." + bonus_text + "\n"
              r"\parskip 1cm" + "\n\n" + r"\Large" + "\n" + r"\begin{verbatim}" + "\n"
              + header_lines + "\n\n\n" + problem_text + "\n" + r"\end{verbatim}" + "\n"
              r"\vfill" + "\n" + r"\uplevel{\hrulefill}")
    return q_text


def fracalphabet(kw):
    kw = kw.upper()
    seen = set(); out = ""
    for c in kw:
        if c not in seen: out += c; seen.add(c)
    for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        if c not in seen: out += c
    return out

def morse_stream(text):
    text = re.sub(r"[^\w\s]","",text).upper()
    stream = ""
    words = text.split()
    for wi, word in enumerate(words):
        for ch in word:
            if ch in _MORSE: stream += _MORSE[ch] + 'x'
        if wi < len(words)-1: stream += 'x'
    return stream

def frac_encode(s, kw):
    kw = kw.replace(" ","")
    alpha = list(fracalphabet(kw))
    fmap = {}
    keys = ["...","..–","..x",".-.",".-–",".-x",".x.",".x-",".xx","-..","-.–","-.x","--.","---","--x","-x.","-x-","-xx","x..","x.-","x.x","x-.","x--","x-x","xx.","xx-"]
    # Use the real trigram keys
    trigrams = ["...","..−","..x","...",]  # rebuild properly
    dots   = ['.','.','.','.','.','.','.','.','.', '-','-','-','-','-','-','-','-','-', 'x','x','x','x','x','x','x','x']
    dashes = ['.','.','.', '-','-','-', 'x','x','x', '.','.','.', '-','-','-', 'x','x','x', '.','.','.', '-','-','-', 'x','x']
    thirds = ['.', '-','x', '.', '-','x', '.', '-','x', '.', '-','x', '.', '-','x', '.', '-','x', '.', '-','x', '.', '-','x', '.', '-']
    real_keys = [dots[i]+dashes[i]+thirds[i] for i in range(26)]
    fmorse = {real_keys[i]: alpha[i] for i in range(26)}

    # Build morse stream with word separators
    s_clean = re.sub(r"[^\w\s]","",s).upper()
    stream = ""
    ws = s_clean.split()
    for wi, word in enumerate(ws):
        for ch in word:
            if ch in _MORSE: stream += _MORSE[ch] + 'x'
        if wi < len(ws)-1: stream += 'x'

    # Pad
    while len(stream) % 3 != 0: stream += 'x'

    encoded = ""
    for i in range(0, len(stream), 3):
        tri = stream[i:i+3]
        encoded += fmorse.get(tri, '?')
    return encoded, stream

def fractionatedFormatter(s, keyword, crib, value, hint_type, hint, bonus):
    s = re.sub(r"[^\w\s]","",s).upper()
    encoded, stream = frac_encode(s, keyword.replace(" ",""))

    # Space out display
    display = "  " + "  ".join(encoded)

    bonus_text = " \\emph{$\\bigstar$\\textbf{This question is a special bonus question.}}" if bonus else ""

    # Auto hint
    if crib:
        pt = re.sub(r"[^\w]","",s).upper()
        cr = re.sub(r"[^\w]","",crib).upper()
        try: hint_type = detect_hint_type(pt, cr)
        except: pass

    # Build hint string
    auto_hint = hint
    if crib and hint_type in ("Start Crib","Middle Crib","End Crib"):
        try:
            crib_stream = morse_stream(crib)
            full_stream = morse_stream(s)
            idx = full_stream.find(crib_stream)
            if idx >= 0:
                alpha = list(fracalphabet(keyword.replace(" ","")))
                dots=['.','.','.','.','.','.','.','.','.', '-','-','-','-','-','-','-','-','-', 'x','x','x','x','x','x','x','x']
                dashes=['.','.','.', '-','-','-', 'x','x','x', '.','.','.', '-','-','-', 'x','x','x', '.','.','.', '-','-','-', 'x','x']
                thirds=['.', '-','x', '.', '-','x', '.', '-','x', '.', '-','x', '.', '-','x', '.', '-','x', '.', '-','x', '.', '-','x', '.', '-']
                rk=[dots[i]+dashes[i]+thirds[i] for i in range(26)]
                fmorse={rk[i]:alpha[i] for i in range(26)}
                offset = idx % 3
                padded = 'x'*offset + crib_stream
                while len(padded)%3!=0: padded+='x'
                seen={}
                for i in range(0,len(padded),3):
                    tri=padded[i:i+3]
                    if tri not in fmorse: continue
                    ct=fmorse[tri]; pretty=''.join(_SYM[c] for c in tri)
                    as_=i-offset; ae=as_+3
                    if as_>=0 and ae<=len(crib_stream): seen[ct]=pretty
                auto_hint = '; '.join(f"{ct} = {tri}" for ct,tri in sorted(seen.items()))
        except Exception as e:
            print(f"[frac hint] {e}")

    if hint_type == "Start Crib":
        q = (f"\\normalsize \\question[{value}] Decode this phrase that was encoded using the \\textbf{{Fractionated Morse}} cipher. "
             f"You are told the plaintext begins with \\textbf{{{crib}}} corresponding to \\textbf{{{auto_hint}}}.{bonus_text}")
    elif hint_type == "Middle Crib":
        q = (f"\\normalsize \\question[{value}] Decode this phrase that was encoded using the \\textbf{{Fractionated Morse}} cipher. "
             f"You are told the plaintext contains \\textbf{{{crib}}} corresponding to \\textbf{{{auto_hint}}}.{bonus_text}")
    elif hint_type == "End Crib":
        pad = (3 - len(stream.replace('x','').replace('.','').replace('-','')) % 3) % 3
        q = (f"\\normalsize \\question[{value}] Decode this phrase that was encoded using the \\textbf{{Fractionated Morse}} cipher. "
             f"You are told the plaintext ends with \\textbf{{{crib}}} corresponding to \\textbf{{{auto_hint}}} "
             f"and \\textbf{{{pad} X{'s' if pad!=1 else ''} of padding}} at the very end.{bonus_text}")
    else:
        q = (f"\\normalsize \\question[{value}] Decode this phrase that was encoded using the \\textbf{{Fractionated Morse}} cipher.{bonus_text}")

    frac_table = (
        "\n\\normalsize\n\\begin{center}\n\\begin{tabular}\n"
        "{|m{2cm}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|}\n"
        "\\hline\nReplacement&&&&&&&&&&&&&&&&&&&&&&&&&&\\\\\n\\hline\n"
        "&$\\newmoon$&$\\newmoon$&$\\newmoon$&$\\newmoon$&$\\newmoon$&$\\newmoon$&$\\newmoon$&$\\newmoon$&$\\newmoon$&$-$&$-$&$-$&$-$&$-$&$-$&$-$&$-$&$-$&$\\times$&$\\times$&$\\times$&$\\times$&$\\times$&$\\times$&$\\times$&$\\times$\\\\\n"
        "&$\\newmoon$&$\\newmoon$&$\\newmoon$&$-$&$-$&$-$&$\\times$&$\\times$&$\\times$&$\\newmoon$&$\\newmoon$&$\\newmoon$&$-$&$-$&$-$&$\\times$&$\\times$&$\\times$&$\\newmoon$&$\\newmoon$&$\\newmoon$&$-$&$-$&$-$&$\\times$&$\\times$\\\\\n"
        "&$\\newmoon$&$-$&$\\times$&$\\newmoon$&$-$&$\\times$&$\\newmoon$&$-$&$\\times$&$\\newmoon$&$-$&$\\times$&$\\newmoon$&$-$&$\\times$&$\\newmoon$&$-$&$\\times$&$\\newmoon$&$-$&$\\times$&$\\newmoon$&$-$&$\\times$&$\\newmoon$&$-$\\\\\n"
        "\\hline\n\\end{tabular}\n\\end{center}\n"
    )
    return q + f"\n\n \\Large{{\n\\begin{{verbatim}}\n{display}\n\n\\end{{verbatim}}}}\n{frac_table}\n\\vfill\n\\uplevel{{\\hrulefill}}"

# ── Hill ──────────────────────────────────────────────────────────────────────

def hillCreater(s, keyword, value, bonus):
    s = re.sub(r'[^a-zA-Z]','',s).upper()
    keyword = keyword.upper().replace(" ","")
    z = [ord(c)-65 for c in keyword]

    if len(keyword)==4:
        matrix = (f"\\[\n\\begin{{pmatrix}}{keyword[0]}&{keyword[1]}\\\\{keyword[2]}&{keyword[3]}\\end{{pmatrix}}"
                  f" = \\begin{{pmatrix}}{z[0]}&{z[1]}\\\\{z[2]}&{z[3]}\\end{{pmatrix}}\n\\]")
        c = [ord(c)-65 for c in s]
        if len(c)%2==1: c.append(25)
        e=[]
        for i in range(0,len(c),2):
            e.append(chr((z[0]*c[i]+z[1]*c[i+1])%26+65))
            e.append(chr((z[2]*c[i]+z[3]*c[i+1])%26+65))
    elif len(keyword)==9:
        a=(z[4]*z[8]-z[5]*z[7])%26; b=-(z[3]*z[8]-z[5]*z[6])%26; cc=(z[3]*z[7]-z[4]*z[6])%26
        d=-(z[1]*z[8]-z[2]*z[7])%26; ee=(z[0]*z[8]-z[2]*z[6])%26; f=-(z[0]*z[7]-z[1]*z[6])%26
        g=(z[1]*z[5]-z[2]*z[4])%26; h=-(z[0]*z[5]-z[2]*z[3])%26; ii=(z[0]*z[4]-z[1]*z[3])%26
        det=pow((a*z[0]+b*z[1]+cc*z[2])%26,-1,26)
        w=[(x*det)%26 for x in [a,d,g,b,ee,h,cc,f,ii]]
        matrix = (f"\\begin{{align*}}\n\\begin{{pmatrix}}{keyword[0]}&{keyword[1]}&{keyword[2]}\\\\"
                  f"{keyword[3]}&{keyword[4]}&{keyword[5]}\\\\{keyword[6]}&{keyword[7]}&{keyword[8]}\\end{{pmatrix}}"
                  f"=\\begin{{pmatrix}}{z[0]}&{z[1]}&{z[2]}\\\\{z[3]}&{z[4]}&{z[5]}\\\\{z[6]}&{z[7]}&{z[8]}\\end{{pmatrix}}"
                  f"\\qquad\\begin{{pmatrix}}{z[0]}&{z[1]}&{z[2]}\\\\{z[3]}&{z[4]}&{z[5]}\\\\{z[6]}&{z[7]}&{z[8]}\\end{{pmatrix}}^{{-1}}"
                  f"=\\begin{{pmatrix}}{w[0]}&{w[1]}&{w[2]}\\\\{w[3]}&{w[4]}&{w[5]}\\\\{w[6]}&{w[7]}&{w[8]}\\end{{pmatrix}}\n\\end{{align*}}")
        c = [ord(c)-65 for c in s]
        while len(c)%3!=0: c.append(25)
        e=[]
        for i in range(0,len(c),3):
            e.append(chr((z[0]*c[i]+z[1]*c[i+1]+z[2]*c[i+2])%26+65))
            e.append(chr((z[3]*c[i]+z[4]*c[i+1]+z[5]*c[i+2])%26+65))
            e.append(chr((z[6]*c[i]+z[7]*c[i+1]+z[8]*c[i+2])%26+65))
    else:
        raise ValueError("Hill keyword must be 4 or 9 letters")

    out=""; line=""
    for ch in e:
        if len(line)>=72: out+=line.rstrip()+"\n\n\n"; line=ch+" "
        else: line+=ch+" "
    out+=line.rstrip()
    bonus_text=" \\emph{$\\bigstar$\\textbf{This question is a special bonus question.}}" if bonus else ""
    return (f"\\normalsize \\question[{value}] Decode this phrase that was encoded using the \\textbf{{Hill}} cipher "
            f"and the encoding key \\textbf{{{keyword}}}.{bonus_text}\n{matrix}\n\n \\Large{{\n\\begin{{verbatim}}\n{out}\n\n\\end{{verbatim}}}}\n\\vfill\n\\uplevel{{\\hrulefill}}")

# ── Nihilist ──────────────────────────────────────────────────────────────────

def nihilist_alphabet(kw):
    kw=kw.lower().replace('j','i'); seen=set(); out=[]
    for c in kw:
        if c not in seen and c.isalpha(): seen.add(c); out.append(c)
    for c in 'abcdefghiklmnopqrstuvwxyz':
        if c not in seen: out.append(c)
    return ''.join(out)

def nihilistFormatter(s, key, pk, bs, value, ntype, hint_type, hint, bonus):
    keyf=key.upper().replace("J","I").replace(" ","")
    s=re.sub(r'[^a-zA-Z]','',s).upper().replace("J","I")
    pkf=pk.upper().replace("J","I").replace(" ","")
    b=nihilist_alphabet(pkf).upper()
    pk_dict={b[i]:(i//5+1)*10+(i%5+1) for i in range(25)}
    crib = bs if ntype=="CRIB" else None
    bs_int = 1 if ntype=="CRIB" else (int(bs) if bs else 5)
    encoded=[]
    x=0
    for let in s:
        encoded.append(pk_dict[let]+pk_dict[keyf[x]]); x=(x+1)%len(keyf)
    y=""; z=0
    for i in range(len(encoded)):
        y+=str(encoded[i])+" "
        if i%bs_int==bs_int-1:
            if bs_int==1: z+=1;
            if (bs_int==1 and z==16) or (bs_int<7 and bs_int>1 and z==3) or (bs_int>=7 and z==2):
                y+="\n\n\n"; z=0
            elif bs_int>1: y+="   "; z+=1; z=z  # already incremented above
    bonus_text=" \\emph{$\\bigstar$\\textbf{This question is a special bonus question.}}" if bonus else ""
    if ntype=="DECODE":
        q=(f"\\normalsize \\question[{value}] Decode this phrase that was encoded using the \\textbf{{Nihilist Substitution}} cipher "
           f"with a keyword of \\textbf{{{key}}} and a polybius key of \\textbf{{{pk}}}.{bonus_text}")
    elif ntype=="CRIB":
        crib_c=re.sub(r'[^A-IK-Z]','',crib.upper().replace('J','I'))
        try: ht=detect_hint_type(s,crib_c)
        except: ht="Start Crib"
        if ht=="Start Crib":
            q=(f"\\normalsize \\question[{value}] Decode this phrase that was encoded using the \\textbf{{Nihilist Substitution}} cipher. "
               f"You are told that the keyword used is between 3 and 7 letters long and the plaintext begins with \\textbf{{{crib_c}}}.{bonus_text}")
        elif ht=="End Crib":
            q=(f"\\normalsize \\question[{value}] Decode this phrase that was encoded using the \\textbf{{Nihilist Substitution}} cipher. "
               f"You are told that the keyword used is between 3 and 7 letters long and the plaintext ends with \\textbf{{{crib_c}}}.{bonus_text}")
        else:
            idx=s.find(crib_c); units=encoded[idx:idx+len(crib_c)]
            units_str=' '.join(str(u) for u in units)
            q=(f"\\normalsize \\question[{value}] Decode this phrase that was encoded using the \\textbf{{Nihilist Substitution}} cipher. "
               f"You are told the {ordinal(idx+1)} through {ordinal(idx+len(crib_c))} cipher units ({units_str}) decode to be {crib_c}.{bonus_text}")
    else:
        q=f"\\normalsize \\question[{value}] Decode this phrase that was encoded using the \\textbf{{Nihilist Substitution}} cipher.{bonus_text}"

    nih_table=(
        "\n{\\renewcommand{\\arraystretch}{1.2}\n\\begin{tabular}{|C{18pt}|C{18pt}|C{18pt}|C{18pt}|C{18pt}|C{18pt}|}\n"
        "\\hline\n&1&2&3&4&5  \\\\\n\\hline\n"
        "1&&&&&  \\\\\n\\hline\n2&&&&&  \\\\\n\\hline\n3&&&&&  \\\\\n\\hline\n4&&&&&  \\\\\n\\hline\n5&&&&&  \\\\\n\\hline\n"
        "\\end{tabular}}\n"
    )
    return q+f"\n\n \\Large{{\n\\begin{{verbatim}}\n{y}\n\n\\end{{verbatim}}}}\n{nih_table}\n\\vfill\n\\uplevel{{\\hrulefill}}"

# ── Porta ─────────────────────────────────────────────────────────────────────

def porta_formatter(s, keyword, bs, value, ptype, hint_type, hint, bonus):
    s=re.sub(r'[^a-zA-Z]','',s).upper()
    crib=None
    if ptype=="CRIB": crib=bs; bs=5
    bs=int(bs)
    kw=[ord(c)-65 for c in keyword.upper()]
    c=[ord(c)-65 for c in s]
    encoded=[]; x=0
    for ele in c:
        if ele<13: v2=(ele+math.floor(kw[x]/2))%13+13
        else: v2=(ele-math.floor(kw[x]/2))%13
        encoded.append(chr(v2+65)); x=(x+1)%len(kw)
    enc=''.join(encoded)
    spaced=""
    for i in range(len(enc)):
        spaced+=enc[i]
        if i%bs==bs-1: spaced+=" "
    out=""; line=""; length=0
    for w in spaced.split():
        if length+len(w)+1>52: out+=line.rstrip()+"\n\n\n"; line=w+" "; length=len(w)+1
        else: line+=w+" "; length+=len(w)+1
    out+=line.rstrip()
    bonus_text=" \\emph{$\\bigstar$\\textbf{This question is a special bonus question.}}" if bonus else ""
    if ptype=="DECODE":
        q=(f"\\normalsize \\question[{value}] Decode this phrase that was encoded using the \\textbf{{Porta}} cipher "
           f"with a keyword of \\textbf{{{keyword}}}.{bonus_text}")
    elif ptype=="CRIB":
        crib_c=re.sub(r'[^A-Z]','',crib.upper())
        try: ht=detect_hint_type(s,crib_c)
        except: ht="Start Crib"
        enc_full=''.join(chr(((c2[i] if i<len(c2) else 0)-math.floor(kw[i%len(kw)]/2))%13+65) if c2[i]>=13 else chr((c2[i]+math.floor(kw[i%len(kw)]/2))%13+13+65) for i in range(len(c2)))
        # recalc clean
        enc_clean=''.join(encoded)
        if ht=="Start Crib":
            q=(f"\\normalsize \\question[{value}] Decode this phrase that was encoded using the \\textbf{{Porta}} cipher. "
               f"You are told the plaintext begins with \\textbf{{{crib_c}}}.{bonus_text}")
        elif ht=="End Crib":
            q=(f"\\normalsize \\question[{value}] Decode this phrase that was encoded using the \\textbf{{Porta}} cipher. "
               f"You are told the plaintext ends with \\textbf{{{crib_c}}}.{bonus_text}")
        else:
            idx=s.find(crib_c); ct_chunk=enc_clean[idx:idx+len(crib_c)]
            q=(f"\\normalsize \\question[{value}] Decode this phrase that was encoded using the \\textbf{{Porta}} cipher. "
               f"You are told the {ordinal(idx+1)} through {ordinal(idx+len(crib_c))} cipher characters ({ct_chunk}) decode to be {crib_c}.{bonus_text}")
    else:
        q=f"\\normalsize \\question[{value}] Decode this phrase that was encoded using the \\textbf{{Porta}} cipher.{bonus_text}"
    return q+f"\n\n\\Large{{\n\\begin{{verbatim}}\n{out}\n\n\\end{{verbatim}}}}\n\\vfill\n\\uplevel{{\\hrulefill}}"

# ── Xenocrypt ─────────────────────────────────────────────────────────────────

def remove_accents(s):
    out=""
    for char in s:
        if char in ('ñ','Ñ'): out+=char; continue
        out+=''.join(c for c in unicodedata.normalize('NFD',char) if unicodedata.category(c)!='Mn')
    return out

def xeno_process_word(word,shift):
    seen=set(); ul=[]
    word=word.lower().replace(" ","")
    for c in word:
        if c not in seen: ul.append(c); seen.add(c)
    unused=sorted(set('abcdefghijklmnopqrstuvwxyz')-seen)
    if 'ñ' not in seen:
        if 'o' in unused: unused.insert(unused.index('o'),'ñ')
        else:
            for i,l in enumerate(unused):
                if l>'n': unused.insert(i,'ñ'); break
            else: unused.append('ñ')
    result=''.join(ul)+''.join(unused)
    shift=shift%len(result)
    return result[-shift:]+result[:-shift]

def xeno_creator(s, value, xtype, hint_type, hint, alph="", keyword="", shift="", extract=False):
    s=remove_accents(s)
    def derangement(lst):
        while True:
            r=lst[:]; random.shuffle(r)
            if all(x!=y for x,y in zip(lst,r)): return r
    if alph=="":
        au="ABCDEFGHIJKLMNÑOPQRSTUVWXYZ"; ru=''.join(derangement(list(au)))
    elif alph=="K2":
        au="ABCDEFGHIJKLMNÑOPQRSTUVWXYZ"; ru=xeno_process_word(keyword,shift).upper()
    elif alph=="K1":
        au=xeno_process_word(keyword,shift).upper(); ru="ABCDEFGHIJKLMNÑOPQRSTUVWXYZ"
    elif alph=="K3":
        au=xeno_process_word(keyword,0).upper(); ru=xeno_process_word(keyword,shift).upper()
    for i in range(27):
        if au[i]==ru[i]: raise ValueError("Cannot have a letter map to itself")
    replaced=s.upper().translate(str.maketrans(au,ru))
    formatted=aristo_format_sentence(replaced)

    # frequency table
    ct=replaced
    if alph=="K2":
        tbl="Replacement"
        for i in range(27): tbl+="&"
        tbl+="\\\\\n\\hline\nK2"
        for i in range(14): tbl+="&"+chr(i+65)
        tbl+="&Ñ"
        for i in range(14,26): tbl+="&"+chr(i+65)
        tbl+="\\\\\n\\hline\nFrequency"
        for i in range(14): tbl+="&"+str(ct.count(chr(i+65)))
        tbl+="&"+str(ct.count(chr(209)))
        for i in range(14,26): tbl+="&"+str(ct.count(chr(i+65)))
        tbl+="\\\\"
    else:
        tbl=f"{alph}"
        for i in range(14): tbl+="&"+chr(i+65)
        tbl+="&Ñ"
        for i in range(14,26): tbl+="&"+chr(i+65)
        tbl+="\\\\\n\\hline\nFrequency"
        for i in range(14): tbl+="&"+str(ct.count(chr(i+65)))
        tbl+="&"+str(ct.count(chr(209)))
        for i in range(14,26): tbl+="&"+str(ct.count(chr(i+65)))
        tbl+="\\\\\n\\hline\nReplacement"
        for i in range(27): tbl+="&"
        tbl+="\\\\"

    alph_label=alph+" " if alph else ""
    if not extract:
        v=f"\\normalsize \\question[{value}] Solve this \\textbf{{{alph_label}Xenocrypt}}"
    else:
        v=f"\\normalsize \\question[{value}] The following quote was encoded as a \\textbf{{Xenocrypt}} with a {alph_label}alphabet"
    if hint_type in ("None",None,""):
        v+=".\n"
    elif hint_type in ("Word","Letters"):
        v+=f". You are told that {hint}.\n"
    elif hint_type in ("Word + Subject","Letters + Subject"):
        parts=hint.split(",",1); v+=f" about {parts[1].strip()}. You are told that {parts[0].strip()}.\n"
    elif hint_type=="Subject":
        v+=f" about {hint}.\n"
    else: v+=".\n"
    if extract:
        v+=f"The keyword is {len(keyword)} letters long. What is the keyword? $\\boxed{{\\text{{box}}}}$ your final answer."
    v+="\n\\Large{\n\\begin{verbatim}\n"+formatted+"\n\\end{verbatim}}\n"
    v+=("{\\normalsize\n\\begin{center}\n\\begin{tabular}\n"
        "{|m{2cm}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|m{9.675pt}|}\n"
        "\\hline\n"+tbl+"\n\\hline\n\\end{tabular}\n\\end{center}}\n\\vfill\n\\uplevel{\\hrulefill}\n")
    return v

# ── Affine ────────────────────────────────────────────────────────────────────

def affine_formatter(s, a, b, bs, value, atype, hint, bonus):
    a=int(a); b=int(b); bs=int(bs) if bs else 5
    if a==1 or a==13 or a%2==0: raise ValueError(f"a={a} must be coprime with 26 (odd, not 1 or 13)")
    s=re.sub(r'[^a-zA-Z]','',s).upper()
    encoded=''.join(chr(((ord(c)-65)*a+b)%26+65) for c in s)
    spaced=""
    for i in range(len(encoded)):
        spaced+=encoded[i]
        if i%bs==bs-1: spaced+=" "
    out=""; line=""; length=0
    for w in spaced.split():
        if length+len(w)+1>52: out+=line.rstrip()+"\n\n\n"; line=w+" "; length=len(w)+1
        else: line+=w+" "; length+=len(w)+1
    out+=line.rstrip()
    bonus_text=" \\emph{$\\bigstar$\\textbf{This question is a special bonus question.}}" if bonus else ""
    if atype=="DECODE":
        q=(f"\\normalsize \\question[{value}] Decode this phrase that was encoded using the \\textbf{{Affine}} cipher "
           f"with $\\textrm{{a}}={a}$ and $\\textrm{{b}}={b}$.{bonus_text}")
    elif atype=="CRIB":
        if len(hint)==2:
            ct=''.join(chr(((ord(c)-65)*a+b)%26+65) for c in hint.upper())
            nhint=f"ciphertext {ct} decodes to {hint.upper()}"
        else: nhint=hint
        q=(f"\\normalsize \\question[{value}] Decode this phrase that was encoded using the \\textbf{{Affine}} cipher. "
           f"You are told that {nhint}.{bonus_text}")
    else:
        q=f"\\normalsize \\question[{value}] Decode this phrase that was encoded using the \\textbf{{Affine}} cipher.{bonus_text}"
    return q+f"\n\n\\Large{{\n\\begin{{verbatim}}\n{out}\n\n\\end{{verbatim}}}}\n\\vfill\n\\uplevel{{\\hrulefill}}"

# ── Checkerboard ──────────────────────────────────────────────────────────────

def cb_alphabet(kw):
    kw=kw.lower().replace('j','i'); seen=set(); out=[]
    for c in kw:
        if c not in seen and c.isalpha(): seen.add(c); out.append(c)
    for c in 'abcdefghiklmnopqrstuvwxyz':
        if c not in seen: out.append(c)
    return ''.join(out)

def cb_encode(hkey,vkey,alph,s,bs):
    hkey=hkey.upper(); vkey=vkey.upper(); alph=alph.upper()
    s=re.sub(r'[^a-zA-Z]','',s).upper().replace('J','I')
    pk={alph[j+i*5]:vkey[i]+hkey[j] for i in range(5) for j in range(5)}
    encoded=[pk[c] for c in s]
    y=""; z=0; bs=int(bs)
    for i in range(len(encoded)):
        y+=str(encoded[i])+" "
        if i%bs==bs-1:
            if bs==1: z+=1;
            if (bs==1 and z==16) or (1<bs<7 and z==3) or (bs>=7 and z==2):
                y+="\n\n\n"; z=0
            elif bs>1: y+="   "; z+=1
    return y

def cb_table():
    return (
        "\n{\\renewcommand{\\arraystretch}{1.2}\n\\begin{tabular}{m{18pt}|m{18pt}|m{18pt}|m{18pt}|m{18pt}|m{18pt}|}\n"
        "\\cline{2-6}\n& \\multicolumn{1}{r|}{} &  &  &  &  \\\\ \\hline\n"
        "\\multicolumn{1}{|l|}{} & \\multicolumn{1}{r|}{} &  &  &  &  \\\\ \\hline\n"
        "\\multicolumn{1}{|l|}{} &&&&&\\\\ \\hline\n"
        "\\multicolumn{1}{|l|}{} &&&&&\\\\ \\hline\n"
        "\\multicolumn{1}{|l|}{} &&&&&\\\\ \\hline\n"
        "\\multicolumn{1}{|l|}{} &&&&&\\\\ \\hline\n"
        "\\end{tabular}}\n"
    )

def checkerboarddecode(s,hkey,vkey,pk,bs,value,bonus):
    alph=cb_alphabet(pk); v=cb_encode(hkey,vkey,alph,s,bs)
    bonus_text=" \\emph{$\\bigstar$\\textbf{This question is a special bonus question.}}" if bonus else ""
    return (f"\\normalsize \\question[{value}] Decode this phrase that was encoded using the \\textbf{{Checkerboard}} cipher "
            f"with a polybius keyword of \\textbf{{{pk}}}.{bonus_text}\n"
            f"\n \\Large{{\n\\begin{{verbatim}}\n{v}\n\n\\end{{verbatim}}}}\n{cb_table()}\n\\vfill\n\\uplevel{{\\hrulefill}}")

def checkerboardcrib(s,hkey,vkey,pk,crib,value,bonus):
    s=re.sub(r'[^a-zA-Z]','',s).upper().replace('J','I')
    alph=cb_alphabet(pk); v=cb_encode(hkey,vkey,alph,s,1)
    crib_c=re.sub(r'[^A-IK-Z]','',crib.upper().replace('J','I'))
    pk_dict={alph.upper()[j+i*5]:vkey.upper()[i]+hkey.upper()[j] for i in range(5) for j in range(5)}
    try:
        ht=detect_hint_type(s,crib_c)
        if ht=="Start Crib":
            c=f"the plaintext begins with \\textbf{{{crib_c}}}"
        elif ht=="End Crib":
            c=f"the plaintext ends with \\textbf{{{crib_c}}}"
        else:
            idx=s.find(crib_c); pairs=' '.join(pk_dict[l] for l in crib_c)
            c=f"characters {idx+1}-{idx+len(crib_c)} ({pairs}) decode to {crib_c}"
    except Exception as e:
        c=f"the plaintext contains \\textbf{{{crib_c}}}"
    bonus_text=" \\emph{$\\bigstar$\\textbf{This question is a special bonus question.}}" if bonus else ""
    return (f"\\normalsize \\question[{value}] Decode this phrase that was encoded using the \\textbf{{Checkerboard}} cipher. "
            f"You are told that {c}.{bonus_text}\n"
            f"\n \\Large{{\n\\begin{{verbatim}}\n{v}\n\n\\end{{verbatim}}}}\n{cb_table()}\n\\vfill\n\\uplevel{{\\hrulefill}}")