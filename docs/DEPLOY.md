# Deploying YouTube Galaxy

Covers the **Hostinger** side: the home page and the map. The Cloudflare Worker (chat) comes with Plan 4.

Nothing here costs money. Hostinger Premium is already paid for and only serves static files.

## What gets uploaded where

```
public_html/                    your site root: only index.html and home.css are written here
  galaxy/                       the map: index.html, .htaccess, assets/, data/<version>/, manifest.json
```

- **What the publish never touches:**
  - other folders in `public_html/`;
  - the root `.htaccess`.
- **`manifest.json` goes up last.** It tells the map which `data/<version>/` to read.
  - An upload that fails halfway leaves the old version live.
  - Running `make publish` again picks up where it stopped. Files already on the server at the same size are skipped.
- **Old versions:** the 3 newest data versions stay on the server, so visitors with the page already open keep working, and you can roll back. Older ones are deleted only after the new version is confirmed live.

## One-time setup

1. **Turn on SSH/SFTP in hPanel.**
   - It is off by default on new plans. Look under **Advanced → SSH Access** (some plans call it *Remote Access*).
   - The page lists the **IP address**, **port** (Hostinger uses **65002**) and **username**.
   - Use the password shown there or reset it on that page. You can also add an SSH key.
   - Source: Hostinger, "How to connect to your hosting using SFTP", https://www.hostinger.com/support/5972689-how-to-connect-by-sftp/ (checked 2026-11-22).
2. **Accept the server's host key once.** The publish script refuses servers it hasn't seen before. That protects you from a fake server receiving your password.
   ```bash
   ssh -p 65002 <username>@<ip address>
   ```
   - Answer `yes` to the fingerprint question, then type your password.
3. **While connected, find the web root.** Run `ls` and `ls domains` (if that folder exists).
   - If `public_html` is in your home folder, the defaults below are right.
   - If it's at `domains/spookypharaoh.com/public_html`, use that path in both settings below.
   - Type `exit` to leave.
4. **Fill in `.env`.** It is never committed.
   ```
   HOSTINGER_SFTP_HOST=<ip address>
   HOSTINGER_SFTP_PORT=65002
   HOSTINGER_SFTP_USER=<username>
   HOSTINGER_SFTP_PASSWORD=<password>        # or leave empty and set HOSTINGER_SFTP_KEY_PATH=~/.ssh/<key>
   HOSTINGER_HOME_DIR=public_html            # the folder from step 3
   HOSTINGER_REMOTE_DIR=public_html/galaxy   # always <HOSTINGER_HOME_DIR>/galaxy
   SITE_BASE_PATH=/galaxy/
   SITE_ORIGIN=https://spookypharaoh.com
   ```
5. **Hostinger's placeholder page.** A new site has a default page (`default.php` or `index.php` in `public_html`), which can be shown instead of the new home page.
   - The dry run warns if it finds one.
   - Delete it in hPanel's **File Manager**. The script never deletes files it didn't write.

## Each publish

```bash
make pipeline          # (or make build) newest data in data/artifacts/galaxy/
make web-build         # the map's code into web/dist
make preview           # look at it locally: http://localhost:8080/ (and the phone address it prints)
make publish-dry       # connects read-only and lists every file it would upload, plus any warnings
make publish           # uploads, then checks https://spookypharaoh.com/galaxy/manifest.json
```

`make publish` ends with `live: … reports <version>` when the check passes.

**To check it yourself:**
- open https://spookypharaoh.com/ and https://spookypharaoh.com/galaxy/;
- the map's footer date is the build date;
- headers: `curl -sI https://spookypharaoh.com/galaxy/manifest.json` should show `cache-control: no-cache`.

## Rolling back

```bash
make rollback VERSION=20261122-160428-c390a7b8
```

- **What it does:** re-uploads that version's `manifest.json`, so the map reads the older data again. Nothing is deleted.
- **What it needs:**
  - the version must still be on the server (the newest 3 are kept);
  - its build folder must still exist locally in `data/artifacts/galaxy/`.
- **Code isn't rolled back.** Only the data version changes. To roll the code back too, check out the older commit, then run `make web-build` and `make publish`.

## When something goes wrong

| Symptom | Fix |
|---|---|
| `SFTP connection failed … not found in known_hosts` | Do step 2 above. |
| `missing required setting: HOSTINGER_SFTP_HOST` | Fill in `.env` (step 4). |
| `… was not built for /galaxy/; run make web-build` | Run `make web-build` (it was built with another `SITE_BASE_PATH`). |
| `SITE_BASE_PATH … does not match HOSTINGER_REMOTE_DIR` | The last folder of `HOSTINGER_REMOTE_DIR` must equal `SITE_BASE_PATH` without slashes. |
| `does not report <version> yet` | Wait a minute and reload. If it persists, purge the cache in hPanel (Performance → Cache Manager). Old versions are kept until this check passes. |
| Map says "The map couldn't load" | Check that `galaxy/manifest.json` and `galaxy/data/<version>/` exist in File Manager, then publish again. |

## Free-plan limits

None apply to the static site beyond Hostinger Premium's own storage and bandwidth. One publish is about 22 MB (6 MB compressed in transit), so 3 kept versions use about 65 MB of disk.
