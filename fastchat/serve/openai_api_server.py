"""
OpenAI API compatible server for YeongjoPT
Provides endpoints compatible with OpenAI ChatCompletion API
"""
import argparse
import asyncio
import json
import time
from typing import AsyncGenerator, Dict, List, Optional, Union

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import requests

from fastchat.constants import ErrorCode
from fastchat.protocol.api_protocol import (
    APIChatCompletionRequest,
    APIChatCompletionResponse,
    ChatCompletionResponseChoice,
    ChatCompletionStreamResponse,
    ChatCompletionStreamResponseChoice,
    ChatMessage,
    DeltaMessage,
    UsageInfo,
)
from fastchat.utils import build_logger

logger = build_logger("openai_api_server", "openai_api_server.log")

app = FastAPI(title="YeongjoPT OpenAI API", version="1.0.0")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global variables
controller_address = None
api_key = None

# Security
security = HTTPBearer(auto_error=False)

async def verify_api_key(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if api_key and (not credentials or credentials.credentials != api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True

async def get_worker_address(model_name: str) -> str:
    """Get worker address for the specified model"""
    try:
        response = requests.post(
            f"{controller_address}/get_worker_address",
            json={"model": model_name},
            timeout=10
        )
        response.raise_for_status()
        worker_addr = response.json().get("address", "")
        if not worker_addr:
            raise HTTPException(status_code=404, detail=f"No worker found for model {model_name}")
        return worker_addr
    except requests.RequestException as e:
        logger.error(f"Error getting worker address: {e}")
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

async def generate_stream(
    worker_addr: str, 
    params: Dict
) -> AsyncGenerator[str, None]:
    """Generate streaming response from worker"""
    try:
        response = requests.post(
            f"{worker_addr}/worker_generate_stream",
            json=params,
            stream=True,
            timeout=120
        )
        response.raise_for_status()
        
        for chunk in response.iter_lines(decode_unicode=False, delimiter=b"\0"):
            if chunk:
                data = json.loads(chunk.decode("utf-8"))
                yield data
    except requests.RequestException as e:
        logger.error(f"Error in streaming generation: {e}")
        yield {"text": "Error occurred during generation", "error_code": ErrorCode.INTERNAL_ERROR}

@app.get("/v1/models")
async def list_models(authorized: bool = Depends(verify_api_key)):
    """List available models"""
    try:
        response = requests.post(f"{controller_address}/list_models", timeout=10)
        response.raise_for_status()
        models = response.json()
        
        return {
            "object": "list",
            "data": [
                {
                    "id": model,
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "yeongjopt"
                }
                for model in models
            ]
        }
    except requests.RequestException as e:
        logger.error(f"Error listing models: {e}")
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

@app.post("/v1/chat/completions")
async def create_chat_completion(
    request: APIChatCompletionRequest,
    authorized: bool = Depends(verify_api_key)
):
    """Create chat completion (OpenAI compatible)"""
    
    # Get worker address
    worker_addr = await get_worker_address(request.model)
    
    # Convert messages to prompt
    if isinstance(request.messages, str):
        prompt = request.messages
    else:
        # Convert message format to prompt
        prompt_parts = []
        for msg in request.messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                prompt_parts.append(f"System: {content}")
            elif role == "user":
                prompt_parts.append(f"User: {content}")
            elif role == "assistant":
                prompt_parts.append(f"Assistant: {content}")
        prompt = "\n".join(prompt_parts) + "\nAssistant:"
    
    # Prepare generation parameters
    gen_params = {
        "model": request.model,
        "prompt": prompt,
        "temperature": request.temperature,
        "top_p": request.top_p,
        "max_new_tokens": request.max_tokens or 512,
        "stop": request.stop,
        "stream": request.stream,
        "echo": False,
    }
    
    if request.stream:
        # Streaming response
        async def generate():
            choice_data = ChatCompletionStreamResponseChoice(
                index=0,
                delta=DeltaMessage(role="assistant"),
                finish_reason=None,
            )
            
            chunk = ChatCompletionStreamResponse(
                id=f"chatcmpl-{int(time.time())}",
                choices=[choice_data],
                model=request.model,
            )
            yield f"data: {chunk.json()}\n\n"
            
            # Generate content
            async for data in generate_stream(worker_addr, gen_params):
                if data.get("error_code"):
                    finish_reason = "stop"
                    break
                
                content = data.get("text", "")
                choice_data = ChatCompletionStreamResponseChoice(
                    index=0,
                    delta=DeltaMessage(content=content),
                    finish_reason=None,
                )
                
                chunk = ChatCompletionStreamResponse(
                    id=f"chatcmpl-{int(time.time())}",
                    choices=[choice_data],
                    model=request.model,
                )
                yield f"data: {chunk.json()}\n\n"
                
                if data.get("finish_reason"):
                    break
            
            # Final chunk
            choice_data = ChatCompletionStreamResponseChoice(
                index=0,
                delta=DeltaMessage(),
                finish_reason="stop",
            )
            
            chunk = ChatCompletionStreamResponse(
                id=f"chatcmpl-{int(time.time())}",
                choices=[choice_data],
                model=request.model,
            )
            yield f"data: {chunk.json()}\n\n"
            yield "data: [DONE]\n\n"
        
        return StreamingResponse(generate(), media_type="text/plain")
    
    else:
        # Non-streaming response
        try:
            response = requests.post(
                f"{worker_addr}/worker_generate",
                json=gen_params,
                timeout=120
            )
            response.raise_for_status()
            result = response.json()
            
            if result.get("error_code"):
                raise HTTPException(status_code=500, detail=result.get("text", "Generation failed"))
            
            # Format as OpenAI response
            usage = UsageInfo(
                prompt_tokens=result.get("usage", {}).get("prompt_tokens", 0),
                completion_tokens=result.get("usage", {}).get("completion_tokens", 0),
                total_tokens=result.get("usage", {}).get("total_tokens", 0),
            )
            
            choice = ChatCompletionResponseChoice(
                index=0,
                message=ChatMessage(role="assistant", content=result.get("text", "")),
                finish_reason=result.get("finish_reason", "stop"),
            )
            
            return APIChatCompletionResponse(
                id=f"chatcmpl-{int(time.time())}",
                choices=[choice],
                model=request.model,
                usage=usage,
            )
            
        except requests.RequestException as e:
            logger.error(f"Error in generation: {e}")
            raise HTTPException(status_code=503, detail="Service temporarily unavailable")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": int(time.time())}

def create_app(args):
    global controller_address, api_key
    controller_address = args.controller_address
    api_key = args.api_key
    return app

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OpenAI API compatible server")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind the server")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind the server")
    parser.add_argument("--controller-address", type=str, required=True, help="Controller address")
    parser.add_argument("--api-key", type=str, default=None, help="API key for authentication")
    
    args = parser.parse_args()
    
    app = create_app(args)
    
    logger.info(f"Starting OpenAI API server on {args.host}:{args.port}")
    logger.info(f"Controller address: {args.controller_address}")
    
    uvicorn.run(app, host=args.host, port=args.port) 