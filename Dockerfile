FROM python:3.11-slim

# weasyprint 需要的系统库（Cairo / Pango / GDK-Pixbuf）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .

RUN pip install --no-cache-dir .

CMD ["uvicorn", "app.server:app", "--host", "0.0.0.0", "--port", "8080"]
