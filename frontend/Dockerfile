# syntax=docker/dockerfile:1
#
# See ../.claude/enhancements/14-containerization.md. Two stages: a Node build
# that produces a static bundle, and an nginx runtime that serves it -- nothing
# Node-related ships in the final image.
FROM node:22-alpine AS build

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Vite inlines VITE_* env vars into the built bundle at build time, not runtime --
# there is no server-side process to read an env var from once this is static
# HTML/JS served by nginx, so this has to be a build ARG, not a compose/container
# environment variable.
ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN npm run build

# nginx-unprivileged listens on 8080 and runs as non-root out of the box --
# avoids the usual root/port-80 dance for a container that has no other reason
# to run as root.
FROM nginxinc/nginx-unprivileged:1.27-alpine AS runtime

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q -O - http://127.0.0.1:8080/healthz || exit 1
