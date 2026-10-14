# Zotero on autopilot: making the local API write, and making "Find Full Text" actually find things

*14 October 2026. Linux, Zotero 10.0.3 (flatpak), university network. Everything below was verified on a live library; the steps carry over to macOS with different profile paths.*

The task was ordinary: I was preparing a talk built on 38 papers. I wanted every paper, its PDF and a set of tags to sit in one Zotero collection, and I wanted an agent to do it, not me. It turned out Zotero has everything needed for that, but half of it is undocumented and the other half fails silently.

Four problems, four fixes.

---

## 1. The local API can write, it just does not say so

Zotero listens on `http://127.0.0.1:23119`. The documentation covers reading: `GET /api/users/0/collections`, `GET /api/users/0/items`. Any `POST` answers `428 Precondition Required`, and most people stop there.

I unpacked the source straight out of the installed package and read the header of `server_localAPI.js`:

```bash
unzip -o /var/lib/flatpak/app/org.zotero.Zotero/current/active/files/share/zotero/app/omni.ja \
  'chrome/content/zotero/xpcom/server/*' -d /tmp/zot
sed -n 30,95p /tmp/zot/chrome/content/zotero/xpcom/server/server_localAPI.js
```

It says in plain words: writes are supported with web API v3 semantics, two headers are required.

**Step 1. Get the Zotero-Server-ID.** It comes with every response:

```bash
curl -s -D - -o /dev/null "http://127.0.0.1:23119/api/users/0/collections?limit=1" | grep -i Zotero-Server-ID
```

**Step 2. Get a key.** Once, confirmed in a Zotero dialog:

```bash
curl -s -X POST -H "Content-Type: application/json" \
  -H "Zotero-Server-ID: <ID from step 1>" \
  -d '{"appName":"My script"}' \
  http://127.0.0.1:23119/api/local/authorize
```

Zotero shows a dialog with three buttons. Click **"Always Allow"**. "Allow" gives a single-use key that burns after the first write. Response: `{"key":"…32 chars…","remember":true}`. Put the key and the server id into environment variables, for example in `~/.api_keys`:

```bash
export ZOTERO_LOCAL_API_KEY=…
export ZOTERO_SERVER_ID=…
```

**Step 3. Write.** Every write carries `Zotero-API-Key`, `Zotero-Server-ID` and the library version:

```bash
V=$(curl -s -D - -o /dev/null "http://127.0.0.1:23119/api/users/0/items?limit=1" | grep -i Last-Modified-Version | awk '{print $2}' | tr -d '\r')
curl -s -X POST "http://127.0.0.1:23119/api/users/0/items" \
  -H "Zotero-API-Key: $ZOTERO_LOCAL_API_KEY" -H "Zotero-Server-ID: $ZOTERO_SERVER_ID" \
  -H "If-Unmodified-Since-Version: $V" -H "Content-Type: application/json" \
  -d '[{"itemType":"journalArticle","title":"Test","DOI":"10.1000/xyz","collections":["<collection KEY>"],"tags":[{"tag":"project"}]}]'
```

Create, `PATCH` of fields and tags, `DELETE ?itemKey=A,B` and file upload all work.

**Step 4. Upload a PDF.** Three requests, exactly like the web API:

1. Create a child attachment item: `{"itemType":"attachment","linkMode":"imported_file","parentItem":"<KEY>","filename":"x.pdf","contentType":"application/pdf"}`.
2. `POST /api/users/0/items/<ATT>/file` with the form fields `md5, filename, filesize, mtime, contentType` and the header `If-None-Match: *`. The response carries `url` and `uploadKey`.
3. Send the raw PDF bytes to that `url`, then `POST …/file` again with `upload=<uploadKey>` and `If-None-Match: *`. Response `204`; the file sits in Zotero storage.

A dependency-free Python client lives in `scripts/zotero_local.py`: `create_items`, `patch_item`, `delete_items`, `upload_file`.

**Side bonus.** A collection can be created without the API through Better BibTeX: `POST /better-bibtex/json-rpc` with method `collection.scanAUX("/My Library/Name", "/path/to/empty.aux")`. The `.aux` file is empty; the collection appears anyway.

---

## 2. Why "Find Full Text" finds nothing

"Find Full Text" does three things: it opens the DOI landing page and looks for a PDF link, it asks Unpaywall, and it asks the custom resolvers in the hidden pref `extensions.zotero.findPDFs.resolvers`.

I probed the publishers from inside a licensed university network. JAMA, Sage, Wiley, RSNA, OUP, BMJ, Ovid: every one answers non-browser clients with `403` and a bot-check page. Zotero is not a browser to them. So paywalled papers never arrive through "Find Full Text", regardless of the licence. This is not a setting, it is publisher defence.

---

## 3. Resolvers: a stale selector and a banned user agent

My `findPDFs.resolvers` had carried a Sci-Hub entry for years, selector `#pdf`, attribute `src`. Zotero just said "No file found". Two defects:

**Defect 1, markup.** sci-hub.ee now serves the PDF inside `<iframe src="…">`; there is no `#pdf` element anymore. The selector has to become `iframe`.

**Defect 2, user agent.** Zotero identifies as `… Firefox/140.0 Zotero/10.0.3`. Cloudflare in front of the mirror rejects any agent containing `Zotero/`. Three lines prove it:

```bash
D=10.7326/0003-4819-101-5-692
curl -s -o /dev/null -w "%{http_code}\n" -A "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0 Zotero/10.0.3" "https://sci-hub.ee/$D"   # 403
curl -s -o /dev/null -w "%{http_code}\n" -A "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0" "https://sci-hub.ee/$D"                 # 200
```

The resolver request does not set its own agent, so only the global Gecko setting helps. Both edits go into the profile's `prefs.js` while Zotero is closed (Linux: `~/.zotero/zotero/<profile>/prefs.js`; macOS: `~/Library/Application Support/Zotero/Profiles/<profile>/prefs.js`):

```js
user_pref("extensions.zotero.findPDFs.resolvers", "[{\"name\":\"Sci-Hub (iframe)\",\"method\":\"GET\",\"url\":\"https://sci-hub.ee/{doi}\",\"mode\":\"html\",\"selector\":\"iframe\",\"attribute\":\"src\",\"automatic\":true},{\"name\":\"Unpaywall all locations\",\"method\":\"GET\",\"url\":\"https://api.unpaywall.org/v2/{doi}?email=nodp53@gmail.com\",\"mode\":\"json\",\"selector\":\".oa_locations\",\"mappings\":{\"url\":\"url_for_pdf\",\"pageURL\":\"url_for_landing_page\"},\"automatic\":true}]");
user_pref("general.useragent.override", "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0");
```

Back up `prefs.js` first. After restarting Zotero: right-click an item without a PDF → "Find Full Text". Old paywalled papers arrive in seconds. Papers published after 2022 are not on Sci-Hub; that is a limit of the source, not of the setting.

What did not work and why: `annas-archive.org` has no DNS record on the university network, the `.li` mirror renders its page with JavaScript, which Zotero does not execute. `libgen.im` has no DOI search; its form leads to a word-based book search. Neither is usable as a resolver.

Legal note: Sci-Hub infringes publishers' copyright in most jurisdictions. The setting and the responsibility are yours. For licensed access there is section 4.

---

## 4. Licensed PDFs without hands: your own Chrome over the DevTools protocol

If you need a publisher PDF under a subscription, the only client they let through is a real browser. `scripts/cdp_pdf.js` is a small Node script: it launches Chrome with its own profile, opens the URL and intercepts the response with `Content-Type: application/pdf` at the response stage via `Fetch.enable`, before Chrome's built-in viewer swallows it.

```bash
node scripts/cdp_pdf.js "https://www.thelancet.com/action/showPdf?pii=S0140-6736(26)01763-0" Omar_2026.pdf
node scripts/cdp_pdf.js "https://pmc.ncbi.nlm.nih.gov/articles/PMC1003190/pdf/x.pdf" Peterson_1992.pdf --headful
```

The one subtlety: `Network.getResponseBody` returns a 536-byte stub for PDFs because the viewer already took the body. Intercepting through `Fetch.requestPaused` at `requestStage: "Response"` and calling `Fetch.getResponseBody` gives the real bytes. Cloudflare Turnstile sites (bmj.com, sagepub.com) still block this route; there the user's own logged-in browser remains.

JAMA has its own trick: open the `…/articlepdf/…pdf` link, wait about six seconds for the redirect to `watermark*.silverchair.com`, and run `fetch(location.href)` on that page.

---

## Result

One run of the sync script (`examples/zotero_sync_example.py`) deletes stray items, creates missing ones from Crossref by DOI, sets tags following the scheme `PROJECT`, `PROJECT:slide:03`, `PROJECT:block:…`, `PROJECT:role:core|context|reserve`, `PROJECT:pdf:attached|missing`, `PROJECT:fulltext:read|abstract:only`, and attaches every PDF from a folder. A second run changes nothing. 34 of 38 papers got their PDF automatically; the remaining four sit behind Turnstile or do not exist online.

Time to figure it out: about three hours. Time to repeat it for the next project: minutes.

---

## Prompt for a Claude Code agent

Paste this whole block into a fresh Claude Code session on a machine with Zotero 7 or newer.

```text
Task: set up Zotero on this machine for automated agent use and verify every step. Treat nothing as done without a command-level check. Report in short sentences with the result of each check.

Context: Zotero ≥ 7 is installed and running; the local API listens on http://127.0.0.1:23119. Detect the OS yourself (Linux or macOS). Profile paths: Linux ~/.zotero/zotero/*/prefs.js, macOS ~/Library/Application Support/Zotero/Profiles/*/prefs.js.

Step 1. Check that the local API answers: GET http://127.0.0.1:23119/api/users/0/collections. If not, ask the user to enable in Zotero: Settings → Advanced → "Allow other applications on this computer to communicate with Zotero", then retry.

Step 2. Read the Zotero-Server-ID from the response header of any GET. Request a write key: POST /api/local/authorize with JSON {"appName":"Claude Code"} and the Zotero-Server-ID header. Tell the user a dialog will appear in Zotero and that they must click "Always Allow", otherwise the key is single-use. Wait for the response and check "remember": true. Store the key and the server id in the environment file the user names (default ~/.api_keys) as ZOTERO_LOCAL_API_KEY and ZOTERO_SERVER_ID. Never print the key in chat.

Step 3. Write a dependency-free Python client, file zotero_local.py, with get(path), create_items(list), patch_item(key, fields), delete_items(keys), upload_file(parent_key, path). Rules: every write carries Zotero-API-Key and Zotero-Server-ID; create and delete carry If-Unmodified-Since-Version equal to the Last-Modified-Version header of GET /items?limit=1; PATCH carries the item's own version; at most 50 objects per request. upload_file: create a child attachment with linkMode imported_file, parentItem, filename, contentType; POST /items/<att>/file with form md5, filename, filesize, mtime, contentType and header If-None-Match: *; take url and uploadKey; POST the raw bytes to url; then POST /items/<att>/file with form upload=<uploadKey> and If-None-Match: *; expect 204.

Step 4. Test the client on the live library: create a collection "API test <date>" (via Better BibTeX JSON-RPC collection.scanAUX with an empty .aux if BBT is installed, otherwise POST /api/users/0/collections), create one test journalArticle with DOI 10.7326/0003-4819-101-5-692 and tag test:api, add a second tag via patch_item, upload any small PDF via upload_file, read /items/<key>/children and confirm the attachment exists. Show the user the result. Delete the test item only after the user says so.

Step 5. Diagnose "Find Full Text". Read extensions.zotero.findPDFs.resolvers and general.useragent.override from prefs.js. For each resolver run curl against its URL with DOI 10.7326/0003-4819-101-5-692 twice: with a user agent containing "Zotero/" and with a plain Firefox agent. Compare status codes. Check whether the resolver's selector exists on the page. Print a table: resolver, status with Zotero agent, status with Firefox agent, selector found.

Step 6. If a resolver blocks the "Zotero/" agent or its selector is stale, propose exact prefs.js edits: a new resolver JSON and a general.useragent.override line with a plain Firefox agent. State that Sci-Hub is a legal grey area and the decision is the user's. Apply edits only while Zotero is closed and only after the user's go; back up prefs.js with a date suffix first. After Zotero restarts, ask the user to run "Find Full Text" on the test item and report.

Step 7. Write zotero_sync.py for the user's project: takes a PDF folder and a table DOI → (file name, slide or section list, block, role), sets tags following PROJECT, PROJECT:slide:NN, PROJECT:block:…, PROJECT:role:core|context|reserve, PROJECT:pdf:attached|missing, PROJECT:fulltext:read|abstract:only, attaches a PDF when the item has no attachment yet, and creates no duplicates on rerun. Run it twice and show that the second run changed nothing.

Step 8. Final report: what was verified by which command and output, what remains open, which files were created, with absolute paths. Do not claim "works" for any step that did not pass its check.
```
