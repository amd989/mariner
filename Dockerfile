# Stage 1: Build frontend
FROM node:20-slim AS frontend-builder
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Build Python package
FROM python:3.11-slim AS python-builder
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libffi-dev \
  && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir poetry
WORKDIR /build
COPY pyproject.toml poetry.lock ./
RUN poetry config virtualenvs.in-project true && \
    poetry install --only main --no-root
COPY . .
RUN poetry install --only main

# Stage 3: Runtime
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 libxslt1.1 zlib1g \
  && rm -rf /var/lib/apt/lists/* \
  && useradd -r -s /sbin/nologin -d /nonexistent mariner \
  && usermod -aG dialout mariner

COPY --from=python-builder /build/.venv /opt/venvs/mariner3d
COPY --from=frontend-builder /build/frontend/dist /opt/venvs/mariner3d/dist
COPY config.toml /etc/mariner/config.toml

ENV PATH="/opt/venvs/mariner3d/bin:${PATH}"

EXPOSE 5000
USER mariner
ENTRYPOINT ["mariner"]
