#build the React frontend
FROM node:20-alpine AS frontend-build

WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm install

COPY frontend/ ./
RUN npm run build


#flask backend
FROM python:3.11-slim

WORKDIR /app

# Install Python dependencies
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copy backend source
COPY backend/ ./

# Copy the built React app into the location Flask expects
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

# Create the db directory
RUN mkdir -p db

# Expose the port Fly.io will route traffic to
EXPOSE 8080

# Run with gunicorn 
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--timeout", "60", "app:app"]
