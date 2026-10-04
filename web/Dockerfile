# deps: every dependency at /, so a checkout mounted anywhere below resolves /node_modules.
FROM node:22-alpine AS deps
WORKDIR /
COPY package.json package-lock.json ./
RUN npm ci

# test: what CI runs the typecheck and the tests in (test-docker mounts the checkout at /src).
FROM deps AS test
ENV PATH=/node_modules/.bin:$PATH
WORKDIR /src/web
COPY . .

# build: the static app. The base path is baked into the asset URLs, so it is a build argument.
FROM deps AS build
ARG VITE_BASE_PATH=/memoir/
ENV VITE_BASE_PATH=$VITE_BASE_PATH PATH=/node_modules/.bin:$PATH
WORKDIR /app
COPY . .
RUN npm run build

# The image: an unprivileged nginx serving the app under the base path. It also forwards
# <base>api/ to the API, so the app works with no other proxy in front (local compose).
FROM nginxinc/nginx-unprivileged:1.29-alpine
ARG VITE_BASE_PATH=/memoir/
ENV BASE_PATH=$VITE_BASE_PATH API_UPSTREAM=http://memoir-api:8000
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html${VITE_BASE_PATH}
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s CMD wget -qO- http://127.0.0.1:8080/healthz || exit 1
