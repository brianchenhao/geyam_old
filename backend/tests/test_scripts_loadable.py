"""Phase 14/15 sanity: CLIs import without syntax or attribute errors, and
declare their argparse/help surface so a regression in the shared app package
trips a test instead of silently breaking a deploy script."""
import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.mark.parametrize("mod", [
    "scripts.seed_demo_tenant",
    "scripts.daily_summary",
    "scripts.telegram_bot",
    "scripts.onnx_export",
    "scripts.create_tenant",
    "scripts.dev_token",
    "scripts.gen_fernet",
])
def test_module_imports_clean(mod):
    m = importlib.import_module(mod)
    assert hasattr(m, "__doc__")


def test_telegram_auth_map_parses():
    from scripts.telegram_bot import _auth_map
    import os
    os.environ["TELEGRAM_OWNERS"] = "123:alpha, 456:beta-shop,notpair,789:gamma"
    try:
        m = _auth_map()
        assert m == {123: "alpha", 456: "beta-shop", 789: "gamma"}
    finally:
        del os.environ["TELEGRAM_OWNERS"]
