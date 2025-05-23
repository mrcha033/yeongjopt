#!/bin/bash
# Script to run YeongjoPT as OpenAI API compatible backend

# Load configuration
source config.py 2>/dev/null || true

# Default configuration (can be overridden by arguments or environment variables)
DEFAULT_MODEL_PATH=${MODEL_PATH:-"mistralai/Mistral-7B-Instruct-v0.1"}
MODEL_PATH=${1:-$DEFAULT_MODEL_PATH}

# Ports
CONTROLLER_PORT=${CONTROLLER_PORT:-21001}
MODEL_WORKER_PORT=${MODEL_WORKER_PORT:-21002}
API_PORT=${API_PORT:-8000}

# Addresses
HOST_IP=${HOST:-"0.0.0.0"}
CONTROLLER_URL="http://${HOST_IP}:${CONTROLLER_PORT}"
MODEL_WORKER_URL="http://${HOST_IP}:${MODEL_WORKER_PORT}"

# Model configuration
YEONGJOPT_MODEL_NAME=${MODEL_NAME:-"yeongjopt-mistral-7b"}
WORKER_CONCURRENCY=${WORKER_CONCURRENCY:-5}

# API Key (optional)
API_KEY=${API_KEY:-""}

# Logging
LOG_DIR=${LOG_DIR:-"./logs"}
mkdir -p $LOG_DIR

echo "Starting YeongjoPT OpenAI API Backend..."
echo "Model: $MODEL_PATH"
echo "Model Name: $YEONGJOPT_MODEL_NAME"
echo "API Port: $API_PORT"
echo "Controller: $CONTROLLER_URL"
echo "Worker: $MODEL_WORKER_URL"

# Function to cleanup on exit
cleanup() {
    echo "Shutting down YeongjoPT services..."
    if [ ! -z "$CONTROLLER_PID" ]; then kill $CONTROLLER_PID 2>/dev/null; fi
    if [ ! -z "$MODEL_WORKER_PID" ]; then kill $MODEL_WORKER_PID 2>/dev/null; fi
    if [ ! -z "$API_SERVER_PID" ]; then kill $API_SERVER_PID 2>/dev/null; fi
    wait
    echo "All services shut down."
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

# 3. Launch OpenAI API Server
echo "Starting OpenAI API Server on port ${API_PORT}..."
API_KEY_ARG=""
if [ ! -z "$API_KEY" ]; then
    API_KEY_ARG="--api-key $API_KEY"
    echo "API Key authentication enabled"
fi

python3 -m fastchat.serve.openai_api_server \
    --host ${HOST_IP} \
    --port ${API_PORT} \
    --controller-address ${CONTROLLER_URL} \
    ${API_KEY_ARG} > ${LOG_DIR}/api_server.log 2>&1 &
API_SERVER_PID=$!
echo "API Server PID: $API_SERVER_PID"

echo ""
echo "🚀 YeongjoPT API Backend is running!"
echo "📝 OpenAI API Endpoint: http://${HOST_IP}:${API_PORT}"
echo "📊 Health Check: http://${HOST_IP}:${API_PORT}/health"
echo "📋 Available Models: http://${HOST_IP}:${API_PORT}/v1/models"
echo "📁 Logs directory: ${LOG_DIR}"
echo ""
echo "Example usage:"
echo "curl -X POST http://${HOST_IP}:${API_PORT}/v1/chat/completions \\"
echo "  -H 'Content-Type: application/json' \\"
if [ ! -z "$API_KEY" ]; then
    echo "  -H 'Authorization: Bearer ${API_KEY}' \\"
fi
echo "  -d '{"
echo "    \"model\": \"${YEONGJOPT_MODEL_NAME}\","
echo "    \"messages\": [{\"role\": \"user\", \"content\": \"Hello!\"}]"
echo "  }'"
echo ""
echo "Press Ctrl+C to stop all services"

# Wait for any process to exit
wait -n

# Cleanup will be called automatically due to trap 