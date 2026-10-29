# syntax=docker/dockerfile:1.7
FROM node:24-bookworm-slim AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --ignore-scripts
COPY frontend/ ./
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN npm run build

FROM node:24-bookworm-slim
WORKDIR /app
COPY --from=build /app/dist ./dist
COPY infra/docker/static-server.mjs ./
USER node
EXPOSE 3000
CMD ["node", "static-server.mjs"]
