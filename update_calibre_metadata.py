"""
Update Calibre library metadata (title, authors, tags) from a CSV.

Normally started by double-clicking  "Update Calibre Metadata.bat".
You can also run it by hand with Calibre's bundled Python:

    calibre-debug -e update_calibre_metadata.py -- --new my.csv            # dry run
    calibre-debug -e update_calibre_metadata.py -- --new my.csv --apply    # write

IMPORTANT: Calibre (and its Content Server) must be closed when using --apply.

What gets changed
-----------------
ONLY title (+ title sort), authors (+ author sort) and tags. Tags are completely
replaced by what is in the CSV (a clean rewrite). Ratings, series, comments,
covers, identifiers, publisher, dates, formats etc. are NOT touched.
(Exception: with --split-series the series field is set from the title.)

The CSV needs the columns  title, author, tags   (several authors or tags are
separated with ";"). Optionally an  id  column (Calibre's book id).

How each CSV row is matched to a book
-------------------------------------
1. If the CSV has an "id" column      -> by Calibre book id (most reliable).
2. Else, if the CSV has exactly as many rows as the "old" export
   (My books2.csv)                    -> row N of the old export = row N of the CSV,
                                         the book is found by its current title +
                                         author sort as listed in the old export.
                                         The row -> book id mapping is remembered in
                                         book_id_map.json so re-runs keep working.
3. Otherwise                          -> by title (+ authors) as it is now in Calibre.

Options
-------
  --new CSV           CSV with the wanted metadata (required)
  --old CSV           export of the current metadata (default: My books2.csv next to this script)
  --library PATH      Calibre library folder (default: read from Calibre's settings)
  --apply             actually write the changes (otherwise only a dry run)
  --split-series      turn "Title (Series #3)" into title "Title", series "Series", index 3
  --report PATH       where to write the report (default: report.md next to this script)
"""

import argparse
import csv
import html
import json
import os
import re
import shutil
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
DOWNLOADS = os.path.join(os.path.expanduser('~'), 'Downloads')

# Rules applied to rows of the NEW csv: matching rows are never written.
# The Calibre-generated catalog is not a real book - delete it in Calibre instead.
SKIP_IF = [
    lambda new: new.get('author', '').strip().lower() == 'calibre' and 'catalog' in new.get('tags', '').lower(),
]

SERIES_RE = re.compile(r'^(?P<title>.+?)\s*\((?P<series>[^()#]+?)\s*#(?P<idx>\d+(?:\.\d+)?)\)\s*$')


# --------------------------------------------------------------------------- helpers
def norm(s):
    s = unicodedata.normalize('NFC', s or '')
    return ' '.join(s.split()).casefold()


def split_list(value, sep=';'):
    return [p.strip() for p in (value or '').split(sep) if p.strip()]


def read_csv(path):
    """Read a CSV into dicts. Tolerates unquoted commas in the FIRST column
    (deepseek_csv.csv has titles like `84, Charing Cross Road` without quotes):
    surplus fields are glued back onto the first column."""
    with open(path, newline='', encoding='utf-8-sig') as f:
        rows = list(csv.reader(f))
    header = [h.strip().lower() for h in rows[0]]
    out = []
    n = len(header)
    for r in rows[1:]:
        if not any(c.strip() for c in r):
            continue
        if len(r) > n:
            extra = len(r) - n
            r = [','.join(r[:extra + 1])] + r[extra + 1:]
        out.append(dict(zip(header, r + [''] * (n - len(r)))))
    return out


def find_matching_old_csv(target_rows):
    """Look for an export CSV (My books3.csv, My books2.csv, etc.) with the same row count."""
    candidates = [
        os.path.join(HERE, 'My books3.csv'),
        os.path.join(DOWNLOADS, 'My books3.csv'),
        os.path.join(HERE, 'My books2.csv'),
        os.path.join(DOWNLOADS, 'My books2.csv'),
    ]
    for path in candidates:
        if os.path.exists(path):
            rows = read_csv(path)
            if len(rows) == target_rows:
                return path, rows
    return None, []


def default_library():
    try:
        from calibre.utils.config import prefs
        lp = prefs['library_path']
        if lp:
            return lp
    except Exception:
        pass
    return os.path.join(os.path.expanduser('~'), 'Calibre Library')


def backup_db(library):
    src = os.path.join(library, 'metadata.db')
    dst = os.path.join(library, 'metadata.db.bak-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
    shutil.copy2(src, dst)
    return dst


# --------------------------------------------------------------------------- main
def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--new', required=True)
    ap.add_argument('--old', default=None)
    ap.add_argument('--library', default=None)
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--split-series', action='store_true')
    ap.add_argument('--report', default=os.path.join(HERE, 'report.md'))
    ap.add_argument('--preview-html', default=os.path.join(HERE, 'preview.html'))
    ap.add_argument('--map-file', default=os.path.join(HERE, 'book_id_map.json'))
    args = ap.parse_args(argv)

    from calibre.library import db as open_db
    from calibre.ebooks.metadata import title_sort

    library = args.library or default_library()
    if not os.path.exists(os.path.join(library, 'metadata.db')):
        sys.exit(f'ERROR: no Calibre library found at {library}')
    new_rows = read_csv(args.new)
    if not new_rows or 'title' not in new_rows[0]:
        sys.exit('ERROR: the CSV needs at least a "title" column (plus "author" and "tags").')
    has_author = 'author' in new_rows[0]
    has_tags = 'tags' in new_rows[0]

    if args.old and os.path.exists(args.old):
        old_path, old_rows = args.old, read_csv(args.old)
    else:
        old_path, old_rows = find_matching_old_csv(len(new_rows))
    if 'id' in new_rows[0]:
        mode = 'id'
    elif old_rows and len(old_rows) == len(new_rows):
        mode = 'row'
    else:
        mode = 'title'

    print(f'Library : {library}')
    print(f'CSV     : {args.new} ({len(new_rows)} rows)')
    print('Matching: ' + {'id': 'by the "id" column',
                          'row': f'row by row against {os.path.basename(old_path or "")}',
                          'title': 'by the current title in Calibre'}[mode])
    print('Mode    : ' + ('APPLY (writing changes)' if args.apply else 'DRY RUN (nothing is changed)'))
    print()

    if args.apply:
        print('Backup  : ' + backup_db(library))
        print()

    cache = open_db(library).new_api
    all_ids = set(cache.all_book_ids())

    by_title_as = defaultdict(list)
    by_title = defaultdict(list)
    for bid in all_ids:
        t = cache.field_for('title', bid)
        by_title_as[(norm(t), norm(cache.field_for('author_sort', bid)))].append(bid)
        by_title[norm(t)].append(bid)

    def authors_equal(bid, author_field):
        return [norm(a) for a in cache.field_for('authors', bid)] == [norm(a) for a in split_list(author_field)]

    def match_by_title(title, author_field):
        cand = by_title.get(norm(title), [])
        if has_author:
            exact = [b for b in cand if authors_equal(b, author_field)]
            if exact:
                return exact
        return cand if len(cand) == 1 else []

    saved_map = {}
    if mode == 'row' and os.path.exists(args.map_file):
        with open(args.map_file, encoding='utf-8') as f:
            raw = json.load(f)
        if isinstance(raw, dict) and raw.get('old_csv') == os.path.basename(old_path or ''):
            saved_map = {int(k): v for k, v in raw.get('map', {}).items()}

    planned = []        # (row_no, book_id, new_values, current_values)
    unmatched = []      # (row_no, description)
    ambiguous = []      # (row_no, title, ids)
    skipped = []        # (row_no, new_row)
    matched_ids = set()
    new_map = {}

    for i, new in enumerate(new_rows, start=1):
        if any(rule(new) for rule in SKIP_IF):
            skipped.append((i, new))
            continue

        ids = []
        if mode == 'id':
            try:
                bid = int(new['id'])
                ids = [bid] if bid in all_ids else []
            except ValueError:
                ids = []
            desc = f'id {new["id"]!r} "{new["title"]}"'
        elif mode == 'row':
            old = old_rows[i - 1]
            desc = f'"{old["title"]}" / {old.get("author_sort", "")}  ->  "{new["title"]}"'
            if saved_map.get(i) in all_ids:
                ids = [saved_map[i]]
            else:
                ids = by_title_as.get((norm(old['title']), norm(old.get('author_sort', ''))), [])
                if not ids:
                    cand = by_title.get(norm(old['title']), [])
                    ids = cand if len(cand) == 1 else []
                if not ids:   # already renamed on an earlier run
                    ids = match_by_title(new['title'], new.get('author', ''))
        else:
            desc = f'"{new["title"]}" by {new.get("author", "?")}'
            ids = match_by_title(new['title'], new.get('author', ''))

        if not ids:
            unmatched.append((i, desc))
            continue
        if len(ids) > 1:
            ambiguous.append((i, new['title'], ids))   # identical copies: all get updated

        for bid in ids:
            matched_ids.add(bid)
            new_map.setdefault(i, bid)

            title = new['title'].strip()
            vals = {}
            if args.split_series:
                m = SERIES_RE.match(title)
                if m:
                    title = m['title'].strip()
                    vals['series'] = m['series'].strip()
                    vals['series_index'] = float(m['idx'])
            vals['title'] = title
            vals['sort'] = title_sort(title)
            if has_author:
                authors = split_list(new['author']) or ['Unknown']
                vals['authors'] = authors
                vals['author_sort'] = cache.author_sort_from_authors(authors)
            if has_tags:
                vals['tags'] = split_list(new['tags'])        # clean rewrite, no merging
            cur = {
                'title': cache.field_for('title', bid),
                'authors': list(cache.field_for('authors', bid)),
                'tags': list(cache.field_for('tags', bid)),
            }
            planned.append((i, bid, vals, cur))

    # ------------------------------------------------------------------ show plan
    changed = 0
    preview_blocks = []
    preview_rows = []   # (row_no, title, author_str, tags_str, is_changed)
    for i, bid, vals, cur in planned:
        final_title = vals['title']
        final_authors = vals.get('authors', cur['authors'])
        final_tags = vals.get('tags', cur['tags'])
        is_changed = (
            final_title != cur['title']
            or final_authors != cur['authors']
            or final_tags != cur['tags']
            or 'series' in vals
        )
        if is_changed:
            changed += 1
        author_str = '; '.join(final_authors)
        tags_str = '; '.join(final_tags) if final_tags else '(none)'
        preview_rows.append((i, final_title, author_str, tags_str, is_changed))
        preview_blocks.append(
            f'{i:3}. {final_title}\n'
            f'     Author: {author_str}\n'
            f'     Tags:   {tags_str}\n'
        )
    print('\n'.join(preview_blocks))

    # ------------------------------------------------------------------ write
    if args.apply and planned:
        for field in ('title', 'sort', 'authors', 'author_sort', 'tags', 'series', 'series_index'):
            m = {bid: vals[field] for _, bid, vals, _ in planned if field in vals}
            if m:
                cache.set_field(field, m)
        if mode == 'row':
            with open(args.map_file, 'w', encoding='utf-8') as f:
                json.dump({'old_csv': os.path.basename(old_path or ''), 'map': {**saved_map, **new_map}}, f, indent=1)
        print(f'\nDONE: wrote changes to {len(planned)} books.')

    # ------------------------------------------------------------------ report & HTML preview
    final = defaultdict(list)
    for i, bid, vals, _ in planned:
        final[(norm(vals['title']), tuple(map(norm, vals.get('authors', []))))].append((i, bid))
    dup_groups = [v for v in final.values() if len({b for _, b in v}) > 1]
    not_in_csv = sorted(all_ids - matched_ids)
    sus = [(i, n) for i, n in enumerate(new_rows, 1)
           if (has_author and norm(n['author']) in ('unknown', ''))
           or re.search(r'_v\d+|[A-Za-z]\d{2}$', n['title'])]

    lines = [f'# Calibre metadata update report ({datetime.now():%Y-%m-%d %H:%M})', '',
             f'- Library: `{library}`',
             f'- CSV: `{args.new}`',
             f'- Mode: {"APPLIED" if args.apply else "dry run (nothing changed)"}',
             f'- Books matched: {len(matched_ids)} ({changed} will change)', '',
             '## How your books will look (Title with Series | Author | Tags)', '']
    for i, title, author_str, tags_str, _ in preview_rows:
        lines += [f'{i}. **{title}**', f'   - Author: {author_str}', f'   - Tags: {tags_str}', '']
    lines += ['## Duplicates (same title + authors after the update)', '']
    if dup_groups:
        for members in dup_groups:
            for i, bid in members:
                fmts = ', '.join(cache.formats(bid)) or 'no files'
                lines.append(f'- row {i}: book #{bid} "{new_rows[i-1]["title"]}" [{fmts}]')
            lines.append('')
    else:
        lines += ['None.', '']
    lines += ['## CSV rows not found in the library', '']
    lines += [f'- row {i}: {d}' for i, d in unmatched] or ['None.']
    lines += ['', '## CSV rows matching more than one book (identical copies)', '']
    lines += [f'- row {i}: "{t}" -> books {ids}' for i, t, ids in ambiguous] or ['None.']
    lines += ['', '## Skipped rows', '']
    lines += [f'- row {i}: "{n["title"]}" (Calibre catalog, not a book - delete it in Calibre)'
              for i, n in skipped] or ['None.']
    lines += ['', '## Books in the library that are not in the CSV (left unchanged)', '']
    lines += [f'- book #{b}: "{cache.field_for("title", b)}" by '
              f'{" & ".join(cache.field_for("authors", b))}' for b in not_in_csv] or ['None.']
    lines += ['', '## Entries that still look suspicious (Unknown author etc.)', '']
    lines += [f'- row {i}: "{n["title"]}" by {n.get("author", "?")}' for i, n in sus] or ['None.']

    with open(args.report, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')

    # Write a dyslexia-friendly HTML preview showing the exact final result
    def esc(s):
        return html.escape(str(s))

    table_rows = []
    for i, title, author_str, tags_str, _ in preview_rows:
        table_rows.append(
            f'<tr>'
            f'<td class="num">{i}</td>'
            f'<td class="title">{esc(title)}</td>'
            f'<td class="author">{esc(author_str)}</td>'
            f'<td class="tags">{esc(tags_str)}</td>'
            f'</tr>'
        )

    def section_list(heading, items):
        if not items:
            return f'<h2>{esc(heading)}</h2><p class="muted">None.</p>'
        lis = ''.join(f'<li>{esc(item)}</li>' for item in items)
        return f'<h2>{esc(heading)}</h2><ul>{lis}</ul>'

    dup_items = []
    for members in dup_groups:
        for i, bid in members:
            fmts = ', '.join(cache.formats(bid)) or 'no files'
            dup_items.append(f'Row {i} (book #{bid}): {new_rows[i-1]["title"]} [{fmts}]')
    unmatched_items = [f'Row {i}: {d}' for i, d in unmatched]
    skipped_items = [f'Row {i}: {n["title"]} (Calibre catalog - not a book)' for i, n in skipped]
    extra_items = [f'Book #{b}: {cache.field_for("title", b)} — {"; ".join(cache.field_for("authors", b))}'
                   for b in not_in_csv]
    sus_items = [f'Row {i}: {n["title"]} — Author: {n.get("author", "?")}' for i, n in sus]

    status_banner = (
        'APPLIED — these changes have been saved to your Calibre library.'
        if args.apply else
        'PREVIEW ONLY — nothing has been changed yet. Check this list, then go back to the black window and press Y to apply or N to cancel.'
    )
    html_doc = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Calibre Metadata Preview</title>
<style>
  body {{
    background: #FAF8F5;
    color: #1F1F1F;
    font-family: Verdana, Arial, sans-serif;
    font-size: 16px;
    line-height: 1.65;
    letter-spacing: 0.02em;
    max-width: 1200px;
    margin: 24px auto;
    padding: 0 24px 60px;
  }}
  h1 {{ font-size: 24px; margin-bottom: 8px; }}
  h2 {{ font-size: 19px; margin-top: 36px; border-bottom: 2px solid #D8D2C8; padding-bottom: 6px; }}
  .banner {{
    background: {"#E3F2E6" if args.apply else "#FFF3CD"};
    border-left: 6px solid {"#2E7D32" if args.apply else "#C98A00"};
    padding: 14px 18px;
    margin: 16px 0 24px;
    font-weight: bold;
  }}
  .summary {{ margin-bottom: 20px; }}
  table {{
    width: 100%;
    border-collapse: collapse;
    margin-top: 12px;
  }}
  th {{
    background: #E8E2D8;
    text-align: left;
    padding: 12px 14px;
    border-bottom: 2px solid #C5BEB2;
    position: sticky;
    top: 0;
  }}
  td {{
    padding: 12px 14px;
    border-bottom: 1px solid #E2DDD4;
    vertical-align: top;
    text-align: left;
  }}
  tr:nth-child(even) td {{ background: #F2EFE9; }}
  td.num {{ width: 48px; color: #666; }}
  td.title {{ font-weight: bold; width: 42%; }}
  td.author {{ width: 24%; }}
  td.tags {{ width: 30%; }}
  ul {{ padding-left: 24px; }}
  li {{ margin-bottom: 8px; }}
  .muted {{ color: #666; }}
</style>
</head>
<body>
  <h1>Calibre Library Preview</h1>
  <div class="banner">{esc(status_banner)}</div>
  <div class="summary">
    <strong>Books matched:</strong> {len(matched_ids)} &nbsp;|&nbsp;
    <strong>Will change:</strong> {changed} &nbsp;|&nbsp;
    <strong>Duplicates:</strong> {len(dup_groups)} &nbsp;|&nbsp;
    <strong>Not found:</strong> {len(unmatched)} &nbsp;|&nbsp;
    <strong>CSV:</strong> {esc(os.path.basename(args.new))}
  </div>
  <table>
    <thead>
      <tr>
        <th>#</th>
        <th>Title (with Series)</th>
        <th>Author</th>
        <th>Tags</th>
      </tr>
    </thead>
    <tbody>
      {''.join(table_rows)}
    </tbody>
  </table>
  {section_list('Duplicates (same title and author)', dup_items)}
  {section_list('Still need checking (Unknown author or unclear title)', sus_items)}
  {section_list('CSV rows not found in your Calibre library', unmatched_items)}
  {section_list('Skipped (not a book)', skipped_items)}
  {section_list('Books in your Calibre library not in the CSV (left untouched)', extra_items)}
</body>
</html>
'''
    with open(args.preview_html, 'w', encoding='utf-8') as f:
        f.write(html_doc)

    print()
    print('=' * 70)
    print(f'SUMMARY: {changed} books {"changed" if args.apply else "would change"}, '
          f'{len(unmatched)} CSV rows not found, {len(dup_groups)} duplicate group(s), '
          f'{len(not_in_csv)} library books not in the CSV.')
    print(f'Easy-to-read preview: {args.preview_html}')
    print('=' * 70)


if __name__ == '__main__':
    main(sys.argv[1:])
