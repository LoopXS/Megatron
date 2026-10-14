FROM python:3.14-bookworm

ENV TZ=Asia/Tehran \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /Megatron

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    mediainfo \
    curl \
    git \
    unzip \
    wget \
    tzdata \
    gcc \
    g++ \
    make \
    libffi-dev \
    libssl-dev \
    && ln -snf /usr/share/zoneinfo/${TZ} /etc/localtime \
    && echo ${TZ} > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

# Copy the complete project
COPY . .

# Upgrade pip tooling
RUN python -m pip install --upgrade pip setuptools wheel

# Core dependencies
RUN python -m pip install \
    playwright \
    anyio \
    redis

# Project requirements
RUN python -m pip install -r requirements.txt

# Addons
RUN python -m pip install -r addons.txt

# Verify that the application can at least import
RUN python -m compileall -q .
RUN spotdl --version

EXPOSE 8080

# Start CythonX
CMD ["python", "-m", "CythonX"]
