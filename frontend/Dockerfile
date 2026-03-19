# ============================================
# Arch Analyzer Frontend Dockerfile (Nginx)
# ============================================
FROM nginx:alpine

# Copy custom Nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy static frontend files
COPY index.html /usr/share/nginx/html/
COPY styles.css /usr/share/nginx/html/
COPY script.js  /usr/share/nginx/html/
COPY fiap-png.png /usr/share/nginx/html/

# Expose port 8051
EXPOSE 8051

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8051 || exit 1

# Start Nginx
CMD ["nginx", "-g", "daemon off;"]