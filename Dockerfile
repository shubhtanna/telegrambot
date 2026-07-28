# Railway auto-detects a Dockerfile in the repo root and uses it instead
# of its default Python build — that's what actually fixes this, since
# the default build only runs "pip install" and never downloads the
# Chromium browser binary or its Linux system libraries.

FROM python:3.13-slim

WORKDIR /app

# Playwright's browser installer needs these to fetch packages over
# HTTPS during the build step below.
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Chromium + Google Chrome along with all required Linux dependencies
RUN python -m playwright install --with-deps chromium chrome

COPY . .

CMD ["python", "start_all.py"]