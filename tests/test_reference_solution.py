from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.agent.graph import build_system_prompt
import src.agent.graph as src_graph
from src.utils.data_store import OrderDataStore
from src.core.schemas import OrderLineInput


def test_save_order_matches_expected_fixture(tmp_path: Path) -> None:
    store = OrderDataStore(ROOT_DIR / "data", tmp_path, today="2026-06-01")
    detail_token = store.build_detail_token(["LT-001", "MS-001", "MN-002"])
    result = store.save_order(
        customer_name="Nguyễn Lan Anh",
        customer_phone="0901234567",
        customer_email="lananh@example.com",
        shipping_address="18 Nguyễn Huệ, Quận 1, TP.HCM",
        items=[
            OrderLineInput(product_id="LT-001", quantity=1),
            OrderLineInput(product_id="MS-001", quantity=2),
            OrderLineInput(product_id="MN-002", quantity=1),
        ],
        detail_token=detail_token,
        discount_rate=0.1,
        campaign_code="FLASH-10",
    )

    expected = json.loads(
        (ROOT_DIR / "data" / "expected_orders" / "gaming_bundle_exact_match.json").read_text(encoding="utf-8")
    )
    assert result["saved_order"]["order_id"] == expected["order_id"]
    assert result["saved_order"]["pricing"] == expected["pricing"]
    assert result["saved_order"]["items"] == expected["items"]


def test_system_prompt_has_clarification_rules() -> None:
    prompt = build_system_prompt("2026-06-01").lower()
    assert "mình cần thêm" in prompt
    assert "sđt" in prompt or "số điện thoại" in prompt
    assert "email" in prompt
    assert "địa chỉ giao hàng" in prompt


def test_system_prompt_has_guardrail_rules() -> None:
    prompt = build_system_prompt("2026-06-01").lower()
    assert "hóa đơn giả" in prompt
    assert "90%" in prompt
    assert "không thể" in prompt
    assert "không gọi tool" in prompt


def test_reference_agent_no_longer_uses_preflight_shortcuts() -> None:
    assert not hasattr(src_graph, "build_guardrail_response")
    assert not hasattr(src_graph, "build_clarification_response")
