# syntax=docker/dockerfile:1.7
# Isolated regression-test validator. Accepts JSON specs only; reaches the demo fixtures only
# (sandbox network, no egress). Official Playwright image; version matches package.json pin.
FROM mcr.microsoft.com/playwright:v1.64.1-noble
ENV NODE_ENV=production PLAYWRIGHT_BROWSERS_PATH=/ms-playwright HOST=0.0.0.0 PORT=4300
WORKDIR /app
COPY test-runner/package.json test-runner/package-lock.json ./
RUN npm ci --ignore-scripts --omit=dev
COPY test-runner/src ./src
RUN mkdir -p /app/.work && chown -R pwuser /app/.work
USER pwuser
EXPOSE 4300
CMD ["node", "src/server.mjs"]
