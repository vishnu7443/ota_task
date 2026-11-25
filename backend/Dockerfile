FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir uv

COPY pyproject.toml ./
RUN uv pip install --system --no-cache .

COPY . .

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && python -m app.seeds.benchmark_seed && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
