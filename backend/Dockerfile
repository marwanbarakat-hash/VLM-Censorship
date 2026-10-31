# Stage 1: Compile Native C++ ASan Binary
FROM ubuntu:24.04 AS builder

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    clang \
    libclang-rt-dev \
    libopencv-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src/native
COPY native/ .

RUN mkdir -p build && cd build && \
    cmake -DCMAKE_CXX_COMPILER=clang++ .. && \
    cmake --build .


# Stage 2: Python Runtime + Dependencies
FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    libasan8 \
    libubsan1 \
    libopencv-core-dev \
    libopencv-imgproc-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy compiled ASan C++ binary from builder
COPY --from=builder /src/native/build/censor_engine /app/native/build/censor_engine

# Install Python requirements (including CLIP)
COPY backend/requirements.txt /app/backend/
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# Copy backend code and weights
COPY backend/ /app/backend/

WORKDIR /app/backend
EXPOSE 8080

CMD ["python", "main.py"]