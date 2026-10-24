FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    API_HOST=0.0.0.0 \
    API_PORT=8000

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY sql ./sql

RUN pip install --no-cache-dir .

RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

CMD ["humanitarian-api"]
