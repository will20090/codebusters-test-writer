"""
scoring.py — Suggested point-value calculators for each cipher type.

Each cipher gets a `suggest_<cipher>(payload)` function that returns:
    {
        'suggested': int,
        'min': int,
        'max': int,
        'text': str   (HTML explanation, safe to drop into the popup)
    }

`payload` is the same dict shape sent to /api/generate (cipher, plaintext,
type, key1-4, hint_type, hint, etc.) so this can be called with the exact
current form state.
"""

import re
import math

# ── Standard English letter frequencies (for Chi-Square) ──────────────────────
ENGLISH_FREQ = {
    'A': 8.2, 'B': 1.5, 'C': 2.8, 'D': 4.3, 'E': 12.7, 'F': 2.2, 'G': 2.0,
    'H': 6.1, 'I': 7.0, 'J': 0.15, 'K': 0.77, 'L': 4.0, 'M': 2.4, 'N': 6.7,
    'O': 7.5, 'P': 1.9, 'Q': 0.095, 'R': 6.0, 'S': 6.3, 'T': 9.1, 'U': 2.8,
    'V': 0.98, 'W': 2.4, 'X': 0.15, 'Y': 2.0, 'Z': 0.074,
}

# ── Shared text analysis ────────────────────────────────────────────────────

def compute_stats(plaintext):
    """
    Basic analysis of the plaintext used as a baseline for scoring.
    Returns a dict with: len, unique, minlength (shortest word length),
    chi_square, recommended, minscore, maxscore.

    This is a simplified placeholder for the full analysis described in
    genScoreRangeAndTextForStr (grade level, word commonality, pattern
    word detection, etc. are not yet implemented).
    """
    clean = re.sub(r'[^A-Za-z]', '', plaintext).upper()
    length = len(clean)
    unique = len(set(clean))

    words = re.sub(r'[^A-Za-z ]', '', plaintext).upper().split()
    minlength = min((len(w) for w in words), default=0)

    # Chi-square against expected English frequencies
    chi_square = 0.0
    if length > 0:
        for letter, expected_pct in ENGLISH_FREQ.items():
            expected = expected_pct / 100.0 * length
            observed = clean.count(letter)
            if expected > 0:
                chi_square += (observed - expected) ** 2 / expected

    # Baseline score range purely from length (placeholder heuristic)
    # Longer quotes -> easier -> lower score; shorter -> harder -> higher score
    if length == 0:
        base = 250
    else:
        base = max(150, min(700, int(900 - length * 2)))

    minscore = max(150, base - 75)
    maxscore = min(700, base + 75)
    recommended = base

    return {
        'len': length,
        'unique': unique,
        'minlength': minlength,
        'chi_square': round(chi_square, 2),
        'recommendedScore': recommended,
        'minscore': minscore,
        'maxscore': maxscore,
    }


def _clamp_range(suggested, minscore, maxscore, adjust):
    """Apply an adjustment while keeping the range within [150, 700]."""
    if (minscore + adjust) < 150:
        adjust = 150 - minscore
    if (maxscore + adjust) > 700:
        adjust = 700 - maxscore
    return suggested + adjust, minscore + adjust, maxscore + adjust, adjust


# ── Aristocrat / Patristocrat / Xenocrypt ──────────────────────────────────────

def suggest_aristocrat_family(payload):
    cipher = payload.get('cipher', '').upper()
    plaintext = payload.get('plaintext', '')
    alph_type = (payload.get('key3') or '').upper()  
    hint_type = payload.get('hint_type', 'None')
    hint = payload.get('hint', '')
    rtype = payload.get('type', 'DECODE')

    qrecord = compute_stats(plaintext)
    base = max(150, min(700, 2 * qrecord['len'] + 80))
    minscore = max(180, base - 75)
    maxscore = min(700, base + 75)
    qrecord['recommendedScore'] = base
    qrecord['minscore'] = minscore
    qrecord['maxscore'] = maxscore

    if qrecord['len'] == 0:
        return {
            'suggested': qrecord['recommendedScore'],
            'min': qrecord['minscore'],
            'max': qrecord['maxscore'],
            'text': '<b>You need to enter a plaintext quote to get a recommendation for the score.</b>',
        }

    if qrecord['len'] < 50:
        return {
            'suggested': qrecord['recommendedScore'],
            'min': qrecord['minscore'],
            'max': qrecord['maxscore'],
            'text': '<b>The plaintext quote is too short to get a recommendation.</b>',
        }

    text = ''
    if qrecord['unique'] < 16:
        text += (f"<b>The plaintext only has {qrecord['unique']} unique characters. "
                 f"It should have at least 19 unique characters to get a good recommendation.</b>")

    text += (
        "<p>Based on analysis of the cipher which includes examining the cipher text for "
        "the Chi-Square (\u03c7\u00b2) distribution of letters, "
        "grade level of the text, "
        "number of unknown words, "
        "commonality of words, "
        "and commonness of pattern words"
    )

    adjust = 0

    # Cipher-type adjustments
    if cipher == 'PATRISTOCRAT':
        adjust += 300
        text += ". Encoding as a Patristocrat adds 400 points"
    elif cipher == 'XENOCRYPT':
        adjust += 200
        text += ". Because it is a Xenocrypt, it adds 200 points"

    # Extract (keyword) vs alphabet-type adjustments
    if rtype == 'EXTRACT':
        if alph_type == 'K3':
            adjust += 150
            text += ". Asking for a K3 alphabet keyword or key phrase adds 150 points"
        else:
            adjust += 100
            text += ". Asking for a keyword or key phrase adds 100 points"
    elif alph_type == 'K1':
        adjust -= 100
        text += ". A K1 alphabet takes away 100 points"
    elif alph_type == 'K2':
        adjust -= 75
        text += ". A K2 alphabet takes away 75 points"
    elif alph_type == 'K3':
        adjust += 75
        text += ". A K3 alphabet adds 75 points"

    # Single-letter A/I hint adjustment (Aristocrat only)
    if cipher == 'ARISTOCRAT' and qrecord['minlength'] == 1:
        # We don't have the actual replacement alphabet here (it's randomized
        # at generation time), so this is noted as a possible adjustment
        # rather than applied automatically.
        text += (". <i>Note: if the single-letter word A/I maps to A/I in the generated "
                 "alphabet, this would make the question 25 points easier "
                 "(not yet reflected above).</i>")

    suggested, minscore, maxscore, adjust = _clamp_range(
        qrecord['recommendedScore'], qrecord['minscore'], qrecord['maxscore'], adjust
    )

    range_text = ''
    if maxscore > minscore:
        range_text = f" out of a <em>suggested range of {minscore} to {maxscore}</em>"

    text += f", try a score of {suggested}{range_text}.</p>"

    if hint_type and hint_type != 'None' and hint:
        text += (
            "<p><b>NOTE:</b> <em>Since you provided a hint in the question, "
            "you may want to adjust the score down by approximately 20 points "
            "per letter hinted.</em></p>"
        )

    return {'suggested': suggested, 'min': minscore, 'max': maxscore, 'text': text}


# ── Atbash ──────────────────────────────────────────────────────────────────

def suggest_atbash(payload):
    return {'suggested': 250, 'min': 150, 'max': 350,
            'text': 'Point suggestions for Atbash are <b>WIP</b>.'}


# ── Baconian ──────────────────────────────────────────────────────────────────

def suggest_baconian(payload):
    return {'suggested': 250, 'min': 150, 'max': 400,
            'text': 'Point suggestions for Baconian are <b>WIP</b>.'}


# ── Caesar ──────────────────────────────────────────────────────────────────

def suggest_caesar(payload):
    return {'suggested': 200, 'min': 150, 'max': 300,
            'text': 'Point suggestions for Caesar are <b>WIP</b>.'}


# ── Complete Columnar ─────────────────────────────────────────────────────────

def suggest_columnar(payload):
    return {'suggested': 300, 'min': 200, 'max': 450,
            'text': 'Point suggestions for Complete Columnar are <b>WIP</b>.'}


# ── Cryptarithm ───────────────────────────────────────────────────────────────

def suggest_cryptarithm(payload):
    return {'suggested': 300, 'min': 200, 'max': 500,
            'text': 'Point suggestions for Cryptarithm are <b>WIP</b>.'}


# ── Fractionated Morse ────────────────────────────────────────────────────────

def suggest_fracmorse(payload):
    return {'suggested': 350, 'min': 250, 'max': 500,
            'text': 'Point suggestions for Fractionated Morse are <b>WIP</b>.'}


# ── Hill ──────────────────────────────────────────────────────────────────────

def suggest_hill(payload):
    return {'suggested': 400, 'min': 300, 'max': 600,
            'text': 'Point suggestions for Hill are <b>WIP</b>.'}


# ── Nihilist ──────────────────────────────────────────────────────────────────

def suggest_nihilist(payload):
    return {'suggested': 350, 'min': 250, 'max': 500,
            'text': 'Point suggestions for Nihilist are <b>WIP</b>.'}


# ── Porta ─────────────────────────────────────────────────────────────────────

def suggest_porta(payload):
    return {'suggested': 300, 'min': 200, 'max': 450,
            'text': 'Point suggestions for Porta are <b>WIP</b>.'}


# ── Affine ────────────────────────────────────────────────────────────────────

def suggest_affine(payload):
    return {'suggested': 300, 'min': 200, 'max': 450,
            'text': 'Point suggestions for Affine are <b>WIP</b>.'}


# ── Checkerboard ──────────────────────────────────────────────────────────────

def suggest_checkerboard(payload):
    return {'suggested': 350, 'min': 250, 'max': 500,
            'text': 'Point suggestions for Checkerboard are <b>WIP</b>.'}


# ── Homophonic ────────────────────────────────────────────────────────────────

def suggest_homophonic(payload):
    return {'suggested': 350, 'min': 250, 'max': 500,
            'text': 'Point suggestions for Homophonic are <b>WIP</b>.'}


# ── Dispatch ──────────────────────────────────────────────────────────────────

_HANDLERS = {
    'ARISTOCRAT': suggest_aristocrat_family,
    'PATRISTOCRAT': suggest_aristocrat_family,
    'XENOCRYPT': suggest_aristocrat_family,
    'ATBASH': suggest_atbash,
    'BACONIAN': suggest_baconian,
    'CAESAR': suggest_caesar,
    'COLUMNAR': suggest_columnar,
    'CRYPTARITHM': suggest_cryptarithm,
    'FRACMORSE': suggest_fracmorse,
    'HILL': suggest_hill,
    'NIHILIST': suggest_nihilist,
    'PORTA': suggest_porta,
    'AFFINE': suggest_affine,
    'CHECKERBOARD': suggest_checkerboard,
    'HOMOPHONIC': suggest_homophonic,
}


def get_suggestion(payload):
    cipher = (payload.get('cipher') or '').upper()
    handler = _HANDLERS.get(cipher)
    if not handler:
        return {'suggested': 250, 'min': 150, 'max': 400,
                'text': f'Point suggestions for {cipher} are <b>WIP</b>.'}
    return handler(payload)