import os
import sys
import json
import time
import queue
import random
import asyncio
import threading
import multiprocessing
import gradio as gr

from typing import Generator
sys.path.append(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
from AsyncAudioChat import Backend,LLM,STT,LOGGER,END,lingji_stt_gradio_va

class STT(STT):
    def __init__(self, stt_api, text, *args, **kwargs):
        super().__init__(stt_api, text, *args, **kwargs)
        self.stt_for_web_display:multiprocessing.Queue = kwargs['stt_for_web_display']
    
    def run(self,):
        super().run()
        self.stt_for_web_display.put(self.text['text'])

class LLM(LLM):
    def __init__(self, text, text_queue: queue.Queue, *args_for_run, **kwargs_for_run):
        super().__init__(text, text_queue, *args_for_run, **kwargs_for_run)

        # 解决前端无法实时获取token的问题。
        '''在后端线程实现里expose一个`response_for_web_display`的队列，如果LLM推理出了一个新的token，就放到这个队列里，如果推理完毕，则放入一个推理结束标志符号。'''
        self.response_for_web_display:multiprocessing.Queue = kwargs_for_run['response_for_web_display']
        
    def __run2_ollama(self, llm_iterator, *args, **kwargs):
        old_total_response = ""
        current_total_response = ""
        
        for response_token in llm_iterator:
            response_token = response_token.content

            # 解决前端无法实时获取token的问题。
            self.response_for_web_display.put(response_token)
            
            # 每次拿到reponse时，使用新的response去掉old_total_response，得到response_delta，这个就是在当前时间点得到的response。
            current_total_response += response_token
            response_delta = self.__remove_first_match(current_total_response, old_total_response)

            # 我们对response_delta进行这样的操作，从左到右，判断其是否有有‘，。！？’等符号，如果有的话，就从左到右，从开头到这个符号为止，截取这段文本，然后把这段文本放入到text队列中，以及拼接到old_total_response对象右侧。如果没有，则不做操作。
            while response_delta:
                # 找到第一个标点符号的位置
                ## i for i in xxx, 叫做生成器表达式，使用圆括号包裹生成器表达式，表示这是一个generator，而使用[]或{}的话，则表示是一个列表或集合表达式，
                ## 前者不会把for表达式执行完，然后返回结果，而是返回一个generator对象，只有在遍历这个对象（比如使用next方法）的时候才会执行for表达式，然后返回结果。
                ## 而列表或集合表达式会立即执行for表达式，然后返回结果。
                ## 返回generator的方式称为惰性计算，只有在需要的时候才把值放到内存中。每次迭代时，生成器都会返回一个值，然后记住当前位置，下次遍历这个生成器时，则会从之前记住的位置的下一个位置开始便利。
                ## 不把英文的'.'算入截断标点符号中，因为大模型生成的文本中，标题会用到'.'，比如‘6.’
                punctuation_index = next((i for i, char in enumerate(response_delta) if char in [',' , '，', '。', '！', '？', '!', '?']), -1)
                if punctuation_index != -1:                          # 如果生成器表达式不是空的，即找的到第一个标点符号
                    text = response_delta[:punctuation_index + 1]    # 截取这段文本
                    old_total_response += text                  # 拼接到old_total_response对象右侧
                    self.text_queue.put(text)               # 把这段文本放入到text队列中
                    LOGGER.info("LLM: new sentence: {}".format(old_total_response))
                    
                    # 如果response_delta中存在不止一个符号，那么我们在做完第一个符号对应的工作后，把response_delta更新为去掉第一段文本的剩下文本，然后进行同样的操作。
                    response_delta = response_delta[punctuation_index + 1:]
                
                # 如果response_delta没有‘，。！？’等符号了，则不做操作。
                if punctuation_index==-1:
                    break
        
        # 最后一个句子可能会没有标点符号，所以需要特殊处理。
        if response_delta:  # 如果最后一个句子确实没有标点。
            self.text_queue.put(response_delta)
        
        # 生成完成后，往队列中放入一个END结束标识符。
        self.text_queue.put(END)    
        self.response_for_web_display.put(END) 

class Backend(Backend):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.stt_thread = STT(lingji_stt_gradio_va, self.text, stt_for_web_display=kwargs['stt_for_web_display'])
        self.llm_thread = LLM(self.text, self.text_queue, ollama_model_name=self._ollama_model_name, ollama_base_url=self._ollama_base_url, response_for_web_display=kwargs['response_for_web_display'])
        
        self.stt_for_web_display = self.stt_thread.stt_for_web_display
        self.response_for_web_display = self.llm_thread.response_for_web_display

class Chatbot:    
    def __init__(self) -> None:
        self.css ="""
                .contain { display: flex; flex-direction: column; }
                .gradio-container { height: 100vh !important; }
                #component-0 { height: 100%; }
                #chatbot { flex-grow: 1; overflow: auto;}
                """
        # 为了提高整体性，我们会把对话封装为一个进程，而当用户再次点击按钮后，
        # 则需要停止对话的创建，取消子进程的运行。这可以通过一个flag_stop_chat变量来表示：
        # 第一次点击时，flag_stop_chat为False，创建进程，当用户再次点击按钮后，flag_stop_chat为True，取消进程。
        self.stt_for_web_display = multiprocessing.Queue()
        self.response_for_web_display = multiprocessing.Queue()
        # 要在gr的范围内定义，否则会爆粗key error
        self.flag_stop_chat = None

    def _run_backend(self, stt_for_web_display:multiprocessing.Queue, response_for_web_display:multiprocessing.Queue, *args, **kwargs):
        '''后端对话实现：单轮'''
        backend_thread = Backend(stt_for_web_display=stt_for_web_display, response_for_web_display=response_for_web_display, *args, **kwargs)
        backend_thread.start()
        backend_thread.join()

    def run_backend(self, chatbot, flag_stop_chat):
        # 为了提高整体性，我们会把对话封装为一个进程，而当用户再次点击按钮后，
        # 则需要停止对话的创建，取消子进程的运行。这可以通过一个flag_stop_chat变量来表示：
        # 第一次点击时，flag_stop_chat为False，创建进程，当用户再次点击按钮后，flag_stop_chat为True，取消进程。
        if not flag_stop_chat:
            while True:
                flag_stop_chat = True
                self.process_backend = multiprocessing.Process(target=self._run_backend, daemon=True, args=(self.stt_for_web_display, self.response_for_web_display))
                self.process_backend.start()
                
                # 后端运行
                # 前端对后端进程通信，获取数据。
                for chatbot_ in self.communicate_backend(chatbot):
                    yield chatbot_,flag_stop_chat
                
                self.process_backend.join()

                if self.flag_skip_out_loop.value:
                    # LOGGER.info("I have skip out of loop.")
                    self.flag_skip_out_loop.value = False
                    break
        else:
            # 如果后端进程存在，则关闭。
            flag_stop_chat = False
            self.stt_for_web_display = multiprocessing.Queue()
            self.response_for_web_display = multiprocessing.Queue()
            if self.process_backend.is_alive():
                self.process_backend.terminate()
                self.flag_skip_out_loop.value = True
                # LOGGER.info("Backend process terminated.")
            yield [],flag_stop_chat

    def communicate_backend(self, chatbot):
        
        user_text = None
        while True:
            # 如果进程已经取消了，并且这里还使用queue.get方法的话，就会一直卡在这里。
            if not self.process_backend.is_alive():
                return []

            try:
                user_text = self.stt_for_web_display.get_nowait()
            except queue.Empty:
                time.sleep(0.01)
                # LOGGER.error("No data received from the stt.")
            finally:
                if user_text:
                    break
        
        chatbot += [[user_text,None]]
        yield chatbot
            
        chatbot[-1][1] = ""
        while True:
            token = self.response_for_web_display.get()
            if token == END:
                break
            chatbot[-1][1] += token
            yield chatbot

    def run_web(self,):
        with gr.Blocks(css=self.css) as demo:         # css: 实现全高 分布
            chatbot = gr.Chatbot(elem_id="chatbot")   # css: 实现全高 分布
            # 要在gr的范围内定义，否则会报key error
            self.flag_stop_chat = gr.State(False)
            self.flag_skip_out_loop = gr.State(False)

            with gr.Row():
                msg = gr.Button("AudioChat")
                clear = gr.Button("Stop & Clear")

            msg.click(
                self.run_backend, 
                [chatbot, self.flag_stop_chat], 
                [chatbot, self.flag_stop_chat],
            )
            clear.click(self.run_backend, 
                [chatbot, self.flag_stop_chat], 
                [chatbot, self.flag_stop_chat],
            ).then(lambda: None, None, chatbot)

        demo.launch()

if __name__ == "__main__":
    process = multiprocessing.Process(target=Chatbot().run_web)

    process.start()
    process.join()

