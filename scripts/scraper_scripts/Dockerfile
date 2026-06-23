FROM python:3.13-slim

# System libraries Firefox/Camoufox needs, plus the virtual display
RUN apt-get update && apt-get install -y \
    libgtk-3-0 \
    libx11-xcb1 \
    libasound2 \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (cached unless requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bake the Camoufox browser binary into the image at build time
RUN python -m camoufox fetch

# Copy the three scraper scripts in last, so code edits don't bust the cache above
COPY config.py pib_fetcher.py pib_parser.py pib_deep_fetcher.py .

# Run a stage by appending its script name to `docker run`
ENTRYPOINT ["python"]