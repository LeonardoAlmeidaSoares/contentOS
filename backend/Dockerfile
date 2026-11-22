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
# Vozes Piper pt_BR adicionais (Laboratório de Vozes; mesma fonte/licença) — opcionais, o fallback continua sendo a faber.
RUN cd /opt/piper && for v in cadu jeff; do \
      (curl -fsSL -O https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/$v/medium/pt_BR-$v-medium.onnx \
       && curl -fsSL -O https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/$v/medium/pt_BR-$v-medium.onnx.json) || true; done
# Kokoro 82M (kokoro-onnx, modelo int8 ~92 MB + vozes ~28 MB; download autorizado pelo PO em 2026-11-21).
RUN pip install --no-cache-dir kokoro-onnx || true
RUN mkdir -p /opt/kokoro && cd /opt/kokoro && \
    (curl -fsSL -O https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.int8.onnx \
     && curl -fsSL -O https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin) || true
COPY . .
