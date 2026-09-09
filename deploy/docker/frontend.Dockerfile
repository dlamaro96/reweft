FROM node:22.22.2-alpine AS build
WORKDIR /work
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM nginx:1.29.1-alpine
COPY deploy/docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /work/dist /usr/share/nginx/html
EXPOSE 8080
