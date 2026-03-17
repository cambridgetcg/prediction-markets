FROM python:3.12-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements-pipeline.txt .
RUN pip install --no-cache-dir -r requirements-pipeline.txt

# App code
COPY scripts/ scripts/
COPY config/ config/
COPY sources/ sources/
COPY prompts/truth_extraction_brave.txt prompts/

# Data dir (mount as volume)
RUN mkdir -p data

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python3", "scripts/orchestrator.py"]
CMD ["--config", "config/news-pipeline.yaml"]
