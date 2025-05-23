#!/bin/bash
# Script to run the minimal YeongjoPT chatbot

# Default model path (can be overridden by an argument)
DEFAULT_MODEL_PATH="mistralai/Mistral-7B-Instruct-v0.1"
MODEL_PATH=${1:-$DEFAULT_MODEL_PATH}

# Ports (ensure they are free)
CONTROLLER_PORT=21001
MODEL_WORKER_PORT=21002
GRADIO_PORT=7860

# Addresses
HOST_IP="0.0.0.0" # Listen on all interfaces, or use 127.0.0.1 for local only
CONTROLLER_URL="http://${HOST_IP}:${CONTROLLER_PORT}"
MODEL_WORKER_URL="http://${HOST_IP}:${MODEL_WORKER_PORT}"

# Model name that worker registers and Gradio server looks for
# This should match what global_fixed_model_name in gradio_web_server.py expects
# or what the controller will report based on the worker's registration.
# For simplicity, let's use a consistent name passed to the worker.
YEONGJOPT_MODEL_NAME="yeongjopt-mistral-7b"

echo "Starting YeongjoPT components..."

# 1. Launch Controller
echo "Starting Controller on port ${CONTROLLER_PORT}..."
python3 -m fastchat.serve.controller --host ${HOST_IP} --port ${CONTROLLER_PORT} & 
CONTROLLER_PID=$!
sleep 5 # Give controller time to start

# 2. Launch Model Worker
echo "Starting Model Worker with model ${MODEL_PATH} on port ${MODEL_WORKER_PORT}..."
echo "Model will be registered as: ${YEONGJOPT_MODEL_NAME}"
# The --model-names argument in model_worker.py (if derived from add_model_args) is used for registration.
# We pass a single name here.
python3 -m fastchat.serve.model_worker \
    --host ${HOST_IP} \
    --port ${MODEL_WORKER_PORT} \
    --worker-address ${MODEL_WORKER_URL} \
    --controller-address ${CONTROLLER_URL} \
    --model-path ${MODEL_PATH} \
    --model-names ${YEONGJOPT_MODEL_NAME} \
    --limit-worker-concurrency 5 & # Adjust concurrency as needed
MODEL_WORKER_PID=$!
sleep 20 # Give model worker time to load model and register

# 3. Launch Gradio Web Server
echo "Starting Gradio Web Server on port ${GRADIO_PORT}..."
python3 -m fastchat.serve.gradio_web_server \
    --host ${HOST_IP} \
    --port ${GRADIO_PORT} \
    --controller-url ${CONTROLLER_URL} \
    --share # Optional: remove if you don't want a public link
GRADIO_PID=$!

echo "YeongjoPT services started."
echo "Controller PID: ${CONTROLLER_PID}"
echo "Model Worker PID: ${MODEL_WORKER_PID}"
echo "Gradio Server PID: ${GRADIO_PID}"
echo "Access YeongjoPT at http://${HOST_IP}:${GRADIO_PORT} (or 127.0.0.1 if HOST_IP is 0.0.0.0)"

# Wait for any process to exit
wait -n

# Cleanup on exit
echo "One of the YeongjoPT services has exited. Shutting down others..."
kill $CONTROLLER_PID $MODEL_WORKER_PID $GRADIO_PID
wait
echo "All YeongjoPT services shut down." 