"""
A controller manages distributed workers.
It sends worker addresses to clients.
"""
import argparse
import asyncio
import dataclasses
from enum import Enum, auto
import json
import logging
import os
import time
from typing import List, Union
import threading

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
import numpy as np
import requests
import uvicorn

from fastchat.constants import (
    CONTROLLER_HEART_BEAT_EXPIRATION,
    WORKER_API_TIMEOUT,
    ErrorCode,
    SERVER_ERROR_MSG,
)
from fastchat.utils import build_logger


logger = build_logger("controller", "controller.log")
app = FastAPI() # Define the FastAPI app instance globally
controller_instance: 'Controller' = None # Global controller instance


@dataclasses.dataclass
class WorkerInfo:
    model_names: List[str]  # Will be a list with one model name
    speed: int
    queue_length: int
    check_heart_beat: bool
    last_heart_beat: str
    multimodal: bool # Keep for now, can be removed if vision is not planned for yeongjopt


def heart_beat_controller(controller_obj: 'Controller'): # Use a more descriptive name for 'controller' argument
    while True:
        time.sleep(CONTROLLER_HEART_BEAT_EXPIRATION)
        if controller_obj: # Ensure controller_instance is initialized
            controller_obj.remove_stale_workers_by_expiration()


class Controller:
    def __init__(self, dispatch_method: str = "shortest_queue"): # dispatch_method is vestigial
        self.worker_info = {} # Stores info for the single worker
        self.heart_beat_thread = threading.Thread(
            target=heart_beat_controller, args=(self,)
        )
        self.heart_beat_thread.daemon = True # Ensure thread exits when main program exits
        self.heart_beat_thread.start()

    def register_worker(
        self,
        worker_name: str,
        check_heart_beat: bool,
        worker_status: dict,
        multimodal: bool,
    ):
        if not self.worker_info: # Only allow one worker
            logger.info(f"Registering worker: {worker_name}")
            if not worker_status: # Attempt to get status if not provided
                worker_status = self.get_worker_status_direct(worker_name) # Renamed to avoid conflict
            if not worker_status:
                logger.error(f"Failed to get status for worker {worker_name} during registration.")
                return False

            self.worker_info[worker_name] = WorkerInfo(
                worker_status["model_names"],
                worker_status["speed"],
                worker_status["queue_length"],
                check_heart_beat,
                time.time(),
                multimodal,
            )
            logger.info(f"Register done: {worker_name}, {worker_status}")
            return True
        else:
            # Prevent re-registering if a worker already exists.
            if worker_name not in self.worker_info:
                 logger.warning(f"A worker is already registered. Ignoring new registration: {worker_name}")
                 return False # Do not allow a new worker if one is already registered
            else: # Allow re-registration of the same worker (e.g. on restart)
                 logger.info(f"Re-registering existing worker: {worker_name}")
                 # Update status
                 if not worker_status:
                    worker_status = self.get_worker_status_direct(worker_name)
                 if not worker_status:
                    logger.error(f"Failed to get status for worker {worker_name} during re-registration.")
                    return False
                 self.worker_info[worker_name] = WorkerInfo(
                    worker_status["model_names"],
                    worker_status["speed"],
                    worker_status["queue_length"],
                    check_heart_beat,
                    time.time(),
                    multimodal,
                )
                 logger.info(f"Re-register done: {worker_name}, {worker_status}")
                 return True


    def get_worker_status_direct(self, worker_name: str): # Renamed for clarity
        # This method directly fetches status, used internally
        try:
            r = requests.post(worker_name + "/worker_get_status", timeout=WORKER_API_TIMEOUT)
            r.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
            return r.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Get status direct fails for {worker_name}: {e}")
            return None

    def remove_worker(self, worker_name: str):
        if worker_name in self.worker_info:
            del self.worker_info[worker_name]
            logger.info(f"Removed worker: {worker_name}")

    def refresh_all_workers(self):
        if self.worker_info:
            worker_name = list(self.worker_info.keys())[0]
            # w_info = self.worker_info[worker_name] # Not used
            if not self.get_worker_status_direct(worker_name):
                 logger.warning(f"Stale worker detected during refresh: {worker_name}. Removing.")
                 self.remove_worker(worker_name)
            else:
                 logger.info(f"Refreshed worker: {worker_name}")
        else:
            logger.info("No worker to refresh.")

    def list_models(self):
        if self.worker_info:
            worker = list(self.worker_info.values())[0]
            return worker.model_names
        return []

    def list_multimodal_models(self): # Retained for compatibility, behavior simplified
        if self.worker_info:
            worker = list(self.worker_info.values())[0]
            if worker.multimodal:
                return worker.model_names
        return []

    def list_language_models(self): # Retained for compatibility, behavior simplified
        if self.worker_info:
            worker = list(self.worker_info.values())[0]
            if not worker.multimodal:
                return worker.model_names
        return []

    def get_worker_address(self, model_name: str):
        if self.worker_info:
            worker_name = list(self.worker_info.keys())[0] # Get the first (and only) worker
            worker_data = self.worker_info[worker_name]
            if model_name in worker_data.model_names:
                # logger.info(f"Get worker address for {model_name}: {worker_name}") # Too verbose
                return worker_name
        logger.warning(f"No worker available for model: {model_name}")
        return ""

    def receive_heart_beat(self, worker_name: str, queue_length: int):
        if worker_name in self.worker_info:
            self.worker_info[worker_name].queue_length = queue_length
            self.worker_info[worker_name].last_heart_beat = time.time()
            return True
        # else: # Do not log for unknown heartbeats if they are frequent
            # logger.info(f"Receive unknown heart beat from {worker_name}")
        return False

    def remove_stale_workers_by_expiration(self):
        expire = time.time() - CONTROLLER_HEART_BEAT_EXPIRATION
        to_delete = []
        # Iterate over a copy for safe deletion
        for worker_name, w_info in list(self.worker_info.items()):
            if w_info.check_heart_beat and w_info.last_heart_beat < expire:
                to_delete.append(worker_name)

        for worker_name in to_delete:
            logger.warning(f"Worker {worker_name} timed out. Removing.")
            self.remove_worker(worker_name)

    # Removed worker_api_get_status and worker_api_generate_stream from Controller class
    # as controller no longer acts as a worker.

# FastAPI Endpoints
@app.post("/register_worker")
async def app_register_worker(request: Request):
    global controller_instance
    data = await request.json()
    multimodal = data.get("multimodal", False) # Default to False if not provided
    worker_status = data.get("worker_status", None) # Can be None
    success = controller_instance.register_worker(
        data["worker_name"], data["check_heart_beat"], worker_status, multimodal
    )
    if success:
        return {"message": "Worker registered/updated successfully."}
    else:
        return {"message": "Worker registration failed."} # More generic message

@app.post("/refresh_all_workers")
async def app_refresh_all_workers():
    global controller_instance
    controller_instance.refresh_all_workers()
    return {"message": "Workers refreshed successfully."}

@app.post("/list_models")
async def app_list_models():
    global controller_instance
    models = controller_instance.list_models()
    return {"models": models}

@app.post("/list_multimodal_models")
async def app_list_multimodal_models():
    global controller_instance
    models = controller_instance.list_multimodal_models()
    return {"models": models}

@app.post("/list_language_models")
async def app_list_language_models():
    global controller_instance
    models = controller_instance.list_language_models()
    return {"models": models}

@app.post("/get_worker_address")
async def app_get_worker_address(request: Request):
    global controller_instance
    data = await request.json()
    addr = controller_instance.get_worker_address(data["model"])
    return {"address": addr}

@app.post("/receive_heart_beat")
async def app_receive_heart_beat(request: Request):
    global controller_instance
    data = await request.json()
    exist = controller_instance.receive_heart_beat(data["worker_name"], data["queue_length"])
    return {"exist": exist}

@app.get("/test_connection")
async def app_test_connection():
    return {"message": "Controller is active."}


def create_fastapi_app(args): # Renamed from create_controller to avoid confusion
    global controller_instance
    controller_instance = Controller(args.dispatch_method) # dispatch_method is vestigial
    logger.info("FastChat YeongjoPT Controller is running.")
    return app # Return the global app instance with routes attached


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", type=str, default="localhost")
    parser.add_argument("--port", type=int, default=21001)
    parser.add_argument(
        "--dispatch-method", # This argument is no longer used by Controller logic
        type=str,
        default="shortest_queue", # Default value, but logic is removed
        choices=["lottery", "shortest_queue"], # Kept for CLI compatibility for now
    )
    parser.add_argument(
        "--ssl",
        action="store_true",
        required=False,
        default=False,
        help="Enable SSL for controller server.",
    )
    args = parser.parse_args()
    # logger.info(f"args: {args}") # Can be verbose

    # Configure logger
    logger.handlers.clear() # Remove existing handlers
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(stream_handler)
    logger.setLevel(logging.INFO)


    # Create the FastAPI app and controller instance
    # The app instance is global, create_fastapi_app initializes the controller
    initialized_app = create_fastapi_app(args)

    if args.ssl:
        # Ensure FASTCHAT_SSL_KEY and FASTCHAT_SSL_CERT env vars are set
        # if not (os.environ.get("FASTCHAT_SSL_KEY") and os.environ.get("FASTCHAT_SSL_CERT")):
        #     raise ValueError("FASTCHAT_SSL_KEY and FASTCHAT_SSL_CERT must be set for SSL")
        logger.info(f"Running with SSL. Key: {os.environ.get('FASTCHAT_SSL_KEY')}, Cert: {os.environ.get('FASTCHAT_SSL_CERT')}")
        uvicorn.run(
            initialized_app,
            host=args.host,
            port=args.port,
            log_level="info",
            ssl_keyfile=os.environ.get("FASTCHAT_SSL_KEY"),
            ssl_certfile=os.environ.get("FASTCHAT_SSL_CERT"),
        )
    else:
        logger.info(f"Running without SSL on http://{args.host}:{args.port}")
        uvicorn.run(initialized_app, host=args.host, port=args.port, log_level="info")
