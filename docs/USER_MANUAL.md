# GEYAM — User Manual

> Audience: shop owners and cashiers who will use GEYAM day-to-day.
> This manual explains how to **operate** the app. It does **not** cover how to install or deploy it — that lives in [SETUP.md](SETUP.md).

---

## Table of Contents

1. What GEYAM does, in plain language
2. Who uses what (Owner vs Cashier)
3. Opening the app (web vs phone)
4. First-time owner sign-up
5. Cashier login
6. Taking a sale — the everyday flow
7. Refunding or cancelling a sale (void)
8. Managing your menu
9. Teaching the camera (training)
10. Inventory
11. Staff (adding cashiers, resetting PINs)
12. Settings
13. Dashboard and reports
14. Ask GEYAM (the built-in Q&A)
15. Audit log
16. Notifications and the offline banner
17. Troubleshooting
18. FAQ

---

## 1. What GEYAM does, in plain language

GEYAM is a cash register for a packaged-food shop, with three things that make it different from a normal POS:

- **The camera knows your products.** You film each product once on a phone video, GEYAM trains its own AI for your shop, and after that the camera recognises items on the counter instead of the cashier typing codes.
- **Customers pay by DuitNow QR.** Every sale generates a QR code the customer scans with any Malaysian bank app. Money goes straight to **your** Billplz account, not through us.
- **Each shop is walled off.** If you run two shops on one GEYAM installation, neither shop can see the other's sales, menu, staff, or inventory. This is enforced inside the database, not just in the app screens.

Everything else — the menu, the cart, the receipts, the dashboard — works the way a cashier or shop owner would expect.

---

## 2. Who uses what (Owner vs Cashier)

There are two kinds of login, and they see different screens.

| Area | Owner | Cashier |
|---|---|---|
| POS (take a sale) | Yes | Yes |
| Transactions list | Yes (full) | Yes (their shop) |
| Dashboard (charts, KPIs) | Yes | No |
| Menu manager | Yes | No |
| Training (teach the camera) | Yes | No |
| Inventory adjust | Yes | No |
| Staff manager | Yes | No |
| Settings | Yes | No |
| Audit log | Yes | No |
| Reports export | Yes | No |
| Override-void a paid sale | Yes | No |
| Ask GEYAM Q&A | Yes | No |

**Owner** logs in with a real Google account (with 2FA enabled on Google's side).
**Cashier** logs in with a shop handle + username + **6-digit PIN**. Cashiers do not use Google. The owner creates cashier accounts from the Staff screen.

---

## 3. Opening the app (web vs phone)

GEYAM runs the same code on a web browser and on Android. You choose the one that fits the situation.

- **Web (owner, any desktop browser):** go to `https://geyam.com`. You land on a public page with a **Login** button top-right. Click it.
- **Android (cashier at the counter):** install the GEYAM APK on the phone. When you open it, it skips the public landing page and goes straight to the login screen — cashiers don't need to see the marketing page.

> Behind the scenes, the web build lives on Hostinger and the app talks to the owner's laptop via `api.geyam.com` (a Cloudflare Tunnel). If the laptop is off, the app will show an **offline banner** and will block new sales — see §16.

---

## 4. First-time owner sign-up

Only needed once, when the shop is brand new.

1. On the login screen, choose the **Owner** tab.
2. Click **Sign in with Google**. Pick the Gmail account you want to use as the owner. This must be a real Gmail — the 2FA is handled by Google.
3. If your account is already linked to a shop, you go straight to the Dashboard. Skip the rest of this section.
4. If your account is **new** to GEYAM, you get a short onboarding screen asking for:
   - **Shop name** — the name printed on receipts and shown at the top of the dashboard (e.g. "Brian's Corner Shop").
   - **Shop handle** — a short URL-safe nickname cashiers will type when they log in (e.g. `brianshop`). Letters and digits only, no spaces. This is permanent.
5. Click **Create shop**. You are now the owner of that shop and land on the Dashboard.

Tip: the handle is what your cashiers type on their phones every day. Keep it short and easy to spell.

---

## 5. Cashier login

1. On the login screen, choose the **Cashier** tab.
2. Enter:
   - **Shop handle** — e.g. `brianshop` (the owner will have given you this).
   - **Username** — e.g. `staff1` (also given to you by the owner).
   - **PIN** — your six-digit PIN.
3. Tap **Login**. You go straight to the POS screen.

Your login lasts **12 hours**. After that GEYAM will log you out and you'll type the PIN again.

If you forget the PIN, the owner resets it from the Staff screen (§11). There is no self-serve PIN reset by design — PINs are trusted to the owner, not to email.

---

## 6. Taking a sale — the everyday flow

This is the screen cashiers spend most of their day on. On a tablet-ish screen it shows two columns (scan/menu on the left, cart on the right). On a phone it shows three tabs — **Scan**, **Menu**, **Cart** — with a sticky **Checkout** bar at the bottom.

### 6.1 Add items to the cart

You have three ways to add items, and you can mix them in one sale:

**A. Camera scan (the GEYAM way).**
   1. On the **Scan** tab, point the camera at the products on the counter and tap the shutter.
   2. GEYAM shows each item it recognised as a chip with a **confidence badge**:
      - **Green** — confident. Tap **Add** to put it in the cart.
      - **Yellow** — "needs confirm". The camera is not sure. Tap to confirm or drop it.
      - If nothing was recognised, the badge says so and you fall back to the Menu.
   3. If the green/yellow hit has a number next to it ("x3"), that's GEYAM's guess at how many pieces of that item are on the counter. You can adjust in the cart.

**B. Pick from the menu.**
   1. Go to the **Menu** tab. There's a search bar and a grid of product tiles.
   2. Type the first letters of the name (or scroll) and tap the tile to add one to the cart.

**C. Scan a barcode** (only if the owner entered barcodes on the menu).
   - Type or scan the barcode into the search bar.

### 6.2 Adjust the cart

On the **Cart** tab:
- **+ / −** to change the quantity.
- **×** to remove a line.
- The **total** updates as you change things.
- A line from the camera that still says "needs confirm" will not let you check out until you confirm or remove it.

### 6.3 Checkout with DuitNow QR

1. Tap **Checkout**. GEYAM creates the transaction in **pending** state (the sale exists, but the money has not moved).
2. A dialog appears showing a **QR code**. Show the screen to the customer.
3. The customer opens any Malaysian bank app, scans, confirms the amount, and pays.
4. GEYAM is waiting for Billplz (the payment gateway) to confirm the payment. It checks every **3 seconds**.
5. When payment confirms, the dialog flips:
   - Status turns **Paid**.
   - A new QR appears — this one is the **receipt QR**. The customer can scan it with their phone camera to download a PDF of the receipt. They don't need an account.
   - If you also want to email the receipt, tap **Email receipt**, type the customer's email, and tap Send. The PDF is emailed from `noreply@geyam.com`.
6. Close the dialog. The cart is cleared, ready for the next customer.

### 6.4 If the webhook is slow

Sometimes the network is slow and the payment is done but GEYAM has not yet heard from Billplz. You have two options:

- Wait a few more seconds — the polling loop will pick it up.
- Ask the **owner** to tap **Recheck Billplz** on the Transaction Detail screen — this forces GEYAM to ask Billplz directly whether the bill is paid. Only the owner has this button.

### 6.5 Cash sales

If the customer pays cash instead of DuitNow:
1. Check out normally, but on the payment dialog pick **Cash**.
2. The sale is recorded as paid immediately. There is no QR, no webhook, no online receipt.
3. This is recorded in reports and the dashboard like any other sale.

> GEYAM does **not** do a till reconciliation — there is no "drawer count" step. Cash is tracked only as a payment method.

---

## 7. Refunding or cancelling a sale (void)

Two ways to void, depending on who you are and whether the customer has paid.

### 7.1 Cashier self-void (pending only)

If a sale has not been paid yet and the cashier realises they added the wrong item:

1. Open the **Transactions** list and pick the pending sale (or use the row that's still open on the POS).
2. Tap **Void**.
3. Any stock that was reserved is returned to inventory.

The cashier **cannot** void a sale that's already been paid. That needs the owner.

### 7.2 Owner override-void (paid sales)

If a paid sale needs to be reversed (customer returns product, double-charge, mistake caught later):

1. Owner opens the transaction from the Transactions list.
2. Taps **Override void**.
3. A dialog asks for a **mandatory reason** (e.g. "customer returned expired product"). GEYAM will not let you skip this — the reason is saved to the audit log with the owner's name.
4. The sale's status becomes **Voided**. Inventory is restored with a `void_restore` row in the stock-movement ledger. The payment row is untouched so you still see the original Billplz record for reconciliation.

### 7.3 Auto-void

Any pending transaction that sits unpaid for more than **24 hours** is voided automatically by a background worker, so the cashier screen is never cluttered with stale carts. You'll see these as `voided` in the transactions list.

---

## 8. Managing your menu

*Owner screen: Menu Manager.*

### 8.1 Add a single item

1. **Menu Manager → New item**.
2. Fill in:
   - **Name** — the human-readable name ("Milo 3-in-1 Sachet").
   - **Price** — in MYR.
   - **Category** — free text ("Beverage", "Snack"). Used for grouping in reports.
   - **Barcode** — optional, if your products have printed barcodes.
   - **Stock qty** — how many are on the shelf right now.
   - **Reorder point** — when stock drops to this, the item shows up in Low Stock alerts. Default is 5.
   - **Avg cost** — what you paid per piece. Used for margin in reports. Optional.
3. **Save**.

### 8.2 Upload a product image

Open the item in the Menu Manager and tap **Upload image**. Pick a photo or take one. GEYAM resizes and stores it under your shop's upload folder. This image shows on the cashier's Menu tab and on the receipt.

### 8.3 Bulk import via CSV

If you have 50+ items, don't type them one by one.

1. Prepare a CSV with **at least** these columns: `name`, `price`. Optional: `category`, `barcode`, `stock_qty`, `reorder_point`, `avg_cost`.
2. **Menu Manager → Import CSV → pick file**.
3. GEYAM shows a **preview** of the first 50 rows. Check that the columns mapped correctly.
4. **Confirm**. GEYAM reports how many rows were **inserted**, how many **updated** (matched by name), and any **errors** with row numbers.

> CSV tip: export from Excel with UTF-8 encoding. If your names contain commas (like "Nasi Lemak, Mini"), make sure Excel quotes the field.

### 8.4 Archive and restore

- **Delete** (the trash icon) does not actually delete the item — it marks it **inactive**. The item disappears from the cashier's Menu tab but still shows up on old receipts and in reports.
- Toggle **Show archived** in the toolbar to see inactive items, then tap **Restore** to bring them back.

You cannot hard-delete items you've sold — that would break historical reports.

---

## 9. Teaching the camera (training)

*Owner screen: Training.*

This is the only screen that's unique to GEYAM. The idea: you film a short phone video of one product rotating in your hand, GEYAM extracts frames, builds a tiny AI model for your shop, and from then on the camera recognises that product.

### 9.1 What a good training video looks like

- **Duration:** 15–30 seconds (hard cap: 30 seconds; over that and GEYAM will reject the upload).
- **Size:** up to 100 MB.
- **Content:** the product fills most of the frame, rotating slowly so every face is seen — front, back, sides, top, bottom. Plain background is easier. Good lighting.
- **One product per video.** Don't film a stack.
- **Shaky is fine, blurry is not.** Slow rotation beats fast rotation.

### 9.2 Upload the video

1. **Training → Upload video**.
2. A picker asks you **which menu item** this video is for. Pick it (or create the menu item first in §8.1).
3. Pick the video file. GEYAM checks size and duration, extracts the middle frame as a preview thumbnail, and creates a **Queued** training job.

You can queue multiple videos (multiple products) before running training — they'll all train in one batch.

### 9.3 Run training

1. Review the Queued jobs table. Remove any you don't want.
2. Tap **Train now**.
3. The jobs move to **Training** status. A progress chip appears. Training runs in the background on the laptop's CPU — you can keep using the app.
4. When the batch finishes, the **Active model** card updates with:
   - **Version** — which model run this is (1, 2, 3, …).
   - **Classes** — how many distinct products the model can now recognise.
   - **mAP50** — a quality score from 0 to 1. Higher is better. 0.7+ is usable; 0.9+ is excellent.
   - **Trained at** — timestamp.
5. You'll also get a notification toast. From this moment, the POS camera is using the new model — no restart needed.

### 9.4 If training fails

- Check the **Error** column on the failed job. Common causes: corrupted video, too-dark footage, product barely visible.
- Delete the failed job and re-film.
- If training gets stuck with no progress for hours, ask the developer to clear the training lock (see Troubleshooting §17).

### 9.5 How the camera actually decides

When the cashier snaps a photo, GEYAM tries three things in order:

1. **Your trained model (YOLO)** — fast, free, runs on the laptop. If a product is recognised with high confidence (default ≥ 0.60), that's the answer.
2. **A general category model (MediaPipe)** — if YOLO is unsure, this narrows down the guess ("it's a drink").
3. **OpenAI** — last resort if nothing else worked. Uses a paid API. Capped at **50 calls per shop per day** by default, and results are cached for 7 days to avoid paying twice for the same photo.

You can tune these thresholds in Settings (§12.4).

---

## 10. Inventory

*Owner screen: Inventory.*

Two tabs: **All** (everything in the menu that's active) and **Low stock** (items at or below their reorder point).

### 10.1 Adjust stock

1. Find the item (use Low stock tab for the shortlist).
2. Tap **Adjust**.
3. Fill in:
   - **Delta** — a positive number (you received more stock) or a negative one (damage, theft, etc.). Must not be zero.
   - **Reason** — required, pick from the dropdown: `po_receive`, `adjust_damage`, `adjust_loss`, `adjust_theft`, `adjust_miscount`, `adjust_expired`, `adjust_other`.
   - **Note** — free text (optional but recommended).
4. **Save**. The adjustment is written to an append-only ledger and the running total updates.

> Every sale, void, and adjustment is a row in the ledger. You don't edit stock directly — you always write a new adjustment. This means the history of how your stock got to "27 packs" is always auditable.

### 10.2 Low stock alerts

The Dashboard shows a **Low stock** KPI card. The number is "how many items are at or below their reorder point". Tap it to jump to the Inventory → Low stock tab.

---

## 11. Staff (adding cashiers, resetting PINs)

*Owner screen: Staff Manager.*

### 11.1 Add a cashier

1. **Staff Manager → New cashier**.
2. Fill in:
   - **Username** — optional. If you leave it blank, GEYAM generates `staffN.<your-handle>` for you.
   - **PIN** — must be **6 digits**. GEYAM refuses trivial PINs like `111111` or `123456`.
3. **Save**. Write the username + PIN down somewhere safe and give them to the cashier.

### 11.2 Reset a PIN

Happens when the cashier forgets their PIN.

1. Find the cashier in the table.
2. Tap **Reset PIN**.
3. Enter the new 6-digit PIN.
4. Tell the cashier the new PIN in person.

### 11.3 Disable a cashier

If an employee leaves, flip the **Active** switch off. Their login stops working immediately. Their past sales are preserved.

You cannot delete a cashier outright — that would break historical transactions. Disable is the correct action.

---

## 12. Settings

*Owner screen: Settings.* Three blocks.

### 12.1 Billplz (payments)

This is what lets your shop accept DuitNow QR.

- **Mode** — `sandbox` or `production`. Use **sandbox** while you test, then flip to **production** when you're ready to accept real money.
- **API Key** — your Billplz API key.
- **Collection ID** — your Billplz collection ID.
- **X-Signature Key** — used to verify that incoming payment confirmations really came from Billplz and not a forgery.

Keys are stored **encrypted** in the database. The Settings screen never shows you the key back — it only shows a **"Configured ✓"** chip. To change a key, type the new one in; to leave it alone, leave the field blank and Save (a blank save will not wipe your credentials).

### 12.2 Shop & Receipt

- **Shop contact email** — shown on receipts as the "reply to".
- **Shop contact phone** — shown on receipts.
- **Receipt footer** — free text, e.g. "Thank you for shopping at Brian's Corner!"
- **Logo** — tap **Upload logo** to add a shop logo. It appears on receipts and in the app header.

### 12.3 Detection thresholds

Fine-tuning for the camera. Defaults work for most shops.

- **YOLO confidence threshold** (default 0.60) — scores at or above this are "green / confident" and auto-added to the cart.
- **YOLO minimum** (default 0.40) — scores between the minimum and the threshold are "yellow / needs confirm". Below the minimum, the guess is dropped.
- **OpenAI daily limit** (default 50) — how many OpenAI fallback calls are allowed per day. When you hit this, the cascade stops calling OpenAI for the rest of the day and yellow guesses go to manual confirm instead.

### 12.4 When to lower the YOLO threshold

If the camera is recognising your items but always marking them yellow, your model is underconfident — either retrain with more varied video, or lower the threshold to 0.50. Don't go below 0.40 unless you want a lot of false positives.

---

## 13. Dashboard and reports

*Owner screen: Dashboard.*

### 13.1 Range picker

Top of the screen: **Today**, **7d**, **30d**. Pick the window you want to see. Everything on the page re-aggregates.

### 13.2 KPI cards

Each card is a big coloured tile with a number:

- **Revenue** — total paid amount in the window.
- **Transactions** — count of paid sales.
- **Avg basket** — average ringgit per sale.
- **Top item** — the single product that sold the most.
- **Low stock** — items at or below their reorder point.
- **Anomaly z** — a statistical score of how unusual today's sales are vs the last 30 days. A z > 2 is "something noticeably different", either good or bad. Tap the card to see which direction.

### 13.3 Charts

- **Sales pie** — top 6 items + "Other".
- **Revenue line** — revenue per day over the range.
- **Staff performance** — table of cashier, sales count, total rung up.
- **Detection source bar** — how many line items came from YOLO vs MediaPipe vs OpenAI vs manual. Useful for seeing how well your trained model is working (more YOLO = better).

### 13.4 Reports

*Owner screen: Reports.*

Pick a format:
- **JSON** — preview on screen.
- **CSV** — downloadable file.
- **XLSX** — Excel file with one sheet per section.
- **PDF** — formatted report, suitable for printing.

---

## 14. Ask GEYAM (the built-in Q&A)

On the Dashboard there's a floating chat bubble. Tap it and type a question in plain English:

- "What sold best last week?"
- "Compare Monday to Tuesday."
- "Which staff member rang up the most sales?"

The question goes to a small language model (`phi3:mini`) running **locally on the laptop**, together with a summary of your dashboard data. The answer stays inside your shop — none of your sales data is sent to a cloud LLM.

Limitations:
- It reads only the dashboard window you currently have open. "Last year" questions when you're looking at "Today" will get a confused answer.
- It's a small model. Keep questions concrete and single-topic.
- It's slower on first question after a long pause (the model loads on demand).

---

## 15. Audit log

*Owner screen: Audit Log.*

Every important event in your shop has a row here:

- Owner and cashier logins.
- Menu changes.
- Staff created, disabled, PIN reset.
- Settings changed.
- Override-void (with the reason the owner typed).
- Admin impersonation (rare — only happens if support logs in to help you).

You can filter by **action prefix** (e.g. `auth.` for all logins, `menu.` for menu changes, `tx.` for transactions). 50 rows per page.

This log is append-only. It's the answer to "who changed the price of Milo yesterday?"

---

## 16. Notifications and the offline banner

### 16.1 The bell

Top-right of every screen is a **bell icon**. It holds the last 50 live events from your shop:

- `training_done` — a training batch finished. Shows the new mAP50.
- `tx_paid` — a transaction was paid. Useful if you're not the one at the POS.
- `tx_autovoid` — the scheduler voided a stale pending transaction.
- `low_conf` — the camera saw something with low confidence and needed manual confirm.

### 16.2 Offline banner

If the laptop's backend is unreachable (laptop off, tunnel down, network cut), you'll see a red **Offline** banner across the top.

While offline:
- You can still browse lists that were loaded before going offline.
- You **cannot** take new sales, change stock, or do anything that modifies the database. Those buttons are disabled.
- When the backend comes back, the banner clears automatically.

This is intentional — GEYAM would rather refuse a sale than record one that might later disappear when the laptop comes back online.

---

## 17. Troubleshooting

### 17.1 "Login failed" when using Google

- Wrong Google account. GEYAM is tied to the Gmail the developer used when creating your tenant.
- 2FA not set up. Turn it on in your Google account settings.
- Popup blocker. Allow popups for `geyam.com`.
- If you're on the Brave browser, its shield can block the sign-in redirect. Try Edge, Chrome, or Firefox.

### 17.2 "Login failed" as a cashier

- Check the **shop handle** (no spaces, all lowercase).
- Check that your account is **Active** (ask the owner).
- PIN brute-forcing is slow on purpose — if you've typed it wrong three times, pause and try again carefully.

### 17.3 QR code doesn't appear at checkout

- The shop's Billplz credentials aren't configured. Owner → Settings → Billplz.
- The shop is in `sandbox` mode but Billplz sandbox is down. Status at `status.billplz.com`.
- Network issue between the laptop and Billplz. Check the offline banner.

### 17.4 Customer paid but GEYAM still says "pending"

Wait 5–10 seconds — the polling loop picks it up every 3 seconds. If it's still pending after 30 seconds:

1. Owner → Transactions → open the transaction → **Recheck Billplz**. This asks Billplz directly.
2. If Billplz says **paid**, GEYAM updates the sale immediately and kicks off the receipt.
3. If Billplz says **unpaid**, the customer's payment didn't actually go through — ask them to retry, or use cash.

### 17.5 Camera recognises nothing

- You haven't trained a model yet. Training screen → upload a video → Train now.
- Your model trained but with very few items — it only recognises what it's seen. Keep training.
- Bad lighting. Move closer to a window or a lamp.
- Product is on the edge of the frame. Centre it.

### 17.6 Camera recognises the wrong item

- Your product and another one look similar. Film a new training video with more variation — different angles, different lighting.
- Drop the "needs confirm" yellow hit and pick from Menu instead, so the sale is still correct. Then retrain later.

### 17.7 Training stuck in "Training" for hours

- Training on a CPU can take a while for a large batch (dozens of videos, many epochs). Check back after lunch.
- If it's been over 4 hours, something may have crashed. Ask the developer to:
  1. Check `docker compose logs worker`.
  2. If the worker is dead, `docker compose restart worker`.
  3. If the per-tenant lock is stuck, clear it in SQL (see PROJECT_OVERVIEW §15).

### 17.8 Receipts not emailing

- Customer's email address had a typo. Resend the receipt from Transaction Detail with the corrected address.
- Customer's inbox filtered it. Ask them to check spam / add `noreply@geyam.com` to contacts.
- Resend is down or out of quota. Check the Resend dashboard.

### 17.9 Dashboard numbers look wrong

- Wrong range picker. Check the Today / 7d / 30d toggle.
- A sale is still `pending`. The dashboard counts only **paid** sales.
- A sale was **voided** — voided sales don't count in revenue.

### 17.10 Still stuck

Take a screenshot, note the time, and send both to the developer along with what you were trying to do. They can cross-reference the audit log and server logs.

---

## 18. FAQ

**Q: Can two cashiers be logged in at the same time?**
Yes. Each cashier has their own username + PIN and their own session.

**Q: Can I log in as owner on the phone?**
Yes — on the cashier login screen, you still have the Owner tab with Google Sign-In. But most dashboard screens are laid out for bigger screens; you'll find them cramped on a phone.

**Q: What happens to my data if my laptop dies?**
The backup service runs `pg_dump` **every night** and keeps the last **7 days** on disk. Your Flutter builds and the static site are on Hostinger so they survive. As long as you have a recent backup, a new laptop can be restored in an hour.

**Q: Does GEYAM work without internet?**
Not today. The Flutter app needs to reach the backend, which needs the Cloudflare tunnel, which needs the internet. An offline mode is not in scope for this version.

**Q: Can I change my shop handle?**
No. The handle is permanent and is used in URLs, audit rows, and cashier logins. If you really need to, the developer can do it in SQL but it's a manual operation.

**Q: Can I have one owner account for two shops?**
Yes — you can be an owner of multiple tenants. On the tenant picker screen (for admin-scoped users) you can pick which shop to open. Normal owners are tied to one shop.

**Q: Are my Billplz keys and customer emails stored safely?**
Billplz keys are Fernet-encrypted at rest. Customer emails used for receipts live on the `transactions` row and are only visible to the owner and the specific cashier for that sale. Nightly backups are as sensitive as the Fernet key, which lives in `.env` on the laptop only.

**Q: Can I use GEYAM with a barcode scanner?**
Yes — a USB barcode scanner behaves like a keyboard. On the Menu tab's search bar, the scan appears as typed text and matches products whose `barcode` field was filled in when the item was created.

**Q: What's the receipt QR the customer scans?**
It's a link to a read-only web page (and PDF) of that one receipt. The link contains a token that's valid for **30 days**. The customer can get their receipt even weeks later, but they cannot see any other data in your shop.

**Q: What if OpenAI isn't available?**
The cascade just stops at stage 2. Any products that YOLO couldn't recognise become yellow "needs confirm" hits. The cashier picks manually from the Menu. No sales are lost.

---

*End of manual. For the developer runbook see [SETUP.md](SETUP.md); for architecture and internals see [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md).*
