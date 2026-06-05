FROM python:3.11-slim

# weasyprint 系统库 + Noto CJK 字体（matplotlib 图表和 weasyprint PDF 中文渲染）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    fonts-noto-cjk \
    && fc-cache -fv \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .

RUN pip install --no-cache-dir . && \
    python -c "import matplotlib, shutil; shutil.rmtree(matplotlib.get_cachedir(), ignore_errors=True)"

CMD ["uvicorn", "app.server:app", "--host", "0.0.0.0", "--port", "8080"]
