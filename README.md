# Job Boat

A local-first UK job review dashboard with separate fast-money and career tracks. It records approvals, but does not submit applications. Your profile and job data stay in `data/jobs.sqlite3` by default.

## Run

Requires Python 3.12. No packages to install.

```sh
python app.py
```

Open `http://127.0.0.1:8765` locally. Set `PORT` to use another port. `JOB_BOAT_DB` selects the database path. Set `JOB_BOAT_AUTO_SCAN=1` to scan public feeds on startup and every six hours. Use the **Scan public feeds** button for an immediate scan.

The initial public feed adapters are Remotive, Arbeitnow, and selected Greenhouse company boards. GOV.UK Find a Job, Civil Service Jobs, LinkedIn, Indeed, Reed, Totaljobs, CV-Library, and Welcome to the Jungle are linked in the UI; their automated collection and account integrations are not yet implemented. The feed hosts must be permitted by the cloud environment network policy. Manual listings can be added by HTTPS URL.

## Current scope

Upload PDF, DOCX, or TXT CVs into the library, then choose one to populate the reusable CV text. Set Bristol as the local search area and note that career roles may include relocation. Review jobs and mark each approved, skipped, or applied. The application pack shows the stored CV and answers for review; it does not tailor them or fill external forms yet. Gmail OAuth, interview detection, browser application automation, and AI matching remain future integrations. Keep the app bound to localhost because it has no authentication.

To import an attached asset folder containing CVs, supporting PDFs, and the Bristol job spreadsheet, run `python import_assets.py /workspace/attachments`. This importer requires `openpyxl` and `pdftotext` on the machine. It is safe to run again: files and linked listings are deduplicated. The database stores private document bytes and extracted text, so back it up securely and never commit `data/`.

## Verified browser runtime

Playwright WebKit runs in the pinned `Dockerfile.browser` image. Build it with the cloud proxy CA supplied as a Docker build secret; TLS verification stays enabled:

```sh
mkdir -p data/docker-config
DOCKER_CONFIG="$PWD/data/docker-config" docker build --build-arg HTTPS_PROXY --build-arg HTTP_PROXY --build-arg NO_PROXY --secret id=proxy_ca,src=/usr/local/share/ca-certificates/environment-proxy-ca.crt -f Dockerfile.browser -t jobboat-playwright:local .
```

Check one job page without mounting the private database into the browser container:

```sh
docker run --rm --env HTTPS_PROXY --env HTTP_PROXY --env NO_PROXY --ipc=host -v "$PWD/browser_check.py:/work/browser_check.py:ro" jobboat-playwright:local python /work/browser_check.py 'https://example.com/job'
```

The check reports the page title, visible Apply controls, and common expiry messages. It is a browser readiness and vacancy evidence step, not an application submission. An HTTP 200 response alone does not prove a vacancy is open. Chromium and Firefox are not used here because they reject the cloud proxy certificate in this environment.
