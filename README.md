# License Server — for your eyes only

This is YOUR server, not something a pharmacy ever sees directly.
It does three things:

1. **Registers** each pharmacy's app the first time they open it
   (free trial starts automatically).
2. **Confirms subscription status** every time a pharmacy's app opens
   or runs — using this server's own clock, so a pharmacy can't get
   free access by changing their PC's date.
3. Gives **you** (via `/admin`) a dashboard of every pharmacy using
   your software, lets you extend/mark-paid a subscription, disable a
   pharmacy entirely, and change your price, payment details, or push
   an announcement — which every pharmacy sees on their next check-in.

## What "automatic" actually means here

You said you want the system to "automatically detect and give
subscription." Being straight with you: **verifying that a bank
transfer or JazzCash/Easypaisa payment actually arrived requires a
real merchant account with them** — that's a business step (their
registration, likely fees, KYC), not something this code can fake.
Faking it would mean the app claims to verify payment when it
doesn't, which risks pharmacies getting free access, or you being
seen as promising something the software doesn't do.

So what's actually automatic here: a pharmacy clicks "I've Paid,"
you see it appear on your dashboard, you check your account for the
money, and one click ("Confirm") on your side extends them —
their app unlocks itself within 30 seconds with no restart needed.
That's the realistic version of "automatic" without a payment
gateway. When you do get a JazzCash/Easypaisa business account or a
Pakistan-available Stripe alternative, true one-click auto-verification
can be added as an upgrade to `/api/payment_claim` — it slots into
this same structure.

## Local admin login (change before deploying!)
Set in `app.py`:
```python
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'change-this-password'
```

## Files
- `app.py` — the whole server (models, API, admin panel)
- `templates/` — admin panel pages only (pharmacies never see these)
- `DEPLOY.md` — how to put this online for free
- `requirements.txt` — what to `pip install`

## Run locally
```
pip install -r requirements.txt
python app.py
```
Then visit `http://127.0.0.1:5001/admin`.
