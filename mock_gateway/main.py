import os
import secrets
from pathlib import Path
from threading import Lock
from typing import Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

app = FastAPI(
    title="Mock Payment Gateway",
    description="Simulasi pembayaran untuk Task 12.",
    version="1.1.0",
)

API_KEY = Path(
    os.environ["PAYMENT_API_KEY_FILE"]
).read_text(encoding="utf-8").strip()

if not API_KEY:
    raise RuntimeError("API key belum dikonfigurasi")

key_header = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
)

# Penyimpanan sementara untuk satu proses gateway.
payments: dict[int, dict] = {}
payment_lock = Lock()


def verify_api_key(key: str | None = Depends(key_header)):
    """Verifikasi API key tanpa mencatat nilainya ke log."""
    if not key or not secrets.compare_digest(
        key.encode("utf-8"),
        API_KEY.encode("utf-8"),
    ):
        raise HTTPException(
            status_code=401,
            detail="API key tidak valid",
            headers={"WWW-Authenticate": "APIKey"},
        )


class GatewayRequest(BaseModel):
    order_id: int = Field(gt=0, strict=True)
    amount_idr: int = Field(gt=0, strict=True)
    currency: Literal["IDR"] = "IDR"


class GatewayResponse(GatewayRequest):
    payment_id: str
    status: Literal["SIMULATED_SUCCESS"]


class ErrorResponse(BaseModel):
    detail: str


@app.get("/health", tags=["Health"])
def health_check():
    """Memeriksa apakah proses gateway dapat merespons."""
    return {
        "status": "ok",
        "service": "mock-payment-gateway",
    }


@app.post(
    "/payments",
    response_model=GatewayResponse,
    dependencies=[Depends(verify_api_key)],
    tags=["Payments"],
    responses={
        401: {
            "model": ErrorResponse,
            "description": "API key tidak tersedia atau tidak valid",
        },
        409: {
            "model": ErrorResponse,
            "description": "Nominal berbeda untuk order yang sama",
        },
    },
)
def create_payment(payload: GatewayRequest):
    """Buat pembayaran simulasi sekali untuk setiap order.

    Lock melindungi pemeriksaan dan penyimpanan dari permintaan
    bersamaan dalam satu proses. Order berulang dengan nominal sama
    mengembalikan hasil sebelumnya; nominal berbeda ditolak.

    Data tersimpan dalam memori dan hilang saat proses direstart.
    """
    with payment_lock:
        existing = payments.get(payload.order_id)

        if existing is not None:
            if existing["amount_idr"] != payload.amount_idr:
                raise HTTPException(
                    status_code=409,
                    detail="Nominal order tidak konsisten",
                )

            return existing

        result = {
            **payload.model_dump(),
            "payment_id": str(uuid4()),
            "status": "SIMULATED_SUCCESS",
        }

        payments[payload.order_id] = result
        return result