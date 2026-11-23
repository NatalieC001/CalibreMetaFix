"""
Find and merge/remove duplicate books in a Calibre library.

Normally started by double-clicking  "Remove Duplicates.bat".
You can also run it by hand:

    calibre-debug -e remove_duplicates.py                  # preview only
    calibre-debug -e remove_duplicates.py -- --apply       # apply changes

IMPORTANT: Calibre (and its Content Server) must be closed when using --apply.

Rules for every duplicate group (same Title + same Authors)
-----------------------------------------------------------
1. Always keep a copy that HAS book files (a copy with no files is broken and
   is deleted).
2. Among copies that have files, prefer the one with a rating, then EPUB,
   then the original (lowest book ID).
3. If a duplicate being removed has a format the kept copy does NOT have
   (for example [EPUB] and [PDF]), that format is merged into the kept book
   first so nothing is lost.
4. If the kept copy has no rating but a duplicate being removed does, the
   rating is copied over before deletion.
"""

import argparse
import html
import os
import shutil
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))


def norm(s):
    s = unicodedata.normalize('NFC', s or '')
    return ' '.join(s.split()).casefold()


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


def format_rating(r):
    if not r:
        return ''
    stars = r / 2
    return f'{stars:g} star' + ('s' if stars != 1 else '')


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--library', default=None)
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--preview-html', default=os.path.join(HERE, 'duplicates_preview.html'))
    args = ap.parse_args(argv)

    from calibre.library import db as open_db

    library = args.library or default_library()
    if not os.path.exists(os.path.join(library, 'metadata.db')):
        sys.exit(f'ERROR: no Calibre library found at {library}')

    print(f'Library : {library}')
    print('Mode    : ' + ('APPLY (merging & removing duplicates)' if args.apply else 'PREVIEW ONLY (nothing is changed)'))
    print()

    cache = open_db(library).new_api
    all_ids = sorted(cache.all_book_ids())

    # Group books by normalised (title, authors)
    groups = defaultdict(list)
    no_file_standalone = []
    for bid in all_ids:
        title = cache.field_for('title', bid)
        authors = tuple(cache.field_for('authors', bid))
        key = (norm(title), tuple(norm(a) for a in authors))
        groups[key].append(bid)

    dup_groups = [bids for bids in groups.values() if len(bids) > 1]
    for bids in groups.values():
        if len(bids) == 1 and not cache.formats(bids[0]):
            no_file_standalone.append(bids[0])

    # Plan each duplicate group
    plans = []   # list of dicts describing keep, removes, merges, rating_copy
    for bids in sorted(dup_groups, key=lambda b: norm(cache.field_for('title', b[0]))):
        def keep_score(bid):
            fmts = list(cache.formats(bid))
            rating = cache.field_for('rating', bid) or 0
            has_files = 1 if fmts else 0
            has_rating = 1 if rating > 0 else 0
            has_epub = 1 if 'EPUB' in [f.upper() for f in fmts] else 0
            # Higher tuple wins; negate bid so original (lowest ID) wins ties
            return (has_files, has_rating, has_epub, len(fmts), -bid)

        ranked = sorted(bids, key=keep_score, reverse=True)
        keep_id = ranked[0]
        drop_ids = ranked[1:]

        keep_fmts = set(f.upper() for f in cache.formats(keep_id))
        keep_rating = cache.field_for('rating', keep_id) or 0

        merges = []        # (from_bid, fmt)
        rating_from = None
        new_rating = keep_rating
        planned_fmts = set(keep_fmts)

        for did in drop_ids:
            for fmt in cache.formats(did):
                uf = fmt.upper()
                if uf not in planned_fmts:
                    merges.append((did, fmt))
                    planned_fmts.add(uf)
            dr = cache.field_for('rating', did) or 0
            if dr > new_rating:
                new_rating = dr
                rating_from = did

        plans.append({
            'title': cache.field_for('title', keep_id),
            'authors': '; '.join(cache.field_for('authors', keep_id)),
            'keep_id': keep_id,
            'keep_fmts': sorted(keep_fmts),
            'final_fmts': sorted(planned_fmts),
            'final_rating': new_rating,
            'rating_from': rating_from,
            'merges': merges,
            'drops': [(did, sorted(f.upper() for f in cache.formats(did))) for did in drop_ids],
        })

    # Console preview
    total_remove = sum(len(p['drops']) for p in plans)
    total_merges = sum(len(p['merges']) for p in plans)

    for idx, p in enumerate(plans, 1):
        keep_fmt_str = ', '.join(p['final_fmts']) or 'no files'
        r_str = f' | {format_rating(p["final_rating"])}' if p['final_rating'] else ''
        print(f'{idx:2}. {p["title"]}')
        print(f'    Author : {p["authors"]}')
        print(f'    KEEP   : book #{p["keep_id"]} [{keep_fmt_str}]{r_str}')
        for did, fmt in p['merges']:
            print(f'    MERGE  : copy [{fmt}] from book #{did} into book #{p["keep_id"]}')
        for did, fmts in p['drops']:
            fstr = ', '.join(fmts) if fmts else 'no files - broken'
            print(f'    DELETE : book #{did} [{fstr}]')
        print()

    # Apply changes
    if args.apply and plans:
        print('Backup  : ' + backup_db(library))
        to_delete = []
        for p in plans:
            keep_id = p['keep_id']
            for did, fmt in p['merges']:
                path = cache.format_abspath(did, fmt)
                if path and os.path.exists(path):
                    cache.add_format(keep_id, fmt, path, replace=False)
            if p['rating_from'] is not None:
                cache.set_field('rating', {keep_id: p['final_rating']})
            to_delete.extend(did for did, _ in p['drops'])
        if to_delete:
            cache.remove_books(to_delete, permanent=False)
        print(f'DONE: merged {total_merges} format(s) and removed {len(to_delete)} duplicate book(s).')

    # Write dyslexia-friendly HTML preview
    def esc(s):
        return html.escape(str(s))

    rows_html = []
    for idx, p in enumerate(plans, 1):
        keep_fmt_str = ', '.join(p['final_fmts']) or 'no files'
        r_note = f' ({format_rating(p["final_rating"])})' if p['final_rating'] else ''
        actions = [f'<div class="keep"><strong>KEEP:</strong> book #{p["keep_id"]} [{esc(keep_fmt_str)}]{esc(r_note)}</div>']
        for did, fmt in p['merges']:
            actions.append(f'<div class="merge"><strong>MERGE FORMAT:</strong> copy [{esc(fmt)}] from book #{did} so nothing is lost</div>')
        for did, fmts in p['drops']:
            fstr = ', '.join(fmts) if fmts else 'no files (broken)'
            actions.append(f'<div class="del"><strong>DELETE:</strong> book #{did} [{esc(fstr)}]</div>')
        rows_html.append(
            f'<tr>'
            f'<td class="num">{idx}</td>'
            f'<td class="title">{esc(p["title"])}</td>'
            f'<td class="author">{esc(p["authors"])}</td>'
            f'<td class="action">{"".join(actions)}</td>'
            f'</tr>'
        )

    standalone_html = ''
    if no_file_standalone:
        items = ''.join(
            f'<li>Book #{b}: <strong>{esc(cache.field_for("title", b))}</strong> — {esc("; ".join(cache.field_for("authors", b)))} [no files]</li>'
            for b in no_file_standalone
        )
        standalone_html = (
            '<h2>Other books with no files (not duplicates — left untouched)</h2>'
            f'<ul>{items}</ul>'
        )

    banner = (
        f'DONE — merged {total_merges} format(s) and removed {total_remove} duplicate book(s) (sent to Recycle Bin).'
        if args.apply else
        'PREVIEW ONLY — nothing has been deleted yet. Check this list, then go back to the black window and press Y to apply or N to cancel.'
    )

    html_doc = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Calibre Duplicates Preview</title>
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
  table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
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
  td.num {{ width: 42px; color: #666; }}
  td.title {{ font-weight: bold; width: 34%; }}
  td.author {{ width: 20%; }}
  td.action {{ width: 42%; }}
  .keep {{ color: #1B5E20; margin-bottom: 4px; }}
  .merge {{ color: #0D47A1; margin-bottom: 4px; }}
  .del {{ color: #9A1B1B; margin-bottom: 4px; }}
</style>
</head>
<body>
  <h1>Calibre Duplicates Preview</h1>
  <div class="banner">{esc(banner)}</div>
  <div class="summary">
    <strong>Duplicate groups found:</strong> {len(plans)} &nbsp;|&nbsp;
    <strong>Formats to merge:</strong> {total_merges} &nbsp;|&nbsp;
    <strong>Duplicate copies to remove:</strong> {total_remove}
  </div>
  {"<p>No duplicate books found! Your library is clean.</p>" if not plans else f"""
  <table>
    <thead>
      <tr>
        <th>#</th>
        <th>Title (with Series)</th>
        <th>Author</th>
        <th>What will happen</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows_html)}
    </tbody>
  </table>
  """}
  {standalone_html}
</body>
</html>
'''
    with open(args.preview_html, 'w', encoding='utf-8') as f:
        f.write(html_doc)

    print('=' * 70)
    print(f'SUMMARY: {len(plans)} duplicate group(s), {total_merges} format(s) to merge, '
          f'{total_remove} duplicate copy/copies to remove.')
    print(f'Easy-to-read preview: {args.preview_html}')
    print('=' * 70)


if __name__ == '__main__':
    main(sys.argv[1:])
