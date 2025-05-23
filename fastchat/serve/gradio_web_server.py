"""
The gradio demo server for chatting with a single model.
"""

import argparse
import datetime
import json
import os
import random
import time
import uuid
from typing import List, Dict, Optional

import gradio as gr
import requests

from fastchat.constants import (
    WORKER_API_TIMEOUT,
    ErrorCode,
    SERVER_ERROR_MSG,
    INPUT_CHAR_LEN_LIMIT,
)
from fastchat.model.model_adapter import (
    get_conversation_template,
)
from fastchat.utils import (
    build_logger,
    get_window_url_params_js,
    load_image,
)

logger = build_logger("yeongjopt_web_server", "yeongjopt_web_server.log")

headers = {"User-Agent": "YeongjoPT Client"}

no_change_btn = gr.Button()
enable_btn = gr.Button(interactive=True, visible=True)
disable_btn = gr.Button(interactive=False)
invisible_btn = gr.Button(interactive=False, visible=False)
enable_text = gr.Textbox(
    interactive=True, visible=True, placeholder="👉 메시지를 입력하고 Enter를 누르세요..."
)
disable_text = gr.Textbox(
    interactive=False,
    visible=True,
    placeholder='새 대화를 시작하려면 "새 대화" 버튼을 누르세요.',
)

controller_url: Optional[str] = None

global_fixed_model_name: str = "yeongjopt-default-model"

YEONGJOPT_SYSTEM_PROMPT: str = """당신은 '영조피티'입니다. 실존 인물 조민영의 성격을 반영해, 조롱과 냉소로 질문자에게 응답합니다.
서울은 강남 3구만 서울이라 여기며, 청바지에 집착하고, 논리 없는 질문에는 무자비하게 비꼽니다."""

class State:
    "Manages the conversation state for a single user session."    
    def __init__(self, model_name_to_use: str):
        self.conv = get_conversation_template(model_name_to_use)
        self.conv.set_system_message(YEONGJOPT_SYSTEM_PROMPT)
        self.conv_id = uuid.uuid4().hex
        self.skip_next = False
        self.model_name = model_name_to_use
        self.regen_support = True

    def to_gradio_chatbot(self):
        return self.conv.to_gradio_chatbot()

    def to_dict(self): # Renamed from dict to avoid conflict with built-in
        return {
            "conv_id": self.conv_id,
            "model_name": self.model_name,
            "conversation_history": self.conv.messages,
        }

class GradioContext:
    "Holds context for the Gradio app, like the model list (single model for YeongjoPT)."    
    def __init__(self, models: Optional[List[str]] = None):
        self.models = models if models else [global_fixed_model_name]

context_singleton: Optional[GradioContext] = None

title_markdown = """
<h1 align="center">👑 영조피티 (YeongjoPT) 👑</h1>
<h3 align="center">조롱과 냉소로 가득한, 조민영 페르소나 챗봇</h3>
"""

css_code = """ 
#chatbot { font-size: 16px; }
.gradio-container { max-width: 800px !important; margin: auto !important; }
h1, h3 { text-align: center; }
footer { display: none !important; }
"""

def set_global_vars_yeongjopt(controller_url_provided: str):
    global controller_url
    controller_url = controller_url_provided

def get_model_list_from_controller(controller_addr: str) -> List[str]:
    global global_fixed_model_name
    if not controller_addr:
        logger.error("Controller URL is not set. Cannot fetch model list.")
        return [global_fixed_model_name] # Return default, expect failure later

    try:
        logger.info(f"Fetching model list from controller: {controller_addr}")
        res = requests.post(controller_addr + "/list_models", timeout=WORKER_API_TIMEOUT)
        res.raise_for_status()
        models_ret = res.json().get("models", [])
        if models_ret:
            if len(models_ret) > 1:
                logger.warning(f"Controller listed multiple models: {models_ret}. YeongjoPT will use the first: {models_ret[0]}")
            global_fixed_model_name = models_ret[0]
            logger.info(f"Successfully fetched model from controller: {global_fixed_model_name}")
            return [global_fixed_model_name]
        else:
            logger.error(f"Controller at {controller_addr} listed no models. Using default: {global_fixed_model_name}. This may fail if worker uses a different name.")
            return [global_fixed_model_name]
    except requests.exceptions.RequestException as e:
        logger.error(f"Could not connect to controller at {controller_addr} to get model list: {e}. Using default: {global_fixed_model_name}")
        return [global_fixed_model_name]
    except Exception as e:
        logger.error(f"Generic error fetching model list from {controller_addr}: {e}. Using default: {global_fixed_model_name}")
        return [global_fixed_model_name]

def load_demo(context: GradioContext, request: gr.Request):
    logger.info(f"Loading demo for YeongjoPT. Model configured: {global_fixed_model_name}")
    state = State(global_fixed_model_name)
    # Chatbot, Textbox, Send, Regenerate, Clear
    return state, state.to_gradio_chatbot(), enable_text, enable_btn, enable_btn, enable_btn

def clear_history_fn(request: gr.Request): # Added _fn suffix
    logger.info("Clear history clicked.")
    state = State(global_fixed_model_name)
    return state, state.to_gradio_chatbot(), enable_text, disable_btn # Disable send initially

def regenerate_fn(state: State, request: gr.Request): # Added _fn suffix
    logger.info(f"Regenerate clicked. Conversation ID: {state.conv_id}")
    if state.conv.messages and state.conv.messages[-1][0] == state.conv.roles[1]: # If last is assistant
        state.conv.messages.pop() # Remove last assistant message
    # UI updates: Textbox remains enabled for potential immediate new message, send button disabled until bot_response cycle starts
    return state, state.to_gradio_chatbot(), enable_text, disable_btn

def add_text_fn(state: State, text: str, request: gr.Request): # Added _fn suffix
    logger.info(f"Add text. Conv ID: {state.conv_id}, Text: \"{text[:30]}...\"")
    if not text or len(text.strip()) == 0:
        state.skip_next = True
        return state, state.to_gradio_chatbot(), disable_text, no_change_btn
    
    state.conv.append_message(state.conv.roles[0], text.strip())
    state.conv.append_message(state.conv.roles[1], None) # Assistant's turn
    state.skip_next = False
    return state, state.to_gradio_chatbot(), disable_text, disable_btn

def model_worker_stream_iter_fn(
    current_state: State, 
    worker_addr_local: str,
    temperature_val: float,
    repetition_penalty_val: float, 
    top_p_val: float,
    max_new_tokens_val: int,
):
    prompt_text = current_state.conv.get_prompt()
    gen_params = {
        "model": current_state.model_name,
        "prompt": prompt_text,
        "temperature": temperature_val,
        "repetition_penalty": repetition_penalty_val,
        "top_p": top_p_val,
        "max_new_tokens": max_new_tokens_val,
        "stop": current_state.conv.stop_str,
        "stop_token_ids": current_state.conv.stop_token_ids,
        "echo": False,
    }
    # logger.debug(f"Worker stream params: {gen_params}")
    try:
        response = requests.post(
            worker_addr_local + "/worker_generate_stream",
            json=gen_params, stream=True, timeout=WORKER_API_TIMEOUT, headers=headers)
        response.raise_for_status()
        for chunk in response.iter_lines(decode_unicode=False, delimiter=b"\0"):
            if chunk:
                yield json.loads(chunk.decode("utf-8"))
    except requests.exceptions.RequestException as e:
        logger.error(f"Stream error from {worker_addr_local}: {e}")
        yield {"text": f"{SERVER_ERROR_MSG}\n(Worker Connection Error: {e})", "error_code": ErrorCode.CONNECTION_ERROR}
    except Exception as e:
        logger.error(f"Unknown stream processing error: {e}")
        yield {"text": f"{SERVER_ERROR_MSG}\n(Streaming Error: {e})", "error_code": ErrorCode.INTERNAL_ERROR}

def bot_response_fn(
    state_obj: State, temperature: float, top_p: float, max_new_tokens: int, request: gr.Request
):
    logger.info(f"Bot response requested. Conv ID: {state_obj.conv_id}. Model: {state_obj.model_name}")
    start_t = time.time()

    if state_obj.skip_next:
        state_obj.skip_next = False
        yield state_obj, state_obj.to_gradio_chatbot(), enable_text, enable_btn
        return

    if not controller_url:
        logger.critical("Controller URL not set globally!")
        state_obj.conv.update_last_message(f"{SERVER_ERROR_MSG} (System Error: Controller not configured)")
        yield state_obj, state_obj.to_gradio_chatbot(), enable_text, enable_btn
        return

    worker_addr = ""
    try:
        res = requests.post(controller_url + "/get_worker_address", json={"model": state_obj.model_name}, timeout=WORKER_API_TIMEOUT)
        res.raise_for_status()
        worker_addr = res.json().get("address", "")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to get worker for {state_obj.model_name} from {controller_url}: {e}")
        state_obj.conv.update_last_message(f"{SERVER_ERROR_MSG} (Controller/Worker Error)")
        yield state_obj, state_obj.to_gradio_chatbot(), enable_text, enable_btn
        return

    if not worker_addr:
        logger.error(f"No worker found for {state_obj.model_name} via controller {controller_url}")
        state_obj.conv.update_last_message(f"{SERVER_ERROR_MSG} (No worker for {state_obj.model_name})")
        yield state_obj, state_obj.to_gradio_chatbot(), enable_text, enable_btn
        return

    logger.info(f"Streaming from worker {worker_addr} for model {state_obj.model_name}")
    state_obj.conv.update_last_message("▌") # Initial streaming placeholder
    yield state_obj, state_obj.to_gradio_chatbot() # Update UI with placeholder

    repetition_penalty = getattr(state_obj.conv, 'repetition_penalty', 1.0)
    full_resp_text = ""
    for data_chunk in model_worker_stream_iter_fn(
        current_state=state_obj, worker_addr_local=worker_addr, temperature_val=temperature,
        repetition_penalty_val=repetition_penalty, top_p_val=top_p, max_new_tokens_val=max_new_tokens,
    ):
        if data_chunk.get("error_code", 0) != 0:
            err_msg = data_chunk.get("text", SERVER_ERROR_MSG)
            state_obj.conv.update_last_message(err_msg)
            logger.error(f"Stream error code {data_chunk['error_code']}: {err_msg}")
            yield state_obj, state_obj.to_gradio_chatbot(), enable_text, enable_btn
            return
        
        text_chunk = data_chunk.get("text", "")
        if not isinstance(text_chunk, str): text_chunk = str(text_chunk)
        full_resp_text += text_chunk
        state_obj.conv.update_last_message(full_resp_text + "▌")
        yield state_obj, state_obj.to_gradio_chatbot()
    
    state_obj.conv.update_last_message(full_resp_text) # Final update without placeholder
    logger.info(f"Stream complete. Conv ID: {state_obj.conv_id}. Duration: {time.time() - start_t:.2f}s")
    yield state_obj, state_obj.to_gradio_chatbot(), enable_text, enable_btn

def build_yeongjopt_ui_main(context_obj: GradioContext):
    with gr.Blocks(title="영조피티", theme=gr.themes.Default(), css=css_code, elem_id="yeongjopt_main_block") as demo_main:
        session_state = gr.State()
        gr.Markdown(title_markdown)

        with gr.Row():
            with gr.Column(scale=20):
                bot_avatar_path = "https://raw.githubusercontent.com/lm-sys/FastChat/main/assets/bot.png" 
                chat_interface = gr.Chatbot(
                    elem_id="chatbot_display", label="영조피티", height=550, 
                    avatar_images=(None, bot_avatar_path) 
                )
        with gr.Row():
            with gr.Column(scale=12):
                input_textbox = gr.Textbox(show_label=False, placeholder="영조피티에게 뭐든 물어보세요. 단, 논리적인 질문만...", elem_id="user_input_box", container=False)
            with gr.Column(scale=1, min_width=60):
                send_button = gr.Button("전송", variant="primary", min_width=60)
        with gr.Row():
            regenerate_button = gr.Button("🔄 다시 생성", interactive=True)
            clear_button = gr.Button("✨ 새 대화", interactive=True)

        with gr.Accordion("🔧 설정 (Parameters)", open=False):
            temperature_slider = gr.Slider(minimum=0.0, maximum=1.0, value=0.7, step=0.1, interactive=True, label="Temperature (창의성)")
            top_p_slider = gr.Slider(minimum=0.0, maximum=1.0, value=1.0, step=0.1, interactive=True, label="Top P (단어 다양성)")
            max_tokens_slider = gr.Slider(minimum=32, maximum=2048, value=512, step=32, interactive=True, label="최대 생성 토큰")

        # Event Listeners
        demo_main.load(lambda req: load_demo(context_obj, req), [context_obj], 
                       [session_state, chat_interface, input_textbox, send_button, regenerate_button, clear_button])

        input_textbox.submit(add_text_fn, [session_state, input_textbox], [session_state, chat_interface, input_textbox, send_button])\
                     .then(bot_response_fn, [session_state, temperature_slider, top_p_slider, max_tokens_slider], 
                           [session_state, chat_interface, input_textbox, send_button])

        send_button.click(add_text_fn, [session_state, input_textbox], [session_state, chat_interface, input_textbox, send_button])\
                     .then(bot_response_fn, [session_state, temperature_slider, top_p_slider, max_tokens_slider], 
                           [session_state, chat_interface, input_textbox, send_button])

        regenerate_button.click(regenerate_fn, [session_state], [session_state, chat_interface, input_textbox, send_button])\
                         .then(bot_response_fn, [session_state, temperature_slider, top_p_slider, max_tokens_slider], 
                               [session_state, chat_interface, input_textbox, send_button])

        clear_button.click(clear_history_fn, [], [session_state, chat_interface, input_textbox, send_button])
    return demo_main

def main_gradio_server(cli_args):
    global controller_url, context_singleton, global_fixed_model_name

    set_global_vars_yeongjopt(cli_args.controller_url)
    
    models_available = get_model_list_from_controller(cli_args.controller_url)

    if not models_available or global_fixed_model_name == "yeongjopt-default-model" or not global_fixed_model_name:
        logger.critical(f"CRITICAL: YeongjoPT model name not confirmed from controller at {cli_args.controller_url}. Current name: '{global_fixed_model_name}'. Ensure ModelWorker is running and registered with controller.")
        print(f"EXITING: YeongjoPT could not confirm model. Check controller & worker logs.")
        return
    
    logger.info(f"YeongjoPT Web Server starting. Will use model: {global_fixed_model_name}")
    context_singleton = GradioContext(models=models_available)
    
    demo_instance = build_yeongjopt_ui_main(context_singleton)
    demo_instance.queue(
        api_open=False, 
        default_concurrency_limit=cli_args.default_concurrency_limit
    ).launch(
        server_name=cli_args.host, 
        server_port=cli_args.port, 
        share=cli_args.share, 
        max_threads=150, 
    )

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="YeongjoPT Gradio Web Server")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Server host")
    parser.add_argument("--port", type=int, default=7860, help="Server port")
    parser.add_argument("--controller-url", type=str, default="http://localhost:21001", help="FastChat Controller URL")
    parser.add_argument("--share", action="store_true", help="Enable Gradio public share link")
    parser.add_argument("--default-concurrency-limit", type=int, default=20, help="Gradio queue concurrency limit")
    
    args = parser.parse_args()

    if not logger.handlers:
        console_handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        logger.setLevel(logging.INFO)
    
    logger.info(f"Starting YeongjoPT Gradio server with args: {args}")
    main_gradio_server(args)
