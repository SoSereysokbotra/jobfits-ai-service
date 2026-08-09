import time
import runpod
import requests
import subprocess
import os

# Start Ollama server in the background inside the container
subprocess.Popen(["ollama", "serve"])

# Give Ollama a few seconds to start up before accepting requests
time.sleep(3)

def handler(job):
    """
    This is the function that RunPod calls when a request comes in.
    The `job` object contains the payload sent from your FastAPI backend.
    """
    job_input = job.get('input', {})
    
    # We expect the FastAPI to send something like:
    # { "model": "qwen3", "prompt": "Score this resume...", "endpoint": "api/generate" }
    
    endpoint = job_input.get("endpoint", "api/generate")
    
    # Remove 'endpoint' from the payload before sending to Ollama
    if "endpoint" in job_input:
        del job_input["endpoint"]
        
    # Forward the request to the local Ollama instance running inside the container
    ollama_url = f"http://localhost:11434/{endpoint}"
    
    try:
        response = requests.post(ollama_url, json=job_input, timeout=120)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}

# Start the RunPod Serverless worker
runpod.serverless.start({"handler": handler})
