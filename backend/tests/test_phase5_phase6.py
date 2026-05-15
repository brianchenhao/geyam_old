"""Phase 5 (Menu + CSV + images) + Phase 6 (Training) comprehensive validation.

Runs against the docker stack's Postgres via the app's own SessionLocal/ASGI app.
    docker compose exec backend pytest -xvs tests/test_phase5_phase6.py
"""
import io
import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image
from sqlalchemy import delete, select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app import tenant_context  # noqa: E402
from app.database import SessionLocal, engine  # noqa: E402


@pytest.fixture(autouse=True)
async def _dispose_engine_between_tests():
    yield
    await engine.dispose()


from app.deps import bypass_tenant_scope  # noqa: E402
from app.models.audit_log import AuditLog  # noqa: E402
from app.models.menu_item import MenuItem  # noqa: E402
from app.models.model_version import ModelVersion  # noqa: E402
from app.models.tenant import Tenant  # noqa: E402
from app.models.tenant_settings import TenantSettings  # noqa: E402
from app.models.training_job import TrainingJob  # noqa: E402
from app.models.user import User  # noqa: E402
from app.security import issue_access_token  # noqa: E402
from main import app  # noqa: E402

HANDLE_A = "p56a"
HANDLE_B = "p56b"


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def _cleanup():
    tenant_context.set_current_tenant_id(None)
    async with SessionLocal() as s:
        async with bypass_tenant_scope():
            tids = (await s.execute(
                select(Tenant.id).where(Tenant.handle.in_([HANDLE_A, HANDLE_B]))
            )).scalars().all()
            if tids:
                await s.execute(delete(AuditLog).where(AuditLog.tenant_id.in_(tids)))
                await s.execute(delete(TrainingJob).where(TrainingJob.tenant_id.in_(tids)))
                await s.execute(delete(ModelVersion).where(ModelVersion.tenant_id.in_(tids)))
                await s.execute(delete(MenuItem).where(MenuItem.tenant_id.in_(tids)))
                await s.execute(delete(User).where(User.tenant_id.in_(tids)))
                await s.execute(delete(TenantSettings).where(TenantSettings.tenant_id.in_(tids)))
                await s.execute(delete(Tenant).where(Tenant.id.in_(tids)))
            await s.commit()


async def _seed():
    """Create tenants A and B each with an owner + a cashier (A only)."""
    await _cleanup()
    async with SessionLocal() as s:
        async with bypass_tenant_scope():
            tA = Tenant(handle=HANDLE_A, name="A Shop", owner_email="a@p56.test")
            tB = Tenant(handle=HANDLE_B, name="B Shop", owner_email="b@p56.test")
            s.add_all([tA, tB]); await s.flush()
            ownerA = User(tenant_id=tA.id, username=HANDLE_A, email="a@p56.test",
                          role="owner", is_active=True, google_sub="sub56-a")
            ownerB = User(tenant_id=tB.id, username=HANDLE_B, email="b@p56.test",
                          role="owner", is_active=True, google_sub="sub56-b")
            from app.security import hash_pin
            cashA = User(tenant_id=tA.id, username=f"staff1.{HANDLE_A}",
                         role="cashier", is_active=True, pin_hash=hash_pin("482913"))
            s.add_all([ownerA, ownerB, cashA]); await s.commit()
            return {
                "tA_id": tA.id, "tB_id": tB.id,
                "ownerA_id": ownerA.id, "ownerB_id": ownerB.id, "cashA_id": cashA.id,
            }


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _owner_tok(ids, which="A"):
    return issue_access_token(
        tenant_id=ids[f"t{which}_id"],
        user_id=ids[f"owner{which}_id"],
        role="owner",
    )


def _cash_tok(ids):
    return issue_access_token(tenant_id=ids["tA_id"], user_id=ids["cashA_id"], role="cashier")


# ====================================================================
# PHASE 5: MENU CRUD + CSV + IMAGES
# ====================================================================

@pytest.mark.asyncio
async def test_phase5_create_and_list_menu_item():
    ids = await _seed()
    try:
        tok = _owner_tok(ids)
        async with _client() as c:
            r = await c.post("/menu", json={"name": "Coke 330ml", "price": "2.50",
                                             "category": "drinks", "stock_qty": 20},
                             headers={"Authorization": f"Bearer {tok}"})
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["name"] == "Coke 330ml"
            assert body["label"] == "coke_330ml"
            assert body["tenant_id"] == ids["tA_id"]
            assert body["is_active"] is True
            r2 = await c.get("/menu", headers={"Authorization": f"Bearer {tok}"})
            assert r2.status_code == 200
            names = [m["name"] for m in r2.json()]
            assert "Coke 330ml" in names
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_phase5_patch_menu_item_updates_label_on_rename():
    ids = await _seed()
    try:
        tok = _owner_tok(ids)
        async with _client() as c:
            created = (await c.post("/menu", json={"name": "Milo", "price": "3.00"},
                                    headers={"Authorization": f"Bearer {tok}"})).json()
            r = await c.patch(f"/menu/{created['id']}",
                              json={"name": "Milo Ais", "price": "3.50"},
                              headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["name"] == "Milo Ais"
        assert body["label"] == "milo_ais"
        assert body["price"] == "3.50"
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_phase5_soft_delete_and_restore():
    ids = await _seed()
    try:
        tok = _owner_tok(ids)
        async with _client() as c:
            it = (await c.post("/menu", json={"name": "100Plus", "price": "2.80"},
                               headers={"Authorization": f"Bearer {tok}"})).json()
            r = await c.delete(f"/menu/{it['id']}", headers={"Authorization": f"Bearer {tok}"})
            assert r.status_code == 200 and r.json()["is_active"] is False
            # default list excludes archived
            r2 = await c.get("/menu", headers={"Authorization": f"Bearer {tok}"})
            assert not any(m["id"] == it["id"] for m in r2.json())
            # include_archived=true shows it
            r3 = await c.get("/menu?include_archived=true", headers={"Authorization": f"Bearer {tok}"})
            assert any(m["id"] == it["id"] for m in r3.json())
            # restore
            r4 = await c.post(f"/menu/{it['id']}/restore", headers={"Authorization": f"Bearer {tok}"})
            assert r4.status_code == 200 and r4.json()["is_active"] is True
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_phase5_duplicate_name_conflicts_409():
    ids = await _seed()
    try:
        tok = _owner_tok(ids)
        async with _client() as c:
            r1 = await c.post("/menu", json={"name": "Kit Kat", "price": "2.00"},
                              headers={"Authorization": f"Bearer {tok}"})
            assert r1.status_code == 200
            r2 = await c.post("/menu", json={"name": "Kit Kat", "price": "2.00"},
                              headers={"Authorization": f"Bearer {tok}"})
        assert r2.status_code == 409
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_phase5_cashier_blocked_from_mutations():
    ids = await _seed()
    try:
        cash = _cash_tok(ids)
        async with _client() as c:
            r = await c.post("/menu", json={"name": "X", "price": "1"},
                             headers={"Authorization": f"Bearer {cash}"})
        assert r.status_code == 403
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_phase5_menu_tenant_isolated():
    ids = await _seed()
    try:
        tokA = _owner_tok(ids, "A")
        tokB = _owner_tok(ids, "B")
        async with _client() as c:
            await c.post("/menu", json={"name": "A-item", "price": "1.00"},
                         headers={"Authorization": f"Bearer {tokA}"})
            rb = await c.get("/menu", headers={"Authorization": f"Bearer {tokB}"})
        assert rb.status_code == 200
        assert not any(m["name"] == "A-item" for m in rb.json())
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_phase5_bulk_csv_insert_and_upsert():
    ids = await _seed()
    try:
        tok = _owner_tok(ids)
        csv1 = (
            b"name,price,category,stock_qty,reorder_point\n"
            b"Nasi Lemak,5.50,food,10,3\n"
            b"Teh Tarik,3.00,drinks,50,10\n"
            b"Roti Canai,2.20,food,30,5\n"
        )
        async with _client() as c:
            r = await c.post("/menu/bulk",
                             files={"file": ("m.csv", csv1, "text/csv")},
                             headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["inserted"] == 3 and body["updated"] == 0 and body["errors"] == []

        # Upsert: one existing, one new
        csv2 = (
            b"name,price,category,stock_qty\n"
            b"Nasi Lemak,6.00,food,8\n"
            b"Iced Lemon Tea,4.50,drinks,20\n"
        )
        async with _client() as c:
            r2 = await c.post("/menu/bulk",
                              files={"file": ("m2.csv", csv2, "text/csv")},
                              headers={"Authorization": f"Bearer {tok}"})
        assert r2.status_code == 200, r2.text
        b2 = r2.json()
        assert b2["updated"] == 1 and b2["inserted"] == 1

        # Verify Nasi Lemak price was updated
        async with _client() as c:
            rl = await c.get("/menu", headers={"Authorization": f"Bearer {tok}"})
        nl = next(m for m in rl.json() if m["name"] == "Nasi Lemak")
        assert nl["price"] == "6.00" and nl["stock_qty"] == 8
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_phase5_bulk_csv_bad_price_recorded_as_error():
    ids = await _seed()
    try:
        tok = _owner_tok(ids)
        csv = b"name,price\nGood,1.00\nBad,not-a-number\n,2.00\n"
        async with _client() as c:
            r = await c.post("/menu/bulk", files={"file": ("x.csv", csv, "text/csv")},
                             headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["inserted"] == 1
        assert len(body["errors"]) == 2
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_phase5_bulk_csv_missing_columns_400():
    ids = await _seed()
    try:
        tok = _owner_tok(ids)
        async with _client() as c:
            r = await c.post("/menu/bulk",
                             files={"file": ("x.csv", b"foo,bar\n1,2\n", "text/csv")},
                             headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 400
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_phase5_image_upload_saves_and_sets_path():
    ids = await _seed()
    try:
        tok = _owner_tok(ids)
        async with _client() as c:
            it = (await c.post("/menu", json={"name": "Biscuit", "price": "1.50"},
                               headers={"Authorization": f"Bearer {tok}"})).json()
            buf = io.BytesIO()
            Image.new("RGB", (800, 600), (0, 128, 255)).save(buf, format="PNG")
            r = await c.post(f"/menu/{it['id']}/image",
                             files={"file": ("i.png", buf.getvalue(), "image/png")},
                             headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["image_path"] == f"/uploads/{ids['tA_id']}/products/{it['id']}.jpg"
        from app.config import UPLOADS_DIR
        saved = UPLOADS_DIR / str(ids["tA_id"]) / "products" / f"{it['id']}.jpg"
        assert saved.exists()
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_phase5_image_upload_rejects_bad_mime():
    ids = await _seed()
    try:
        tok = _owner_tok(ids)
        async with _client() as c:
            it = (await c.post("/menu", json={"name": "X", "price": "1"},
                               headers={"Authorization": f"Bearer {tok}"})).json()
            r = await c.post(f"/menu/{it['id']}/image",
                             files={"file": ("x.txt", b"nope", "text/plain")},
                             headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 400
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_phase5_image_upload_rejects_oversize():
    ids = await _seed()
    try:
        tok = _owner_tok(ids)
        async with _client() as c:
            it = (await c.post("/menu", json={"name": "Y", "price": "1"},
                               headers={"Authorization": f"Bearer {tok}"})).json()
            big = b"\x00" * (6 * 1024 * 1024)
            r = await c.post(f"/menu/{it['id']}/image",
                             files={"file": ("big.png", big, "image/png")},
                             headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 413
    finally:
        await _cleanup()


# ====================================================================
# PHASE 6: TRAINING
# ====================================================================

def _make_mp4(seconds: float) -> bytes:
    """Use ffmpeg to synthesize a tiny test video of the requested length."""
    import imageio_ffmpeg
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    out = Path("/tmp") / f"syn_{int(seconds*1000)}.mp4"
    if not out.exists():
        subprocess.run(
            [ffmpeg, "-y", "-f", "lavfi", "-i", f"color=c=blue:s=64x64:d={seconds}",
             "-pix_fmt", "yuv420p", "-r", "10", str(out)],
            capture_output=True, check=True, timeout=30,
        )
    return out.read_bytes()


@pytest.mark.asyncio
async def test_phase6_upload_video_happy_path():
    ids = await _seed()
    try:
        tok = _owner_tok(ids)
        async with _client() as c:
            it = (await c.post("/menu", json={"name": "TrainItem", "price": "1"},
                               headers={"Authorization": f"Bearer {tok}"})).json()
            vid = _make_mp4(1.0)
            r = await c.post("/train/video",
                             data={"menu_item_id": str(it["id"])},
                             files={"file": ("v.mp4", vid, "video/mp4")},
                             headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "queued"
        assert body["menu_item_id"] == it["id"]
        assert Path(body["video_path"]).exists()
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_phase6_upload_video_rejects_too_long():
    ids = await _seed()
    try:
        tok = _owner_tok(ids)
        async with _client() as c:
            it = (await c.post("/menu", json={"name": "LongItem", "price": "1"},
                               headers={"Authorization": f"Bearer {tok}"})).json()
            # mock probe duration to simulate >30s without building a huge video
            with patch("app.routers.train.probe_duration_seconds", return_value=45.0):
                r = await c.post("/train/video",
                                 data={"menu_item_id": str(it["id"])},
                                 files={"file": ("v.mp4", _make_mp4(1.0), "video/mp4")},
                                 headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 400
        assert "30" in r.json()["detail"]
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_phase6_upload_video_rejects_bad_mime():
    ids = await _seed()
    try:
        tok = _owner_tok(ids)
        async with _client() as c:
            it = (await c.post("/menu", json={"name": "M", "price": "1"},
                               headers={"Authorization": f"Bearer {tok}"})).json()
            r = await c.post("/train/video",
                             data={"menu_item_id": str(it["id"])},
                             files={"file": ("v.txt", b"nope", "text/plain")},
                             headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 400
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_phase6_upload_video_sets_image_path_if_missing():
    ids = await _seed()
    try:
        tok = _owner_tok(ids)
        async with _client() as c:
            it = (await c.post("/menu", json={"name": "NeedsImg", "price": "1"},
                               headers={"Authorization": f"Bearer {tok}"})).json()
            r = await c.post("/train/video",
                             data={"menu_item_id": str(it["id"])},
                             files={"file": ("v.mp4", _make_mp4(1.0), "video/mp4")},
                             headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200, r.text
        # Check menu item's image_path got populated
        async with _client() as c:
            rl = await c.get("/menu", headers={"Authorization": f"Bearer {tok}"})
        row = next(m for m in rl.json() if m["id"] == it["id"])
        assert row["image_path"] and "/products/" in row["image_path"]
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_phase6_train_run_requires_queued_jobs():
    ids = await _seed()
    try:
        tok = _owner_tok(ids)
        async with _client() as c:
            r = await c.post("/train/run", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 400
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_phase6_train_run_409_when_locked():
    ids = await _seed()
    try:
        tok = _owner_tok(ids)
        # seed a queued job + set lock
        from datetime import datetime
        async with SessionLocal() as s:
            async with bypass_tenant_scope():
                mi = MenuItem(tenant_id=ids["tA_id"], name="X", label="x", price=1,
                              stock_qty=0, reorder_point=0)
                s.add(mi); await s.flush()
                s.add(TrainingJob(tenant_id=ids["tA_id"], menu_item_id=mi.id,
                                   video_path="/tmp/x.mp4", status="queued"))
                s.add(TenantSettings(tenant_id=ids["tA_id"],
                                      training_locked_at=datetime.utcnow()))
                await s.commit()
        async with _client() as c:
            r = await c.post("/train/run", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 409
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_phase6_train_run_enqueues_and_sets_lock():
    ids = await _seed()
    try:
        tok = _owner_tok(ids)
        async with SessionLocal() as s:
            async with bypass_tenant_scope():
                mi = MenuItem(tenant_id=ids["tA_id"], name="X", label="x", price=1,
                              stock_qty=0, reorder_point=0)
                s.add(mi); await s.flush()
                s.add(TrainingJob(tenant_id=ids["tA_id"], menu_item_id=mi.id,
                                   video_path="/tmp/x.mp4", status="queued"))
                await s.commit()

        fake_job = MagicMock(); fake_job.id = "rq-abc"
        fake_q = MagicMock(); fake_q.enqueue.return_value = fake_job
        with patch("app.routers.train._get_queue", return_value=fake_q):
            async with _client() as c:
                r = await c.post("/train/run", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "started" and body["job_count"] == 1
        fake_q.enqueue.assert_called_once()

        async with SessionLocal() as s:
            async with bypass_tenant_scope():
                ts = (await s.execute(
                    select(TenantSettings).where(TenantSettings.tenant_id == ids["tA_id"])
                )).scalars().first()
                assert ts is not None and ts.training_locked_at is not None
    finally:
        await _cleanup()


# ----- training service (run_batch) unit tests -----

def _sync_session_for(tenant_id):
    """Helper: read rows in a sync session like the worker does."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    sync_url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg", "postgresql+psycopg")
    eng = create_engine(sync_url, future=True)
    return sessionmaker(bind=eng, expire_on_commit=False)


@pytest.mark.asyncio
async def test_phase6_run_batch_stub_mode_end_to_end():
    """Stub mode: no YOLO. Verify frames extracted, jobs 'done', ModelVersion flipped, lock cleared."""
    ids = await _seed()
    try:
        # Prepare a real short video on disk for ffmpeg to slice.
        from app.config import UPLOADS_DIR
        video_dir = UPLOADS_DIR / str(ids["tA_id"]) / "videos"
        video_dir.mkdir(parents=True, exist_ok=True)
        v_path = video_dir / "test.mp4"
        v_path.write_bytes(_make_mp4(1.0))

        from datetime import datetime
        async with SessionLocal() as s:
            async with bypass_tenant_scope():
                mi = MenuItem(tenant_id=ids["tA_id"], name="Widget", label="widget", price=1,
                              stock_qty=0, reorder_point=0)
                s.add(mi); await s.flush()
                s.add(TrainingJob(tenant_id=ids["tA_id"], menu_item_id=mi.id,
                                   video_path=str(v_path), status="queued"))
                # pre-existing active model to verify deactivation
                s.add(ModelVersion(tenant_id=ids["tA_id"], filename="old.pt",
                                    num_classes=1, is_active=True))
                s.add(TenantSettings(tenant_id=ids["tA_id"],
                                      training_locked_at=datetime.utcnow()))
                await s.commit()

        os.environ["TRAIN_MODE"] = "stub"
        from app.services.training import run_batch
        result = run_batch(ids["tA_id"])
        assert result["failed"] is False, result
        assert result["frames"] > 0
        assert all(j["status"] == "done" for j in result["jobs"])

        async with SessionLocal() as s:
            async with bypass_tenant_scope():
                ts = (await s.execute(
                    select(TenantSettings).where(TenantSettings.tenant_id == ids["tA_id"])
                )).scalars().first()
                assert ts.training_locked_at is None, "lock must release on success"

                mvs = (await s.execute(
                    select(ModelVersion).where(ModelVersion.tenant_id == ids["tA_id"])
                )).scalars().all()
                active = [m for m in mvs if m.is_active]
                inactive = [m for m in mvs if not m.is_active]
                assert len(active) == 1 and active[0].filename == "best.pt"
                assert any(m.filename == "old.pt" for m in inactive)
    finally:
        os.environ.pop("TRAIN_MODE", None)
        await _cleanup()


@pytest.mark.asyncio
async def test_phase6_run_batch_failure_releases_lock_and_keeps_old_model():
    """If training raises, lock must release, jobs must go 'failed', old active model unchanged."""
    ids = await _seed()
    try:
        from app.config import UPLOADS_DIR
        video_dir = UPLOADS_DIR / str(ids["tA_id"]) / "videos"
        video_dir.mkdir(parents=True, exist_ok=True)
        v_path = video_dir / "fail.mp4"
        v_path.write_bytes(_make_mp4(1.0))

        from datetime import datetime
        async with SessionLocal() as s:
            async with bypass_tenant_scope():
                mi = MenuItem(tenant_id=ids["tA_id"], name="Widget2", label="widget2", price=1,
                              stock_qty=0, reorder_point=0)
                s.add(mi); await s.flush()
                s.add(TrainingJob(tenant_id=ids["tA_id"], menu_item_id=mi.id,
                                   video_path=str(v_path), status="queued"))
                s.add(ModelVersion(tenant_id=ids["tA_id"], filename="stay.pt",
                                    num_classes=1, is_active=True))
                s.add(TenantSettings(tenant_id=ids["tA_id"],
                                      training_locked_at=datetime.utcnow()))
                await s.commit()

        os.environ["TRAIN_MODE"] = "stub"
        from app.services import training as tsvc
        with patch.object(tsvc, "extract_frames_at_fps", side_effect=RuntimeError("boom")):
            result = tsvc.run_batch(ids["tA_id"])
        assert result["failed"] is True
        assert "boom" in (result["error"] or "")

        async with SessionLocal() as s:
            async with bypass_tenant_scope():
                ts = (await s.execute(
                    select(TenantSettings).where(TenantSettings.tenant_id == ids["tA_id"])
                )).scalars().first()
                assert ts.training_locked_at is None, "lock must release on failure"

                jobs = (await s.execute(
                    select(TrainingJob).where(TrainingJob.tenant_id == ids["tA_id"])
                )).scalars().all()
                assert all(j.status == "failed" for j in jobs)

                mvs = (await s.execute(
                    select(ModelVersion).where(ModelVersion.tenant_id == ids["tA_id"])
                )).scalars().all()
                active = [m for m in mvs if m.is_active]
                assert len(active) == 1 and active[0].filename == "stay.pt", \
                    "old active model must stay active on failure"
    finally:
        os.environ.pop("TRAIN_MODE", None)
        await _cleanup()


@pytest.mark.asyncio
async def test_phase6_run_batch_real_mode_extracts_accuracy_from_yolo():
    """Simulate real mode: mock YOLO, confirm mAP50 → ModelVersion.accuracy."""
    ids = await _seed()
    try:
        from app.config import UPLOADS_DIR, BASE_DIR
        video_dir = UPLOADS_DIR / str(ids["tA_id"]) / "videos"
        video_dir.mkdir(parents=True, exist_ok=True)
        v_path = video_dir / "real.mp4"
        v_path.write_bytes(_make_mp4(1.0))

        from datetime import datetime
        async with SessionLocal() as s:
            async with bypass_tenant_scope():
                mi = MenuItem(tenant_id=ids["tA_id"], name="RealItem", label="realitem", price=1,
                              stock_qty=0, reorder_point=0)
                s.add(mi); await s.flush()
                s.add(TrainingJob(tenant_id=ids["tA_id"], menu_item_id=mi.id,
                                   video_path=str(v_path), status="queued"))
                s.add(TenantSettings(tenant_id=ids["tA_id"],
                                      training_locked_at=datetime.utcnow()))
                await s.commit()

        # Fake YOLO: train() returns an object with save_dir + results_dict
        fake_save_dir = Path("/tmp/fake_yolo_run")
        (fake_save_dir / "weights").mkdir(parents=True, exist_ok=True)
        # Create a fake best.pt so shutil.copy succeeds
        (fake_save_dir / "weights" / "best.pt").write_bytes(b"\x00")

        fake_out = MagicMock()
        fake_out.save_dir = str(fake_save_dir)
        fake_out.results_dict = {"metrics/mAP50(B)": 0.873}

        fake_model = MagicMock()
        fake_model.train.return_value = fake_out

        os.environ["TRAIN_MODE"] = "real"
        os.environ["TRAIN_EPOCHS"] = "1"

        # Patch YOLO import inside run_batch
        import types
        fake_ultralytics = types.ModuleType("ultralytics")
        fake_ultralytics.YOLO = MagicMock(return_value=fake_model)
        sys.modules["ultralytics"] = fake_ultralytics

        # Also ensure baseline yolov8n.pt exists (copy path) — create a stub
        baseline = Path(BASE_DIR) / "yolov8n.pt"
        if not baseline.exists():
            baseline.write_bytes(b"\x00")

        from app.services.training import run_batch
        result = run_batch(ids["tA_id"])
        assert result["failed"] is False, result

        async with SessionLocal() as s:
            async with bypass_tenant_scope():
                mv = (await s.execute(
                    select(ModelVersion).where(ModelVersion.tenant_id == ids["tA_id"],
                                                ModelVersion.is_active.is_(True))
                )).scalars().first()
                assert mv is not None
                assert mv.accuracy is not None, "accuracy should be parsed from YOLO results"
                assert abs(mv.accuracy - 0.873) < 1e-6
                assert mv.notes == "fine-tuned"
    finally:
        os.environ.pop("TRAIN_MODE", None)
        os.environ.pop("TRAIN_EPOCHS", None)
        sys.modules.pop("ultralytics", None)
        await _cleanup()


# ----- yolo_cache hot-reload -----

def test_phase6_yolo_cache_reloads_on_mtime_change(tmp_path, monkeypatch):
    """Our fix: cache serves a newer best.pt automatically when mtime advances."""
    from app.services import yolo_cache
    # Point cache at a temp model dir
    monkeypatch.setattr(yolo_cache, "MODEL_DIR", tmp_path)
    # Reset the in-memory cache
    yolo_cache._cache.clear()

    tenant_dir = tmp_path / "42"
    tenant_dir.mkdir()
    weights = tenant_dir / "best.pt"
    weights.write_bytes(b"v1")

    calls = []

    def fake_yolo_ctor(path):
        calls.append(Path(path).read_bytes())
        return f"model-{len(calls)}"

    # Replace ultralytics import with a stub
    import types
    stub = types.ModuleType("ultralytics")
    stub.YOLO = fake_yolo_ctor
    sys.modules["ultralytics"] = stub
    try:
        m1 = yolo_cache.get_model(42)
        assert m1 == "model-1"

        # Second call, same file → same cached model (no reload)
        m1b = yolo_cache.get_model(42)
        assert m1b == "model-1"
        assert len(calls) == 1

        # Simulate worker writing new weights with a newer mtime
        time.sleep(0.05)
        weights.write_bytes(b"v2-new")
        new_mtime = weights.stat().st_mtime + 5
        os.utime(weights, (new_mtime, new_mtime))

        m2 = yolo_cache.get_model(42)
        assert m2 == "model-2", "cache should reload when file mtime advances"
        assert len(calls) == 2
    finally:
        sys.modules.pop("ultralytics", None)
