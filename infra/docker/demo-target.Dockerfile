# syntax=docker/dockerfile:1.7
FROM node:24-bookworm-slim AS build
WORKDIR /app
COPY demo-target/package.json demo-target/package-lock.json ./
RUN npm ci --ignore-scripts
COPY demo-target/ ./
RUN npm run build

FROM node:24-bookworm-slim
ENV NODE_ENV=production
WORKDIR /app
# Only what the server needs at runtime: built bundles, server code and fixed server overlays.
COPY --from=build /app/dist ./dist
COPY --from=build /app/server ./server
COPY --from=build /app/fixtures/fixed/server ./fixtures/fixed/server
COPY --from=build /app/package.json ./
USER node
EXPOSE 4173
CMD ["node", "server/index.mjs", "--port", "4173"]
