# Use the official Python slim image for a smaller footprint
FROM python:3.11-slim

# Set environment variables to prevent Python from writing .pyc files
# and to keep stdout/stderr unbuffered
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies including FFmpeg
# FFmpeg is absolutely required for yt-dlp to merge video/audio and extract MP3
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg curl && \
    rm -rf /var/lib/apt/lists/*

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file and install dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application files
COPY . /app/

# Expose the port that Uvicorn will listen on
EXPOSE 8000

# Start the application with Uvicorn, using the PORT environment variable (Render assigns this dynamically)
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
