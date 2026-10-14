#!/usr/bin/env python3
"""EXAMPLE project sync (taken from a real talk project; edit COLL, FT and META for yours).
Syncs one Zotero collection:
- delete items that are not deck references (the three 2020 Lancet letters)
- create missing items (Brodeur 2026, Omar 2026) from DOI metadata
- set tags in the owner's style: project tag + folie/block/role/status tags
- upload PDFs from literature/fulltext/ as child attachments (idempotent)
Run: source ~/.api_keys && python3 build_scripts/zotero_sync.py
"""
import json
import os
import pathlib
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scripts'))
from zotero_local import Z  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
FT = ROOT / 'literature/fulltext'
COLL = 'PW2SQRWG'
PROJECT_TAG = 'AMIE_FB'

# doi (lowercase) -> (file, folien, block, rolle, fulltext_status)
META = {
 '10.1001/jama.281.3.283': ('Marvel_1999.pdf', ['03', '04b'], 'anamnese', 'kern', 'fulltext:read'),
 '10.1007/s11606-018-4540-5': ('SinghOspina_2018.pdf', ['03'], 'anamnese', 'kern', 'fulltext:read'),
 'pmid:11456245': ('Rhoades_2001_FamMed.pdf', ['03'], 'anamnese', 'kontext', 'fulltext:read'),
 '10.1111/j.1525-1497.2005.40266.x': ('Dyche_2005.pdf', ['03', '04b'], 'anamnese', 'kontext', 'fulltext:read'),
 '10.1136/bmj.325.7366.682': ('Langewitz_2002.pdf', ['04', '04b', '08'], 'anamnese', 'kern', 'fulltext:read'),
 '10.1136/bmj.2.5969.486': ('Hampton_1975.pdf', ['05', '06', '06b'], 'anamnese', 'kern', 'abstract:only'),
 'pmid:1536065': ('Peterson_1992.pdf', ['06', '06b'], 'anamnese', 'kontext', 'abstract:only'),
 'pmid:11273467': ('Roshan_2000.pdf', ['06'], 'anamnese', 'kontext', 'abstract:only'),
 '10.1007/s00423-026-04098-z': ('Henn_2026.pdf', ['07', '07b'], 'chirurgie', 'kern', 'abstract:only'),
 '10.1136/bmj.325.7362.472': ('Deveugele_2002.pdf', ['08'], 'dauer', 'kern', 'fulltext:read'),
 '10.1111/j.1475-6773.2006.00689.x': ('TaiSeale_2007.pdf', ['08'], 'dauer', 'kontext', 'fulltext:read'),
 '10.1136/bmjopen-2017-017902': ('Irving_2017.pdf', ['08', '08b'], 'dauer', 'kontext', 'fulltext:read'),
 'pmid:12528590': ('Wilson_2002.pdf', ['08b'], 'dauer', 'kontext', 'abstract:only'),
 '10.1002/14651858.cd003540.pub3': ('Wilson_2016.pdf', ['08b'], 'dauer', 'kontext', 'abstract:only'),
 '10.1136/bmjoq-2023-002311': ('LenGarca_2023.pdf', ['08b'], 'dauer', 'kontext', 'abstract:only'),
 '10.1136/bmj.323.7316.784': ('Campbell_2001.pdf', ['08b'], 'dauer', 'kontext', 'abstract:only'),
 '10.3399/bjgp16x687733': ('Elmore_2016.pdf', ['08b'], 'dauer', 'kontext', 'abstract:only'),
 '10.1097/acm.0000000000001098': ('ALQahtani_2016.pdf', ['08b'], 'dauer', 'kontext', 'abstract:only'),
 '10.1111/medu.13686': ('ALQahtani_2018.pdf', ['08b'], 'dauer', 'kontext', 'abstract:only'),
 '10.1001/jamahealthforum.2023.0052': ('Neprash_2023.pdf', ['08b'], 'dauer', 'kontext', 'abstract:only'),
 '10.1038/s41586-025-08866-7': ('Tu_2025.pdf', ['10'], 'amie', 'kern', 'abstract:only'),
 '10.1038/s41586-025-08869-4': ('McDuff_2025.pdf', ['10', '17'], 'amie', 'kern', 'abstract:only'),
 '10.1016/s0140-6736(26)01535-7': ('Brodeur_2026.pdf', ['10', '11', '12', '13', '13b', '14', '15', '16', '18'], 'amie', 'kern', 'fulltext:read'),
 '10.1016/s0140-6736(26)01763-0': ('Omar_2026.pdf', ['12', '16'], 'amie', 'kern', 'fulltext:read'),
 '10.1001/jamanetworkopen.2024.40969': ('Goh_2024.pdf', ['17'], 'ki_arzt', 'kern', 'abstract:only'),
 '10.1038/s41591-024-03456-y': ('Goh_2025.pdf', ['17'], 'ki_arzt', 'kontext', 'abstract:only'),
 '10.1515/dx-2025-0176': ('Healy_2026.pdf', ['17'], 'ki_arzt', 'kontext', 'abstract:only'),
 '10.1001/jama.2023.22295': ('Jabbour_2023.pdf', ['18', '18b'], 'ki_risiken', 'kern', 'abstract:only'),
 '10.1148/radiol.222176': ('Dratsch_2023.pdf', ['18', '18b'], 'ki_risiken', 'kontext', 'abstract:only'),
 '10.1001/jamanetworkopen.2025.49963': ('Lee_2025.pdf', ['18', '18b'], 'ki_risiken', 'kern', 'abstract:only'),
 '10.1038/s41746-025-01670-7': ('Asgari_2025.pdf', ['18'], 'ki_risiken', 'kontext', 'abstract:only'),
 '10.1177/10926429251408802': ('Balthazar_2026.pdf', ['19'], 'chirurgie', 'kern', 'abstract:only'),
 '10.1007/s11695-026-08562-z': ('Hany_2026.pdf', ['19'], 'chirurgie', 'kern', 'abstract:only'),
 '10.1227/neu.0000000000004070': ('Alyakin_2026.pdf', ['19'], 'chirurgie', 'kern', 'abstract:only'),
 '10.1038/s41591-025-04176-7': ('Tao_2026.pdf', ['19'], 'chirurgie', 'kern', 'abstract:only'),
 '10.1038/s41591-026-04371-0': ('Saab_2026.pdf', [], 'amie', 'reserve', 'abstract:only'),
 '10.1136/bmj.h3480': ('Semigran_2015.pdf', [], 'ki_risiken', 'reserve', 'abstract:only'),
 '10.1038/s41746-022-00667-w': ('Wallace_2022.pdf', [], 'ki_risiken', 'reserve', 'abstract:only'),
}

NEW_ITEMS = [
 {'itemType': 'journalArticle', 'title': 'Conversational diagnostic artificial intelligence in ambulatory primary care: a prospective feasibility study',
  'creators': [{'creatorType': 'author', 'lastName': 'Brodeur', 'firstName': 'Peter G'}, {'creatorType': 'author', 'lastName': 'Koshy', 'firstName': 'Jacob M'}, {'creatorType': 'author', 'lastName': 'Palepu', 'firstName': 'Anil'}],
  'publicationTitle': 'The Lancet', 'journalAbbreviation': 'Lancet', 'date': '2026-10-08', 'DOI': '10.1016/S0140-6736(26)01535-7',
  'url': 'https://doi.org/10.1016/S0140-6736(26)01535-7', 'extra': 'Published online 8 Oct 2026. AMIE (Google DeepMind / BIDMC), n=98, single-arm feasibility.',
  'collections': [COLL], 'tags': [], 'relations': {}},
 {'itemType': 'journalArticle', 'title': 'Conversational diagnostic AI in primary care: what happens after it speaks?',
  'creators': [{'creatorType': 'author', 'lastName': 'Omar', 'firstName': 'Mahmud'}, {'creatorType': 'author', 'lastName': 'Nadkarni', 'firstName': 'Girish N'}],
  'publicationTitle': 'The Lancet', 'journalAbbreviation': 'Lancet', 'date': '2026-10-08', 'DOI': '10.1016/S0140-6736(26)01763-0',
  'url': 'https://doi.org/10.1016/S0140-6736(26)01763-0', 'extra': 'Comment on Brodeur et al. 2026.',
  'collections': [COLL], 'tags': [], 'relations': {}},
]


def ident(d):
    doi = (d.get('DOI') or '').lower().strip()
    if doi:
        return doi
    m = re.search(r'PMID:\s*(\d+)', d.get('extra') or '')
    if m:
        return 'pmid:' + m.group(1)
    if d.get('archiveLocation', '').isdigit():
        return 'pmid:' + d['archiveLocation']
    return ''


def main():
    z = Z()
    items = z.get(f'/collections/{COLL}/items/top')
    by_id = {}
    for it in items:
        if it['data']['itemType'] in ('note', 'attachment'):
            continue
        by_id[ident(it['data'])] = it
    # 1) delete non-deck items
    junk = [it for i, it in by_id.items() if i not in META]
    if junk:
        print('deleting', [it['data']['title'][:50] for it in junk])
        z.delete_items([it['key'] for it in junk])
    # 2) create missing items
    missing = [n for n in NEW_ITEMS if n['DOI'].lower() not in by_id]
    if missing:
        res = z.create_items(missing)
        print('created', res.get('successful', {}).keys(), 'failed', res.get('failed'))
        items = z.get(f'/collections/{COLL}/items/top')
        by_id = {ident(it['data']): it for it in items if it['data']['itemType'] not in ('note', 'attachment')}
    # 3) tags + attachments
    for i, (fname, folien, block, rolle, ft) in META.items():
        it = by_id.get(i)
        if not it:
            print('MISSING in Zotero:', i, fname)
            continue
        kids = z.get(f"/items/{it['key']}/children")
        has_pdf = any(k['data']['itemType'] == 'attachment' and (k['data'].get('contentType') == 'application/pdf') for k in kids)
        path = FT / fname
        if not has_pdf and path.exists():
            try:
                z.upload_file(it['key'], str(path))
                has_pdf = True
                print('uploaded', fname)
            except Exception as e:
                print('UPLOAD FAIL', fname, e)
        tags = [PROJECT_TAG, f'{PROJECT_TAG}:block:{block}', f'{PROJECT_TAG}:rolle:{rolle}', f'{PROJECT_TAG}:{ft}',
                f'{PROJECT_TAG}:' + ('pdf:attached' if has_pdf else 'pdf:missing')]
        tags += [f'{PROJECT_TAG}:folie:{f}' for f in folien]
        cur = {t['tag'] for t in it['data'].get('tags', [])}
        want = set(tags)
        if cur != want:
            extra = it['data'].get('extra') or ''
            if i.startswith('pmid:') and 'PMID' not in extra:
                extra = (extra + '\n' if extra else '') + 'PMID: ' + i[5:]
            z.patch_item(it['key'], {'tags': [{'tag': t} for t in sorted(want)], 'extra': extra})
            print('tagged', fname, '| pdf' if has_pdf else '| NO PDF')
    print('done')


if __name__ == '__main__':
    main()
