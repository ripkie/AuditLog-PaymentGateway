import os
from pathlib import Path
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, ValidationError

app = FastAPI(
    title="Telco-Health Connect Payment API",
    description="Integrasi pembayaran dengan gateway simulasi.",
    version="1.1.0",
)

GATEWAY_URL = os.environ["PAYMENT_GATEWAY_URL"].rstrip("/")
API_KEY = Path(
    os.environ["PAYMENT_API_KEY_FILE"]
).read_text(encoding="utf-8").strip()

if not API_KEY:
    raise RuntimeError("API key belum dikonfigurasi")

# Data order simulasi; nominal ditentukan server.
ORDERS = {
    1001: 75000,
    1002: 100000,
}


class PaymentRequest(BaseModel):
    order_id: int = Field(gt=0, strict=True)


class PaymentResponse(BaseModel):
    payment_id: str
    order_id: int = Field(gt=0)
    amount_idr: int = Field(gt=0)
    currency: Literal["IDR"]
    status: Literal["SIMULATED_SUCCESS"]


class ErrorResponse(BaseModel):
    detail: str


@app.get("/health", tags=["Health"])
def health_check():
    """Memeriksa apakah proses API transaksi dapat merespons."""
    return {
        "status": "ok",
        "service": "transaction-service",
    }


@app.post(
    "/v1/payments",
    response_model=PaymentResponse,
    tags=["Payments"],
    responses={
        404: {
            "model": ErrorResponse,
            "description": "Order tidak ditemukan",
        },
        502: {
            "model": ErrorResponse,
            "description": "Komunikasi atau respons gateway tidak valid",
        },
        504: {
            "model": ErrorResponse,
            "description": "Gateway timeout; hasil pembayaran belum diketahui",
        },
    },
)
async def create_payment(payload: PaymentRequest):
    """Kirim nominal order dari server ke gateway.

    Nominal tidak diambil dari input pelanggan. API key dibaca dari
    secret runtime dan dikirim melalui header ke gateway.

    Timeout tidak diulang otomatis karena gateway mungkin sudah
    menerima permintaan. Respons mitra divalidasi sebelum diteruskan.
    """
    amount = ORDERS.get(payload.order_id)

    if amount is None:
        raise HTTPException(
            status_code=404,
            detail="Order tidak ditemukan",
        )

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{GATEWAY_URL}/payments",
                headers={"X-API-Key": API_KEY},
                json={
                    "order_id": payload.order_id,
                    "amount_idr": amount,
                    "currency": "IDR",
                },
            )
            response.raise_for_status()

    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Gateway timeout; hasil pembayaran belum diketahui",
        ) from None

    except httpx.HTTPError:
        raise HTTPException(
            status_code=502,
            detail="Komunikasi dengan gateway gagal",
        ) from None

    try:
        result = PaymentResponse.model_validate(response.json())

    except (ValueError, ValidationError):
        raise HTTPException(
            status_code=502,
            detail="Format respons gateway tidak valid",
        ) from None

    if (
        result.order_id != payload.order_id
        or result.amount_idr != amount
    ):
        raise HTTPException(
            status_code=502,
            detail="Data respons gateway tidak sesuai order",
        )

    return result