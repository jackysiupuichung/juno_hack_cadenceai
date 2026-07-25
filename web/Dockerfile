# syntax=docker/dockerfile:1

FROM node:22-bookworm-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# ---- dev target ----------------------------------------------------------
# What docker-compose runs locally: source is bind-mounted over this, so
# edits apply without a rebuild (see docker-compose.yml). Kept as its own
# stage so the full devDependencies install never has to happen in the
# production image below.
FROM deps AS dev
COPY . .
ENV NODE_ENV=development
EXPOSE 3000
CMD ["npx", "next", "dev", "-H", "0.0.0.0"]

# ---- build stage (production only) ---------------------------------------
FROM deps AS builder
COPY . .
RUN npm run build

# ---- production runtime ---------------------------------------------------
# Default target (`docker build .` with no --target) — a minimal standalone
# server, not the dev toolchain.
FROM node:22-bookworm-slim AS runtime
ENV NODE_ENV=production

RUN useradd --create-home --uid 1000 cadence
WORKDIR /app

COPY --from=builder --chown=cadence:cadence /app/public ./public
COPY --from=builder --chown=cadence:cadence /app/.next/standalone ./
COPY --from=builder --chown=cadence:cadence /app/.next/static ./.next/static

USER cadence

# Hosts inject their own $PORT; 3000 is the fallback for a plain `docker run`.
ENV PORT=3000
ENV HOSTNAME=0.0.0.0
EXPOSE 3000

CMD ["node", "server.js"]
