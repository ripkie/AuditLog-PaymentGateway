FROM python:3.12-slim-bookworm AS builder

WORKDIR /build

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.lock .
RUN pip install --no-cache-dir --require-hashes -r requirements.lock


FROM python:3.12-slim-bookworm AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home app

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=10001:10001 app/ ./app/
COPY --chown=10001:10001 mock_gateway/ ./mock_gateway/

USER 10001:10001

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]