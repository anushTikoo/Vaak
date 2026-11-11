# Vaak (वाक्) — API Interface Contracts

All endpoints are hosted by the FastAPI backend on Cloudflare Python Workers.

Base Local URL: `http://localhost:8000`

---

## 1. Health & Status

### `GET /health`
Returns root container / worker health.
- **Response `200 OK`**:
```json
{
  "status": "healthy",
  "service": "vaak-backend",
  "environment": "development"
}
```

### `GET /api/v1/health`
Detailed subsystem health and integration status.
- **Response `200 OK`**:
```json
{
  "status": "healthy",
  "version": "v1",
  "integrations": {
    "sarvam": "configured",
    "zepto_mcp": "ready",
    "database": "unconfigured"
  }
}
```

---

## 2. User & Session

### `GET /api/v1/me`
Retrieves current user identity and integration auth status.
- **Response `200 OK`**:
```json
{
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "phone_number": "+91 98765 43210",
  "is_zepto_authenticated": false,
  "preferred_language": "en-IN"
}
```

---

## 3. Voice Infrastructure

### `POST /api/v1/voice/session`
Initiates a new voice session.
- **Request Body**:
```json
{
  "language_code": "auto"
}
```
- **Response `200 OK`**:
```json
{
  "session_id": "c1f729f2-2ea9-42b4-82a1-fae792b0fa1a",
  "ws_endpoint": "/api/v1/voice/stream",
  "status": "ready",
  "active_language": "auto"
}
```

### `POST /api/v1/voice/transcribe`
Multipart file upload for discrete audio chunk transcription.
- **Request**: `audio: UploadFile (wav/m4a/webm)`
- **Response `200 OK`**:
```json
{
  "session_id": "c1f729f2-2ea9-42b4-82a1-fae792b0fa1a",
  "transcript": "I need two litres of milk and six eggs",
  "detected_language": "en-IN",
  "confidence": 0.95
}
```

---

## 4. Conversational Chat & Intent

### `POST /api/v1/chat/message`
Processes natural language text input, executes product matching through Zepto MCP, and returns suggested actions.
- **Request Body**:
```json
{
  "session_id": "c1f729f2-2ea9-42b4-82a1-fae792b0fa1a",
  "message": "Add 2 packets of brown bread",
  "language": "auto"
}
```
- **Response `200 OK`**:
```json
{
  "session_id": "c1f729f2-2ea9-42b4-82a1-fae792b0fa1a",
  "reply_text": "I found 2 matching items on Zepto for 'Add 2 packets of brown bread'. Would you like me to add them to your cart?",
  "suggested_products": [
    {
      "product_id": "z_bread_brown_400g",
      "name": "The Health Factory Zero Maida Brown Bread",
      "price": 55.0,
      "pack_size": "400 g",
      "image_url": "https://cdn.zeptonow.com/catalog/bread.jpg",
      "is_available": true
    }
  ],
  "action_type": "clarification_needed"
}
```

---

## 5. Shopping Cart Management

### `GET /api/v1/cart`
Returns the active shopping cart and calculated subtotal.
- **Response `200 OK`**:
```json
{
  "items": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "product_id": "z_milk_toned_1l",
      "name": "Amul Taaza Toned Fresh Milk",
      "quantity": 2,
      "unit_price": 54.0,
      "total_price": 108.0,
      "image_url": "https://cdn.zeptonow.com/catalog/milk.jpg",
      "pack_size": "1 L"
    }
  ],
  "currency": "INR",
  "subtotal": 108.0,
  "total_items": 2
}
```

### `POST /api/v1/cart/items`
Adds an item to the shopping cart.
- **Request Body**:
```json
{
  "product_id": "z_eggs_6pk",
  "name": "Eggoz Farm Fresh White Eggs - Pack of 6",
  "quantity": 1,
  "unit_price": 58.0,
  "pack_size": "6 pcs"
}
```

### `PATCH /api/v1/cart/items/{item_id}`
Updates the quantity of an item. Setting quantity to `0` removes it.

### `DELETE /api/v1/cart/items/{item_id}`
Removes an item from the cart.

---

## 6. Orders

### `GET /api/v1/orders`
Retrieves past order records.
- **Response `200 OK`**: `[]`
