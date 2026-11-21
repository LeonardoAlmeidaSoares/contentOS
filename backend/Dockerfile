FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
# FFmpeg (montagem), eSpeak NG (voz de reserva) e fontes para legendas
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg espeak-ng fonts-dejavu-core curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Piper (TTS neural local, gratuito) + voz pt_BR (rhasspy/piper-voices, licença permissiva). Se o download falhar, o eSpeak assume.
RUN pip install --no-cache-dir piper-tts==1.3.0 pathvalidate || true
RUN mkdir -p /opt/piper && cd /opt/piper && \
    (curl -fsSL -O https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx \
     && curl -fsSL -O https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx.json) || true
COPY . .
