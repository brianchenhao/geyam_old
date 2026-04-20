"""Phase 15 #90: export a tenant's active YOLO model to ONNX (optionally INT8).

Ultralytics handles the export + optional per-channel quantization for us.
After export, swap `best.pt` loading with the `.onnx` file in `yolo_service`
for a ~2-4× inference speedup on CPU.

Usage:
    python scripts/onnx_export.py --tenant-id 1 [--int8]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ultralytics import YOLO  # noqa: E402

from app.services import yolo_service  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant-id", type=int, required=True)
    ap.add_argument("--int8", action="store_true", help="quantize to INT8")
    ap.add_argument("--imgsz", type=int, default=320)
    args = ap.parse_args()

    pt = yolo_service.active_model_path(args.tenant_id)
    if not pt.exists():
        print(f"! no active model at {pt}")
        return
    model = YOLO(str(pt))
    out = model.export(format="onnx", int8=args.int8, imgsz=args.imgsz, simplify=True)
    print(f"+ exported: {out}  (INT8={args.int8})")


if __name__ == "__main__":
    main()
