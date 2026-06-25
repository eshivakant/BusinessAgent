FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src

WORKDIR /app

RUN adduser --disabled-password --gecos "" appuser

COPY requirements.lock ./requirements.lock
RUN pip install --upgrade pip && pip install -r requirements.lock

COPY pyproject.toml ./pyproject.toml
COPY README.md ./README.md
COPY src ./src

USER appuser
EXPOSE 8080

CMD ["uvicorn", "business_agent.main:app", "--host", "0.0.0.0", "--port", "8080"]

