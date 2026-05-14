# Codebusters Test Builder

## Setup (one time)

1. Make sure Python is installed. Open a terminal / VSCode terminal.

2. Install dependencies:
   ```
   pip install flask pandas openpyxl numpy
   ```

3. Make sure `pdflatex` is on your PATH (you need a LaTeX install like TeX Live or MiKTeX).
   Test with: `pdflatex --version`

4. Copy your `sgb-words.txt` file into this folder (needed for Baconian Words).

## Run

In VSCode, open the terminal (Ctrl+`) and run:

```
python app.py
```

Then open your browser to: http://localhost:5000

## How to use

1. Fill in **Test Settings** at the top (tournament name, division, date, timed question).
2. In **Add Question**, pick a cipher, fill in the plaintext and keys, click **Add Question**.
3. The question appears in the list. **Drag rows to reorder.**
4. Click **Refresh Preview** to compile and see the PDF live in the right panel.
5. Switch between **Test** and **Answer Key** tabs.
6. Use **Download Test PDF** / **Download Key PDF** buttons to save.

## Key fields by cipher

| Cipher        | Key1          | Key2     | Key3          | Hint          |
|---------------|---------------|----------|---------------|---------------|
| Aristocrat    | Keyword       | Shift    | K1/K2/K3/blank| Hint text     |
| Patristocrat  | Keyword       | Shift    | K1/K2/K3/blank| Hint text     |
| Xenocrypt     | Keyword       | Shift    | K1/K2/K3/blank| Hint text     |
| Atbash        | —             | —        | Block size    | —             |
| Baconian      | A-letters     | B-letters| Crib/block    | Hint text     |
| Caesar        | Shift         | —        | —             | —             |
| Columnar      | # Columns     | Crib word| —             | —             |
| Cryptarithm   | Problem text  | Solution | Operation     | —             |
| Frac Morse    | Keyword       | Crib     | —             | Hint          |
| Hill          | Keyword (4/9) | —        | —             | —             |
| Nihilist      | Keyword       | Poly key | Block size    | —             |
| Porta         | Keyword       | —        | Block size    | —             |
| Affine        | a             | b        | Block size    | Crib/hint     |
| Checkerboard  | H-key (5)     | V-key (5)| Poly keyword  | Crib          |
