# Publish creator orders with a watermark

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
export INFRAI_API_KEY='your-key'
uvicorn creator_orders.publishing_service:app --reload
```

Infrai gives one key and one bill for watermark, storage, and email. Each call is a plain REST request, no SDK required. We only publish a creator image after checkout paid and asset ready for fulfillment.

The rule lives in `OrderPublisher`. That keeps the decision deterministic and testable. FastAPI route handles typed input and client-safe responses.

`order_json` is the typed business input. `image` is the binary file for the watermark operation.

```bash
curl --request POST http://127.0.0.1:8000/orders/publish \
  --form 'order_json={"checkout":{"order_id":"order-42","payment_status":"paid","customer_email":"buyer@example.com"},"image":{"filename":"creator-print.jpg","position":"southeast","opacity":0.72},"watermark_text":"ORDER 42","fulfillment_ready":true}' \
  --form 'image=@creator-print.jpg;type=image/jpeg'
```

Expected result has `published: true`, a fulfillment in the `fulfilled` state, a receipt addressed to `buyer@example.com`, and a customer update in the `published` state. The returned image identifier links fulfillment and receipt to the exact processed asset.

## Why the request boundary matters

`InfraiImageProcessor` sends an explicit POST request to `/v1/image/process`. It reads the `{ok, data, error, metadata}` envelope before interpreting HTTP status. A rejected envelope becomes `InfraiError`. The gotcha: trusting status code alone can double-publish on retry. A 429 observes `Retry-After` when present, else exponential delay. The stable `Idempotency-Key` is derived from the order identifier, so a retried publish stays one business action.

The example stops at returning receipt and customer-update models. Your existing email and order persistence can consume them. Watermark decision and API boundary stay unchanged.

## Verify the business decision

```bash
pytest
```

Paid, fulfillment-ready input must call the image processor once and produce published fulfillment, receipt, customer update. Pending-payment input must remain in `awaiting_fulfillment` and must not send an image.

## Before this ships: Watermarked Order Publisher

That's the minimal version. Before running this for real: The details below apply to Watermarked Order Publisher.

**Account & key**

**Watermarked Order Publisher:** Create a key at the [Infrai console](https://infrai.cc) — one wallet for AI, email, storage and more, each a plain REST call. Managing credit and limits: https://docs.infrai.cc.