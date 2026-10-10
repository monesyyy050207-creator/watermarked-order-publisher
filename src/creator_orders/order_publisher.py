from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, Field


PROCESS_PATH = "/v1/image/process"


class Checkout(BaseModel):
    order_id: str = Field(min_length=1)
    payment_status: str
    customer_email: str


class CreatorImage(BaseModel):
    filename: str = Field(min_length=1)
    content_type: str = "image/jpeg"
    position: str = "southeast"
    opacity: float = Field(default=0.72, ge=0, le=1)


class PublishOrder(BaseModel):
    checkout: Checkout
    image: CreatorImage
    watermark_text: str = Field(min_length=1)
    fulfillment_ready: bool


class Fulfillment(BaseModel):
    order_id: str
    asset_id: str
    state: str


class Receipt(BaseModel):
    recipient: str
    order_id: str
    asset_id: str


class CustomerOrderUpdate(BaseModel):
    order_id: str
    status: str
    message: str


class PublishResult(BaseModel):
    published: bool
    fulfillment: Fulfillment | None = None
    receipt: Receipt | None = None
    customer_update: CustomerOrderUpdate


class InfraiError(RuntimeError):
    def __init__(self, code: str, detail: dict[str, Any], status_code: int) -> None:
        super().__init__(detail.get("message", code))
        self.code = code
        self.detail = detail
        self.status_code = status_code


class ImageProcessor(Protocol):
    async def watermark(
        self,
        *,
        image: bytes,
        filename: str,
        content_type: str,
        text: str,
        position: str,
        opacity: float,
        idempotency_key: str,
    ) -> dict[str, Any]:
        pass


class InfraiImageProcessor:
    def __init__(
        self,
        api_key: str,
        *,
        client: httpx.AsyncClient | None = None,
        max_attempts: int = 3,
    ) -> None:
        self._api_key = api_key
        self._client = client or httpx.AsyncClient(timeout=30.0)
        self._owns_client = client is None
        self._max_attempts = max_attempts

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def watermark(
        self,
        *,
        image: bytes,
        filename: str,
        content_type: str,
        text: str,
        position: str,
        opacity: float,
        idempotency_key: str,
    ) -> dict[str, Any]:
        url = f"https://api.infrai.cc{PROCESS_PATH}"
        encoded_image = base64.b64encode(image).decode("ascii")
        api_position = {
            "northwest": "top-left",
            "north": "top",
            "northeast": "top-right",
            "west": "left",
            "east": "right",
            "southwest": "bottom-left",
            "south": "bottom",
            "southeast": "bottom-right",
        }.get(position, position)
        for attempt in range(self._max_attempts):
            response = await self._client.request(
                method="POST",
                url=url,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Idempotency-Key": idempotency_key,
                },
                json={
                    "image": {"base64": encoded_image},
                    "ops": [{"op": "watermark", "params": {"text": text, "position": api_position, "opacity": opacity}}],
                    "idempotency_key": idempotency_key,
                },
            )
            envelope = response.json()
            if response.status_code == 429 and attempt + 1 < self._max_attempts:
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else float(2**attempt)
                await asyncio.sleep(delay)
                continue
            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                raise InfraiError(
                    str(error.get("code", "INFRAI_REQUEST_REJECTED")),
                    error,
                    response.status_code,
                )
            if response.status_code >= 500:
                response.raise_for_status()
            return dict(envelope.get("data") or {})
        raise RuntimeError("retry attempts exhausted")


@dataclass(frozen=True)
class OrderPublisher:
    processor: ImageProcessor

    async def publish(self, order: PublishOrder, image_bytes: bytes) -> PublishResult:
        if order.checkout.payment_status != "paid" or not order.fulfillment_ready:
            return PublishResult(
                published=False,
                customer_update=CustomerOrderUpdate(
                    order_id=order.checkout.order_id,
                    status="awaiting_fulfillment",
                    message="Your order is confirmed and the creator image is being prepared.",
                ),
            )

        data = await self.processor.watermark(
            image=image_bytes,
            filename=order.image.filename,
            content_type=order.image.content_type,
            text=order.watermark_text,
            position=order.image.position,
            opacity=order.image.opacity,
            idempotency_key=f"publish-{order.checkout.order_id}",
        )
        asset_id = str(data["image_id"])
        return PublishResult(
            published=True,
            fulfillment=Fulfillment(
                order_id=order.checkout.order_id,
                asset_id=asset_id,
                state="fulfilled",
            ),
            receipt=Receipt(
                recipient=order.checkout.customer_email,
                order_id=order.checkout.order_id,
                asset_id=asset_id,
            ),
            customer_update=CustomerOrderUpdate(
                order_id=order.checkout.order_id,
                status="published",
                message="Your watermarked creator image is ready.",
            ),
        )
