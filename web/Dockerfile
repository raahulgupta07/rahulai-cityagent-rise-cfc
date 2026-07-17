# CFC Forecaster — Web (SvelteKit, adapter-node)
# Stage 1: build
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Stage 2: runtime
FROM node:20-alpine AS runtime
WORKDIR /app
# adapter-node writes build/ with its own node_modules embed
COPY --from=builder /app/build ./build
COPY --from=builder /app/package.json ./
# adapter-node needs the package.json for the entry point; install prod deps only
RUN npm install --omit=dev --ignore-scripts 2>/dev/null || true

ENV HOST=0.0.0.0
ENV PORT=3000
ENV NODE_ENV=production

EXPOSE 3000
CMD ["node", "build"]
