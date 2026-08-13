# Slim Python base - smaller image, faster pulls on a small EC2 instance.
FROM python:3.12-slim

WORKDIR /app

# Install dependencies first, separately from app code, so Docker's layer cache means
# `pip install` only re-runs when requirements.txt actually changes, not on every code edit.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Now copy the actual app: backend code, migrations, and the static frontend.
COPY app/ ./app/
COPY frontend/ ./frontend/
COPY alembic/ ./alembic/
COPY alembic.ini .

EXPOSE 8000

# Run pending migrations, THEN start the server. If migrations fail, the container exits
# immediately instead of serving against a schema that doesn't match the code.
CMD alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000
