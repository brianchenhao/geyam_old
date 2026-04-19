# GEYAM — Smart POS for Packaged Food

## What This System Does

A POS system for selling **packaged food only** (canned drinks, snack packets, boxed items — anything with a fixed price). The system starts empty. The manager teaches it new products by filming a short video of the item. Over time it learns the full inventory.

---

## Architecture

```
                         ┌──────────────────────────┐
                         │  geyam.com (Hostinger)   │
                         │  Serves Flutter Web       │
                         │  (static HTML/JS/CSS)     │
                         │  HTTPS via Cloudflare     │
                         └────────────┬─────────────┘
                                      │
              Users visit geyam.com   │   API calls go to your laptop
              get the frontend        │   via Cloudflare Tunnel
                                      │
┌──────────────────┐                  │
│  Flutter Mobile   │                  │
│  (Cashier/Staff)  │                  │
│  Camera → send    │                  │
│  image to server  │                  │
└────────┬──────────┘                  │
         │ REST                        │
         └───────────┬─────────────────┘
                     ▼
     ┌──────────────────────────────────────┐
     │  YOUR LAPTOP (the real server)       │
     │                                      │
     │  ┌──────────────┐  ┌──────────────┐  │
     │  │  FastAPI      │  │  PostgreSQL  │  │
     │  │  YOLO model   │  │  All data    │  │
     │  │  LLM          │  │              │  │
     │  │  FFmpeg        │  │              │  │
     │  └──────────────┘  └──────────────┘  │
     │                                      │
     │  Exposed via Cloudflare Tunnel       │
     │  e.g. api.geyam.com → localhost:8000 │
     └──────────────────────────────────────┘
```

### How This Works

- **geyam.com** (Hostinger) — serves the Flutter web build (just static files). This is what managers open in their browser.
- **api.geyam.com** (your laptop) — Cloudflare Tunnel exposes your laptop's FastAPI to the internet. No port forwarding needed.
- **Flutter mobile app** — also hits api.geyam.com for all API calls.
- **Everything heavy** (YOLO, training, LLM, database) stays on your laptop.

### Cloudflare Tunnel Setup (one-time)

```bash
# Install cloudflared on your laptop
# macOS
brew install cloudflared

# Login
cloudflared tunnel login

# Create tunnel
cloudflared tunnel create geyam

# Route to your subdomain
cloudflared tunnel route dns geyam api.geyam.com

# Run it (points api.geyam.com → localhost:8000)
cloudflared tunnel --url http://localhost:8000 run geyam
```

In Cloudflare DNS, `api.geyam.com` will point to the tunnel. Your FastAPI runs on `localhost:8000`, Cloudflare handles HTTPS.

---

## Two User Roles

**Staff (Cashier)** — Flutter mobile app. Camera → snap tray → see detected items in cart → confirm sale. That is all.

**Manager (Admin)** — Opens geyam.com in browser. Upload product videos to teach the system. View sales data. View forecast. Ask AI restock questions. Toggle light/dark mode.

---

## Two Core Flows

### Flow 1 — Manager Adds a New Product

```
Manager films 15-sec video of "Milo Can"
         │
         ▼
POST api.geyam.com/train/video  (video + name: "Milo Can" + price: RM2.50)
         │
         ▼
Server (your laptop) extracts frames using FFmpeg
         │
         ▼
Frames auto-labeled → YOLO fine-tunes
         │
         ▼
New model saved → system now recognizes "Milo Can"
```

### Flow 2 — Staff Scans a Tray

```
Staff places tray on counter → takes photo
         │
         ▼
POST api.geyam.com/detect  (image)
         │
         ▼
Server runs YOLO → detects:
  - Milo Can      (0.94) → RM2.50
  - Chipster      (0.87) → RM3.00
  - 100Plus       (0.91) → RM2.20
         │
         ▼
Validation layer: reject result if any item appears >3 times
  - passes → return YOLO result (source: "yolo")
  - fails  → fall back to GPT-4o vision, constrained to the menu
             → return vision result (source: "openai")
         │
         ▼
Cart shown on phone → staff confirms → transaction saved
Total: RM7.70
```

### Detect Validation + Vision Fallback

YOLO on a small/early dataset can hallucinate duplicate detections (e.g.
"14 cans of Milo" on a tray holding one). The detect endpoint guards
against this with a simple heuristic:

1. YOLO runs first on the uploaded image.
2. Count detections per label. If `max_count > 3`, the result is
   considered implausible.
3. Fall back to OpenAI GPT-4o vision with a prompt constrained to the
   current `menu_items` list, asking for `{items: [{label, quantity}]}`.
4. Parse and match labels back to `menu_items`. Each quantity is
   expanded into N entries so the existing response shape + total
   calculation stays the same.
5. Response includes a `source` field: `"yolo"` or `"openai"`. If vision
   itself errors, the original YOLO result is returned with a `warning`
   field so the client can still function.

`OPENAI_API_KEY` lives in `backend/.env` and is loaded via
`python-dotenv` at the top of `main.py` before any `app.*` modules read
env vars. It is never hardcoded. Model defaults to `gpt-4o` but can be
overridden with `OPENAI_VISION_MODEL`.

---

## Theme: Light / Dark Mode

```
LIGHT MODE
  Background:    #FFFFFF
  Surface:       #F5F5F5
  Text:          #1A1A1A
  Primary:       #000080 (Navy Blue)
  Accent:        #1E90FF

DARK MODE
  Background:    #000080 (Navy Blue)
  Surface:       #000066
  Text:          #F0F0F0
  Primary:       #4DA6FF
  Accent:        #1E90FF
  Card BG:       #00004D
```

Toggle stored in local state. Default to dark mode.

---

## Folder Structure

```
geyam/
├── docker-compose.yml
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py
│   ├── app/
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── models/
│   │   │   ├── user.py
│   │   │   ├── menu_item.py
│   │   │   ├── transaction.py
│   │   │   └── model_version.py
│   │   ├── schemas/
│   │   │   ├── user.py
│   │   │   ├── menu.py
│   │   │   ├── transaction.py
│   │   │   └── detection.py
│   │   ├── routers/
│   │   │   ├── auth.py
│   │   │   ├── menu.py
│   │   │   ├── detect.py
│   │   │   ├── transaction.py
│   │   │   ├── forecast.py
│   │   │   ├── ask.py
│   │   │   └── train.py
│   │   └── services/
│   │       ├── yolo_service.py
│   │       ├── training.py
│   │       ├── llm_service.py
│   │       └── forecast.py
│   ├── ml_models/
│   │   └── (empty — models appear here after training)
│   └── training_data/
│       ├── images/
│       │   ├── train/
│       │   └── val/
│       ├── labels/
│       │   ├── train/
│       │   └── val/
│       └── data.yaml
├── frontend/
│   └── geyam_pos/
│       ├── lib/
│       │   ├── main.dart
│       │   ├── config/
│       │   │   ├── api_config.dart        # base URL: api.geyam.com
│       │   │   └── theme.dart             # light + dark theme definitions
│       │   ├── providers/
│       │   │   └── theme_provider.dart    # toggle state
│       │   ├── services/
│       │   │   ├── api_service.dart
│       │   │   └── auth_service.dart
│       │   ├── screens/
│       │   │   ├── login_screen.dart
│       │   │   ├── pos_screen.dart
│       │   │   ├── dashboard_screen.dart
│       │   │   └── product_upload_screen.dart
│       │   └── widgets/
│       │       ├── cart_widget.dart
│       │       ├── sales_chart.dart
│       │       └── theme_toggle.dart      # light/dark switch
│       └── pubspec.yaml
└── data/
    └── seed_menu.sql
```

---

## Database Schema (PostgreSQL)

```sql
CREATE TABLE users (
    id          SERIAL PRIMARY KEY,
    username    VARCHAR(50) UNIQUE NOT NULL,
    password    VARCHAR(255) NOT NULL,
    role        VARCHAR(20) NOT NULL CHECK (role IN ('staff', 'manager')),
    created_at  TIMESTAMP DEFAULT NOW()
);

CREATE TABLE menu_items (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    label       VARCHAR(50) UNIQUE NOT NULL,
    price       DECIMAL(6,2) NOT NULL,
    category    VARCHAR(50),
    is_active   BOOLEAN DEFAULT TRUE,
    image_url   TEXT,
    frame_count INTEGER DEFAULT 0,
    created_at  TIMESTAMP DEFAULT NOW()
);

CREATE TABLE transactions (
    id          SERIAL PRIMARY KEY,
    staff_id    INTEGER REFERENCES users(id),
    total       DECIMAL(8,2) NOT NULL,
    payment     VARCHAR(20) DEFAULT 'cash',
    created_at  TIMESTAMP DEFAULT NOW()
);

CREATE TABLE transaction_items (
    id              SERIAL PRIMARY KEY,
    transaction_id  INTEGER REFERENCES transactions(id) ON DELETE CASCADE,
    menu_item_id    INTEGER REFERENCES menu_items(id),
    quantity        INTEGER DEFAULT 1,
    unit_price      DECIMAL(6,2) NOT NULL,
    confidence      REAL
);

CREATE TABLE model_versions (
    id          SERIAL PRIMARY KEY,
    filename    VARCHAR(255) NOT NULL,
    num_classes INTEGER NOT NULL,
    accuracy    REAL,
    is_active   BOOLEAN DEFAULT FALSE,
    trained_at  TIMESTAMP DEFAULT NOW(),
    notes       TEXT
);
```

---

## docker-compose.yml

```yaml
version: "3.9"

services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: pos_user
      POSTGRES_PASSWORD: pos_pass
      POSTGRES_DB: geyam
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./data/seed_menu.sql:/docker-entrypoint-initdb.d/seed.sql

  backend:
    build: ./backend
    ports:
      - "8000:8000"
    depends_on:
      - db
    environment:
      DATABASE_URL: postgresql+asyncpg://pos_user:pos_pass@db:5432/geyam
      MODEL_DIR: /app/ml_models
      TRAINING_DATA_DIR: /app/training_data
    volumes:
      - ./backend:/app
      - ./backend/ml_models:/app/ml_models
      - ./backend/training_data:/app/training_data

volumes:
  pgdata:
```

---

## API Endpoints

| Method | Endpoint           | Role    | What It Does                                          |
|--------|--------------------|---------|-------------------------------------------------------|
| POST   | `/auth/login`      | any     | Returns JWT token                                     |
| GET    | `/menu`            | any     | List all known products + prices                      |
| POST   | `/menu`            | manager | Manually add/edit a product                           |
| POST   | `/detect`          | staff   | Upload tray image → YOLO → detected items + prices    |
| POST   | `/transaction`     | staff   | Save confirmed sale                                   |
| GET    | `/sales`           | manager | Sales history with date filters                       |
| GET    | `/sales/summary`   | manager | Aggregated revenue, top sellers                       |
| GET    | `/forecast`        | manager | Demand forecast per item                              |
| POST   | `/ask`             | manager | Ask LLM about sales data                              |
| POST   | `/train/video`     | manager | Upload video + name + price → extract frames → train  |
| GET    | `/model/status`    | manager | Current model version, num classes, accuracy           |

---

## Build Order

```
PHASE 1 — Server boots
──────────────────────────────────────────────
  1. docker-compose up -d db              → Postgres running
  2. FastAPI hello world + GET /health    → server responds
  3. SQLAlchemy connects, tables created   → DB wired up
  4. Seed a test user (staff + manager)

PHASE 2 — Video upload → training pipeline (KEY FEATURE)
──────────────────────────────────────────────
  5. POST /train/video accepts video file + name + price
  6. FFmpeg extracts frames from video
  7. Frames saved to training_data/images/
  8. Auto-generate YOLO label .txt files
  9. Update data.yaml with new class
  10. Run YOLO fine-tune → save best.pt
  11. Save product to menu_items table
  12. Test: upload video of a can → model now detects it

PHASE 3 — Detection works
──────────────────────────────────────────────
  13. POST /detect loads the trained model
  14. Accepts image, runs YOLO inference
  15. Matches detections to menu_items by label
  16. Returns item names + prices + confidence
  16a. Validation layer: if YOLO reports >3 of any single item,
       fall back to GPT-4o vision constrained to the menu.
       Key loaded from backend/.env via python-dotenv.

PHASE 4 — Transactions + sales
──────────────────────────────────────────────
  17. POST /transaction saves to DB
  18. GET /sales returns history
  19. GET /sales/summary returns totals

PHASE 5 — Smart features
──────────────────────────────────────────────
  20. GET /forecast — moving average per product
  21. POST /ask — local LLM answers restock questions

PHASE 6 — Flutter frontend
──────────────────────────────────────────────
  22. Theme setup — light + dark mode with toggle
  23. Login screen + role routing
  24. Staff: camera → send to /detect → cart → confirm
  25. Manager: dashboard with sales table + chart
  26. Manager: video upload screen for new products

PHASE 7 — Deploy + connect
──────────────────────────────────────────────
  27. Build Flutter web → upload to Hostinger (geyam.com)
  28. Set up Cloudflare Tunnel → api.geyam.com
  29. Update api_config.dart base URL to api.geyam.com
  30. Test: open geyam.com on another device → it works

PHASE 8 — Polish (only if time)
──────────────────────────────────────────────
  31. Telegram bot for quick sales queries
  32. Model version history in dashboard
  33. Batch video upload for multiple products
```

---

## Training Pipeline Detail (Phase 2 internals)

When manager uploads a video of "Milo Can" at RM2.50:

```
1. Save video to temp file

2. FFmpeg extracts frames:
   ffmpeg -i video.mp4 -vf "fps=2" frames/milo_can_%04d.jpg
   (2 frames per second, ~30 frames from 15-sec video)

3. For each frame, create a YOLO label file:
   - Product fills most of the frame in the video
   - Use a centered bounding box covering ~80% of the image
   - label: class_id  0.5  0.5  0.8  0.8

4. Add "milo_can" to data.yaml class list

5. Split frames 80/20 into train/val folders

6. Fine-tune:
   model = YOLO("yolov8n.pt")  # or previous best.pt
   model.train(data="data.yaml", epochs=30, imgsz=640)

7. Save new best.pt to ml_models/

8. Insert into menu_items table:
   name="Milo Can", label="milo_can", price=2.50

9. Insert into model_versions table:
   filename="best_v2.pt", num_classes=1, is_active=True

10. Hot-reload model in memory
```

---

## Minimum Demo (4 things that must work)

1. Upload video of a product → system learns it
2. Photo of tray → server detects learned products → returns names + prices
3. Transaction saved → visible in sales dashboard
4. Ask AI "should I restock Milo?" → gets a real answer

---

## Anti-Mistake Habits

- Git commit after every working step
- Test endpoint with curl/Postman before building any UI
- Hardcode first, abstract later
- One terminal per service
- If stuck more than 10 minutes, hardcode a fallback and move on
- Keep a notepad open: what just worked, what is next
