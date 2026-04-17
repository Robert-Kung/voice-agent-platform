FROM node:20-alpine AS base

# Install pnpm
RUN npm install -g pnpm@9.15.9

# ── Stage 1: Install dependencies ─────────────────────────────────────────────
FROM base AS deps
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

# ── Stage 2: Build ────────────────────────────────────────────────────────────
FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Build args passed at build time (needed for Next.js build)
ARG LIVEKIT_URL
ARG LIVEKIT_API_KEY
ARG LIVEKIT_API_SECRET
ARG AGENT_NAME
# NEXT_PUBLIC_* 需於 build time 注入（會被編譯進 client bundle）
ARG NEXT_PUBLIC_ADMIN_API_URL=http://localhost:8080

ENV LIVEKIT_URL=$LIVEKIT_URL
ENV LIVEKIT_API_KEY=$LIVEKIT_API_KEY
ENV LIVEKIT_API_SECRET=$LIVEKIT_API_SECRET
ENV AGENT_NAME=$AGENT_NAME
ENV NEXT_PUBLIC_ADMIN_API_URL=$NEXT_PUBLIC_ADMIN_API_URL
ENV NEXT_TELEMETRY_DISABLED=1

RUN pnpm build

# ── Stage 3: Run ──────────────────────────────────────────────────────────────
FROM base AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]
