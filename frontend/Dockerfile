# Stage 1: Build React static assets
FROM node:20-alpine AS builder

WORKDIR /app

# Copy dependency definitions
COPY package.json package-lock.json ./

# Install exact dependencies
RUN npm ci

# Copy application source code and config
COPY index.html vite.config.js ./
COPY public/ ./public/
COPY src/ ./src/

# Build static bundle for production
RUN npm run build

# Stage 2: Serve with ultra-lightweight Nginx Alpine
FROM nginx:alpine AS runtime

# Remove default nginx HTML files
RUN rm -rf /usr/share/nginx/html/*

# Copy compiled files from builder
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy custom Nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 5173

CMD ["nginx", "-g", "daemon off;"]
