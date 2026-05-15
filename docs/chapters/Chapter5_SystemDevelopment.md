# Chapter 5: System Development

## 5.1 Overview

This chapter covers how GEYAM was actually built, as opposed to how it was designed in Chapter 3 or specified in Chapter 4. Where those chapters answer "what should the system do," this one answers "what did I write, and why did I write it that way rather than the more obvious alternative." The bias throughout is towards the parts of the system that an FYP examiner cannot reconstruct from the plan alone — the per-tenant YOLO cascade, the local-LLM dashboard Q&A, the SQLAlchemy tenant-scope hook, and the Billplz DuitNow QR webhook — because those four are where the engineering risk and the academic contribution both live.

The chapter is organised into three blocks. Section 5.2 walks through the development tooling and environment, which is more than a formality because the choice of WSL2 + Docker Compose + Cloudflare Tunnel shaped how the rest of the system could be deployed on a single laptop. Sections 5.3 to 5.6 each describe one of the four unique subsystems using the same three-part structure (development approach, code development, advantages of the approach), with real code pulled from the repository rather than pseudo-code. Section 5.7 maps each functional requirement from Chapter 3 to the module that implements it, so the examiner can trace a requirement to a line of code. Section 5.8 summarises the lessons learned and flags what I would do differently on a second pass.

The full repository layout is documented in `docs/PROJECT_OVERVIEW.md` Appendix A. For this chapter I treat it as assumed context and only reference specific files when they are being discussed.

[image/screenshot/figure 1] Figure 5.1: Development workflow overview — from local code on Windows, through WSL2 Docker containers, out to the public internet via Cloudflare Tunnel.

---

## 5.2 System Development Tools and Configuration

GEYAM runs entirely on the developer's laptop during normal development, and on the same laptop in "production" for the FYP demo. This is a deliberate constraint — I wanted to prove that a realistic multi-tenant POS can be built and demoed without renting any cloud compute — and every tooling choice was made to support it.

### 5.2.1 Local AI Engine Configuration (Ollama + YOLOv8 + MediaPipe)

The AI stack has two halves that run very differently. The vision models (YOLOv8n fine-tunes and MediaPipe EfficientDet-Lite0) run **inside** the backend container because they are called synchronously during a `POST /detect` request and need to share the image bytes without crossing process boundaries. The local LLM (`phi3:mini` served by Ollama) runs **outside** the container on the Windows host, because Ollama is already tuned to use the laptop's CPU scheduler directly and the container boundary only slowed things down in my earlier tests.

To make the backend reach the host-side Ollama, the Compose file sets `extra_hosts: host.docker.internal:host-gateway` on the `backend` service, and `ollama_ask.py` talks to `http://host.docker.internal:11434`. This is not a dramatic trick, but it is the kind of line that the project collapses without — when I first tried to put Ollama inside a container, the `phi3:mini` 3.8-billion-parameter weights loaded twice as slowly and one of the dashboards took eight seconds to render.

YOLO weights live under `backend/ml_models/<tenant_id>/best.pt`. The backend process keeps at most three tenants' weights in memory via an LRU cache in `yolo_cache.py`; a file-mtime check means the cache auto-invalidates the moment the RQ training worker writes a fresh `best.pt`, so new weights go live without a process restart. This is the kind of small decision that had a big impact — before the mtime check, I had to either poll a flag table every request (slow) or run with stale weights until I manually restarted the backend (unacceptable during a demo).

[image/screenshot/figure 2] Figure 5.2: Ollama reachable from the backend container via `host.docker.internal` — screenshot of successful `/ask` response.

### 5.2.2 WSL (Windows Subsystem for Linux) Configuration & Network Troubleshooting

Windows is my daily operating system, but the backend stack (Postgres 16, Redis, RQ, FastAPI, and the Ultralytics stack) is orders of magnitude smoother on Linux. WSL2 with Docker Desktop's WSL2 backend was the path of least resistance: Windows Explorer still owns the files, VS Code can open the repo natively via the WSL extension, and the Docker daemon runs inside WSL so Compose startup is under ten seconds.

The networking is the part that caught me out. WSL2 runs in a Hyper-V-managed VM with its own IP, and Windows services (including `cloudflared` if installed on the host) talk to WSL through a NAT layer that randomly refused connections on the first day I tried to open the Cloudflare Tunnel. The fix was to run `cloudflared` **inside** WSL rather than on Windows so that the tunnel binary and the backend container share the same loopback. Two lines in `/etc/wsl.conf` — `[boot] systemd=true` and `[network] generateResolvConf=true` — made `cloudflared` run as a systemd service on WSL boot, which meant the tunnel reconnected automatically whenever I rebooted the laptop.

Postgres and Redis are published on non-standard host ports (5433 and 6380) so they do not collide with any local Postgres service a marker might have running on their own machine when cloning the repo. This is a small courtesy, but it is the kind of detail that determines whether a stranger can `docker compose up -d` and see the app running in five minutes.

### 5.2.3 Frontend Build Tools and Security Configuration

The Flutter client compiles to two targets from the same `pubspec.yaml`: `flutter build web --release` produces the bundle uploaded to Hostinger, and `flutter build apk --release` produces the APK sideloaded onto the cashier's Android phone. A `kIsWeb` gate in `main.dart` swaps the first screen between a landing page (web) and a login screen (mobile), which is how one codebase covers both the owner-facing showcase and the cashier-facing tool.

On the security side, the Flutter `ApiService` singleton injects `Authorization: Bearer <access_token>` on every request, and every mutating method is wrapped in a `guardMutation()` helper that refuses to send if the `ConnectivityProvider` is currently offline. The reasoning was that a cashier in a patchy-signal area would otherwise queue up partial carts and charge customers twice — I would rather fail loud than fail silent. On the backend, JSON Web Tokens are signed with HS256 and one server-side secret, access tokens are 24 hours for owners and 12 hours for cashiers, and the tenant id embedded in the token is what the SQLAlchemy hook reads on every request (discussed in detail in section 5.5).

[image/screenshot/figure 3] Figure 5.3: Flutter web build output — same codebase, `kIsWeb` branch picks landing vs login screen.

---

## 5.3 Uniqueness of System 1: Per-Tenant YOLO Food Detection Cascade

### 5.3.1 Development Approach

Food detection is the academic heart of the project, and it was also the system I rewrote the most times. The original Stage-1 plan used a single pre-trained YOLOv8 model shared across tenants, which made sense on paper but collapsed the moment I tested it with real Malaysian mamak snacks — the pre-trained COCO classes do not contain "Milo kotak" or "Tora biskut," and the detector returned either nothing or the wrong thing with embarrassing confidence. The obvious fix was to fine-tune one detector per shop on the shop's own product photos, which is what the production version does.

Training per-tenant models, however, creates new problems. Phone-recorded video is the easiest thing a non-technical shop owner can produce, so the training pipeline had to accept a 15–30-second video, auto-extract frames, auto-label them, and run the fine-tune. Because the owner has no ML background, I cannot ask for bounding boxes — the pipeline auto-generates centred 0.8-by-0.8 boxes on every frame, which is defensible because a phone video of a single product in the hand is dominated by that product. Accuracy suffers on edge crops, but it suffers a lot less than asking the owner to draw rectangles.

The inference-time problem then becomes: what happens when the per-tenant model is uncertain or wrong? My reading of the literature — and the reason I went with a cascade rather than a single model — is that a small fine-tuned detector is almost always either confidently right or confidently wrong, and the middle band (0.40 to 0.60 confidence) is where most of the real errors live. Rather than ask the cashier to choose between "trust it" and "retrain," I added two more stages: a MediaPipe EfficientDet-Lite0 category shortlister, and a quota-capped OpenAI `gpt-4o-mini` vision fallback that only fires when the first two stages produce nothing useful. The cascade is described in the plan as "YOLO → MediaPipe → OpenAI → manual," but it is fundamentally three independent classifiers whose outputs are merged by a deduplication step that keeps the highest-confidence hit per menu item.

[image/screenshot/figure 4] Figure 5.4: Cascade flow — per-tenant YOLO first, MediaPipe if YOLO is empty, OpenAI if both are empty, dedup at the end.

### 5.3.2 Code Development

The orchestrator is `backend/app/services/detection/cascade.py`, and its most important fifty lines are the three-stage gated flow:

```python
# Stage A — tenant YOLO
model = get_model(tenant_id)
yolo_items = run_yolo(
    model, img,
    conf_threshold=settings.yolo_conf_threshold or 0.60,
    conf_minimum=settings.yolo_conf_minimum or 0.40,
)
for it in yolo_items:
    match = label_to_item.get(it["label"])
    if match:
        it["menu_item_id"] = match["id"]
        it["name"] = match["name"]
        it["price"] = match["price"]
yolo_items = [it for it in yolo_items if "menu_item_id" in it]

# Stage B — MediaPipe (skipped when library unavailable; reserved slot)
mp_items: list[dict] = []
if not yolo_items:
    mp_items = run_mediapipe(img, menu_items)

# Stage C — OpenAI (gated by yolo+mp empty)
ai_items: list[dict] = []
if not yolo_items and not mp_items:
    ai_items, err = run_openai(
        tenant_id=tenant_id, phash=phash, img=img,
        menu_items=menu_items, sync_session=s, settings=settings,
    )
    if err:
        errors.append(err)
```

What is worth noting is that each stage is gated strictly on the previous stage producing zero items, not on low confidence. This is deliberate: once YOLO has matched even one product with reasonable confidence, calling MediaPipe or OpenAI is wasted latency and wasted OpenAI quota. The cascade therefore never "compounds evidence" from multiple stages on the same image — it uses the cheapest confident source it can find and stops there.

The YOLO stage itself is a thin wrapper over `ultralytics.YOLO.predict`, with the three-band thresholding logic inline:

```python
def run_yolo(model, img, conf_threshold, conf_minimum):
    if model is None:
        return []
    results = model.predict(img, conf=conf_minimum, iou=0.45, verbose=False)
    out = []
    for r in results:
        names = r.names
        for box in r.boxes:
            cls = int(box.cls[0].item())
            conf = float(box.conf[0].item())
            if conf < conf_minimum:
                continue
            label = names.get(cls) if isinstance(names, dict) else names[cls]
            out.append({
                "label": label,
                "confidence": conf,
                "source": "yolo",
                "needs_confirm": conf < conf_threshold,
            })
    return out
```

The `needs_confirm=True` flag is surfaced in the POS UI as a yellow chip instead of a green one, so the cashier sees immediately which items the model was only half-sure about. Both thresholds (`yolo_conf_threshold`, `yolo_conf_minimum`) live on `tenant_settings`, so each shop can tune their own sensitivity without a code change.

The OpenAI fallback is the most expensive stage and also the one most likely to cost real money, so three separate guards wrap the actual API call — a perceptual-hash Redis cache with a 7-day TTL, a per-tenant daily quota, and a `OPENAI_SKIP=1` environment variable for test runs:

```python
# pHash cache lookup
r = _redis()
if r is not None:
    cached = r.get(_cache_key(tenant_id, phash))
    if cached is not None:
        cached_names = json.loads(cached)
        return _names_to_matches(cached_names, menu_items), None

# Quota check
usage = sync_session.query(OpenAIUsage).filter(
    OpenAIUsage.tenant_id == tenant_id, OpenAIUsage.day == today
).first()
calls = usage.calls if usage else 0
limit = settings.openai_daily_limit or 50
if calls >= limit:
    return [], "quota_exceeded"
```

When OpenAI does get called, the response names are fuzzy-matched against the tenant's menu via `rapidfuzz.fuzz.partial_ratio` at a 0.80 threshold, which I picked after a short calibration on my own seed data. Anything below 80 is dropped — it is better to show the cashier "no detection" and let them pick from the menu manually than to confidently match "Milo" to "Milo UHT" when the customer is holding "Milo Kotak."

Finally, hot-reloading of weights after training is handled by the LRU cache in `yolo_cache.py`:

```python
def get_model(tenant_id):
    path = _tenant_weights_path(tenant_id)
    if not path.exists():
        _cache.pop(tenant_id, None)
        return None
    disk_mtime = path.stat().st_mtime
    cached = _cache.get(tenant_id)
    if cached is not None and cached[1] >= disk_mtime:
        _cache.move_to_end(tenant_id)
        return cached[0]
    from ultralytics import YOLO
    model = YOLO(str(path))
    _cache[tenant_id] = (model, disk_mtime)
    _cache.move_to_end(tenant_id)
    while len(_cache) > LRU_CAPACITY:
        _cache.popitem(last=False)
    return model
```

The mtime check is the key line. After the RQ worker finishes training and writes a new `best.pt`, the very next `/detect` call for that tenant sees `disk_mtime > cached[1]` and re-loads from disk. No restart, no flag table, no broadcast — just the filesystem as the source of truth.

[image/screenshot/figure 5] Figure 5.5: Screenshot of the POS "Scan" panel showing green (high-confidence) and yellow (needs_confirm) chips for three detected items.

### 5.3.3 Advantages of the Approach

The real advantage of a three-stage cascade over a single model is economic, not just accuracy-related. A single shared model would be cheaper to train once but would need to be retrained every time any shop added a product, and it would either mix every shop's photos (a privacy problem) or require a central annotation service (a cost problem). Per-tenant fine-tuning sidesteps both. The cascade then uses the cheapest stage that works: 98% of requests in my internal tests terminated at Stage A and never paid for OpenAI at all. The per-tenant daily quota of 50 calls is deliberately conservative — at current OpenAI pricing that is around 40 US cents per day per shop in the worst case, and the pHash cache absorbs most of the repeat scans a cashier would otherwise rack up.

The other advantage is operational. Because YOLO weights are on disk and the LRU cache picks up changes via mtime, I can retrain a tenant's model while the POS is running and the cashier sees the new weights on the very next scan. That is the kind of feature an owner will never ask for explicitly but will absolutely notice when a new product appears on the shelf and the scanner already knows about it.

The clearest weakness is that MediaPipe Stage B is currently a stub in the repo (the wiring is complete, but `run_mediapipe` returns `[]`). I did this deliberately to keep the FYP scope tight — MediaPipe's category model would need its own alias table mapping generic classes like "beverage" to the tenant's specific menu, and I would rather ship a clean two-stage cascade than a half-wired three-stage one. The architecture leaves the slot ready for Phase 14 without touching the rest of the pipeline.

---

## 5.4 Uniqueness of System 2: AI Forecasting & Ask GEYAM (Local LLM Q&A)

### 5.4.1 Development Approach

The dashboard is where the shop owner spends most of their time, and I wanted it to answer two different kinds of question: the numeric ones ("how much did we make last week?") and the open-ended ones ("why was yesterday slow?"). The first is a forecasting and aggregation problem, and the second is a natural-language question-answering problem. Building two UIs for these would have been correct in theory and terrible in practice — owners open the dashboard to make a decision, not to pick between tabs.

My reading of the problem is that the numeric side should be computed deterministically (EWMA demand, safety stock, reorder point, EOQ, anomaly z-score) and the narrative side should sit on top of those same numbers, powered by a language model that is told the numbers and asked to write a sentence. This is the core idea behind the Ask GEYAM feature — a floating chat bubble on the dashboard that posts to `/ask`, which serialises the current dashboard window into a compact string and feeds it plus the question into a locally-running `phi3:mini` via Ollama.

Running the LLM locally was not a style choice. Sending shop revenue, transaction counts, and staff performance data to a cloud LLM API would be an unambiguous privacy problem for a small Malaysian shop owner, it would require per-token billing that the owner cannot predict, and it would create a latency floor that the free tier of any major cloud LLM provider would struggle to meet consistently. `phi3:mini` at 3.8 billion parameters fits comfortably in CPU RAM, answers template-style questions in under three seconds on my laptop, and costs nothing per call.

[image/screenshot/figure 6] Figure 5.6: Dashboard screenshot — KPI cards on top row, revenue line chart, staff performance table, and the floating Ask GEYAM bubble on the bottom-right.

### 5.4.2 Code Development

The forecasting primitives live in `backend/app/services/forecast.py` and are pure functions with no database coupling — deliberately, so they are unit-testable in isolation and reusable from the dashboard endpoint, the reports endpoint, and the reorder-point screen:

```python
def ewma(series, alpha=0.3):
    if not series:
        return 0.0
    s = series[0]
    for x in series[1:]:
        s = alpha * x + (1 - alpha) * s
    return s


def safety_stock(series, service_z=1.65, lead_time_days=7):
    if len(series) < 2:
        return 0.0
    mean = sum(series) / len(series)
    var = sum((x - mean) ** 2 for x in series) / (len(series) - 1)
    sigma = math.sqrt(var)
    return service_z * sigma * math.sqrt(lead_time_days)


def reorder_point(ewma_daily, lead_time_days, ss):
    return ewma_daily * lead_time_days + ss


def eoq(annual_demand, order_cost=20.0, holding_cost_per_unit=0.50):
    if annual_demand <= 0 or holding_cost_per_unit <= 0:
        return 0
    q = math.sqrt(2 * annual_demand * order_cost / holding_cost_per_unit)
    return int(round(q))


def z_score_anomaly(today_value, window):
    if len(window) < 3:
        return 0.0
    mean = sum(window) / len(window)
    var = sum((x - mean) ** 2 for x in window) / (len(window) - 1)
    sigma = math.sqrt(var) if var > 0 else 1e-6
    return (today_value - mean) / sigma
```

The choice of exponentially-weighted moving average with `alpha=0.3` over a plain moving average is that a small shop's demand pattern drifts (a new product goes viral on TikTok, or a nearby school's term ends), and the EWMA gives recent days roughly three times the weight of week-old days without throwing the history away entirely. The safety-stock formula is the standard textbook `z · σ · √L` form with a 95th-percentile service level (`z = 1.65`), which matches what most practical inventory textbooks recommend for a non-critical SKU. EOQ uses the classic Wilson formula with defensible defaults — RM20 to place an order and RM0.50 per unit-year holding cost — that the owner can override per item once they have real data.

The z-score anomaly is the feature I use on the dashboard to flag unusual days with a single red chip, rather than forcing the owner to stare at a chart. A z-score above 2.0 or below –2.0 is marked "anomaly" in the UI; an explicit `sigma = 1e-6` floor prevents a division-by-zero when the last thirty days are all identical (which happens on very quiet shops in the demo seed data).

The Ask GEYAM side is even smaller — the entire Ollama client is eighteen lines:

```python
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "phi3:mini")
DEFAULT_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")


def ask(prompt, *, context="", model=None):
    full = f"{context}\n\nQuestion: {prompt}\nAnswer concisely."
    payload = {"model": model or DEFAULT_MODEL, "prompt": full, "stream": False}
    try:
        r = httpx.post(f"{DEFAULT_HOST}/api/generate", json=payload, timeout=60)
        r.raise_for_status()
        data = r.json()
        return data.get("response", "").strip()
    except Exception as e:
        return f"(ollama unavailable: {type(e).__name__})"
```

The interesting design choice here is what sits in `context`. The `/ask` endpoint serialises the current dashboard window — range, total revenue, transaction count, top items, staff performance, anomaly flag — into a short plaintext block and prepends it to the user's question. A typical prompt sent to `phi3:mini` looks like this:

```
Range: last 7 days.
Revenue: RM1,842.50 (18% above 30d avg).
Transactions: 142 (avg basket RM12.97).
Top items: Milo UHT (34), Julie's biscuit (22), Tora strawberry (18).
Staff: Ali 72 tx, Siti 51 tx, Lim 19 tx.
Anomaly: yes (z=2.4 on Monday).

Question: why was monday so busy?
Answer concisely.
```

The point is that `phi3:mini` never queries the database and never sees raw customer data — it only sees the aggregates the dashboard is already showing. This keeps the LLM's surface area tiny and its output grounded: it can only talk about what is in the context, which is what I want for a business-facing Q&A tool.

[image/screenshot/figure 7] Figure 5.7: Ask GEYAM bubble in action — owner asks "what sold best yesterday?" and `phi3:mini` answers from the dashboard context.

### 5.4.3 Advantages of the Approach

The clearest advantage is that forecasting and Q&A share one data path. The dashboard computes the aggregates once per page load; the chart module uses them; the Ask GEYAM bubble uses them. There is no duplicate query layer, no vector database (which would be overkill for a thirty-day window), and no embedding pipeline to maintain. This matters for a solo-developer FYP because every additional system is a system I would need to test and document separately.

The second advantage is data residency. Sales data never leaves the shop. For an examiner evaluating privacy posture this is a cleaner story than "we anonymise before sending to the cloud," and for an actual shop owner it is the difference between "I can use this" and "my accountant would kill me."

The third advantage is cost predictability. Once Ollama is installed, the marginal cost of an `/ask` call is CPU time, not dollars. I can leave the Ask GEYAM bubble open during a demo and pepper it with questions without watching an OpenAI bill tick up in the background.

The honest downside is that `phi3:mini` is demonstrably worse at reasoning than `gpt-4o-mini` or Claude — it occasionally answers the wrong question, and it sometimes restates a number from the context instead of drawing a conclusion from it. I accept this trade-off because the failure mode is a less-useful answer, not a leaked one. Upgrading to `phi3:medium` or `llama3:8b` on a stronger machine is a one-line change (`OLLAMA_MODEL=...`) and does not touch the rest of the pipeline.

---

## 5.5 Uniqueness of System 3: Multi-Tenant Isolation Engine

### 5.5.1 Development Approach

Multi-tenancy is the non-negotiable property of the project. If shop A can see shop B's data, the entire system is a security failure regardless of how well the detection or forecasting works. The plan's Rule 2 — Phase 3 and beyond cannot proceed until the tenant-isolation integration test is green — is not a stylistic choice, it is the gate that all the later work sits on top of.

My first instinct was the obvious one: add `tenant_id` to every table and write `.where(Model.tenant_id == current_tenant_id)` in every query. This is what most tutorials on multi-tenant SaaS suggest and it works, but only if every developer remembers to do it every time. On a one-developer FYP with 14 routers and roughly 40 endpoints, "remember to do it every time" is not a security property — it is a wish. I wanted the system to fail safe: if I forget to filter, the query returns nothing, not the other shop's data.

The cleaner answer is to lift the filter out of the handler entirely and into the ORM layer, so handlers are written as if they were single-tenant and the ORM does the scoping invisibly. SQLAlchemy 2's `do_orm_execute` event is exactly the hook I needed — it fires on every SELECT and lets me rewrite the query plan before it executes. Combined with Python 3's `ContextVar` (which is async-safe in a way thread-locals are not), the whole scheme boils down to: the request dependency reads `tenant_id` from the JWT and sets it on a ContextVar; the event hook reads the ContextVar and appends a `tenant_id = :ctx` filter to every SELECT; handlers don't need to know.

The one wrinkle is that a small number of code paths — admin endpoints, CLI scripts, the RQ training worker, the nightly backup — legitimately need to see across tenants. Those wrap their calls in an `async with bypass_tenant_scope():` context manager which flips a second ContextVar that the hook checks first, and the ContextVar is restored on exit even if the body raises.

[image/screenshot/figure 8] Figure 5.8: Tenant isolation as four cooperating layers — ContextVar, event hook, filesystem prefix, WebSocket hub key.

### 5.5.2 Code Development

The ContextVar module is tiny by design — it declares the two variables and exposes getter/setter pairs, nothing else:

```python
# app/tenant_context.py
from contextvars import ContextVar
from typing import Optional

_current_tenant_id: ContextVar[Optional[int]] = ContextVar(
    "current_tenant_id", default=None
)
_tenant_scope_bypass: ContextVar[bool] = ContextVar(
    "tenant_scope_bypass", default=False
)


def get_current_tenant_id() -> Optional[int]:
    return _current_tenant_id.get()


def set_current_tenant_id(tenant_id: Optional[int]):
    return _current_tenant_id.set(tenant_id)


def is_scope_bypassed() -> bool:
    return _tenant_scope_bypass.get()


def set_scope_bypass(value: bool):
    return _tenant_scope_bypass.set(value)
```

Keeping this file thin was a deliberate decision — it is imported from most of the backend, and the fewer indirections it has the easier it is to reason about. The ContextVar is the only piece of request-scoped state that crosses the async boundary, so making it obvious and dependency-free was worth it.

The event hook itself is about twenty-five lines in `app/database.py` and is the line of defence that turns the ContextVar into an actual filter:

```python
def _install_tenant_scope_hook():
    @event.listens_for(orm.Session, "do_orm_execute")
    def _filter_by_tenant(execute_state):
        if execute_state.is_select \
                and not execute_state.is_column_load \
                and not execute_state.is_relationship_load:
            if tenant_context.is_scope_bypassed():
                return
            tenant_id = tenant_context.get_current_tenant_id()
            if tenant_id is None:
                return
            for mapper in list(_iter_mapped_classes()):
                cls = mapper.class_
                if getattr(cls, "__tenant_root__", False):
                    continue
                if "tenant_id" in mapper.columns.keys():
                    execute_state.statement = execute_state.statement.options(
                        with_loader_criteria(
                            cls, cls.tenant_id == tenant_id, include_aliases=True
                        )
                    )
```

The three guards at the top — `is_select`, `not is_column_load`, `not is_relationship_load` — are there because the hook should only run on top-level SELECTs, not on relationship loads or column refreshes, otherwise SQLAlchemy tries to append the filter to subqueries it has already generated and the result is an unusable statement. I learned this the hard way during Phase 2 when my first version silently dropped rows from relationship joins.

The `__tenant_root__` check lets the `Tenant` model itself be queryable without the filter — without this, owner login would have nothing to look up because "find the tenant whose email matches" happens before the ContextVar has been set.

The FastAPI dependency that wires the JWT to the ContextVar is equally small. In `app/deps.py`, the `get_current_user` dependency decodes the access token, reads `tenant_id` out of the claims, and calls `tenant_context.set_current_tenant_id(tenant_id)` before the handler runs. Any query executed inside the handler — ORM or raw — is then automatically tenant-scoped.

The `bypass_tenant_scope()` context manager closes the last gap:

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def bypass_tenant_scope():
    token = tenant_context.set_scope_bypass(True)
    try:
        yield
    finally:
        tenant_context._tenant_scope_bypass.reset(token)
```

Admin list-all-tenants, the RQ training worker, and the nightly backup use this pattern. The `finally` block is important — if I wrote the reset inline after the `yield`, an exception inside the body would leak the bypass into the next request, which would be a quiet cross-tenant leak exactly of the kind the whole system exists to prevent.

The proof that the scheme works is a single test, `backend/tests/test_tenant_isolation.py`, which seeds two synthetic tenants, sets the ContextVar to tenant A, runs the owner-visible SELECTs, and asserts that none of tenant B's rows appear. It separately flips `bypass_tenant_scope()` on and asserts that both tenants' rows are visible. This test is the Rule-2 green gate and runs on every CI build.

[image/screenshot/figure 9] Figure 5.9: Screenshot of the passing `test_tenant_isolation` test — both "scoped" and "bypass" assertions green.

### 5.5.3 Advantages of the Approach

The real advantage is that tenant scoping is no longer my responsibility as a handler author. Every owner or cashier endpoint in `backend/app/routers/` is a straight-line function that queries the database without a single manual `tenant_id` filter. I cannot forget to apply the filter because it is not mine to apply. That is a qualitatively different security posture from "I try to remember every time."

The second advantage is that the scheme is portable. Uploads use the tenant id as a filesystem prefix (`uploads/<tenant_id>/...`), WebSocket clients are keyed by tenant in the in-process hub, and the Redis pub/sub channel carries the tenant id in the payload — so even paths outside the ORM carry the tenant identity through them. The database hook is the primary defence, but the filesystem and WebSocket layers are two more independent gates.

The weakness worth flagging is that the hook only covers SELECTs. Inserts and updates are implicitly tenant-safe because they operate on objects that were loaded under the scope in the first place, but a raw SQL `DELETE FROM menu_items WHERE id=...` executed by the handler would bypass the hook entirely. I mitigate this by forbidding raw SQL in handler code (all mutations go through the ORM) and by explicitly checking `tenant_id` in any scripting code that does use raw SQL. A stricter scheme would lean on Postgres row-level security policies to enforce the same rule at the database level — that is a fair Phase-14 direction, but for the FYP the ORM-level hook plus the integration test was the right amount of rigour.

---

## 5.6 Uniqueness of System 4: Billplz DuitNow QR Payment Flow

### 5.6.1 Development Approach

Payments are where the plan's "multi-tenant" claim becomes tangible. A naïve SaaS POS would route every shop's payments through the vendor's merchant account, deduct a cut, and settle to the shop weekly — which is convenient but also turns the SaaS operator into a regulated money handler, and reconciliation is a nightmare because one transaction flows through three accounts. GEYAM sidesteps this by making each shop bring their own Billplz API key, storing it encrypted in `tenant_settings`, and having the backend call Billplz with that tenant's credentials so money goes directly from the customer's bank to the shop's bank. The backend only sees a webhook callback confirming payment; no money transits through it.

Billplz was chosen over the other Malaysian DuitNow aggregators because its v3 API is well-documented, its sandbox is suitable for a student project, and its webhook signature scheme is a transparent HMAC-SHA256 that I can implement correctly in fifteen lines. I considered GHL and iPay88 but both require a sales call to get onboarded, which is the kind of friction that would have delayed the entire payments phase by weeks.

The core challenge is that Billplz's webhook scheme is sensitive to field ordering — the X-Signature is computed over a pipe-joined concatenation of specific fields in a fixed order, not over the raw body — and getting the scheme wrong silently accepts or silently rejects webhooks depending on the mismatch. I copied the canonical order from the official `jomweb/billplz` PHP library rather than inferring it, and the `required` vs `optional` field distinction also comes from there. This turned out to be the right call; when I tested with the Billplz sandbox's "resend webhook" tool, the signatures matched on the first attempt.

[image/screenshot/figure 10] Figure 5.10: Payment sequence — cart → create_bill → Billplz QR → customer scans in DuitNow app → webhook → backend verifies signature → transaction flips to paid.

### 5.6.2 Code Development

The Billplz client module is a deliberately small file, `backend/app/services/billplz.py`. The `create_bill` function posts to Billplz v3 with basic HTTP auth (the API key is the username, password empty, which is Billplz's v3 convention):

```python
SANDBOX_BASE = "https://www.billplz-sandbox.com/api/v3"
PRODUCTION_BASE = "https://www.billplz.com/api/v3"


def _base(mode: str) -> str:
    return PRODUCTION_BASE if mode == "production" else SANDBOX_BASE


def create_bill(*, mode, api_key, collection_id, name, email,
                amount_cents, description, callback_url, redirect_url,
                reference_1=None, reference_2=None):
    url = f"{_base(mode)}/bills"
    payload = {
        "collection_id": collection_id,
        "email": email,
        "name": name,
        "amount": amount_cents,
        "description": description,
        "callback_url": callback_url,
        "redirect_url": redirect_url,
    }
    if reference_1:
        payload["reference_1"] = str(reference_1)
    if reference_2:
        payload["reference_2"] = str(reference_2)
    r = httpx.post(url, auth=(api_key, ""), data=payload, timeout=15)
    r.raise_for_status()
    return r.json()
```

The `mode` parameter toggles between sandbox and production URLs from the same function. This matters because each tenant has their own `billplz_mode` field in `tenant_settings` — a shop can run sandbox while testing and flip to production once their Billplz account is live, and the backend routes them to the right base URL without a code change. Amounts are in cents because Billplz quotes in the smallest currency unit; the transaction service multiplies the decimal MYR total by 100 before the call.

The webhook signature verification is the security-critical piece, and it is worth showing in full:

```python
def verify_webhook_signature(*, xsign_key, form_fields, x_signature):
    """Billplz v3 webhook X-Signature:
    fixed field order, pipe-joined as key1val1|key2val2|...,
    HMAC-SHA256 with key as string.
    Required fields contribute even when missing (empty value);
    optional ones only if present."""
    webhook_order = [
        "amount", "collection_id", "due_at", "email", "id", "mobile", "name",
        "paid_amount", "paid_at", "paid", "state",
        "transaction_id", "transaction_status", "url",
    ]
    required = {
        "amount", "collection_id", "due_at", "email", "id", "mobile", "name",
        "paid_amount", "paid_at", "paid", "state", "url",
    }
    parts = []
    for attr in webhook_order:
        if attr in form_fields or attr in required:
            parts.append(f"{attr}{form_fields.get(attr, '')}")
    payload = "|".join(parts).encode()
    expected = hmac.new(xsign_key.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, x_signature)
```

Two implementation details are worth calling out. First, the comparison uses `hmac.compare_digest` rather than `==`, which is a timing-safe comparison that prevents an attacker from learning the signature one character at a time by measuring response-time differences. Second, required fields contribute to the payload even when they are empty strings in the form — this is the quirk I would have missed if I had not read the official library reference. Without that rule, a webhook for an unpaid bill (where `paid_at` is empty) would fail verification even though Billplz would happily accept it, and the real-world effect would be that half of all transactions would be rejected as "invalid signature" and never flip to paid.

The webhook handler itself (`routers/payment.py`) decrypts the tenant's `billplz_xsign_key` from `tenant_settings`, calls `verify_webhook_signature`, updates the `payments` row, flips `transactions.status` to `paid`, and enqueues the `process_receipt` RQ job. It always returns `{"status": "ok"}` to keep Billplz from retrying forever, even on signature failure — the audit log records the failure separately, and the escape hatch at `POST /transaction/{tx_id}/recheck-billplz` lets an owner manually reconcile from the Billplz side if a webhook really did get lost.

Credential storage uses Fernet symmetric encryption from `cryptography.fernet`, wrapped in a `crypto.py` helper that returns `None` when given `None`, so `tenant_settings.billplz_api_key` can be left empty on a fresh tenant without special-casing every read:

```python
from cryptography.fernet import Fernet

_FERNET = Fernet(os.environ["FERNET_KEY"].encode())


def encrypt_secret(plain: Optional[str]) -> Optional[str]:
    if plain is None or plain == "":
        return None
    return _FERNET.encrypt(plain.encode()).decode()


def decrypt_secret(token: Optional[str]) -> Optional[str]:
    if token is None or token == "":
        return None
    return _FERNET.decrypt(token.encode()).decode()
```

The Fernet key itself lives in `backend/.env` and is deliberately never committed — the `.env.example` file has `FERNET_KEY=<generate-your-own>` so a fresh checkout cannot accidentally share keys across deployments. This means the nightly `pg_dump` backup is only as sensitive as the Fernet key: even if the SQL dump leaked, the API keys in it would be opaque tokens.

[image/screenshot/figure 11] Figure 5.11: POS payment dialog showing the Billplz QR code; customer scans with their bank app.

### 5.6.3 Advantages of the Approach

The biggest advantage is that GEYAM is not a money handler. Each shop's Billplz account receives the funds directly — the backend only sees a webhook saying "bill 12345 is paid" and updates its own records. Reconciliation at the end of the day is unambiguous because the shop's bank statement matches the `payments` table one-to-one. For an FYP this dodges a large regulatory question about money-service-business licensing; for a real business this means the operator never has to explain to the tax office where a cent went.

The second advantage is that the sandbox/production toggle lives per tenant. A new shop can onboard, connect their Billplz sandbox credentials, run a few fake transactions end-to-end, and switch to production once they are satisfied, without any downtime and without me having to gate features behind a central flag. This is a much better developer experience than "we run the whole platform in sandbox until launch day" which was my first instinct.

The clearest risk is that a lost webhook leaves a transaction in `pending` forever. I mitigate this at three levels: the POS screen polls `GET /transactions/{tx_id}` every three seconds and catches the transition even without the webhook, the owner can trigger a manual reconciliation via `POST /transaction/{tx_id}/recheck-billplz`, and the auto-void scheduler closes unpaid transactions older than 24 hours so the ledger never grows indefinitely. Between these three safety nets, a lost webhook is an inconvenience rather than a data-integrity failure.

A deeper weakness is that Billplz is a single point of failure. If Billplz is down, no QR payments go through, and the cashier has no backup acquirer to fall back to. A production version of GEYAM would add a second QR provider behind the same `payments` abstraction — the `provider` column on `payments` is already there waiting for it — but for the FYP one acquirer is enough to prove the architecture.

---

## 5.7 System Requirement Implementation

This section maps each functional requirement from Chapter 3 to the module that implements it. The aim is to make the requirement-to-code trace easy for an examiner reading the report alongside the repository.

### 5.7.1 Requirement 1: Multi-Tenant Authentication (FR1)

The requirement is that each shop's owners and cashiers can authenticate into their own shop and only their own shop. Owners authenticate via Google OAuth (the `google_sign_in` Flutter package on the client, the `google_oauth.py` service on the backend), which offloads passwords and 2FA to Google. Cashiers authenticate with a six-digit PIN (bcrypt-hashed), and the PIN login endpoint requires the tenant handle in the request body so a cashier from shop A cannot log in to shop B even with a matching username. Both paths mint a JWT carrying `tenant_id`, `user_id`, and `role`; the JWT is then fed into the ContextVar-based tenant-scope hook described in section 5.5.

The five JWT types (access, refresh, signup, receipt, admin) are all signed with the same server-side HS256 secret, distinguished by their claims and lifetimes. Access tokens are 24 hours for owners and 12 hours for cashiers; the shorter cashier lifetime means a lost or stolen phone stops being a security risk by the next day's shift.

### 5.7.2 Requirement 2: Per-Tenant AI Food Detection (FR2)

Covered in detail in section 5.3. The training pipeline is `services/training.py` (the RQ job `run_batch`), the inference cascade is `services/detection/cascade.py`, the per-tenant LRU cache is `services/yolo_cache.py`, and the thresholds live on `tenant_settings`. The integration point is `POST /detect`, which calls the cascade and returns items with a `source` and `needs_confirm` flag.

### 5.7.3 Requirement 3: Multi-Tenant Payment Gateway (FR3)

Covered in detail in section 5.6. The Billplz client is `services/billplz.py`, the webhook handler is `routers/payment.py`, credentials are Fernet-encrypted in `tenant_settings`, and the recheck escape hatch is `POST /transaction/{tx_id}/recheck-billplz`. Receipts are rendered by `services/receipt_pdf.py` (ReportLab) and emailed via `services/resend_mailer.py` (Resend) as an attached PDF.

### 5.7.4 Requirement 4: Owner Dashboard with AI Q&A (FR4)

Covered in detail in section 5.4. The forecasting primitives are in `services/forecast.py`, the dashboard aggregation endpoint is `routers/dashboard.py`, the Ask GEYAM bubble posts to `POST /ask`, and the LLM client is `services/ollama_ask.py` against a host-side Ollama with `phi3:mini`. The dashboard renders gradient KPI cards, a revenue line chart via `fl_chart`, a top-items pie chart, a staff performance table, and the floating Ask GEYAM bubble on a single screen.

### 5.7.5 Requirement 5: Web and Mobile Single Codebase (FR5)

The Flutter client compiles to web (Hostinger-hosted at `geyam.com`) and Android (sideloaded APK) from the same codebase. `kIsWeb` gates web-only routes; a `ConstrainedBox(maxWidth: 1200)` in `main.dart` keeps the owner-facing web layout readable on desktop monitors without an awkward stretch; the `ApiService` singleton handles auth, offline-guarding, and error surfacing uniformly across platforms.

### 5.7.6 Requirement 6: Row-Level Multi-Tenant Isolation (FR6)

Covered in detail in section 5.5. The cooperating layers are `tenant_context.py` (ContextVar), `database.py` (event hook), the filesystem prefix under `uploads/<tenant_id>/`, and the WebSocket hub key. The green gate is `tests/test_tenant_isolation.py`, which runs on every CI build.

### 5.7.7 Requirement 7: Real-Time Notifications (FR7)

The `/ws?token=...` WebSocket endpoint accepts the access-token JWT in the query string, registers the socket in the in-process hub keyed by tenant, and fans out messages published on the `geyam:ws` Redis pub/sub channel. RQ workers and the scheduler call `ws_broker.publish_sync(tenant_id, message)` after training finishes, a transaction is paid, a transaction is auto-voided, or a low-confidence detection needs review. The Flutter `NotificationProvider` owns the WS connection, parses incoming JSON, and keeps the last 50 events for the notification bell.

---

## 5.8 Summary

This chapter walked through how GEYAM was built in practice, focusing on the four subsystems where the engineering risk and the academic contribution are concentrated: the per-tenant YOLO food-detection cascade, the locally-hosted LLM dashboard Q&A, the SQLAlchemy tenant-scope isolation hook, and the Billplz DuitNow QR payment flow with per-tenant credentials. The consistent pattern across all four is that complexity was pushed into one small, well-tested module and kept out of the handlers — so every router endpoint is a short, readable function, and every subsystem is a place an examiner can read in isolation without needing the whole repository in their head.

Looking back, the decision I would defend most strongly is the tenant-scope event hook. It changed my relationship with the codebase: I stopped worrying about forgetting a filter and started trusting that if a handler is wrong, it is wrong in a way the test suite can catch. The decision I would question most is keeping MediaPipe as a stub in the cascade — the wiring cost is paid, the benefit is zero until the alias table is built, and a reviewer would fairly ask why the slot is there if it is empty. My answer is that shipping the two-stage cascade cleanly was more valuable than shipping the three-stage cascade half-wired, but a stronger version of this project would close that loop.

Two open questions remain for me. The first is whether row-level security in Postgres would be a stronger isolation guarantee than the ORM-level hook — the hook is robust against any handler mistake but not against a direct `psql` session, and a production deployment should probably layer both. The second is whether `phi3:mini` is the right model size for the Ask GEYAM feature on the long run; it is adequate for the demo but I can see a path to a 7-billion-parameter model running on a slightly stronger machine giving noticeably better answers. Both questions belong to the next iteration, not this one, and neither changes the architecture described in this chapter.

The next chapter moves from "how it was built" to "how it was tested and evaluated" — covering the unit and integration test suite (including the Rule-2 tenant-isolation gate), the user testing plan, and the measured accuracy of the food-detection cascade against a small ground-truth set.
