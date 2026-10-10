import json
import os

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import ValidationError

from .order_publisher import InfraiError, InfraiImageProcessor, OrderPublisher, PublishOrder, PublishResult


app = FastAPI(title="Creator order publisher")


@app.post("/orders/publish", response_model=PublishResult)
async def publish_order(
    order_json: str = Form(),
    image: UploadFile = File(),
) -> PublishResult:
    try:
        order = PublishOrder.model_validate(json.loads(order_json))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail="Invalid order request") from exc

    api_key = os.environ.get("INFRAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="INFRAI_API_KEY is required")

    processor = InfraiImageProcessor(api_key)
    try:
        return await OrderPublisher(processor).publish(order, await image.read())
    except InfraiError as exc:
        client_status = exc.status_code if 400 <= exc.status_code < 500 else 502
        raise HTTPException(
            status_code=client_status,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    finally:
        await processor.close()

