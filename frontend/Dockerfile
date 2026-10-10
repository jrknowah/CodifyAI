FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci --legacy-peer-deps
COPY . .
RUN npm run build

FROM nginx:alpine
RUN apk add --no-cache ca-certificates
COPY --from=builder /app/dist /usr/share/nginx/html
# nginx:alpine renders /etc/nginx/templates/*.template with env vars at startup
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
