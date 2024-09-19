import queue
import threading

from langchain_ollama import ChatOllama 
from ali_stt_voice_awake import lingji_stt_gradio_va

def stt(stt_api, text, *args, **kwargs):
    '''STT模块接收用户的语音输入，并保存转录好的文本。'''
    text['text'] = stt_api(*args, **kwargs)

class LLM(threading.Thread):
    def __init__(self, text, text_queue: queue.Queue):
        '''对LLM的输出做实时处理：若输出了完整的一句话，则把这个句子放入到一个Text queue队列中。如果LLM推理结束，则往Text queue队列中放入一个结束标志符号END。'''
        super().__init__(self)

        self.text_queue = text_queue
        self.query = text['text']
    
    def _run(self, query, *args, **kwargs):
        '''LLM推理的设计规范, 强制返回一个迭代器。'''
        return self.__run_ollama(query, *args, **kwargs)
    
    def __run_ollama(self, query, model_url, *args, **kwargs):
        self.model = ChatOllama(
                    base_url=model_url
                )
        return self.model.stream(query)

    def _run2(self, llm_iterator):
        '''对LLM的输出做实时处理：若输出了完整的一句话，则把这个句子放入到一个Text queue队列中。如果LLM推理结束，则往Text queue队列中放入一个结束标志符号END。'''
        # 原先的代码里有一个producer_text函数，可以拿来做参考。
        raise "Not implemented"

    def run(self, *args, **kwargs) -> None:
        response_iterator = self._run(self.query, *args, **kwargs)

        self._run2(response_iterator)

class TTS(threading.Thread):
    def __init__(self, text_queue: queue.Queue, audio_queue: queue.Queue):
        """从Text queue队列中依次拿出sentence，并把其转换成音频，然后存储在一个Audio queue队列中。如果拿到结束标志符号END，则把这个符号放到Audio queue队列中。"""
        super().__init__(self)

        self.text_queue = text_queue
        self.audio_queue = audio_queue
    
    def _run(self, text, *args, **kwargs) -> str:
        '''把text转换成语音，并保存，然后返回语音文件路径。'''
        raise
    
    def run(self, *args, **kwargs):
        raise

class Speaker(threading.Thread):
    def __init__(self, audio_queue: queue.Queue):
        """Audio queue队列被不停的拿出音频，进行播放，直到拿到结束标志符号END"""
        super().__init__(self)

        self.audio_queue = audio_queue
    
    def _run(self, *args, **kwargs):
        raise
    
    def run(self, *args, **kwargs):
        raise

def main():
    text = {"text": None}
    text_queue = queue.Queue()
    audio_queue = queue.Queue()

    stt_thread = threading.Thread(target=stt, args=(lingji_stt_gradio_va,text), daemon=True)
    llm_thread = LLM(text, text_queue)
    audio_thread = TTS(text_queue, audio_queue)

    stt_thread.start()
    llm_thread.start()
    audio_thread.start()

    stt_thread.join()
    llm_thread.join()
    audio_thread.join()