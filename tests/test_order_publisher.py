from typing import Any

import pytest

from creator_orders.order_publisher import OrderPublisher, PublishOrder


class RecordingProcessor:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def watermark(self, **request: Any) -> dict[str, Any]:
        self.calls.append(request)
        return {"image_id": "img_watermarked_42"}


def ready_order(*, payment_status: str = "paid", fulfillment_ready: bool = True) -> PublishOrder:
    return PublishOrder.model_validate(
        {
            "checkout": {
                "order_id": "order-42",
                "payment_status": payment_status,
                "customer_email": "buyer@example.com",
            },
            "image": {"filename": "creator-print.jpg"},
            "watermark_text": "ORDER 42",
            "fulfillment_ready": fulfillment_ready,
        }
    )


@pytest.mark.asyncio
async def test_paid_ready_order_is_watermarked_and_fulfilled() -> None:
    processor = RecordingProcessor()

    result = await OrderPublisher(processor).publish(ready_order(), b"jpeg-content")

    assert result.published is True
    assert result.fulfillment is not None
    assert result.fulfillment.state == "fulfilled"
    assert result.receipt is not None
    assert result.receipt.asset_id == "img_watermarked_42"
    assert result.customer_update.status == "published"
    assert processor.calls[0]["idempotency_key"] == "publish-order-42"


@pytest.mark.asyncio
async def test_unpaid_order_waits_without_processing_image() -> None:
    processor = RecordingProcessor()

    result = await OrderPublisher(processor).publish(
        ready_order(payment_status="pending"), b"jpeg-content"
    )

    assert result.published is False
    assert result.customer_update.status == "awaiting_fulfillment"
    assert processor.calls == []
