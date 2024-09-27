import os
import sys
import time
import json
import queue
import logging
import threading

sys.path.append(
    os.path.dirname(os.path.abspath(__file__))
)

from pygame import mixer
from zijie_tts import tts
from langchain_ollama import ChatOllama 
from ali_stt_voice_awake import lingji_stt_gradio_va
END = None  # 使用None表示结束标识符

def get_logger():
    # 日志收集器
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    
    # Avoid passing messages to the root logger
    logger.propagate = False
    
    # If the logger already has handlers, avoid adding duplicate ones
    if not logger.hasHandlers():
        # 设置控制台处理器，当logger被调用时，控制台处理器额外输出被调用的位置。
        # 创建一个控制台处理器并设置级别为DEBUG
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        # 创建一个格式化器，并设置格式包括文件名和行号
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(pathname)s:%(lineno)d - %(message)s')
        ch.setFormatter(formatter)

        # 将处理器添加到logger
        logger.addHandler(ch)

    return logger

LOGGER = get_logger()

class STT(threading.Thread):
    def __init__(self, stt_api, text, *args, **kwargs):
        super().__init__(daemon=True)

        self.stt_api = stt_api
        self.text = text
        self.args_for_run = args
        self.kwargs_for_run = kwargs

    def run(self):
        '''STT模块接收用户的语音输入，并保存转录好的文本。'''
        self.text['text'] = self.stt_api(*(self.args_for_run), **(self.kwargs_for_run))

class InputProcess(threading.Thread):
    def __init__(self, user_input, history=None, *args, **kwargs):
        super().__init__(daemon=True)
        self.user_input = user_input
        self.history = history
    
    # do not modify this function
    def run(self, *args, **kwargs):
        self.user_input['text']  = self._run(*args, **kwargs)
    
    def _run(self, *args, **kwargs):
        final_input = ""
        if self.history is not None:
            for item in self.history:
                final_input += "User: {}\nAssistant: {}\n".format(item[0], item[1])
        final_input += "User: {}".format(self.user_input['text'])
        LOGGER.info("Prompt is \n\n{}\n\n".format(final_input))
        return final_input
    
class LLM(threading.Thread):
    def __init__(
            self, 
            text, 
            text_queue: queue.Queue,
            *args_for_run,
            **kwargs_for_run
    ):
        '''对LLM的输出做实时处理：若输出了完整的一句话，则把这个句子放入到一个Text queue队列中。如果LLM推理结束，则往Text queue队列中放入一个结束标志符号END。'''
        super().__init__(daemon=True)
        self.text_queue = text_queue
        self.text = text
        
        self.args_for_run = args_for_run
        self.kwargs_for_run = kwargs_for_run

    def _run(self, query, *args, **kwargs):
        '''LLM推理的设计规范, 强制返回一个迭代器。'''
        return self.__run_ollama(query, *args, **kwargs)
    
    def __run_ollama(self, query, *args, ollama_model_name, ollama_base_url, **kwargs):
        messages = [
            ('system', "You are a helpful assistant and only can speak English."),
            ("human", query)
        ]
        self.model = ChatOllama(
            model=ollama_model_name,
            base_url=ollama_base_url
        )
        return self.model.stream(messages, *args, **kwargs)

    def _run2(self, llm_iterator, *args, **kwargs) -> None:
        '''对LLM的输出做实时处理：若输出了完整的一句话，则把这个句子放入到一个Text queue队列中。如果LLM推理结束，则往Text queue队列中放入一个结束标志符号END。'''
        self.__run2_ollama(llm_iterator, *args, **kwargs)
    
    def __run2_ollama(self, llm_iterator, *args, **kwargs):
        old_total_response = ""
        current_total_response = ""
        for response_token in llm_iterator:
            response_token = response_token.content
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

    def __remove_first_match(self, s:str, sub_s:str):
        '''从s中删除第一次出现的sub_s'''
        if sub_s in s:
            return s.replace(sub_s, '', 1)
        else:
            return s
        
    def run(self) -> None:
        self.query = self.text['text']
        response_iterator = self._run(self.query, *(self.args_for_run), **(self.kwargs_for_run))

        self._run2(response_iterator, *(self.args_for_run), **(self.kwargs_for_run))

class TTS(threading.Thread):
    def __init__(self, text_queue: queue.Queue, audio_queue: queue.Queue):
        """从Text queue队列中依次拿出sentence，并把其转换成音频，然后存储在一个Audio queue队列中。如果拿到结束标志符号END，则把这个符号放到Audio queue队列中。"""
        super().__init__(daemon=True)

        self.text_queue = text_queue
        self.audio_queue = audio_queue
    
    def _run(self, text, *args, **kwargs) -> str:
        '''把text转换成语音，并保存，然后返回语音文件路径。'''
        return tts(text)
    
    def run(self, *args, **kwargs):
        while True:
            # block if necessary until an item is available
            sentence = self.text_queue.get()
            if sentence is None:
                self.audio_queue.put(None)
                break
            self.audio_queue.put(self._run(sentence))

class Speaker(threading.Thread):
    def __init__(self, audio_queue: queue.Queue):
        """Audio queue队列被不停的拿出音频，进行播放，直到拿到结束标志符号END"""
        super().__init__(daemon=True)

        self.audio_queue = audio_queue
    
    def _run(self, *args, **kwargs):
        # 使用mixer类进行播放         
        mixer.init()
        while True:
            audio = self.audio_queue.get()
            if audio is None:
                break
            
            mixer.music.load(audio)
            mixer.music.play()
            while mixer.music.get_busy():
                time.sleep(0.001)
            
            mixer.music.unload()
            os.remove(audio)
        mixer.quit()
    
    def run(self, *args, **kwargs):
        self._run(*args, **kwargs)
        LOGGER.info("Speaker: Speaker thread exited.")

class Backend(threading.Thread):
    def __init__(self, *args, **kwargs):
        """把整个异步对话模块整合成一个线程。"""
        super().__init__(daemon=True)
        self.text = {"text": None}
        self.text_queue = queue.Queue()
        self.audio_queue = queue.Queue()

        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')) as F:
            _args = json.load(F)
            self._ollama_model_name = _args['model_name']
            self._ollama_base_url = _args['llm_url']
            for key,value in _args.items():
                os.environ[key] = value

        self.stt_thread = STT(lingji_stt_gradio_va, self.text)
        self.input_preprocessing_thread = InputProcess(self.text, kwargs.get("history", None))
        self.llm_thread = LLM(self.text, self.text_queue, ollama_model_name=self._ollama_model_name, ollama_base_url=self._ollama_base_url)
        self.audio_thread = TTS(self.text_queue, self.audio_queue)
        self.speaker_thread = Speaker(self.audio_queue)

    def run(self,):
        self.stt_thread.start()
        self.stt_thread.join()
        
        self.input_preprocessing_thread.start()
        self.input_preprocessing_thread.join()
        
        self.llm_thread.start()
        self.audio_thread.start()
        self.speaker_thread.start()

        self.llm_thread.join()
        self.audio_thread.join()
        self.speaker_thread.join()

if __name__ == "__main__":
    main_thread = Backend()
    main_thread.start()
    main_thread.join()