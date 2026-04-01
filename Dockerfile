FROM python:3.12-slim

WORKDIR /app

# Cài requirements trước (cache layer)
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt && \
    playwright install --with-deps chromium

# Copy source code
COPY backend/ ./backend/

# Tạo thư mục data và logs
RUN mkdir -p backend/data logs

ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "backend.main"]
