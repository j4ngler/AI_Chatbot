# Demo API + demo_web + enterprise_web (build Vite). Vector store: mount volume hoặc COPY data.
FROM node:20-alpine AS erp_web
WORKDIR /build
COPY enterprise_web/package.json ./
RUN npm install
COPY enterprise_web/ ./
RUN npm run build

FROM python:3.12-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api ./api
COPY tools ./tools
COPY demo_web ./demo_web
COPY data ./data
COPY --from=erp_web /build/dist ./enterprise_web/dist

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
