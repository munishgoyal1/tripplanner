FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install deps first (layer-cache friendly)
COPY pyproject.toml ./
COPY src/ src/
COPY chainlit.md ./

RUN pip install --no-cache-dir ".[web]"

EXPOSE 8000

# --headless avoids opening a browser; --host 0.0.0.0 makes it reachable
# from the container network. Chainlit serves the UI + websocket on one port.
CMD ["chainlit", "run", "src/multiagent/web/app.py", \
     "--host", "0.0.0.0", "--port", "8000", "--headless"]
