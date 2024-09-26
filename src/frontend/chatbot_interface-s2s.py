import os
import sys
import json
import time
import queue
import random
import threading
import gradio as gr

from typing import Generator
sys.path.append(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
from AsyncAudioChat import Backend,LLM,STT,LOGGER,END,lingji_stt_gradio_va

class STT(STT):
    def __init__(self, stt_api, text, *args, **kwargs):
        super().__init__(stt_api, text, *args, **kwargs)
        self.stt_for_web_display = queue.Queue()
    
    def run(self,):
        super().run()
        self.stt_for_web_display.put(self.text['text'])

class LLM(LLM):
    def __init__(self, text, text_queue: queue.Queue, *args_for_run, **kwargs_for_run):
        super().__init__(text, text_queue, *args_for_run, **kwargs_for_run)

        # 解决前端无法实时获取token的问题。
        '''在后端线程实现里expose一个`response_for_web_display`的队列，如果LLM推理出了一个新的token，就放到这个队列里，如果推理完毕，则放入一个推理结束标志符号。'''
        self.response_for_web_display = queue.Queue()
        
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
        
        self.stt_thread = STT(lingji_stt_gradio_va, self.text)
        self.llm_thread = LLM(self.text, self.text_queue, ollama_model_name=self._ollama_model_name, ollama_base_url=self._ollama_base_url)
        
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

    def run(self,):
        with gr.Blocks(css=self.css) as demo:         # css: 实现全高 分布
            chatbot = gr.Chatbot(elem_id="chatbot")   # css: 实现全高 分布
            
            with gr.Row():
                msg = gr.Button("AudioChat")
                clear = gr.Button("Clear")

            msg.click(
                self.run_backend, 
                [chatbot], 
                [chatbot]
            )
            clear.click(lambda: None, None, chatbot, queue=False)

        demo.launch()

    def backend(self, *args, **kwargs) -> Generator[str, None, None]:
        '''后端对话实现：单轮'''
        backend_thread = Backend(*args, **kwargs)
        backend_thread.start()

        # 先返回STT结果
        user_input = backend_thread.stt_for_web_display.get()
        yield user_input
        # 再返回LLM推理结果
        llm_response_queue = backend_thread.response_for_web_display
        while True:
            token = llm_response_queue.get()
            if token == END:
                break
            yield token
        
        backend_thread.join()
        
    def run_backend(self, chatbot):
        while True:
            llm_backend = self.backend()
            
            user_text = next(llm_backend)
            chatbot += [[user_text,None]]
            yield chatbot
            
            chatbot[-1][1] = ""
            for token in llm_backend:
                chatbot[-1][1] += token
                yield chatbot

    def test(self,):
        with gr.Blocks(css=self.css) as demo:         # css: 实现全高 分布
            chatbot = gr.Chatbot(elem_id="chatbot")   # css: 实现全高 分布
            
            with gr.Row():
                msg = gr.Button("AudioChat")
                clear = gr.Button("Clear")

            def test(chatbot):
                # while True:
                time.sleep(1)
                chatbot += [["hello world","hello world"]]
                yield chatbot
            
            msg.click(
                test, 
                [chatbot], 
                [chatbot],
                queue=True,
            )
            clear.click(lambda: None, None, chatbot, queue=False)

        demo.launch()
if __name__ == "__main__":
    main_thread = Chatbot()
    main_thread.run()
