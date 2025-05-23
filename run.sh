#!/bin/bash
# Script to run YeongjoPT with Gradio Web Interface

# Load configuration from config.py if available
if [ -f "config.py" ]; then
    # Extract values from config.py (simplified approach)
    DEFAULT_MODEL_PATH=$(python3 -c "from config import settings; print(settings.DEFAULT_MODEL_PATH)" 2>/dev/null || echo "mistralai/Mistral-7B-Instruct-v0.1")
    CONTROLLER_PORT=$(python3 -c "from config import settings; print(settings.CONTROLLER_PORT)" 2>/dev/null || echo "21001")
    MODEL_WORKER_PORT=$(python3 -c "from config import settings; print(settings.MODEL_WORKER_PORT)" 2>/dev/null || echo "21002")
    GRADIO_PORT=$(python3 -c "from config import settings; print(settings.GRADIO_PORT)" 2>/dev/null || echo "7860")
    HOST_IP=$(python3 -c "from config import settings; print(settings.HOST)" 2>/dev/null || echo "0.0.0.0")
    YEONGJOPT_MODEL_NAME=$(python3 -c "from config import settings; print(settings.MODEL_NAME)" 2>/dev/null || echo "yeongjopt-mistral-7b")
    WORKER_CONCURRENCY=$(python3 -c "from config import settings; print(settings.WORKER_CONCURRENCY)" 2>/dev/null || echo "5")
    LOG_DIR=$(python3 -c "from config import settings; print(settings.LOG_DIR)" 2>/dev/null || echo "./logs")
else
    # Fallback to default values
    DEFAULT_MODEL_PATH="mistralai/Mistral-7B-Instruct-v0.1"
    CONTROLLER_PORT=21001
    MODEL_WORKER_PORT=21002
    GRADIO_PORT=7860
    HOST_IP="0.0.0.0"
    YEONGJOPT_MODEL_NAME="yeongjopt-mistral-7b"
    WORKER_CONCURRENCY=5
    LOG_DIR="./logs"
fi

# Override with command line argument if provided
MODEL_PATH=${1:-$DEFAULT_MODEL_PATH}

# Addresses
CONTROLLER_URL="http://${HOST_IP}:${CONTROLLER_PORT}"
MODEL_WORKER_URL="http://${HOST_IP}:${MODEL_WORKER_PORT}"

# Create logs directory
mkdir -p $LOG_DIR

echo "Starting YeongjoPT Gradio Web Interface..."
echo "Model: $MODEL_PATH"
echo "Model Name: $YEONGJOPT_MODEL_NAME"
echo "Gradio Port: $GRADIO_PORT"
echo "Controller: $CONTROLLER_URL"
echo "Worker: $MODEL_WORKER_URL"
echo "Logs: $LOG_DIR"

# Function to cleanup on exit
cleanup() {
    echo "Shutting down YeongjoPT services..."
    if [ ! -z "$CONTROLLER_PID" ]; then kill $CONTROLLER_PID 2>/dev/null; fi
    if [ ! -z "$MODEL_WORKER_PID" ]; then kill $MODEL_WORKER_PID 2>/dev/null; fi
    if [ ! -z "$GRADIO_PID" ]; then kill $GRADIO_PID 2>/dev/null; fi
    wait
    echo "All YeongjoPT services shut down."
}

# Set up signal handlers
trap cleanup EXIT INT TERM

# 1. Launch Controller
echo "Starting Controller on port ${CONTROLLER_PORT}..."
python3 -m fastchat.serve.controller \
    --host ${HOST_IP} \
    --port ${CONTROLLER_PORT} > ${LOG_DIR}/controller.log 2>&1 & 
CONTROLLER_PID=$!
echo "Controller PID: $CONTROLLER_PID"
sleep 5

# 2. Launch Model Worker
echo "Starting Model Worker with model ${MODEL_PATH}..."
python3 -m fastchat.serve.model_worker \
    --host ${HOST_IP} \
    --port ${MODEL_WORKER_PORT} \
    --worker-address ${MODEL_WORKER_URL} \
    --controller-address ${CONTROLLER_URL} \
    --model-path ${MODEL_PATH} \
    --model-names ${YEONGJOPT_MODEL_NAME} \
    --limit-worker-concurrency ${WORKER_CONCURRENCY} > ${LOG_DIR}/worker.log 2>&1 &
MODEL_WORKER_PID=$!
echo "Model Worker PID: $MODEL_WORKER_PID"
sleep 20

# 3. Launch Gradio Web Server
echo "Starting Gradio Web Server on port ${GRADIO_PORT}..."
python3 -m fastchat.serve.gradio_web_server \
    --host ${HOST_IP} \
    --port ${GRADIO_PORT} \
    --controller-url ${CONTROLLER_URL} \
    --share > ${LOG_DIR}/gradio.log 2>&1 &
GRADIO_PID=$!
echo "Gradio Server PID: $GRADIO_PID"

echo ""
echo "🚀 YeongjoPT Gradio Interface is running!"
echo "🌐 Web Interface: http://${HOST_IP}:${GRADIO_PORT}"
echo "📁 Logs directory: ${LOG_DIR}"
echo ""
echo "Press Ctrl+C to stop all services"

# Wait for any process to exit
wait -n

# Cleanup will be called automatically due to trap 