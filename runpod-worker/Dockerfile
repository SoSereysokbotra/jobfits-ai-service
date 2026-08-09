# Start with a lightweight Ubuntu image with Nvidia CUDA drivers
FROM nvidia/cuda:11.8.0-runtime-ubuntu22.04

# Install basic dependencies (curl, python, zstd)
RUN apt-get update && apt-get install -y \
    curl \
    zstd \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Install Ollama
RUN curl -fsSL https://ollama.com/install.sh | sh

# Set the working directory
WORKDIR /app

# Copy our python requirements
COPY requirements.txt .

# Install the python libraries (runpod, requests)
RUN pip3 install -r requirements.txt

# Start Ollama server in the background and pull the specific models!
# (This bakes the models directly into the Docker image so they don't have to download every time the GPU wakes up)
RUN nohup bash -c "ollama serve &" && sleep 5 && \
    ollama pull qwen3 && \
    ollama pull bge-m3

# Copy the handler script
COPY handler.py .

# Tell the container what to do when it starts
CMD [ "python3", "-u", "handler.py" ]
