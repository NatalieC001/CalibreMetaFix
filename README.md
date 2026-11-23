# CalibreMetaFix

Simple, double-click Windows tools for bulk-updating metadata and merging duplicate books in a **Calibre** e-book library — no coding or separate Python installation required.

Everything runs using the Python bundled inside Calibre (`calibre-debug`), shows a **dyslexia-friendly preview in your web browser** before making any changes, and automatically backs up your Calibre database (`metadata.db`) before writing.

---

## Requirements

- **Windows**
- **Calibre** installed in the default location (`C:\Program Files\Calibre2\`)
  *(If installed elsewhere, edit `CAL_DIR` near the top of the `.bat` files.)*

---

## Included Tools

### 1. Update Calibre Metadata (`Update Calibre Metadata.bat`)

Updates **Title**, **Author**, and **Tags** for your books from a CSV file.

**What it changes:**
- **Title** (and Calibre's Title Sort)
- **Authors** (and Calibre's Author Sort)
- **Tags** — clean rewrite using only the tags in your CSV (old messy tags are replaced, not merged)

**What it leaves untouched:**
- Ratings, covers, comments, series field, dates, publisher, identifiers, and book files (unless you choose the optional final step to embed metadata into the book files).

**How to use it:**
1. Close Calibre completely.
2. Double-click **`Update Calibre Metadata.bat`**.
3. Pick your CSV file in the file picker window.
4. A clean preview (`preview.html`) opens in your web browser showing every book in exact order:
   **Title (with Series)** | **Author** | **Tags**
   Nothing has changed yet.
5. Return to the terminal window and press **Y** to apply (or **N** to cancel).
6. Optionally press **Y** to write the updated metadata directly into the ebook files (`calibredb embed_metadata all`).

---

### 2. Remove & Merge Duplicates (`Remove Duplicates.bat`)

Finds duplicate books (same Title and Author) and safely cleans them up.

**Rules:**
- **Always keeps a copy that has book files** — any broken `[no files]` duplicate is deleted automatically.
- **Merges different formats** — if one copy is `[EPUB]` and another is `[PDF]`, both formats are combined into the kept book so nothing is lost.
- **Preserves ratings** — prefers rated copies (and copies the rating over if needed).
- **Safe removal** — creates a `metadata.db` backup first and sends removed copies to the Windows Recycle Bin.

**How to use it:**
1. Close Calibre completely.
2. Double-click **`Remove Duplicates.bat`**.
3. Review the browser preview (`duplicates_preview.html`) showing **KEEP**, **MERGE FORMAT**, and **DELETE** for each duplicate group.
4. Return to the terminal window and press **Y** to apply (or **N** to cancel).

---

## Preparing Your CSV

See the `examples/` folder for public examples:
- [`examples/sample_books.csv`](examples/sample_books.csv) — example CSV showing the exact format
- [`examples/sample_preview.html`](examples/sample_preview.html) — example of the dyslexia-friendly browser preview for metadata updates
- [`examples/sample_duplicates_preview.html`](examples/sample_duplicates_preview.html) — example of the duplicate merger browser preview

Your CSV should have three columns:

| Column | Format | Example |
|---|---|---|
| `title` | Book title (put series inside parentheses if desired) | `The Fellowship of the Ring (The Lord of the Rings #1)` |
| `author` | Author name (`First Last`); separate multiple authors with `;` | `Terry Pratchett; Neil Gaiman` |
| `tags` | Tags separated with `;` | `Fantasy; Humour; Fiction` |

*(If a title contains a comma, wrap it in quotes, e.g. `"84, Charing Cross Road"`. The script also tolerates unquoted commas in the first column.)*

### How CSV rows are matched to books in Calibre
1. **`id` column (most reliable):** If your CSV includes Calibre's numeric `id` column, books are matched directly by ID.
2. **Row-aligned export:** If an export of your current library (e.g. `My books2.csv` or `My books3.csv`) with the same number of rows is placed in the same folder, row N of your new CSV updates row N of the export.
3. **Current title:** Otherwise, books are matched by their current title (and author) in Calibre.

---

## Optional Command-Line Flags

Advanced users can run the Python scripts directly via `calibre-debug`:

```bat
calibre-debug -e update_calibre_metadata.py -- --new examples\sample_books.csv
calibre-debug -e update_calibre_metadata.py -- --new examples\sample_books.csv --apply
calibre-debug -e update_calibre_metadata.py -- --new examples\sample_books.csv --split-series --apply
calibre-debug -e remove_duplicates.py -- --apply
```

- `--split-series`: Moves `(Series Name #1)` out of the title and into Calibre's dedicated Series & Series Index fields.
- `--library PATH`: Target a specific Calibre library folder instead of Calibre's default library.

---

## Safety & Undo

Before any `--apply` run, a timestamped backup is saved inside your Calibre library folder:

```text
metadata.db.bak-YYYYMMDD-HHMMSS
```

To undo changes:
1. Close Calibre.
2. Open your Calibre library folder.
3. Delete `metadata.db` and rename the newest `metadata.db.bak-...` file to `metadata.db`.
