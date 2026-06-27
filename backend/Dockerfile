FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-noto-cjk \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ===== オートリフレーム(YOLOv8)用の依存 =====
# 注意: ultralytics を通常解決で入れると torch を 2.12 + CUDA wheel 群に巻き上げ、
# whisperx/NeMo(torch 2.6 前提) を壊し CPU イメージが数GB肥大する。これを避けるため
# torch は据え置き、ultralytics は --no-deps、torchvision は torch==2.6.0 一致版を CPU
# wheel で固定する。opencv は GUI 版(libGL 依存)が混入しないよう headless のみ入れる。
RUN pip install --no-cache-dir --no-deps torchvision==0.21.0 \
        --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir --no-deps ultralytics==8.4.80 ultralytics-thop \
 && pip install --no-cache-dir opencv-python-headless==4.13.0.92 polars py-cpuinfo

# YOLO の設定/重みは /opt 配下に置く。dev compose は ./backend:/app を volume mount する
# ため /app 配下に焼くと実行時に隠れる。/opt はマウント外なので確実に参照できる。
ENV YOLO_CONFIG_DIR=/opt/ultralytics \
    REFRAME_MODEL_PATH=/opt/models/yolov8n.pt
RUN mkdir -p /opt/ultralytics /opt/models \
 && python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')" \
 && mv yolov8n.pt /opt/models/yolov8n.pt

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
