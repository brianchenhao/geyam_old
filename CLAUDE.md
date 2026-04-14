# GEYAM — Smart POS for Packaged Food

## What This Is
A POS system that uses YOLOv8 to detect packaged food items on a tray.
The system starts empty and learns new products when the manager uploads
a video of the item with a name and price.

## Tech Stack
- Backend: Python FastAPI
- Database: PostgreSQL (Docker)
- AI: YOLOv8 (ultralytics), local LLM (Ollama)
- Frontend: Flutter (mobile for staff POS, web for manager dashboard)
- Hosting: geyam.com (Hostinger) for frontend, laptop runs backend
- Tunnel: Cloudflare Tunnel exposes localhost:8000 as api.geyam.com

## Architecture
- Flutter mobile = camera + display only, sends image to server
- FastAPI server = runs YOLO, training, LLM, everything
- PostgreSQL = users, menu_items, transactions, model_versions

## Key Endpoints
- POST /detect — upload tray image, get detected items + prices
- POST /train/video — upload video + name + price, system learns product
- POST /transaction — save a sale
- GET /sales — sales history
- POST /ask — ask LLM about sales data

## Current Phase
Phase 1 — getting FastAPI + PostgreSQL running

## Commands
- Start DB: docker-compose up -d db
- Start server: uvicorn main:app --reload --host 0.0.0.0 --port 8000
- Test: curl http://localhost:8000/health

## Rules
- Test every endpoint with curl before building UI
- Git commit after every working step
- Hardcode first, abstract later
- If stuck >10 min, use a dummy fallback and move on