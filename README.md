# Codebusters Test Builder

## Setup

1. Install dependencies:
```
   pip install flask cryptography psycopg2-binary
```

2. Install a LaTeX distribution (TeX Live or MiKTeX) and confirm:
```
   pdflatex --version
```

3. Set environment variables:
   - `DATABASE_URL` — PostgreSQL connection string
   - `SECRET_KEY` — Flask session secret
   - `ENCRYPTION_KEY` — Fernet key for encrypting saved questions

4. Place these data files in the project root:

   | File | Purpose |
   |------|---------|
   | `sgb-words.txt` | Baconian Words |
   | `quotes.txt` | Practice test quote pool |
   | `quotesSpanish.txt` | Practice test Xenocrypt pool |
   | `keywords.txt` | Practice test keyword pool |
   | `homokw.txt` | Homophonic keywords (4-letter words) |
   | `checkkw.txt` | Checkerboard keys (5-letter words) |

## Run

```
python app.py
```

Then open: http://localhost:5000

## Test Builder (`/builder`)

1. Fill in **Tournament Setup** — name, division, date, timed question, writers.
2. Pick a cipher, enter plaintext and keys, click **Add Question**.
3. Drag questions to reorder. Click a question to edit it.
4. Click **Refresh Preview** to compile the PDF.
5. Toggle between **Test** and **Answer Key** tabs.
6. **Download** buttons save the final PDFs.
7. **Share** lets other users view and edit the test.
8. **Edit History** logs all changes with before/after diffs.

## Practice Test Builder (`/practice`)

1. Configure a cipher and click **+ Add to Queue**. Repeat for different cipher types.
2. Click **Generate Practice Test** to batch-generate all questions.
3. Drag to reorder or click **×** to remove questions.
4. Preview and download as normal.

## Cipher key fields

| Cipher | Key1 | Key2 | Key3 | Key4 | Notes |
|--------|------|------|------|------|-------|
| Aristocrat | Keyword | Shift | K1/K2/K3 | — | |
| Patristocrat | Keyword | Shift | K1/K2/K3 | — | |
| Xenocrypt | Keyword | Shift | K1/K2/K3 | — | Supports ñ |
| Atbash | — | — | Block size | — | |
| Baconian | A-letters | B-letters | — | — | Words type uses interactive A/B table |
| Caesar | Shift | — | — | — | |
| Columnar | # Columns | Crib word | — | — | |
| Cryptarithm | Problem text | Solution numbers | Operation | — | Template auto-fills |
| Fractionated Morse | Keyword | Crib | — | — | |
| Hill | Keyword (4 or 9 letters) | — | — | — | Validates determinant |
| Nihilist | Keyword | Polybius key | Block size | Crib | Crib must be >2× keyword length |
| Porta | Keyword | — | Block size | Crib | |
| Affine | a | b | Block size | Crib | a must be coprime with 26 |
| Checkerboard | H-key (5) | V-key (5) | Polybius keyword | Block size | Crib goes in Hint field |
| Homophonic | Keyword (4) | — | Block size | Crib | See below |

## Homophonic decode hint options

Applies to Decode type only. Ignored for Crib type.

| Letters Given | Difficulty | Hint shown |
|---------------|------------|------------|
| 4 or default | — | `keyword is BACK` |
| 2 or 3 | Easy | Random consecutive substring: `keyword contains string AC` |
| 2 or 3 | Hard | Random letters in alphabetical order: `keyword contains the letters A, C, and K` |