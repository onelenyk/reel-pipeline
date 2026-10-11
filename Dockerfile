# The engine and its tools in one image; nothing is installed on the host.
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg curl git ca-certificates fonts-noto-core fonts-inter nodejs npm && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir faster-whisper==1.1.1 requests \
 && pip install --no-cache-dir torch==2.1.2 torchaudio==2.1.2 --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir deepfilternet==0.5.6 soundfile "numpy<2"
RUN mkdir -p /opt/rnnoise && curl -fsSL -o /opt/rnnoise/std.rnnn https://raw.githubusercontent.com/GregorR/rnnoise-models/master/somnolent-hogwash-2018-09-01/sh.rnnn
# The graphics renderer's native canvas, kept outside the mounted source tree
RUN mkdir -p /opt/renderer && cd /opt/renderer && npm init -y >/dev/null && npm install --no-audit --no-fund @napi-rs/canvas@0.1.65 >/dev/null
# Person matting (cutting the speaker out of the background)
RUN pip install --no-cache-dir torchvision==0.16.2 --index-url https://download.pytorch.org/whl/cpu
# Floor plans: finding walls and rooms in a picture
RUN pip install --no-cache-dir "opencv-python-headless<4.11" "numpy<2"
# Reading the numbers and the legend printed on a plan
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-ukr && rm -rf /var/lib/apt/lists/*
# Emoji for stickers drawn over the video
RUN apt-get update && apt-get install -y --no-install-recommends fonts-noto-color-emoji && rm -rf /var/lib/apt/lists/*
ENV TORCH_HOME=/work/models/torch NODE_PATH=/opt/renderer/node_modules PYTHONPATH=/work PYTHONUNBUFFERED=1
WORKDIR /work
ENTRYPOINT ["python", "-m", "engine"]
