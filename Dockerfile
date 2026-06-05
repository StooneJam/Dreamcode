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

# pip install 后立即重建 matplotlib 字体缓存，使 Noto CJK 生效
RUN pip install --no-cache-dir . && \
    python -c "import matplotlib.font_manager as fm; fm._rebuild()"

CMD ["uvicorn", "app.server:app", "--host", "0.0.0.0", "--port", "8080"]
