# GEYAM — Smart POS for Packaged Food

## What This Is
A POS system that uses YOLOv8 to detect packaged food items on a tray.
The system starts empty and learns new products when the manager uploads
a video of the item with a name and price.

## Tech Stack
- Backend: Python FastAPI
- Database: PostgreSQL (Docker)
- AI: YOLOv8 (ultralytics), local LLM (Ollama), OpenAI GPT-4o vision (fallback)
- Frontend: Flutter (mobile for staff POS, web for manager dashboard)
- Hosting: geyam.com (Hostinger) for frontend, laptop runs backend
- Tunnel: Cloudflare Tunnel exposes localhost:8500 as api.geyam.com
- Secrets: backend/.env (loaded via python-dotenv); OPENAI_API_KEY lives here

## Architecture
- Flutter mobile = camera + display only, sends image to server
- FastAPI server = runs YOLO, training, LLM, everything
- PostgreSQL = users, menu_items, transactions, model_versions

## Key Endpoints
- POST /detect — upload tray image, get detected items + prices.
  YOLO runs first. If any single item is counted more than 3 times,
  the result is flagged "not logical" and the endpoint falls back to
  OpenAI GPT-4o vision constrained to the menu. Response includes a
  `source` field (`"yolo"` or `"openai"`).
- POST /train/video — upload video + name + price, system learns product
- POST /transaction — save a sale
- GET /sales — sales history
- POST /ask — ask LLM about sales data

## Current Phase
C:\Programming (Local)\FYP Claude\geyam\docs\PLAN.md the whole plan of the project is in this folder

## Commands
- Start DB: docker-compose up -d db
- Start server: uvicorn main:app --reload --host 0.0.0.0 --port 8500
- Test: curl http://localhost:8500/health

## Rules
- Test every endpoint with curl before building UI
- Git commit after every working step
- Hardcode first, abstract later
- If stuck >10 min, use a dummy fallback and move on