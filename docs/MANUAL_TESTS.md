# Manual tests — Phase 1

Time needed: about 20–30 minutes (the first build takes 5–10 of those).
Record each result as Pass / Fail. For any failure, note what you saw and run `docker compose logs api web > logs.txt`.

## 0. One-time setup

1. Install **Docker Desktop** (Windows/macOS) or Docker Engine + Compose plugin (Linux), and **Git**. Start Docker Desktop and wait until it says it is running.
2. Get the code:
   ```
   git clone https://github.com/Kunledecastro/Wealthwise.git
   cd Wealthwise
   ```
3. Create your settings file:
   - macOS/Linux: `cp .env.example .env`
   - Windows PowerShell: `Copy-Item .env.example .env`
4. Generate a secret key (works on any OS once Docker is running):
   ```
   docker run --rm python:3.13-alpine python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```
5. Open `.env` in a text editor and change these four lines. Use **letters and digits only** for the three database passwords:
   ```
   POSTGRES_SUPERUSER_PASSWORD=<any letters+digits, e.g. Super8812kq>
   WW_MIGRATOR_PASSWORD=<different letters+digits>
   WW_APP_PASSWORD=<different letters+digits>
   SECRET_KEY=<the value from step 4>
   ```
   Leave everything else as it is. Always open the app at exactly **http://localhost:3000**, not `127.0.0.1`: the security check compares the address with `APP_BASE_URL` and blocks mismatches.

## M1 — The stack starts

1. `docker compose up --build -d`
2. Wait until it returns, then run `docker compose ps -a`.
3. Open http://localhost:3000/api/health in a browser.

**Expected:** `db`, `api` and `web` show as running/healthy, and `migrate` shows "Exited (0)". The health page shows `{"status":"ok","database":"ok","app":"Wealthwise"}`.

## M2 — Create the admin and sign in

1. Create the admin. You'll be asked for a password twice and nothing will show as you type:
   ```
   docker compose run --rm -it api python -m app.cli create-admin --email you@yourdomain.com --name "Kunle"
   ```
   Use a real-looking email domain (not `.local` or `.test`). Use a password of 10+ characters that doesn't contain the part of your email before the `@`.
2. Open http://localhost:3000.
3. Sign in with that email and password.

**Expected:** step 1 prints "Admin account created for …". Opening the site sends you to **Sign in**. After signing in you see "Welcome, Kunle" with **Home, Settings, Admin** in the top bar.

## M3 — Invite someone

1. Click **Admin**. Under "Invite someone", enter an email such as `ada@example.com` and the note `Ada`. Click **Create invite**.
2. Click **Copy**.
3. Open a **private/incognito window** and paste the link.

**Expected:** the green box says the link won't be shown again. The private window shows "Create your account", and the address bar shows only `/register` because the token has been removed. Back in the admin window, the invite is listed as **pending**.

## M4 — Register, and the invite can't be reused

1. In the private window, fill in name `Ada`, email `ada@example.com`, and a password, typing it twice. Click **Create account**.
2. Close the private window. Open a new private window and paste the **same** link again.
3. Fill in the form and submit.

**Expected:** step 1 signs you in and shows "Welcome, Ada" (no Admin link). Step 3 shows "This invite link is invalid, expired or already used…". On the admin's Admin page (refresh it), the invite shows **used** and Ada appears under **People**.

**Extra checks:**
- Try registering with the password `password123`. It should be rejected as too common.
- Create an invite bound to `x@example.com` and try to register with a different email. It should be rejected.

## M5 — Preferences save and persist

1. As any user, go to **Settings**.
2. Change the timezone to `Europe/London`, set week start to Sunday, and type `100, 70` into budget alert thresholds. Click **Save preferences**.
3. Reload the page (F5).
4. Type `0, 300` into thresholds and click **Save**.

**Expected:** step 2 shows "Preferences saved". After the reload the values are kept, and the thresholds read `70, 100`. Step 4 shows an error and nothing is saved.

## M6 — Password reset

1. Click **Sign out**. On the Sign in page click **Forgot your password?**, enter Ada's email, and submit.
2. Enter an email that doesn't exist and submit.
3. In a terminal, run `docker compose logs api` and find the "DEV EMAIL" block. Copy the link starting with `http://localhost:3000/reset-password#token=`.
4. Open the link, set a new password, and submit.
5. Open the same link again and try a different password.
6. Sign in with the **old** password, then with the **new** one.

**Expected:**
- Steps 1 and 2 show the same message, so nobody can tell which emails have accounts.
- Step 4 says "Password updated…".
- Step 5 says the link is invalid or expired.
- The old password fails and the new one works.

(In development, emails are printed to the log instead of being sent. Real email needs SMTP settings, which come later.)

## M7 — Lockout after repeated wrong passwords

1. Sign out. Enter Ada's email with a wrong password 6 times.
2. Then try Ada's correct password.

**Expected:** attempts 1–5 say "Incorrect email or password". Attempt 6 and the correct password both say "Too many attempts…". The lockout lasts 15 minutes; your admin account is unaffected.

## M8 — Sign out on all devices

1. Sign in as Ada in two different browsers, for example Chrome and Edge, or one normal and one private window.
2. In browser A, go to **Settings** → **Sign out on all devices** → **Yes, sign out everywhere**.
3. In browser B, refresh the page.

**Expected:** browser A returns to Sign in, and browser B is also sent to Sign in.

Also check that changing the password (Settings → Password) keeps you signed in on the current browser but signs out the other.

## M9 — Mobile layout

**Option A (easiest):** in Chrome, press F12, then Ctrl+Shift+M (Cmd+Shift+M on Mac), and choose "iPhone SE" (375px wide). Visit Sign in, Settings and Admin.

**Option B (real phone on the same Wi-Fi):** in `.env`, set `WEB_BIND=0.0.0.0` and `APP_BASE_URL=http://<your-computer-LAN-IP>:3000`. Run `docker compose up -d`, then open that address on your phone. Change both settings back afterwards.

**Expected:** no sideways scrolling, text is readable without zooming, buttons are easy to tap, and the top bar fits.

## M10 — Keyboard only

1. On Sign in, click the address bar, then use only **Tab**, **Shift+Tab**, **Enter** and **Space**.
2. Sign in, move to Settings, change a toggle with Space, and save with Enter.

**Expected:** every link, field, toggle and button is reachable in a sensible order, and a visible green focus outline shows where you are.

## Reporting back

Reply with a line per test, for example `M1 pass, M2 pass, M5 fail: thresholds didn't save`. Attach screenshots or `logs.txt` for any failure.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `set POSTGRES_SUPERUSER_PASSWORD in .env` | You skipped step 0.5, or `.env` is not in the project folder |
| `migrate` exits with an error about a password or role | You changed DB passwords after the first start. Reset with `docker compose down -v` (**deletes all data**), then `docker compose up --build -d` |
| "Security token missing or invalid" or "Cross-site request blocked" | Use exactly `http://localhost:3000` (or the address set in `APP_BASE_URL`), then refresh the page |
| Port 3000 already in use | Set `WEB_PORT=3001` and `APP_BASE_URL=http://localhost:3001` in `.env` |
| Locked out of the admin account | `docker compose run --rm api python -m app.cli reset-link --email you@yourdomain.com`, then open the printed link |

## Cleaning up

- Stop and keep data: `docker compose down`
- Stop and erase everything: `docker compose down -v`
