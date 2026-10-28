# Manual tests

- [Phase 4](#phase-4) (current)
- [Phase 3](#phase-3)
- [Phase 2](#phase-2)
- [Phase 1](#phase-1) (passed 26 Oct 2026)

---

## Phase 1

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


---

## Phase 2

Time needed: about 25 minutes. Use your normal browser, signed in as yourself, at http://localhost:3000.

### 0. Update and restart

In PowerShell, in the Wealthwise folder:
```
git pull
docker compose up --build -d
docker compose ps -a
```
**Expected:** as before, `migrate` shows Exited (0), and `db`/`api` are healthy. Refresh the browser. The top bar now shows **Home · Transactions · Accounts · Settings · Admin**.

### N1 — Add accounts
1. Go to **Accounts** → **Add account**.
2. Type: Bank account. Name: `GTBank`. Last 4 digits: `4821`. Starting balance: `350,000`. As of: a date about 3 weeks ago. Click **Add account**.
3. Add a second account. Type: Wallet. Name: `Kuda`. Starting balance: `0`. Same date.
4. Try to add a third account with last 4 digits `12AB`, then with a date in the future.

**Expected:** both accounts show **₦350,000.00** and **₦0.00** with a "Manual · estimated" badge. Step 4 shows errors and nothing is saved.

### N2 — Income, expense and the monthly summary
1. Go to **Home** → **Add transaction**. Type: **Income**. Amount `450,000`. Account GTBank. Date: this month. Payer `Salary`. Save.
2. Add an **Expense**: `25,000.50` at `Shoprite` from GTBank, this month.
3. Add a **Bank fee**: `52.50`, description `SMS alert`, GTBank.

**Expected:** Home shows:
- Income **₦450,000.00**
- Spending **₦25,053.00** ("Includes bank fees")
- Net cash flow **₦424,947.00**
- GTBank **₦774,947.00**

### N3 — Refund reduces spending (not income)
1. **Transactions** → **Add** → **Refund**: `5,000`, merchant `Shoprite`, GTBank, this month.

**Expected:** on Home, income stays **₦450,000.00**. Spending drops to **₦20,053.00** with "After refunds of ₦5,000.00". GTBank shows **₦779,947.00**.

### N4 — Transfer between your accounts
1. **Add** → **Transfer**: `100,000`, from GTBank to Kuda.

**Expected:**
- GTBank is **₦679,947.00** and Kuda **₦100,000.00**. The total stays **₦779,947.00**.
- Income and spending on Home **don't change**.
- In Transactions the transfer appears twice: "Transfer to Kuda" and "Transfer from GTBank".

### N5 — Pending, then completed or failed
1. **Add** an **Expense**: `1,500` at `Bolt` from Kuda, status **Pending**.
2. Check Home, then open the Bolt transaction in Transactions → **Mark completed**.
3. Add another pending expense of `800`, open it → **Mark failed**.

**Expected:**
- After step 1, Spending is unchanged and Pending shows **−₦1,500.00**. On Accounts, Kuda shows "Including pending: ₦98,500.00".
- After step 2, spending rises by ₦1,500 and Kuda is ₦98,500.00.
- After step 3, the ₦800 is shown crossed out as "Failed" and counts nowhere.

### N6 — Edit with history
1. Open the **Shoprite** expense → **Edit**. Change the amount to `24,000` and the reason to `typo`. Save.
2. Look at **History** at the bottom of the panel.

**Expected:** the balance and spending update by ₦1,000.50. History shows "Created" and "Edited: Amount: ₦25,000.50 → ₦24,000.00 · Reason: typo".

### N7 — Bank reversal
1. **Add** an expense: `4,400` at `Netflix` from Kuda, Completed.
2. Open it → **Bank reversed it** → reason `double charge` → **Record reversal**.

**Expected:**
- Kuda's balance is back where it was before Netflix.
- Netflix shows crossed out as "Reversed", with a separate "Reversal of Netflix" entry.
- The original can't be edited except its notes.
- Deleting the reversal entry makes Netflix count again. Try it, then reverse again to tidy up.

### N8 — Delete
1. Open the transfer from N4 → **Delete** → confirm.

**Expected:** both sides disappear, and the balances return to GTBank +₦100,000 / Kuda −₦100,000 compared with N4. Re-add the transfer if you want to keep your test data tidy.

### N9 — Filters, search and CSV
1. In **Transactions**: search `shop`, then filter Type = Refund, then Status = Pending, then a date range. Click **Clear filters**.
2. Click **CSV** and open the file in Excel.

**Expected:** each filter narrows the list correctly. The CSV opens with ₦ amounts (negative for spending) and readable columns.

### N10 — Settings: email, export, delete
1. **Settings → Sign-in email**: enter a new email and your password → **Change email**. Sign out and sign in with the new email.
2. **Settings → Your data → Everything (JSON)**. The file downloads and contains your accounts and transactions.
3. **Delete my account** as Ada (from Phase 1), not as yourself:
   - Sign in as Ada.
   - Settings → Delete my account… → enter Ada's password → type `DELETE` → **Delete everything**.
   - Ada can no longer sign in.
4. As yourself (the only admin), open Delete my account…, fill it in and submit.

**Expected:** step 4 says "You are the only admin…" and nothing is deleted. **Don't** make Ada an admin first unless you really mean to test that path.

### N11 — Mobile and keyboard (quick)
- With F12 + Ctrl+Shift+M (iPhone SE), add an expense from Home. The form appears as a bottom sheet and the amount field shows a number keypad on a real phone.
- Press **Esc** to close a panel. Use Tab to move through the Add-transaction form.

### Reporting back
Reply in one line, for example `N1 pass … N7 fail: …`, with a screenshot for any failure.


---

## Phase 3

Time needed: about 30 minutes. The test files are in your Wealthwise folder under **docs\samples**. They contain made-up data.

### 0. Update and restart
```
cd C:\Users\AdekunleOludele\Wealthwise
git pull
docker compose up --build -d
docker compose ps -a
```
**Expected:** `migrate` shows Exited (0) and the others are healthy. The top bar now includes **Imports**.

### S1 — Import a statement (with a deliberate mistake)
1. **Accounts → Add account**: name `GT test`, type Bank, starting balance `0`, as of **30 Sep 2026**.
2. **Imports → Import statement**: account GT test, file `docs\samples\sample-gtbank-style-statement.csv` → **Upload and review**.
3. Look at the review. **Don't** tick "Set the account's starting balance from this statement". Click **Import 9**.

**Expected in step 3, before importing:**
- **9 New** and nothing else.
- "SMS ALERT CHARGES" and "VAT ON CHARGES" are typed as **Bank fee**.
- "REVERSAL WEB PURCHASE NETFLIX" is typed as **Reversal**, with a note that it reverses another row.
- Both "POS PURCHASE BOLT" rows are present.
- Narrations show `••••••6789` and `••••7895` instead of full account and card numbers.

**Expected after importing:** an amber box saying the statement says **₦423,943.06** but Wealthwise calculates **₦323,943.06** (difference **₦100,000.00**).

### S2 — Fix the starting balance → it matches
1. **Accounts → GT test → Edit**: starting balance `100,000`, keep 30 Sep 2026. Save.

**Expected:** GT test shows **₦423,943.06** with a green **✓ Matches statement · 6 Oct** badge.

### S3 — Re-importing adds nothing
1. Import the **same CSV** into GT test again.
2. Import `sample-wallet-statement.xlsx` (the same transactions as Excel) into GT test.

**Expected:** both show **9 Already imported**, **0 selected**, and the Import button is disabled. The CSV also shows "You already imported this exact file on …". Click **Cancel import** both times.

### S4 — Transfer between your accounts
1. Add account `Kuda test` (Wallet, starting `0`, as of 30 Sep 2026).
2. Import `sample-kuda-transfer-in.csv` into Kuda test.

**Expected:**
- "TRF FROM GTB JOHN DOE" is typed **Transfer between my accounts**, with the note "Matches money from GT test on 3 Oct…".
- After **Import 2**: "matched 1 transfer between your accounts" and **Balance check passed: ₦98,500.00**.
- In **Transactions**, the ₦100,000 appears as "Transfer to Kuda test" and "Transfer from GT test".
- On Home, this month's spending does **not** include that ₦100,000.

### S5 — Undo an import
1. **Imports** → open the Kuda import → **Undo import… → Yes, undo import**.

**Expected:**
- Kuda test goes back to **₦0.00** and **Estimated**.
- GT test's "NIP TRF TO KUDA…" row goes back to type **Expense**.
- GT test still shows ✓ Matches statement.
- Importing the Kuda file again works, and the transfer is matched again.

### S6 — Choose columns yourself (and have them remembered)
1. Add account `Header test` (starting `0`, as of 30 Sep 2026).
2. Import `sample-unusual-headers.csv` into it. The **Columns** section opens with "Couldn't detect the columns".
3. Set:
   - Heading row: **Row 3** (When, What, Out)
   - How amounts are shown: **Separate money in / money out**
   - Date: **When**; Description: **What**; Money out: **Out**; Money in: **In**
4. Click **Apply and re-check rows**, then **Import 2**. Keep "Remember these column settings" ticked.
5. Import the same file into Header test again.

**Expected:** after step 4 there are 2 New rows, and "Refund from seller" is typed **Refund**. In step 5, Columns says "Using the settings you saved for this account" and both rows are **Already imported**. Cancel it.

### S7 — Possible duplicate of something you typed by hand
1. Add account `Dup test` (starting `100,000`, as of 30 Sep 2026).
2. **Transactions → Add** an **Expense** of `25,000.50` at `Shoprite`, Dup test, dated **2 Oct 2026**.
3. Import the GTBank sample CSV into Dup test.

**Expected:** 8 New and **1 Possible duplicate** (unticked, with the note "Looks like 'Shoprite' on 02 Oct…"). After **Import 8**, the balance check passes at **₦423,943.06**, because your manual entry stands in for that row.

### S8 — Check against your bank by hand
1. **Accounts → GT test → Check against bank**: balance `400,000`, at the end of **6 Oct 2026** → **Check balance**.
2. Repeat with `423,943.06` for the same date.

**Expected:** step 1 shows a difference of **₦23,943.06** and the badge changes to "Differs from statement by ₦23,943.06". Step 2 shows "Matches", the badge returns to green, and "Previous checks" lists both.

### S9 — Editing old data breaks the match (and fixing it restores it)
1. **Transactions** → open the GT test **Shoprite** row → Edit → amount `25,500.50` → Save.
2. Edit it back to `25,000.50`.

**Expected:** after step 1, GT test shows "Differs from statement by ₦500.00". After step 2 it shows ✓ Matches statement again.

### S10 — Bad files are explained
Import into any account:
- a PDF, or
- a file renamed to `.xls` that was really saved from a web page (if you have one).

**Expected:** a clear message, e.g. "PDF statements aren't supported yet…" or "This file is a web page saved with a spreadsheet name…". Nothing is staged.

### S11 — Mobile and keyboard
With F12 + Ctrl+Shift+M (iPhone SE), open an import review. The rows are readable, the checkboxes and type menus are tappable, and the Import bar stays at the bottom. Tab through the review with the keyboard.

### Optional — simulated bank events
1. In `.env` set `DEMO_MODE=true`, then run `docker compose up -d`.
2. **Imports → Simulate bank events → Import**.

**Expected:** a "Demo bank (simulated)" account appears with ✓ Matches statement. Undo that import afterwards, then set `DEMO_MODE=false` and run `docker compose up -d` again.

### Reporting back
Reply with one line, for example `S1 pass … S11 pass`. For anything that fails, add a screenshot.

**Most useful of all:** try a **real statement** from your own bank (CSV or Excel) in a test account, then tell me whether the columns were detected and whether the balance check passed. **Don't send me the file.** If you want an exact preset added, send a redacted copy with names and account numbers replaced by X.


---

## Phase 4

Time needed: about 20 minutes.

### 0. Update and restart
```
cd C:\Users\AdekunleOludele\Wealthwise
git pull
docker compose up --build -d
docker compose ps -a
```
**Expected:** `migrate` shows Exited (0); `docker compose logs migrate` ends with "Categorised N transaction(s)." The top bar now has **To review** (with a number if anything needs attention) and **Categories**.

### C1 — Your existing data was categorised
Open **Transactions**.

**Expected:** most rows show a coloured category chip, for example:
- Shoprite → Food & groceries
- Bolt → Transport
- Netflix → Entertainment & subscriptions
- SMS ALERT and VAT → Bank fees
- Salary → Salary
- Transfers → Transfers between my accounts

Open any one: the **Category** box shows the reason, e.g. "Recognised 'SHOPRITE'".

### C2 — The review queue
Open **To review**.

**Expected:** person-to-person transfers like "NIP TRF TO KUDA/JOHN DOE…" are listed with "Needs a category". The number matches the badge in the top bar.

### C3 — Correct one, and teach a rule
1. In **To review**, choose **Family support** for one item.
2. A green box appears: "Always put transactions containing [ … ] in Family support?" Edit the text if needed, keep "Also update … similar transactions" ticked, and click **Create rule**.

**Expected:** a message says how many similar transactions were updated, and they leave the queue. **Categories → Your rules** lists the rule with "learned from you".

### C4 — Rules don't overwrite your own choices
1. Add an expense: `5,000` at `Mama Put Yaba`, and pick the category **Eating out** yourself.
2. **Categories → Add rule**: contains `MAMA PUT` → **Family support**, with "Also apply to existing" ticked → **Check matches**, then **Add rule**.

**Expected:** your Mama Put Yaba transaction still says **Eating out**, marked "You chose". New "Mama Put" transactions get Family support.

### C5 — Automatic categories for new entries
**Add**: an expense of `2,500` at `Chicken Republic Ikeja`, a `1,200` expense at `Ikeja Electric`, and a `3,000` expense at `Some Supermarket`.

**Expected:**
- **Eating out** for Chicken Republic.
- **Electricity & utilities** for Ikeja Electric.
- **Food & groceries · check** for Some Supermarket, which also appears in To review because a generic word is only a suggestion. Click **Confirm** there.

### C6 — Refund follows the purchase
1. Open a categorised purchase.
2. Add a **Refund** linked to it: refunds created from the transaction's own panel are linked automatically. If you're adding it from the form, just add a refund for the same merchant.

**Expected:** a linked refund shows the same category as the purchase, with "Same as original".

### C7 — Spending by category
Open **Categories**.

**Expected:**
- Bars for this month's spending by category; click one to see its transactions.
- "Total spending" equals **Spending** on the Home page for this month.
- The ← → buttons switch months.

### C8 — Manage categories
1. **Add category**: `Generator diesel` (Spending), any colour.
2. Edit a transaction's category to Generator diesel.
3. Edit the category → **Merge into another category** → Electricity & utilities.

**Expected:**
- Step 1: the category appears.
- Step 2: the transaction shows it.
- Step 3: the transaction now shows Electricity & utilities and Generator diesel is gone.
- **Bank fees** can be renamed but has no Archive or Delete.

### C9 — Categories in statement imports
Import `docs\samples\sample-gtbank-style-statement.csv` into a **new** test account.

**Expected:**
- Each new row shows a category menu, pre-filled where recognised (Salary, Bank fees, Entertainment…).
- The NIP transfer row is empty.
- If you choose one for it before importing, the saved transaction shows "You chose".

### C10 — Filters and export
1. In **Transactions**, filter Category = Uncategorised, then tick "Only show ones that need a category".
2. Click **CSV**.

**Expected:** the filters narrow the list correctly, and the CSV has a **category** column.

### Reporting back
Reply with one line, for example `C1 pass … C10 pass`, and add a screenshot for any failure. If built-in recognition misses merchants you use often, list them and I'll add them.
