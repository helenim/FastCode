FROM python:3.12-slim-bookworm

# Install system dependencies for tree-sitter and git
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git \
        build-essential \
        curl \
        ca-certificates && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first for better Docker layer caching
COPY requirements.txt ./
RUN pip install --no-cache-dir --retries 5 --timeout 60 -r requirements.txt

# Install ebridge-shared (provides ebridge_auth.KeycloakAuth used by api.py).
# The `shared` build context is wired in compose via:
#     additional_contexts:
#       shared: ./shared
# When building outside compose, pass it via:
#     docker build --build-context shared=../shared .
COPY --from=shared / /tmp/shared/
RUN pip install --no-cache-dir --no-deps /tmp/shared/ && rm -rf /tmp/shared/

# Pre-download the embedding model BEFORE copying app code
# so that code changes don't invalidate this ~470MB cached layer
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')"

# Create non-root user and necessary directories
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --shell /bin/bash --create-home appuser && \
    mkdir -p /app/repos /app/data /app/logs && \
    chown -R appuser:appuser /app

# Copy application code (changes here won't re-download the model)
COPY --chown=appuser:appuser fastcode/ fastcode/
COPY --chown=appuser:appuser api.py ./
COPY --chown=appuser:appuser config/ config/

# Default port for FastCode API
EXPOSE 8001

# Environment defaults (can be overridden in docker-compose)
ENV PYTHONUNBUFFERED=1
ENV TOKENIZERS_PARALLELISM=false

USER appuser
CMD ["python", "api.py", "--host", "0.0.0.0", "--port", "8001"]
