# Little Chits in a box. Stage 1 builds the observer (web/dist); stage 2 runs the world.
FROM node:22-slim AS web
WORKDIR /src/web
COPY web/package.json web/package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY server/ server/
RUN pip install --no-cache-dir .
COPY --from=web /src/web/dist web/dist
ENV CHITS_DATA_DIR=/data CHITS_WEB_DIST=/app/web/dist
VOLUME /data
EXPOSE 8000
WORKDIR /app/server
# listens on every interface inside the container, so it needs CHITS_TOKEN (or --insecure on a trusted machine)
CMD ["python", "-m", "chits.cli", "--host", "0.0.0.0", "--port", "8000", "--no-browser"]
