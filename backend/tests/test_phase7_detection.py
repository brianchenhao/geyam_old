"""Phase 7 — per-stage unit tests for the detection cascade.

Pure-unit tests: no DB, no Redis, no external APIs. Each detection stage is
exercised with mocked dependencies so CI can run it offline.

    docker compose exec backend pytest -xvs tests/test_phase7_detection.py
"""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.detection.mediapipe_stage import CATEGORY_ALIAS, category_shortlist, run_mediapipe  # noqa: E402
from app.services.detection.openai_stage import _fuzzy_match, _names_to_matches  # noqa: E402
from app.services.detection.yolo_stage import run_yolo  # noqa: E402


# ---------- Stage A — YOLO ----------

def _fake_yolo_model(detections: list[tuple[int, float]], names: dict[int, str]):
    """Build a minimal duck-typed YOLOv8 result list."""
    boxes = []
    for cls, conf in detections:
        box = SimpleNamespace(cls=[SimpleNamespace(item=lambda c=cls: c)],
                              conf=[SimpleNamespace(item=lambda c=conf: c)])
        boxes.append(box)
    result = SimpleNamespace(names=names, boxes=boxes)
    model = MagicMock()
    model.predict.return_value = [result]
    return model


def test_yolo_high_conf_is_green():
    model = _fake_yolo_model([(0, 0.85)], {0: "coke"})
    out = run_yolo(model, Image.new("RGB", (8, 8)), conf_threshold=0.60, conf_minimum=0.40)
    assert len(out) == 1
    assert out[0]["label"] == "coke"
    assert out[0]["source"] == "yolo"
    assert out[0]["needs_confirm"] is False


def test_yolo_mid_conf_needs_confirm():
    model = _fake_yolo_model([(0, 0.50)], {0: "coke"})
    out = run_yolo(model, Image.new("RGB", (8, 8)), conf_threshold=0.60, conf_minimum=0.40)
    assert len(out) == 1
    assert out[0]["needs_confirm"] is True


def test_yolo_below_minimum_dropped():
    model = _fake_yolo_model([(0, 0.30)], {0: "coke"})
    out = run_yolo(model, Image.new("RGB", (8, 8)), conf_threshold=0.60, conf_minimum=0.40)
    assert out == []


def test_yolo_none_model_returns_empty():
    assert run_yolo(None, Image.new("RGB", (8, 8)), 0.6, 0.4) == []


def test_yolo_prediction_error_returns_empty():
    model = MagicMock()
    model.predict.side_effect = RuntimeError("CUDA OOM")
    assert run_yolo(model, Image.new("RGB", (8, 8)), 0.6, 0.4) == []


# ---------- Stage B — MediaPipe + shortlist ----------

def test_category_alias_table_covers_core_classes():
    # Plan requires the alias table to map generic MP classes → tenant categories.
    for key in ("bottle", "cup", "can", "bowl", "package"):
        assert key in CATEGORY_ALIAS
        assert CATEGORY_ALIAS[key], f"{key} alias set must not be empty"


def test_category_shortlist_matches_alias():
    menu = [
        {"id": 1, "name": "Coke", "label": "coke", "category": "drink", "is_active": True},
        {"id": 2, "name": "Chips", "label": "chips", "category": "snack", "is_active": True},
        {"id": 3, "name": "Old Coke", "label": "old", "category": "drink", "is_active": False},
    ]
    got = category_shortlist("bottle", menu)
    assert {m["id"] for m in got} == {1}  # drink, active only


def test_category_shortlist_unknown_guess():
    assert category_shortlist("spaceship", [{"id": 1, "category": "drink", "is_active": True}]) == []


def test_run_mediapipe_noop_when_detector_unavailable():
    # Detector is None in this environment → clean empty result (cascade falls through).
    assert run_mediapipe(Image.new("RGB", (8, 8)), []) == []


# ---------- Stage C — OpenAI naming → menu fuzzy match ----------

def test_fuzzy_match_picks_above_threshold():
    menu = [
        {"id": 1, "name": "Milo Kotak", "label": "milo", "is_active": True},
        {"id": 2, "name": "Coca-Cola Can", "label": "coke", "is_active": True},
    ]
    m = _fuzzy_match("milo", menu)
    assert m is not None and m["id"] == 1


def test_fuzzy_match_below_threshold_returns_none():
    menu = [{"id": 1, "name": "Milo Kotak", "label": "milo", "is_active": True}]
    assert _fuzzy_match("spaceship", menu) is None


def test_fuzzy_match_skips_inactive():
    menu = [{"id": 1, "name": "Milo Kotak", "label": "milo", "is_active": False}]
    assert _fuzzy_match("milo kotak", menu) is None


def test_names_to_matches_emits_openai_source_and_needs_confirm():
    menu = [{"id": 9, "name": "Milo Kotak", "label": "milo", "is_active": True}]
    out = _names_to_matches(["Milo Kotak"], menu)
    assert len(out) == 1
    assert out[0]["menu_item_id"] == 9
    assert out[0]["source"] == "openai"
    assert out[0]["needs_confirm"] is True
    assert out[0]["confidence"] == 0.5
