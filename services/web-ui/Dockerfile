FROM node:22-alpine AS build
WORKDIR /app
COPY services/web-ui/package.json services/web-ui/package-lock.json ./
RUN npm ci
COPY services/web-ui/ ./
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
