# Cloud Setup Guide

Step-by-step instructions for migrating the DSE dashboard from a locally-
triggered pipeline to a fully automated, cloud-based system.

---

## 1. Convert & upload the workbook to Google Sheets

1. Open **Google Drive** → click **+ New** → **File upload** → select
   `DSE MARKET UPDATE.xlsx`.
2. Once uploaded, double-click the file → Google will offer to open it in
   Sheets → click **Open with Google Sheets**.
3. Go to **File → Save as Google Sheets** — this creates a native Google
   Sheets copy. Delete the uploaded `.xlsx` from Drive if you like; only
   the Sheets version is needed.
4. **Copy the spreadsheet ID** from the URL:
   ```
   https://docs.google.com/spreadsheets/d/<THIS_IS_THE_ID>/edit
   ```
5. Leave sharing as **Private** (default) — the service account will get
   access in step 3 below.

> **Important:** Verify that all five sheets exist with their original names:
> `DSE`, `Historical Data`, `ALL DATA`, `Sector Report`, `EPS PE & NAV`.
> Google Sheets sometimes truncates or renames sheets during import.

---

## 2. Create a Google Cloud service account

1. Go to [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project (or select an existing one).
3. Enable the **Google Sheets API**:
   - Navigation menu → **APIs & Services** → **Library**
   - Search "Google Sheets API" → **Enable**.
4. Enable the **Google Drive API** (same flow).
5. Create a service account:
   - **APIs & Services** → **Credentials** → **+ Create Credentials** →
     **Service Account**.
   - Name: `dse-dashboard` (or anything).
   - Skip optional permissions, click **Done**.
6. Create a key:
   - Click the service account you just made → **Keys** tab →
     **Add Key** → **Create new key** → **JSON** → **Create**.
   - A `.json` file downloads — this is your **service account key**.
     Keep it safe; do not commit it to any repository.
7. **Copy the service account email** (looks like
   `dse-dashboard@project-id.iam.gserviceaccount.com`).

---

## 3. Share the Google Sheet with the service account

1. Open your Google Sheet from step 1.
2. Click **Share** → paste the service account email from step 2.
3. Set permission to **Viewer** (read-only is enough).
4. Uncheck "Notify people" → **Share**.

---

## 4. Store secrets in GitHub

1. Go to your GitHub repo → **Settings** → **Secrets and variables** →
   **Actions**.
2. Click **New repository secret** and add:

   | Secret name | Value |
   |---|---|
   | `DSE_DASHBOARD_KEY` | Paste the **entire contents** of the `.json` key file |
   | `GSHEET_ID` | The spreadsheet ID from step 1 |

---

## 5. Test the workflow

1. Go to **Actions** tab in your GitHub repo.
2. Click **Refresh Dashboard** in the left sidebar.
3. Click **Run workflow** → **Run workflow** (uses `workflow_dispatch`).
4. Watch the job. On success, it commits an updated
   `dashboard_snapshot.html` and pushes. Streamlit Cloud redeploys
   automatically.

If the job fails, check the logs — common issues:

| Error | Fix |
|---|---|
| `gspread.exceptions.SpreadsheetNotFound` | Share the sheet with the service account email (step 3) |
| `KeyError: 'DSE'` | Sheet names don't match — check the Google Sheet has `DSE`, `Historical Data`, etc. |
| `google.auth.exceptions.DefaultCredentialsError` | `GCP_SA_KEY` secret is missing or malformed JSON |
| `Permission denied` pushing | Ensure the workflow has `permissions: contents: write` |

---

## 6. Schedule

The workflow runs automatically on the cron schedule in
`.github/workflows/refresh.yml`:

```yaml
cron: "30 10 * * 0-4"  # 4:30 PM BDT, Sun-Thu
```

Adjust the time if your data is updated later than 4:30 PM. GitHub Actions
cron can be delayed 5-30 minutes during peak hours — this is normal.

---

## 7. (Optional) Streamlit Cloud secrets

If you later want Streamlit Cloud to read the Google Sheet **live** instead
of from a committed snapshot, add the same secrets to Streamlit Cloud:

1. Go to your app on [share.streamlit.io](https://share.streamlit.io) →
   **Settings** → **Secrets**.
2. Paste:
   ```toml
   [gcp_service_account]
   type = "service_account"
   project_id = "..."
   # ... (paste all fields from the JSON key)

   [google_sheets]
   spreadsheet_id = "YOUR_SPREADSHEET_ID"
   ```

This is **not needed** for the snapshot approach (which is what's configured
now). It's only relevant if you switch `streamlit_app.py` to read the sheet
directly.

---

## Keeping the Google Sheet updated

The GitHub Actions cron job reads whatever is in the Google Sheet at trigger
time. You still need to update the sheet with daily market data — either
manually or with a separate automation. The pipeline only reads; it never
writes to the sheet.

---

## Removing the local pipeline (optional)

Once the cloud pipeline is confirmed working, you can stop running:

- `Refresh Snapshot and Push.bat`
- `watch_and_publish.py` / `Enable Auto-Publish.ps1`
- `Disable Auto-Publish.bat`

These are already `.gitignore`d and were never in the public repo.
