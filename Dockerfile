FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .
COPY config ./config
ENV PYTHONUNBUFFERED=1 \
    DEADAIR_CONFIG=/app/config \
    DEADAIR_DB=/app/data/deadair.db
VOLUME ["/app/data", "/app/recordings"]
EXPOSE 8000
# PORT is set by Railway/Render; defaults to 8000
CMD ["python", "-m", "deadair", "serve", "--host", "0.0.0.0"]
