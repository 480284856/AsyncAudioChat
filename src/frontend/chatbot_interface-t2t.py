import os
import sys
import json
import time
import queue
import gradio as gr

from typing import Generator
sys.path.append(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
from AsyncAudioChat import LLM

def backend(*args, **kwargs):
    '''后端对话实现'''
    text_queue = queue.Queue()
    text = {"text": kwargs["user_input"]}

    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')) as F:
        _args = json.load(F)
        ollama_model_name = _args['model_name']
        ollama_base_url = _args['llm_url']

    llm_thread = LLM(text=text, text_queue=text_queue, ollama_model_name=ollama_model_name, ollama_base_url=ollama_base_url)
    llm_thread.start()
    while True:
        text = text_queue.get()
        if text == None:
            break
        yield text

def chatbot(user_input, history) -> Generator[str, None, None]:
    '''基于用户的输入"user_input"以及历史对话"history"，返回一个回复'''
    for sentence in backend(user_input=user_input):
        yield sentence

gr.ChatInterface(
    chatbot,
    retry_btn="重来一次",
    clear_btn="清除对话",
    undo_btn="撤销",
    submit_btn="Enter",
).launch()