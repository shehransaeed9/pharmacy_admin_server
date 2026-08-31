# Deploying the License Server — Free Option (Render.com)

You said you have no budget, so here's a genuinely free path. Read the
"Important limitation" section before you rely on this for real
pharmacies — it's a real trade-off, not a technicality.

## Steps

1. Create a free account at https://render.com (you can sign in with GitHub).
2. Put this ADMIN_SERVER_keep_for_yourself folder in its own GitHub repository
   (create a new repo, upload these files — Render deploys from GitHub).
3. In Render: **New +** → **Web Service** → connect that repo.
4. Settings:
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app`
   - **Instance Type:** Free
5. Click **Create Web Service**. Render gives you a URL like
   `https://your-app-name.onrender.com` — that's your license server's address.
6. Open `https://your-app-name.onrender.com/admin`, log in with the
   `ADMIN_USERNAME` / `ADMIN_PASSWORD` you set in `app.py`, and go to
   **Settings** to enter your real bank/JazzCash/Easypaisa details and
   subscription fee.
7. **Before you upload to GitHub**, change these in `app.py`:
   - `app.secret_key` — set it to something random
   - `ADMIN_USERNAME` / `ADMIN_PASSWORD` — do not ship the defaults
8. Open `CUSTOMER_APP_give_to_pharmacies/license_client.py` in the pharmacy app and set:
   ```python
   LICENSE_SERVER_URL = 'https://your-app-name.onrender.com'
   ```
   Then re-package the pharmacy app for pharmacies.

## Important limitation — please read

Render's **free** web service tier does not give you a persistent
disk. Your `license_server.db` (SQLite) file lives on that disk. This
means:
- It's fine while the service is just running normally.
- If you **redeploy** (push new code) or Render **rebuilds** your
  service, that file — and every pharmacy's registration, expiry
  date, and payment history — is wiped and starts empty.

For a handful of pharmacies while you're getting started, this is a
real free option and workable if you avoid redeploying often. But
before you have real paying customers depending on this, you should
move to a small **persistent** database — Render's free PostgreSQL
tier or Supabase's free tier both work and neither costs anything to
start. That's a database-connection-string change, not a rebuild —
happy to help with that swap whenever you're ready for it.

## Testing it locally first (recommended)

Before deploying anywhere, run it on your own PC exactly like the
pharmacy app:
```
pip install -r requirements.txt
python app.py
```
Then open `http://127.0.0.1:5001/admin`. Point a local copy of the
pharmacy app at `http://127.0.0.1:5001` (edit `LICENSE_SERVER_URL` in
`license_client.py`) to test the whole flow before anything goes
online.
