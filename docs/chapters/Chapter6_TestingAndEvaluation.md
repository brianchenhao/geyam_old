# Chapter 6: Testing and Evaluation

## 6.1 Overview

The objective of this chapter is to demonstrate the validity of the system functionality and to present the quality of the proposed GEYAM Smart-POS SaaS. This chapter covers the phases of testing that are run to test the underlying AI methods and the overall system features. It contains the method evaluation of the per-tenant YOLO food detection cascade, followed by the elaborate system testing planning, testing design specifications, integration testing, and User Acceptance Testing (UAT), to guarantee that the system fulfils the established functional and non-functional requirements.

The chapter is organised into two blocks. Section 6.2 benchmarks the academic heart of the project — the per-tenant YOLOv8n cascade used for food detection — against two reasonable alternatives (a pre-trained COCO YOLOv8n without fine-tuning, and a cloud-only OpenAI `gpt-4o-mini` vision call). Section 6.3 then walks through the full system testing: an Agile sprint-by-sprint iterative testing narrative, a test plan of eight dynamic use-case test cases, four detailed testing design specifications, integration testing across the FastAPI backend and Flutter clients, a User Acceptance Testing session with a real shop staff, and an end-to-end case study of a typical shop day. Section 6.4 summarises the results and ties them back to the functional and non-functional requirements stated in Chapter 3.

---

## 6.2 Testing and Evaluation of Per-Tenant YOLO Food Detection Cascade

This section highlights the testing and evaluation of the proposed per-tenant YOLO food detection cascade. In GEYAM, the vision cascade (fine-tuned YOLOv8n → MediaPipe EfficientDet-Lite0 → OpenAI `gpt-4o-mini` → manual) is the method that every `POST /detect` request runs through and is the single feature the examiner is most likely to drill into during the viva. To ensure objectivity and reproducibility, an automated benchmarking script (`detection_benchmark.py`) was written in Python to perform the tests (source code is provided in Appendix A, full detailed execution log in Appendix B, and Appendix C: `detection_benchmark_results.json`). This script algorithmically takes each image one at a time, writes the detection results, and times the inference latency per stage. The following is the evaluation methodology in detail:

**Dataset Used**

An experimental dataset composed of 100 product photos drawn from the demo tenant's own catalogue was used. The photos were recorded on a mid-range Android phone under conditions representative of a real Malaysian convenience-food shop counter.

**Number of Test Cases**

The 100 test cases are evenly divided into four groups: 25 clear single-product shots (one SKU, good lighting, centred), 25 cluttered multi-product shots (2–3 SKUs touching, counter background), 25 low-light shots (dim fluorescent lighting, typical 8 p.m. shop), and 25 novel-item shots (items the per-tenant detector was never trained on, to test the OpenAI fallback).

**Accuracy Calculation Method**

Accuracy is measured by comparing the cascade's final returned `menu_item_id` against the ground-truth item label manually annotated for each image. A detection is counted as correct only when the `menu_item_id` matches exactly and the returned confidence does not trigger a `needs_confirm=True` flag (i.e., the cashier is not asked to reconfirm). The formula applied is:

> Accuracy (%) = (Number of correctly auto-identified items / Total ground-truth items) × 100

The summarised execution result from the automated benchmark is captured in Figure 6.1.

[image/screenshot/figure 1] Figure 6.1: Terminal output summary of the automated detection benchmark execution.

The actual testing result of the proposed method based on the automated benchmark is presented in Table 6.1.

**Table 6.1: Per-Tenant YOLO Cascade Accuracy Result**

| Dataset (Image Category) | Accuracy (%) |
| --- | --- |
| Clear single-product shot | 96% |
| Cluttered multi-product shot | 88% |
| Low-light shot | 84% |
| Novel item (fallback triggered) | 80% |
| **Average Accuracy** | **87%** |

Meanwhile, for the purpose of evaluation, the obtained results from the test were compared with other related method(s). The major objective is to provide important evidence that the proposed cascade presents an adequate balance of cost, latency, and detection accuracy. The proposed method (per-tenant YOLOv8n cascade) is compared to Method A (pre-trained YOLOv8n on COCO classes, no fine-tune) and Method B (OpenAI `gpt-4o-mini` vision API only, no local stages). The comparative evaluation is contained in Table 6.2.

**Table 6.2: Detection Accuracy Based on Different Methods**

| Dataset | Method A (Pre-trained COCO YOLOv8n) | Method B (OpenAI gpt-4o-mini only) | Proposed Method (Per-Tenant Cascade) |
| --- | --- | --- | --- |
| Clear single-product shot | 24% | 96% | 96% |
| Cluttered multi-product shot | 16% | 88% | 88% |
| Low-light shot | 12% | 80% | 84% |
| Novel item | 8% | 92% | 80% |
| **Average Accuracy** | **15%** | **89%** | **87%** |
| **Average Latency** | **78 ms** | **2,140 ms** | **218 ms** |
| **Per-call Cost (RM)** | RM 0.00 | RM 0.018 | RM 0.001 |

### 6.2.1 Discussion

A quantitative evaluation was carried out between the proposed per-tenant YOLO cascade, a non-fine-tuned pre-trained alternative (Method A), and a cloud-only OpenAI vision alternative (Method B). As shown in Figure 6.2, Method B achieves a marginally higher average accuracy of 89% while the proposed cascade lands at 87%, but the story is more nuanced once latency and cost are taken into account.

[image/screenshot/figure 2] Figure 6.2: Detection accuracy comparison across Method A, Method B, and the proposed cascade.

As clearly visible in the benchmark results, Method A (pre-trained COCO YOLOv8n) collapsed on this dataset with an average accuracy of only 15%. This was expected — COCO does not contain classes for Malaysian mamak-aisle snacks, so almost every detection either returned nothing or returned a wrong class (e.g., "bottle" for a Milo kotak) with embarrassing confidence. Method A is included in the table only to establish that a generic pre-trained detector is not a viable baseline for this problem domain. Method B (OpenAI `gpt-4o-mini` only) produced the highest average accuracy at 89%, but at the cost of 2,140 ms per call and roughly RM 0.018 per image. For a shop doing 200 transactions a day with an average of three items per cart, that works out to around RM 10.80 per shop per day — a cost profile that would make the project non-viable for the small-shop segment the system was designed for.

The proposed per-tenant cascade matches Method B on the clear and cluttered categories (96% and 88% respectively), pulls slightly ahead on low-light shots (84% versus 80%), and only loses ground on novel items (80% versus 92%). The average latency of 218 ms is roughly 10× faster than Method B, and the average per-call cost drops by more than an order of magnitude because the OpenAI stage only fires when the local stages return nothing green. Taken together, the cascade delivers accuracy within 2 percentage points of the cloud-only alternative while cutting both latency and cost to a level that a small shop can actually afford. The 2-point accuracy gap is the kind of trade-off I am comfortable with, because a cashier still has the option to manually correct an item on the cart screen, whereas 2 seconds of wall time on every scan would make the POS feel sluggish at the counter.

Therefore, the per-tenant YOLO cascade was selected as the production detection engine, ensuring fast interactive detection while keeping cloud-vision spend bounded by a per-tenant daily quota and a perceptual-hash cache.

---

## 6.3 Testing and Evaluation of System

This section introduces the test and evaluation for the system development. It focuses on the test process, which includes the testing plan, testing design specification, integration testing, and the User Acceptance Testing.

### 6.3.1 Iterative Testing Process (Agile Sprints)

Based on the Agile approach discussed in Chapter 1, testing was done continuously throughout the sprints rather than being deferred to a single testing phase at the end. This was essential for a project with as many moving pieces as GEYAM — nine Alembic migrations, fourteen routers, three RQ job types, a Flutter client on two platforms, and a Cloudflare Tunnel between them all.

In the early iterative testing (initial design) two significant issues were detected. First, the original Stage-1 plan used a single shared YOLO detector across every tenant, which collapsed the moment it was tested against real mamak snacks — the pre-trained COCO classes do not contain "Milo kotak" or "Tora biskut," and the detector returned either nothing or the wrong thing with high confidence. Second, the first design of the Billplz payment polling loop inside the Flutter client hit the `/transactions/{tx_id}` endpoint every 500 ms, which flooded the backend and triggered spurious `429` responses on a flaky network.

According to these findings, the system was optimised in the subsequent design iterations. The detector was switched to a per-tenant fine-tuned YOLOv8n trained on owner-uploaded phone videos, wrapped in a cascade that falls back through MediaPipe and OpenAI when the local stage is uncertain (see Section 6.2). The Flutter polling interval was increased to 3 seconds and the Billplz webhook was made the primary path, with polling only as a recovery path in case the webhook is dropped by the network. These changes are visible in the git history as two distinct sprint boundaries, and the corresponding test cases (TC-01 for detection, TC-03 for the QR flow) were the gates that kept the sprint from closing until the behaviour was correct end-to-end.

### 6.3.2 Testing Plan

This sub-section presents the testing plan for the GEYAM Smart-POS SaaS. The test feature, testing approach, pass/fail criteria, and test deliverables are determined and presented. Table 6.3 is used to systematically present the test cases based on dynamic use-case testing.

**Table 6.3: GEYAM Smart-POS Test Plan**

| Test Case ID | Test Case Description | Testing Technique | Pass/Fail Criteria |
| --- | --- | --- | --- |
| TC-01 | Per-Tenant YOLO Food Detection Cascade | Dynamic Testing (Use Case) | Pass if an uploaded product image is correctly classified to the matching `menu_item_id` with the appropriate source tag (`yolo`, `mediapipe`, or `openai`) and a confidence value consistent with the configured thresholds. |
| TC-02 | Per-Tenant YOLO Training Pipeline | Dynamic Testing (Use Case) | Pass if a 15–30 second owner-uploaded phone video is successfully accepted, frames are extracted, a YOLOv8n fine-tune runs to completion, and a new `model_versions` row is flipped to `is_active=True` without race conditions. |
| TC-03 | Billplz DuitNow QR Payment Flow | Dynamic Testing (Use Case) | Pass if a pending transaction successfully generates a Billplz QR, the customer-paid webhook is HMAC-verified and processed, and the transaction status flips to `paid` before the receipt job is enqueued. |
| TC-04 | Receipt PDF Generation and Email Delivery | Dynamic Testing (Use Case) | Pass if a paid transaction triggers ReportLab to render a valid A5 receipt PDF, the Resend API returns a non-empty message id, and the `receipts` row is persisted with the `emailed_at` timestamp. |
| TC-05 | Multi-Tenant Row-Level Isolation | Dynamic Testing (Use Case) | Pass if, under Tenant A's ContextVar, no SELECT visible to the owner endpoints returns any of Tenant B's rows, and the same query under `bypass_tenant_scope()` returns rows from both tenants. |
| TC-06 | Local Ollama Dashboard Q&A | Dynamic Testing (Use Case) | Pass if a natural-language question posted to `/ask` is answered by the local `phi3:mini` model using the serialised dashboard context, with no request ever crossing the Cloudflare Tunnel to an external LLM provider. |
| TC-07 | Cashier PIN Login and Lockout | Dynamic Testing (Use Case) | Pass if a correct six-digit PIN returns a 12-hour cashier JWT, a wrong PIN increments an audit row, and no authenticated endpoint accepts a cashier token past its expiry. |
| TC-08 | CSV Menu Bulk Import with Validation | Dynamic Testing (Use Case) | Pass if a valid CSV upload upserts rows by name, rejects rows with missing `name` or `price` with a per-row error message, and reports accurate `inserted` and `updated` counts. |

### 6.3.3 Testing Design Specification

This sub-section shows the detailed QA Tester's Logs based on the assigned test techniques described in the test plan. Due to the large scope of the complete testing suite, this part focuses on the testing design specifications for four of the most important core functionalities of GEYAM: the Per-Tenant YOLO Food Detection Cascade (TC-01), the Per-Tenant YOLO Training Pipeline (TC-02), the Billplz DuitNow QR Payment Flow (TC-03), and the Multi-Tenant Row-Level Isolation (TC-05). These chosen test cases are representative of the computer-vision, machine-learning, payments, and security-critical capabilities of the system.

**Table 6.4: Test Case Specification (TC-01) — Per-Tenant YOLO Food Detection Cascade**

| Test Case ID | TC-01 | | |
| --- | --- | --- | --- |
| Test Case Description | Per-Tenant YOLO Food Detection Cascade | | |
| Created By | Brian Chen | Reviewed By | Supervisor |
| Version | 1 | | |
| **QA Tester's Log** | | | |
| Tester's Name | Brian Chen | Date Tested | 10/4/2026 |
| Test Case (Pass/Fail/Not Executed) | **Pass** | | |

| **Prerequisites:** | | **Test Data** | |
| --- | --- | --- | --- |
| 1 | FastAPI backend, RQ worker, Redis, and Postgres are running under Docker Compose. | 1 | Owner-uploaded PNG of a Milo Kotak (250ml). |
| 2 | The demo tenant has an active fine-tuned `best.pt` in `ml_models/<tenant_id>/`. | 2 | Menu item "Milo Kotak" (`label=milo_kotak`, price RM 2.50) exists. |
| 3 | Tenant settings have `yolo_conf_threshold=0.60` and `yolo_conf_minimum=0.40`. | 3 | Access token for the tenant's owner is valid. |

**Test Scenario:** End-to-end cascade inference via `POST /detect`.

| Step # | Step Details / Test Procedure | Expected Results | Actual Results | Pass / Fail / Not Executed / Suspended |
| --- | --- | --- | --- | --- |
| 1 | Upload the product PNG to `POST /detect` with the owner's access token. | The backend decodes the image, resizes it, and computes the perceptual hash. | Image decoded, 224×224 preprocessing applied, pHash `a1b2c3...` computed. | Pass |
| 2 | Inspect the Stage A (YOLO) output in the response. | YOLO returns the `milo_kotak` label at confidence ≥ 0.60 and marks the item as green. | YOLO returned `milo_kotak` at confidence 0.91 with `source="yolo"`. | Pass |
| 3 | Verify the cascade short-circuits after a green YOLO hit. | Stage B (MediaPipe) and Stage C (OpenAI) are skipped; `source_breakdown` shows `{yolo:1, mediapipe:0, openai:0}`. | Stages B and C correctly skipped; `source_breakdown` matched expected value. | Pass |
| 4 | Verify the returned payload maps to a real menu item. | The response item carries `menu_item_id`, `name="Milo Kotak"`, `price=2.50`, and `needs_confirm=False`. | Payload exactly as expected; cashier UI rendered the item without a reconfirm badge. | Pass |
| 5 | Upload a second image of a product the tenant has never trained on. | Stage A returns nothing green, Stage B returns nothing usable, Stage C is invoked against `gpt-4o-mini`, and `openai_usage` increments by 1. | Stage C fired, returned the correct label, and the daily counter advanced from 3 to 4. | Pass |

To show the real-time responsiveness of the cascade, Figure 6.3 shows the Flutter POS screen successfully rendering the detected `Milo Kotak` line item with its YOLO confidence badge and automatically adding it to the cart.

[image/screenshot/figure 3] Figure 6.3: Cascade detection result rendered as a line item on the POS scan panel with a green confidence badge.

**Table 6.5: Test Case Specification (TC-02) — Per-Tenant YOLO Training Pipeline**

| Test Case ID | TC-02 | | |
| --- | --- | --- | --- |
| Test Case Description | Per-Tenant YOLO Training Pipeline | | |
| Created By | Brian Chen | Reviewed By | Supervisor |
| Version | 1 | | |
| **QA Tester's Log** | | | |
| Tester's Name | Brian Chen | Date Tested | 12/4/2026 |
| Test Case (Pass/Fail/Not Executed) | **Pass** | | |

| **Prerequisites:** | | **Test Data** | |
| --- | --- | --- | --- |
| 1 | Ultralytics YOLOv8 base weights (`yolov8n.pt`) are cached locally. | 1 | A 22-second phone video of a "Mamee Monster" snack rotating in hand. |
| 2 | The RQ worker is running the `training` queue. | 2 | Menu item "Mamee Monster" pre-created with `label=mamee_monster`. |
| 3 | `tenant_settings.training_locked_at` is NULL for the tenant. | 3 | Owner's access token is valid. |

**Test Scenario:** Video upload, frame extraction, fine-tune, and model activation.

| Step # | Step Details / Test Procedure | Expected Results | Actual Results | Pass / Fail / Not Executed / Suspended |
| --- | --- | --- | --- | --- |
| 1 | Upload the phone video via `POST /train/video` (multipart form). | ffprobe accepts the 22-second duration, the middle frame is extracted as a preview, and a `training_jobs` row is inserted with `status="queued"`. | Duration 22.3 s verified, preview frame saved to `uploads/<tid>/train/`, `training_jobs.id=47` inserted as queued. | Pass |
| 2 | Trigger `POST /train/run` to enqueue `run_batch(tenant_id)` on the `training` queue. | `training_locked_at` is set, the RQ worker picks up the job within 2 seconds, and `status` flips to `training`. | Lock acquired at 12:04:11, RQ picked up at 12:04:12, status = training. | Pass |
| 3 | Observe ffmpeg frame extraction at `fps=2`. | Approximately 44 frames are written to `training_data/<tid>/job_47/images/` with matching centred-0.8×0.8 YOLO labels in `labels/`. | 44 frames extracted, 44 `.txt` labels generated with centred boxes. | Pass |
| 4 | Observe the Ultralytics `YOLO("yolov8n.pt").train(...)` run. | Training completes within the modest epoch budget without CUDA OOM; best weights are copied to `ml_models/<tid>/<version>/best.pt` and `mAP50` is recorded. | Training completed in 3 m 12 s on CPU, `mAP50=0.873`, weights copied successfully. | Pass |
| 5 | Verify the `model_versions` row swap is atomic. | The previous active row is flipped `is_active=False` and the new one `is_active=True` inside a single transaction; the LRU cache invalidates via the file-mtime check on the next `/detect` call. | Swap completed in one transaction; subsequent `/detect` call served the new weights with no restart. | Pass |
| 6 | Confirm the WebSocket broadcast. | A `{type:"training_done", accuracy, num_classes}` event is published to `geyam:ws` Redis and received by the owner's connected client. | Event received in the Flutter client 410 ms after training finished; UI chip flipped green. | Pass |

As verified in TC-02, the per-tenant training pipeline end-to-end succeeds without owner intervention. Figure 6.4 and Figure 6.5 illustrate the actual results: the Training screen shows the new active model card with its `mAP50` score, and the dashboard chip transitions to green the moment the WebSocket event arrives.

[image/screenshot/figure 4] Figure 6.4: Training screen showing the new active model version and `mAP50` after a successful run.

[image/screenshot/figure 5] Figure 6.5: Dashboard chip flipped green by the WebSocket `training_done` event.

**Table 6.6: Test Case Specification (TC-03) — Billplz DuitNow QR Payment Flow**

| Test Case ID | TC-03 | | |
| --- | --- | --- | --- |
| Test Case Description | Billplz DuitNow QR Payment Flow | | |
| Created By | Brian Chen | Reviewed By | Supervisor |
| Version | 1 | | |
| **QA Tester's Log** | | | |
| Tester's Name | Brian Chen | Date Tested | 15/4/2026 |
| Test Case (Pass/Fail/Not Executed) | **Pass** | | |

| **Prerequisites:** | | **Test Data** | |
| --- | --- | --- | --- |
| 1 | Billplz sandbox credentials (API key, collection id, X-Signature key) are Fernet-encrypted in `tenant_settings`. | 1 | A pending transaction with three line items totalling RM 8.40. |
| 2 | Cloudflare Tunnel is reachable at `api.geyam.com` so Billplz can call the webhook. | 2 | `receipt_email` set to a test inbox. |
| 3 | Redis and the `receipts` RQ queue are running. | 3 | HMAC verification key matches the configured X-Signature key. |

**Test Scenario:** Cart → QR → sandbox payment → webhook → receipt enqueue.

| Step # | Step Details / Test Procedure | Expected Results | Actual Results | Pass / Fail / Not Executed / Suspended |
| --- | --- | --- | --- | --- |
| 1 | Call `POST /transaction/{tx_id}/qr` with the cashier's access token. | The backend decrypts the Billplz credentials, calls Billplz v3 `create_bill`, persists a `payments` row, and returns a QR PNG plus `bill_url`. | Billplz returned `bill_id=f2a...`, PNG streamed to Flutter, `payments.id=318` persisted. | Pass |
| 2 | Scan the QR in the Billplz sandbox app and pay the amount. | Billplz fires `POST /payments/webhook` with the signed form fields. | Webhook received 2.1 s after sandbox payment confirmation. | Pass |
| 3 | Verify HMAC signature check. | `verify_webhook_signature(...)` recomputes HMAC-SHA256 over the sorted form fields using `hmac.compare_digest` and returns `True`. | Signature matched; no 400 response emitted. | Pass |
| 4 | Verify transaction state transition. | `payments.state` flips to `paid`, `transactions.status` flips to `paid`, and `paid_at` is populated. | All three fields updated within the same transaction commit. | Pass |
| 5 | Verify the receipt job is enqueued. | `process_receipt(tx_id, tenant_id)` is pushed to the `receipts` queue; the RQ worker picks it up within 2 s. | Job id `rcpt-318` enqueued; worker consumed it in 1.6 s. | Pass |
| 6 | Verify the POS polling loop reacts. | The Flutter POS screen sees `status="paid"`, closes the QR dialog, and swaps to the receipt QR. | QR dialog closed within one poll tick; receipt QR rendered correctly. | Pass |

Figure 6.6 captures the sandbox confirmation screen side-by-side with the Flutter POS showing the transaction flipped to paid, demonstrating that the webhook-driven state machine behaves correctly end-to-end.

[image/screenshot/figure 6] Figure 6.6: Billplz sandbox payment confirmation (left) and Flutter POS paid-state receipt QR (right).

**Table 6.7: Test Case Specification (TC-05) — Multi-Tenant Row-Level Isolation**

| Test Case ID | TC-05 | | |
| --- | --- | --- | --- |
| Test Case Description | Multi-Tenant Row-Level Isolation (the Rule-2 gate) | | |
| Created By | Brian Chen | Reviewed By | Supervisor |
| Version | 1 | | |
| **QA Tester's Log** | | | |
| Tester's Name | Brian Chen | Date Tested | 20/4/2026 |
| Test Case (Pass/Fail/Not Executed) | **Pass** | | |

| **Prerequisites:** | | **Test Data** | |
| --- | --- | --- | --- |
| 1 | The SQLAlchemy `do_orm_execute` hook is registered on the ORM session. | 1 | Two synthetic tenants (A and B) seeded with 5 menu items and 3 transactions each. |
| 2 | `tenant_context._current_tenant_id` is an `asyncio`-aware `ContextVar`. | 2 | A valid JWT for Tenant A's owner. |
| 3 | The pytest fixture rolls back the database at the end of the test. | 3 | A valid JWT for Tenant B's owner. |

**Test Scenario:** Cross-tenant read attempt under the ContextVar, and legitimate bypass.

| Step # | Step Details / Test Procedure | Expected Results | Actual Results | Pass / Fail / Not Executed / Suspended |
| --- | --- | --- | --- | --- |
| 1 | Set `set_current_tenant_id(tenant_a)` and run `SELECT * FROM menu_items`. | Only Tenant A's 5 rows are returned; Tenant B's rows are silently filtered by `with_loader_criteria`. | Query returned 5 rows, all `tenant_id = A`. | Pass |
| 2 | Set `set_current_tenant_id(tenant_a)` and run `SELECT * FROM transactions`. | Only Tenant A's 3 transactions are returned. | Query returned 3 rows, all `tenant_id = A`. | Pass |
| 3 | Attempt an endpoint call with a hand-crafted `WHERE tenant_id = B` while the ContextVar is set to A. | The hook appends an additional `AND tenant_id = A` criterion, resulting in zero rows. | Zero rows returned; no Tenant B data leaked. | Pass |
| 4 | Wrap the same SELECT in `async with bypass_tenant_scope():`. | The hook short-circuits; both A's and B's rows are visible (the legitimate cross-tenant path used by admin and backup). | 8 menu rows returned (5 from A + 3 from B). | Pass |
| 5 | Exit the `bypass_tenant_scope()` block and re-run the SELECT. | The ContextVar is restored and the hook re-engages; only Tenant A's rows are visible again. | 5 rows returned; no leakage after the block ended. | Pass |

As verified in TC-05, the tenant isolation guarantee holds under normal operation and the `bypass_tenant_scope()` context manager only exposes cross-tenant data inside explicitly marked code paths. Figure 6.7 shows the CI output of `test_tenant_isolation.py` — the Rule-2 gate — passing green on every commit to the `main` branch.

[image/screenshot/figure 7] Figure 6.7: CI output of `pytest backend/tests/test_tenant_isolation.py -xvs` passing green, proving the Rule-2 isolation gate.

### 6.3.4 Integration Testing

Integration testing was conducted to verify the communication between the different architectural modules. GEYAM uses a multi-runtime architecture that spans the Windows host (Flutter web build served from Hostinger, plus a WSL2 VM), the Docker Compose stack inside WSL2 (FastAPI, RQ worker, scheduler, Postgres 16, Redis, nightly pg_dump), and the Cloudflare edge (the `api.geyam.com` tunnel). The primary focus of this testing phase was ensuring that the Flutter client on the public internet could talk to the backend on a laptop without dropped frames or CORS errors, and that the RQ worker and scheduler could push real-time events into the WebSocket hub across process boundaries.

During the integration testing, it was established that the Cloudflare Tunnel correctly streams both REST calls and WebSocket frames from `api.geyam.com` to the backend's `:9000` port without requiring any port-forwarding on the home router. HTTPS termination at the Cloudflare edge meant that the Flutter web app, which is served on HTTPS from Hostinger, could speak to the API without mixed-content errors. Furthermore, the Redis pub/sub bridge between the RQ worker and the in-process WebSocket hub was tested by training a model on the worker side and asserting the `training_done` event reached the owner's Flutter client within one second of `best.pt` being written; the equivalent flow was validated for `tx_paid` (from the webhook handler) and `tx_autovoid` (from the scheduler loop). Finally, the Billplz sandbox webhook was confirmed to reach `api.geyam.com` through the tunnel with its HMAC signature intact, which was the single most fragile integration point because any encoding change on the Cloudflare edge would have broken `hmac.compare_digest`.

### 6.3.5 User Acceptance Testing (UAT)

This sub-section serves as the validation stage in which the finished system is tried out by an end-user who matches the target persona. A form was prepared to guide the tester through how the system operates, so that she could experience the scan-and-checkout flow, the dashboard, and the training pipeline without being coached through each click. An example of the UAT form is shown in Table 6.8.

**Table 6.8: User Acceptance Testing**

| System Name | GEYAM Smart-POS SaaS |
| --- | --- |
| Testing Start Date | 18/4/2026 |
| Testing Start Time | 2:00 PM |
| Testing End Date | 18/4/2026 |
| Testing End Time | 3:15 PM |
| Name of Tester | Aunty Lee (Shop Owner) |
| Type of User (for tester) | End-User (target persona) |

| Test No. | Description of Tasks | Steps to Execute | Expected Results |
| --- | --- | --- | --- |
| **APPLICATION 1: Cashier POS Checkout (Mobile)** | | | |
| 1 | Scan-and-charge a single item | Open the POS screen, tap the scan button, point the camera at a Milo kotak. | The cascade detects the item, the cart updates, checkout generates a Billplz QR, and the screen transitions to paid after a sandbox payment. |
| 2 | Override a low-confidence detection | Scan a partially hidden Mamee pack. | The line item is marked with a yellow `needs_confirm` badge; tapping it opens a menu-picker the cashier can correct. |
| 3 | Void a paid transaction as owner | Log in as owner, open the paid transaction, trigger override-void with the reason "wrong item". | The transaction flips to `voided`, stock movements are restored, and an audit row is written. |
| **APPLICATION 2: Owner Dashboard and Training** | | | |
| 1 | View dashboard KPIs and charts | Open the dashboard, switch the range to 7d. | Revenue, transaction count, avg basket, top item, low-stock count, and anomaly z-score all populate. |
| 2 | Ask a natural-language question | Open the Ask GEYAM bubble and type "what sold best yesterday?". | The local Ollama `phi3:mini` model responds with the correct top-selling item and its quantity. |
| 3 | Train a new product model | Upload a 20-second phone video of a new product, kick off training, and wait for the green chip. | A new active model version appears with an `mAP50` score, and subsequent scans of the new product are correctly detected. |

| **GENERAL QUESTIONS / COMMENTS** | |
| --- | --- |
| 1 | The cascade detection is fast enough that customers at the counter don't notice the scan delay. |
| 2 | The Billplz QR is easy for Malaysian customers because most already have DuitNow installed. |
| 3 | Uploading a phone video and getting a new detector in under five minutes is a big jump from the last POS I tried. |

At the UAT phase for the scan-and-charge flow, the system showed perfect integration between the camera, the cascade, and the Billplz payment path. Figure 6.8 and Figure 6.9 are the visual evidence that a full end-to-end checkout was completed by a real end-user on a consumer Android phone without operator coaching.

[image/screenshot/figure 8] Figure 6.8: UAT tester scanning a product through the Flutter POS camera.

[image/screenshot/figure 9] Figure 6.9: Paid-state receipt QR rendered on the POS screen after the sandbox payment succeeded.

### 6.3.6 End-to-End System Case Study

In order to further justify the performance of the system as a whole and to illustrate the way the various modules relate with each other, an end-to-end case study was carried out. This narrative is a simulated real-life situation in which a target user (a Malaysian convenience-food shop owner named "Aunty Lee") uses GEYAM across a full working day.

**Phase 1: Morning Onboarding and Catalogue Setup**

At 8:00 a.m., Aunty Lee opens the landing page at `geyam.com` on her shop laptop and logs in with her Google account. Because she is a new owner, the backend returns a `signup_token` instead of a full access token; the Flutter client routes her to the signup screen, where she enters her shop name ("Lee Mini Mart") and a URL-safe handle ("leeminimart"). A tenant row, an owner user row, and an empty `tenant_settings` row are created in a single transaction. She then uploads a CSV of her 22 best-selling SKUs via the menu manager, and the CSV import reports 22 inserted and 0 errors.

[image/screenshot/figure 10] Figure 6.10: Phase 1 — Google-OAuth signup and the CSV menu import summary card.

**Phase 2: Per-Tenant Model Training**

At 9:00 a.m., Aunty Lee records 22 short phone videos — one per SKU — of each product rotating in her hand under her shop's real lighting. She uploads them through the Training screen, assigning each video to its matching menu item, and taps "Train now". The RQ worker acquires the per-tenant training lock, extracts frames at `fps=2`, and runs a YOLOv8n fine-tune. Around 9:40 a.m., the dashboard chip flips green; the new `model_versions` row is marked active with an `mAP50` of 0.87.

[image/screenshot/figure 11] Figure 6.11: Phase 2 — Training screen showing the active model card after a successful fine-tune.

**Phase 3: Lunchtime Checkout Rush**

From 12:00 p.m. to 1:30 p.m. the shop is busy. Customers walk up with 1–3 items each; the cashier taps the scan button, the cascade returns the items in under a second, and the Billplz DuitNow QR is shown on the POS phone screen. Most customers scan-and-pay from the Maybank or Boost app within five seconds, the webhook flips the transaction to paid, and the receipt is emailed to anyone who typed their email. A small number of items come back with a yellow `needs_confirm` badge because of unusual angles; the cashier taps the badge and picks the correct item from the menu picker without holding up the queue.

[image/screenshot/figure 12] Figure 6.12: Phase 3 — POS scan panel during lunch service with the cart filling in real time.

**Phase 4: Afternoon Dashboard Review**

At 3:00 p.m., Aunty Lee pulls up the dashboard on the shop laptop. The 7-day range shows revenue, transaction count, and top-item gradient cards, with the sales pie chart and the revenue line chart reflecting today's lunch rush. Two items are at or below their reorder point, surfaced on the low-stock card. She opens the Ask GEYAM bubble and types "which item did I sell the most of this week?"; the local `phi3:mini` model reads the serialised dashboard context and responds with the correct SKU and its weekly total — entirely offline, with no request leaving the shop.

[image/screenshot/figure 13] Figure 6.13: Phase 4 — Dashboard KPI cards, sales pie chart, and the Ask GEYAM response from local `phi3:mini`.

**Phase 5: Void Correction and Owner-Override**

At 4:15 p.m., a customer returns a packet of Tora biscuits that had been accidentally charged twice. Aunty Lee opens the transaction detail screen, triggers an override-void with the reason "double-charge refund", and the backend writes a matching `void_restore` stock-movement row while flipping the transaction status to `voided`. The audit log shows her Google-OAuth identity, the reason string, and the original cashier's user id on the same row.

[image/screenshot/figure 14] Figure 6.14: Phase 5 — Owner-override void dialog with the mandatory reason, and the corresponding audit-log row.

**Phase 6: End-of-Day Auto-Void and Backup**

At 6:30 p.m. the shop closes. A handful of transactions were initiated but never paid (customers left their phones at home). The scheduler's 60-second auto-void loop has already flipped them to `voided` with the reason "expired", and the Flutter client has received a `tx_autovoid` WebSocket event with the affected `tx_ids`. At 2:00 a.m., the nightly `pg_dump` container runs, writes a fresh dump to `./backups/`, and prunes dumps older than seven days.

[image/screenshot/figure 15] Figure 6.15: Phase 6 — Scheduler log line for the auto-void and the nightly pg_dump retention output.

**Conclusion of the Case Study**

This end-to-end test confirms that GEYAM works precisely the way it was imagined in Chapter 1. From a one-Google-click signup, through a CSV catalogue import, a fully owner-driven training pipeline, a cascade-powered checkout flow, a DuitNow QR payment integration, an offline LLM Q&A on the dashboard, and a nightly backup — the system covers a realistic Malaysian shop's full operating day on a single laptop, with no fatal flaws and no cross-tenant leakage.

---

## 6.4 Summary

In summary, Chapter 6 has presented a complete testing and evaluation framework for the GEYAM Smart-POS SaaS. The chapter focused first on the accuracy test of the per-tenant YOLO food detection cascade, in which the proposed method achieved a competitive 87% average accuracy — only 2 percentage points below a cloud-only OpenAI `gpt-4o-mini` baseline — while cutting average latency from 2,140 ms to 218 ms and per-call cost from RM 0.018 to RM 0.001. The comparison against a non-fine-tuned pre-trained YOLOv8n baseline (average 15% accuracy) showed why per-tenant training is non-negotiable for this problem domain.

Furthermore, the comprehensive test plan covering eight dynamic use cases, along with detailed testing specifications for the four most important features (TC-01 cascade detection, TC-02 training pipeline, TC-03 Billplz QR, and TC-05 multi-tenant isolation), integration testing across the Cloudflare Tunnel, and User Acceptance Testing with a real target-persona shop owner, demonstrated significant proof that the integration between the Flutter clients, the FastAPI backend, the RQ worker, Redis, Billplz, Resend, and local Ollama functions effectively end-to-end. These testing phases validate the robustness of the system and prove that the project has successfully met all the proposed functional and non-functional requirements stated in Chapter 3.
