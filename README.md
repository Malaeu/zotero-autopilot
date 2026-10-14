# zotero-autopilot

Write to Zotero from scripts, upload PDFs through the local API, and make "Find Full Text" find things again. Verified on Zotero 10.0.3 (Linux flatpak) on 14 Oct 2026; works on macOS with different profile paths.

Read the story: [English](docs/BLOG_en.md) · [Русский](docs/BLOG_ru.md). Both end with a step-by-step prompt for a Claude Code agent that sets everything up on another machine and verifies each step.

## What is in here

| Path | What it does |
|---|---|
| `scripts/zotero_local.py` | Dependency-free Python client for the Zotero local **write** API: `create_items`, `patch_item`, `delete_items`, `upload_file` (three-step file upload). CLI: `collections`, `items <collectionKey>`, `upload <itemKey> <file>`. |
| `scripts/cdp_pdf.js` | Node ≥ 22 script that launches its own Chrome and saves a PDF by intercepting the response at the DevTools `Fetch` stage. Gets through institutional IP access and past Chrome's PDF viewer. `--headful` for sites that reject headless. |
| `examples/zotero_sync_example.py` | Project sync: delete stray items, create missing ones from Crossref by DOI, tag by scheme, attach PDFs from a folder, idempotent on rerun. Edit the `META` table for your project. |
| `examples/findPDFs_resolvers.json` | Working value for the hidden pref `extensions.zotero.findPDFs.resolvers` (Sci-Hub with the current `iframe` markup, Unpaywall over all OA locations). |

## Quick start

```bash
# 1. server id
curl -s -D - -o /dev/null "http://127.0.0.1:23119/api/users/0/collections?limit=1" | grep -i Zotero-Server-ID

# 2. key (click "Always Allow" in Zotero)
curl -s -X POST -H "Content-Type: application/json" -H "Zotero-Server-ID: <id>" \
  -d '{"appName":"my script"}' http://127.0.0.1:23119/api/local/authorize

# 3. export and use
export ZOTERO_LOCAL_API_KEY=<key> ZOTERO_SERVER_ID=<id>
python3 scripts/zotero_local.py collections
python3 scripts/zotero_local.py upload <itemKey> paper.pdf
```

## Why "Find Full Text" fails on paywalled papers

Every large publisher answers non-browser clients with 403 and a bot check, even from a licensed network. Zotero is a non-browser client to them. Custom resolvers can still work, but two things break silently: markup changes (the Sci-Hub mirror moved from `#pdf` to `<iframe>`), and Cloudflare rejecting any user agent containing `Zotero/`. The fix is two lines in `prefs.js` while Zotero is closed:

```js
user_pref("extensions.zotero.findPDFs.resolvers", "<contents of examples/findPDFs_resolvers.json as one JSON string>");
user_pref("general.useragent.override", "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0");
```

Back up `prefs.js` first. Sci-Hub is a legal grey area in most jurisdictions; the setting and the responsibility are yours. For licensed access use `scripts/cdp_pdf.js` or your own logged-in browser.

## How the write API was found

The installed package ships the server source. Unpack `omni.ja` and read the header of `chrome/content/zotero/xpcom/server/server_localAPI.js`; the protocol (authorize endpoint, `Zotero-Server-ID`, version headers, upload flow) is described there in full.

## Licence

MIT. No warranty. Do not point this at a library you have not backed up.
