# Lab for the pipeline experiments: everything heavy lives in this image, nothing is installed on the Mac.
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg curl ca-certificates fonts-noto-core fonts-inter && rm -rf /var/lib/apt/lists/*
# Speech recognition (CPU), a neural speech denoiser, person segmentation
RUN pip install --no-cache-dir faster-whisper==1.1.1 requests \
 && pip install --no-cache-dir torch==2.1.2 torchaudio==2.1.2 --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir deepfilternet==0.5.6 soundfile "numpy<2"
# RNNoise model for ffmpeg's arnndn filter
RUN mkdir -p /opt/rnnoise && curl -fsSL -o /opt/rnnoise/std.rnnn https://raw.githubusercontent.com/GregorR/rnnoise-models/master/somnolent-hogwash-2018-09-01/sh.rnnn
WORKDIR /work
ENTRYPOINT ["python", "/work/lab/lab.py"]
