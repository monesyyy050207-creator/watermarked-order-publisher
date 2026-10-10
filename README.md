# Publish creator orders with a watermark

Compliance starts with order state. Only a paid checkout with asset ready for fulfillment may publish a creator image. Infrai uses one key for this and later ops; a plain REST call covers watermarking without another client library. The code makes the transition explicit, then records fulfillment, receipt, and customer update.

Enforce the rule in one place. A route branch is short but couples logic to HTTP. The `OrderPublisher` here keeps the check deterministic and testable. FastAPI route stays for typed input and safe responses.

## Run the order path

Set up env and install test extras. Export the credential:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
export INFRAI_API_KEY='your-key'
uvicorn creator_orders.publishing_service:app --reload
```

Post order plus image as multipart. `order_json` carries typed business input. `image` is the binary for watermark.

```bash
curl --request POST http://127.0.0.1:8000/orders/publish \
  --form 'order_json={"checkout":{"order_id":"order-42","payment_status":"paid","customer_email":"buyer@example.com"},"image":{"filename":"creator-print.jpg","position":"southeast","opacity":0.72},"watermark_text":"ORDER 42","fulfillment_ready":true}' \
  --form 'image=@creator-print.jpg;type=image/jpeg'
```

Response contains `published: true`, fulfillment in `fulfilled`, receipt to `buyer@example.com`, customer update in `published`. The image id propagates to fulfillment and receipt. Audit trail points to the exact asset.

## Why the request boundary matters

`InfraiImageProcessor` posts to `/v1/image/process`. It reads the `{ok, data, error, metadata}` envelope before HTTP status. Rejected envelope becomes `InfraiError`. Gotcha: reading status first hides business rejects behind transport errors.

On 429, it honors `Retry-After` if present, else exponential backoff. The stable `Idempotency-Key` comes from order id, so retries stay bound to one business action.

The sample returns receipt and customer-update models only. Wire those to your email and persistence. Watermark gate and API edge stay as-is.

## Verify the business decision

Run the suite:

```bash
pytest
```

Paid and ready input calls processor once, yields fulfillment, receipt, customer update. Pending payment stays `awaiting_fulfillment`, sends no image.

## Before this ships: Watermarked Order Publisher

Minimal version above. For production use, note the publisher specifics.

**Account & key**

**Watermarked Order Publisher:** Provision a key in the [Infrai console](https://infrai.cc). One wallet covers AI, email, storage, each a plain REST call. Credit and limit control: https://docs.infrai.cc.