#!/usr/bin/env python3
"""zotero_local.py — thin client for the Zotero 10 local write API (http://127.0.0.1:23119).

Needs in the environment (source ~/.api_keys):
  ZOTERO_LOCAL_API_KEY  — key from POST /api/local/authorize ("Always Allow")
  ZOTERO_SERVER_ID      — value of the Zotero-Server-ID response header

Pure stdlib, POSIX; works on Linux and macOS.

Library usage:
  from zotero_local import Z
  z = Z()
  z.get('/collections')                       # list
  z.create_items([{...}, {...}])              # <=50 per call, returns {successful:{}, failed:{}}
  z.patch_item(key, {'tags':[{'tag':'x'}]})   # merges fields, handles version
  z.delete_items([k1, k2])
  z.upload_file(parent_key, '/abs/file.pdf')  # creates child attachment + uploads bytes

CLI:
  zotero_local.py collections
  zotero_local.py items <collectionKey>
  zotero_local.py upload <parentItemKey> <file>
"""
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get('ZOTERO_LOCAL_URL', 'http://127.0.0.1:23119')
USER = '/api/users/0'


class Z:
    def __init__(self):
        self.key = os.environ.get('ZOTERO_LOCAL_API_KEY')
        self.sid = os.environ.get('ZOTERO_SERVER_ID')
        if not self.key or not self.sid:
            sys.exit('ZOTERO_LOCAL_API_KEY / ZOTERO_SERVER_ID missing (source ~/.api_keys)')

    # ---- low level -------------------------------------------------------
    def _req(self, method, path, data=None, headers=None, raw=False):
        url = BASE + (path if path.startswith('/api') else USER + path)
        h = {'Zotero-Server-ID': self.sid, 'Zotero-API-Key': self.key}
        if headers:
            h.update(headers)
        body = None
        if data is not None:
            if raw:
                body = data
            elif isinstance(data, (dict, list)):
                body = json.dumps(data).encode()
                h.setdefault('Content-Type', 'application/json')
            else:
                body = data.encode() if isinstance(data, str) else data
        req = urllib.request.Request(url, data=body, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                txt = r.read().decode('utf-8', 'replace')
                return r.status, dict(r.headers), txt
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read().decode('utf-8', 'replace')

    def library_version(self):
        st, h, _ = self._req('GET', '/items?limit=1')
        return int(h.get('Last-Modified-Version', '0'))

    def get(self, path):
        st, h, txt = self._req('GET', path)
        if st != 200:
            raise RuntimeError(f'GET {path} -> {st} {txt[:200]}')
        return json.loads(txt)

    # ---- writes -----------------------------------------------------------
    def create_items(self, items):
        st, h, txt = self._req('POST', '/items', items,
                               {'If-Unmodified-Since-Version': str(self.library_version())})
        if st != 200:
            raise RuntimeError(f'POST items -> {st} {txt[:300]}')
        return json.loads(txt)

    def patch_item(self, key, fields):
        it = self.get(f'/items/{key}')
        st, h, txt = self._req('PATCH', f'/items/{key}', fields,
                               {'If-Unmodified-Since-Version': str(it['version'])})
        if st not in (200, 204):
            raise RuntimeError(f'PATCH {key} -> {st} {txt[:300]}')
        return st

    def delete_items(self, keys):
        st, h, txt = self._req('DELETE', '/items?itemKey=' + ','.join(keys), None,
                               {'If-Unmodified-Since-Version': str(self.library_version())})
        if st != 204:
            raise RuntimeError(f'DELETE -> {st} {txt[:300]}')
        return st

    def upload_file(self, parent_key, path, content_type='application/pdf', title=None):
        """Create an imported_file child attachment under parent_key and upload the bytes."""
        p = path
        data = open(p, 'rb').read()
        md5 = hashlib.md5(data).hexdigest()
        fname = os.path.basename(p)
        att = {'itemType': 'attachment', 'linkMode': 'imported_file', 'parentItem': parent_key,
               'title': title or fname, 'contentType': content_type, 'filename': fname,
               'tags': [], 'relations': {}}
        res = self.create_items([att])
        if not res.get('successful'):
            raise RuntimeError('attachment create failed: ' + json.dumps(res)[:300])
        akey = list(res['successful'].values())[0]['key']
        form = urllib.parse.urlencode({'md5': md5, 'filename': fname, 'filesize': len(data),
                                       'mtime': int(os.path.getmtime(p) * 1000),
                                       'contentType': content_type})
        st, h, txt = self._req('POST', f'/items/{akey}/file', form,
                               {'Content-Type': 'application/x-www-form-urlencoded', 'If-None-Match': '*'})
        if st != 200:
            raise RuntimeError(f'authorize upload -> {st} {txt[:300]}')
        auth = json.loads(txt)
        if auth.get('exists'):
            return akey
        st, h, txt = self._req('POST', auth['url'].replace(BASE, ''), data, {'Content-Type': content_type}, raw=True)
        if st != 201:
            raise RuntimeError(f'upload bytes -> {st} {txt[:300]}')
        st, h, txt = self._req('POST', f'/items/{akey}/file', urllib.parse.urlencode({'upload': auth['uploadKey']}),
                               {'Content-Type': 'application/x-www-form-urlencoded', 'If-None-Match': '*'})
        if st != 204:
            raise RuntimeError(f'register upload -> {st} {txt[:300]}')
        return akey


def main(argv):
    z = Z()
    if not argv or argv[0] == 'collections':
        for c in z.get('/collections'):
            print(c['key'], c['data']['name'])
    elif argv[0] == 'items':
        for i in z.get(f'/collections/{argv[1]}/items/top'):
            print(i['key'], i['data'].get('title', '')[:70])
    elif argv[0] == 'upload':
        print(z.upload_file(argv[1], argv[2]))
    else:
        print(__doc__)


if __name__ == '__main__':
    main(sys.argv[1:])
