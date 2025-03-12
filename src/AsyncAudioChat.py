import os
import sys
import time
import json
import queue
import random
import string
import logging
import threading
import multiprocessing

from typing import List
from pygame import mixer
from zijie_tts import tts
from threading import Thread
from ali_tts import AliTTSSpeaker
from zijie_stt import zijie_stt_gradio
from langchain_ollama import ChatOllama 
from flask import Flask, request,send_file, make_response,after_this_request


from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.acs_exception.exceptions import ClientException
from aliyunsdkcore.acs_exception.exceptions import ServerException
from aliyunsdknlp_automl.request.v20191111 import RunPreTrainServiceRequest


# Aliyun Machine Translation
from alibabacloud_tea_util import models as util_models
from alibabacloud_tea_util.client import Client as UtilClient
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_alimt20181012.models import TranslateGeneralResponse
from alibabacloud_alimt20181012 import models as alimt_20181012_models
from alibabacloud_alimt20181012.client import Client as alimt20181012Client



sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

# from ali_stt_voice_awake import lingji_stt_gradio_va
END = None  # 使用None表示结束标识符
OUTPUT_LOG_DEBUG = True # 是否输出日志
PREPARED_TEXT = "你好，此次输入不合规，顾不做回答（此次对话不会记录到聊天记录中）。" # 内容审核模块，如果输入不合规，则输出默认回复

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

def load_config():
    """
    检测当前文件的目录下是否有"config.json"文件，如果有的话，则解析，并放到环境变量中。
    """
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                for key, value in config.items():
                    os.environ[key] = str(value)
                LOGGER.info(f"Loaded config from {config_path}")
        except Exception as e:
            LOGGER.error(f"Error loading config from {config_path}: {e}")
    else:
        LOGGER.warning(f"Config file not found at {config_path}")

LOGGER = get_logger()
load_config()
app = Flask(__name__)


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

        # import random
        # self.text['text'] = random.choice(["你好", "你是谁?"])

class RemoteSTT(STT):
    def __init__(self, stt_api_for_1file, text, *args, **kwargs):
        '''
        stt_api_for_1file: 一个函数，接收一个音频文件路径，返回一个字符串。
        '''
        STT.__init__(self, stt_api_for_1file, text, *args, **kwargs)
        self.audio_queue = multiprocessing.Queue()

    def run(self):
        # Start Flask server in a separate thread
        server_thread = Thread(target=self.start_flask, daemon=True)
        server_thread.start()
        
        # Process audio data from the queue
        while True:
            if not self.audio_queue.empty():
                audio_data = self.audio_queue.get()
                random_name = self.generate_random_name()
                audio_file = f"{random_name}.wav"
                with open(audio_file, 'wb') as f:
                    f.write(audio_data)
                self.text['text'] = self.stt_api(audio_file)
                LOGGER.info(f"Transcribed Text: {self.text['text']}")
                # delete audio file with its absolute path
                os.remove(audio_file)
                break
            else:
                time.sleep(1)
                LOGGER.info("Waiting for audio data...")

    def start_flask(self):
        @app.route('/upload', methods=['POST'])
        def receive_audio():
            audio_data = request.data
            self.audio_queue.put(audio_data)
            return 'Audio data received', 200

        app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

    def generate_random_name(self, length=8):
        parent_path = '/'
        return parent_path + ''.join(random.choices(string.ascii_letters + string.digits, k=length))
    
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
        LOGGER.debug("Prompt is \n\n{}\n\n".format(final_input))
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
            ('system', "You are a helpful assistant and only can speak English and Chinese."),
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

            # 我们对response_delta进行这样的操作，从左到右，判断其是否有有'，。！？'等符号，如果有的话，就从左到右，从开头到这个符号为止，截取这段文本，然后把这段文本放入到text队列中，以及拼接到old_total_response对象右侧。如果没有，则不做操作。
            while response_delta:
                # 找到第一个标点符号的位置
                ## i for i in xxx, 叫做生成器表达式，使用圆括号包裹生成器表达式，表示这是一个generator，而使用[]或{}的话，则表示是一个列表或集合表达式，
                ## 前者不会把for表达式执行完，然后返回结果，而是返回一个generator对象，只有在遍历这个对象（比如使用next方法）的时候才会执行for表达式，然后返回结果。
                ## 而列表或集合表达式会立即执行for表达式，然后返回结果。
                ## 返回generator的方式称为惰性计算，只有在需要的时候才把值放到内存中。每次迭代时，生成器都会返回一个值，然后记住当前位置，下次遍历这个生成器时，则会从之前记住的位置的下一个位置开始便利。
                ## 不把英文的'.'算入截断标点符号中，因为大模型生成的文本中，标题会用到'.'，比如'6.'
                punctuation_index = next((i for i, char in enumerate(response_delta) if char in [',' , '，', '。', '！', '？', '!', '?']), -1)
                if punctuation_index != -1:                          # 如果生成器表达式不是空的，即找的到第一个标点符号
                    text = response_delta[:punctuation_index + 1]    # 截取这段文本
                    old_total_response += text                  # 拼接到old_total_response对象右侧
                    self.text_queue.put(text)               # 把这段文本放入到text队列中
                    LOGGER.debug("LLM: new sentence: {}".format(old_total_response))
                    
                    # 如果response_delta中存在不止一个符号，那么我们在做完第一个符号对应的工作后，把response_delta更新为去掉第一段文本的剩下文本，然后进行同样的操作。
                    response_delta = response_delta[punctuation_index + 1:]
                
                # 如果response_delta没有'，。！？'等符号了，则不做操作。
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

class LLM4AliTTSSpeaker(LLM):
    
    def _LLM__run2_ollama(self, llm_iterator, *args, **kwargs):
        for response_token in llm_iterator:
            response_token = response_token.content
            
            self.text_queue.put({
                "type": "message",
                "content": response_token
            })
        
        # 生成完成后，往队列中放入一个END结束标识符。
        self.text_queue.put({
            "type": "end",
            "content": END
        })

class TTS(threading.Thread):
    def __init__(self, text_queue: queue.Queue, audio_queue: queue.Queue, *args, **kwargs):
        """从Text queue队列中依次拿出sentence，并把其转换成音频，然后存储在一个Audio queue队列中。如果拿到结束标志符号END，则把这个符号放到Audio queue队列中。"""
        super().__init__(daemon=True)

        self.text_queue = text_queue
        self.audio_queue = audio_queue

        self.args_for_run = args
        self.kwargs_for_run = kwargs
    
    def _run(self, text, *args, **kwargs) -> str:
        '''把text转换成语音，并保存，然后返回语音文件路径。'''
        return tts(text, *self.args_for_run, **self.kwargs_for_run)
    
    def run(self, *args, **kwargs):
        while True:
            # block if necessary until an item is available
            sentence = self.text_queue.get()
            if sentence is None:
                self.audio_queue.put(None)
                break
            self.audio_queue.put(self._run(sentence, *self.args_for_run, **self.kwargs_for_run))

class Speaker(threading.Thread):
    def __init__(self, audio_queue: queue.Queue):
        """Audio queue队列被不停的拿出音频，进行播放，直到拿到结束标志符号END"""
        super().__init__(daemon=True)

        self.audio_queue = audio_queue
    
    def _run(self, *args, **kwargs):
        # 使用mixer类进行播放         
        try:
            mixer.init()
            while True:
                audio = self.audio_queue.get()
                # LOGGER.debug("Speaker: Received audio: {}".format(audio))
                if audio is None:
                    break
                
                mixer.music.load(audio)
                mixer.music.play()
                while mixer.music.get_busy():
                    time.sleep(0.001)
                
                mixer.music.unload()
                os.remove(audio)
            mixer.quit()
        except Exception as e:
            LOGGER.error("Speaker: Error in _run: {}".format(e))
    
    def run(self, *args, **kwargs):
        self._run(*args, **kwargs)
        LOGGER.debug("Speaker: Speaker thread exited.")

class RemoteSpeaker(Speaker):
    def __init__(self, audio_queue: queue.Queue):
        """Initialize RemoteSpeaker with an audio queue and set up Flask endpoints"""
        super().__init__(audio_queue)
        self.current_audio = None
        self.audio_ready = threading.Event()
        self.end_of_audio = False
        self.final_request_received = threading.Event()
        self.workflow_started = threading.Event()  # New event for workflow control
        self.heartbeat_timeout = 10  # 25 second timeout
        self.should_terminate = threading.Event()  # New event for graceful termination
        
        app.url_map._rules.clear()
        app.url_map._rules_by_endpoint.clear()

        # @app.route('/start', methods=['POST'])
        # def receive_start_signal():
        #     """Endpoint to receive the initial greeting message"""
        #     self.workflow_started.set()
        #     # regarded as a heartbeat
        #     self.last_heartbeat = time.time()
        #     LOGGER.debug("RemoteSpeaker: Received start signal")
        #     return 'Workflow started', 200


        # I may receive a heartbeat from client before the class' start method is called 
        # because this method is registered when the class is instantiated.
        # so I can receive a heartbeat when the RemoteSTT thread is running.
        @app.route('/heartbeat', methods=['POST', 'GET'])
        def heartbeat():
            """Endpoint to receive heartbeat from client"""
            self.last_heartbeat = time.time()
            LOGGER.debug("RemoteSpeaker: Heartbeat received")
            return 'Heartbeat received', 200

        @app.route('/audio', methods=['GET'])
        def serve_audio():
            # # Only serve audio after receiving start signal
            # if not self.workflow_started.is_set():
            #     return 'Workflow not started', 403
            
            if self.audio_ready.wait(timeout=300):

                if self.current_audio:
                    with open(self.current_audio, 'rb') as f:
                        audio_data = f.read()
                    self.current_audio = None
                    self.audio_ready.clear()
                    return audio_data, 200
                elif self.end_of_audio:
                    @after_this_request
                    def set_final_received(response):
                        # This return is for Flask's middleware chain
                        # Not for sending to client (already sent)
                        # to confirm that the code after the response to client is worked

                        self.final_request_received.set()   # Do task after serving client
                        return response  # Tell Flask "Yes, I did my after-serving task"
                    return 'END', 204
                
            return 'No audio available', 404

    def _run(self, *args, **kwargs):
        server_thread = Thread(target=lambda: app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False, threaded=True), daemon=True)
        server_thread.start()

        flag_first_audio = True

        while not self.should_terminate.is_set():
            audio = self.audio_queue.get()

            # we can't start heartbeat monitor thread before the first audio is received,
            # because the first audio may be available for a long time at the first time because of the LLM loading time.
            if flag_first_audio:
                # Start heartbeat monitor thread
                heartbeat_thread = Thread(target=self._monitor_heartbeat, daemon=True)
                heartbeat_thread.start()
                LOGGER.debug("RemoteSpeaker: Heartbeat monitor thread started")

                flag_first_audio = False

            self.current_audio = audio
            self.audio_ready.set()

            if audio is None:
                self.end_of_audio = True
                # Wait for final request with timeout
                if self.final_request_received.wait(timeout=30):
                    LOGGER.debug("RemoteSpeaker: Final END status sent to client")
                else:
                    LOGGER.warning("RemoteSpeaker: Timeout waiting for final request")
                break
            
            while self.current_audio and not self.should_terminate.is_set():
                LOGGER.debug(f"RemoteSpeaker: Audio file {audio} ready for serving")
                time.sleep(0.5)
        
        LOGGER.debug("RemoteSpeaker: All audio files processed")

    def _monitor_heartbeat(self):
        """Monitor heartbeat and terminate if client is unresponsive"""
        # Reset last_heartbeat when starting the monitor
        self.last_heartbeat = time.time()

        while not self.should_terminate.is_set():
            time.sleep(1)
            if time.time() - self.last_heartbeat > self.heartbeat_timeout:
                LOGGER.error("RemoteSpeaker: Client heartbeat timeout, terminating thread")
                self.should_terminate.set()
                break


class ContextMonitor(threading.Thread):
    def __init__(self, text, flag_is_valid, text_queue:queue.Queue, prepared_text, *args, **kwargs):
        super().__init__(daemon=True)
        self.text = text
        self.flag_is_valid = flag_is_valid

        self.args_for_run = args
        self.kwargs_for_run = kwargs
        self.text_queue = text_queue
        self.prepared_text = prepared_text
    
    def run(self) -> bool:
        self.flag_is_valid['value'] = self._run(self.text['text'], *self.args_for_run, **self.kwargs_for_run)
        
        if self.flag_is_valid['value']:
            LOGGER.debug("ContextMonitor: Context check passed.")
        else:
            LOGGER.debug("ContextMonitor: Context check failed.")
            self.text_queue.put(self.prepared_text)
            self.text_queue.put(END)

    def _run(self, text, *args, **kwargs):
        return self.__run_alibaba_cloud(text, *args, **kwargs)
    def __run_alibaba_cloud(self, text:str, *args, **kwargs):
        assert type(text)==str
        
        access_key_id = os.environ.get("context_checking_access_key_id")
        access_key_secret = os.environ.get("context_checking_access_key_secret")

        # Initialize AcsClient instance
        client = AcsClient(
        access_key_id,
        access_key_secret,
        "cn-hangzhou"
        )
        content = {"session_id": 0, "text": text}
        # Initialize a request and set parameters
        request = RunPreTrainServiceRequest.RunPreTrainServiceRequest()
        request.set_ServiceName('NLP-Dialog-Risk')
        request.set_PredictContent(json.dumps(content))
        # Print response
        response = client.do_action_with_exception(request)
        resp_obj = json.loads(response)
        predict_result = json.loads(resp_obj['PredictResult'])
        if predict_result['label'] == "abuse":
            return False
        else:
            return True

class MT(threading.Thread):
    def __init__(self, text):
        '''Module of Machine Translation'''
        super().__init__(daemon=True)
        self.text = text

    @staticmethod
    def create_client() -> alimt20181012Client:
        """
        使用AK&SK初始化账号Client
        @return: Client
        @throws Exception
        """
        # 工程代码泄露可能会导致 AccessKey 泄露，并威胁账号下所有资源的安全性。以下代码示例仅供参考。
        # 建议使用更安全的 STS 方式，更多鉴权访问方式请参见：https://help.aliyun.com/document_detail/378659.html。
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')) as F:
            args = json.load(F)
            config = open_api_models.Config(
                # 必填，请确保代码运行环境设置了环境变量 ALIBABA_CLOUD_ACCESS_KEY_ID。,
                access_key_id=args['machine_translation_key_id'],
                # 必填，请确保代码运行环境设置了环境变量 ALIBABA_CLOUD_ACCESS_KEY_SECRET。,
                access_key_secret=args['machine_translation_secret_key']
            )
        # Endpoint 请参考 https://api.aliyun.com/product/alimt
        config.endpoint = f'mt.cn-hangzhou.aliyuncs.com'
        return alimt20181012Client(config)

    def run(self):          
        self.text['text'] = self.main(self.text['text'])

    @staticmethod
    def main(
        source_text,
        *args,
        **kwargs
    ) -> None:
        client = MT.create_client()
        translate_general_request = alimt_20181012_models.TranslateGeneralRequest(
            format_type='text',
            source_language='zh',
            target_language='en',
            source_text=source_text,
            scene='general'
        )
        runtime = util_models.RuntimeOptions()
        try:
            result:TranslateGeneralResponse = client.translate_general_with_options(translate_general_request, runtime)
            return result.body.data.translated
        except Exception as error:
            # 此处仅做打印展示，请谨慎对待异常处理，在工程项目中切勿直接忽略异常。
            # 错误 message
            print(error.message)
            # 诊断地址
            print(error.data.get("Recommend"))
            UtilClient.assert_as_string(error.message)

    @staticmethod
    async def main_async(
        args: List[str],
    ) -> None:
        client = MT.create_client()
        translate_general_request = alimt_20181012_models.TranslateGeneralRequest(
            format_type='text',
            source_language='zh',
            target_language='en',
            source_text='你好',
            scene='general'
        )
        runtime = util_models.RuntimeOptions()
        try:
            # 复制代码运行请自行打印 API 的返回值
            await client.translate_general_with_options_async(translate_general_request, runtime)
        except Exception as error:
            # 此处仅做打印展示，请谨慎对待异常处理，在工程项目中切勿直接忽略异常。
            # 错误 message
            print(error.message)
            # 诊断地址
            print(error.data.get("Recommend"))
            UtilClient.assert_as_string(error.message)


class Backend(threading.Thread):
    def __init__(self, *args, **kwargs):
        """把整个异步对话模块整合成一个线程。"""
        super().__init__(daemon=True)
        self.text = kwargs.get("text", {"text": None})
        self.text_queue = queue.Queue()
        self.audio_queue = queue.Queue()

        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')) as F:
            _args = json.load(F)
            self._ollama_model_name = _args['model_name']
            self._ollama_base_url = _args['llm_url']
            for key,value in _args.items():
                os.environ[key] = value
                
        self.stt_thread = STT(zijie_stt_gradio, self.text)
        self.input_preprocessing_thread = InputProcess(self.text, kwargs.get("history", None))
        self.llm_thread = LLM(self.text, self.text_queue, ollama_model_name=self._ollama_model_name, ollama_base_url=self._ollama_base_url)
        self.audio_thread = TTS(self.text_queue, self.audio_queue)
        self.speaker_thread = Speaker(self.audio_queue)

    def run(self,):
        try:
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
        except:
            pass

class Backend4AliTTSSpeaker(threading.Thread):
    def __init__(self, *args, **kwargs):
        """把整个异步对话模块整合成一个线程。"""
        super().__init__(daemon=True)
        self.text = kwargs.get("text", {"text": None})
        self.text_queue = queue.Queue()

        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')) as F:
            _args = json.load(F)
            self._ollama_model_name = _args['model_name']
            self._ollama_base_url = _args['llm_url']
            for key,value in _args.items():
                os.environ[key] = value
                
        self.stt_thread = STT(zijie_stt_gradio, self.text)
        self.input_preprocessing_thread = InputProcess(self.text, kwargs.get("history", None))
        self.llm_thread = LLM4AliTTSSpeaker(self.text, self.text_queue, ollama_model_name=self._ollama_model_name, ollama_base_url=self._ollama_base_url)
        self.ali_tts_thread = AliTTSSpeaker(self.text_queue)

    def run(self,):
        try:
            self.stt_thread.start()
            self.stt_thread.join()
            
            self.input_preprocessing_thread.start()
            self.input_preprocessing_thread.join()
            
            self.llm_thread.start()
            self.ali_tts_thread.start()

            self.llm_thread.join()

            self.text_queue.join()

            self.ali_tts_thread.stop()
        except:
            pass

class ContextMonitorBackend(Backend):
    def __init__(self, prepared_text:str=PREPARED_TEXT, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.flag_is_valid = {"value": False}
        self.context_monitor = ContextMonitor(self.text, self.flag_is_valid, self.text_queue, prepared_text)

    def run(self,):
        try:
            self.stt_thread.start()
            self.stt_thread.join()
            
            self.context_monitor.start()
            self.context_monitor.join()
            
            if self.flag_is_valid['value']:
                self.input_preprocessing_thread.start()
                self.input_preprocessing_thread.join()

                self.llm_thread.start()
                self.audio_thread.start()
                self.speaker_thread.start()

                self.llm_thread.join()
                self.audio_thread.join()
                self.speaker_thread.join()
            else:
                LOGGER.warning("Invalid context, skipping llm")
                self.audio_thread.start()
                self.speaker_thread.start()

                self.audio_thread.join()
                self.speaker_thread.join()
        except:
            pass

class PureEnglishChatBackend(Backend):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.machine_translation_thrad = MT(text=self.text)
        self.audio_thread = TTS(self.text_queue, self.audio_queue, voice_type=kwargs.get("voice_type", "BV503_streaming"))
        self.input_type = kwargs.get("input_type", "en")
    
    def run(self):
        self.stt_thread.start()
        self.stt_thread.join()
        
        if self.input_type == "zh":
            self.machine_translation_thrad.start()
            self.machine_translation_thrad.join()
        
        self.llm_thread.start()
        self.audio_thread.start()
        self.speaker_thread.start()

        self.llm_thread.join()
        self.audio_thread.join()
        self.speaker_thread.join()


class VoiceAwakeBackend(multiprocessing.Process):
    global LOCK
    LOCK = threading.Lock()
    
    class Monitor(threading.Thread):
        global LOCK
        def __init__(self, text:dict, flag_kill_dida:dict, flag_kill_monitor:dict) -> None:
            super().__init__(daemon=True)
            self.text = text
            self.flag_kill_dida = flag_kill_dida
            self.flag_kill_monitor = flag_kill_monitor
        
        def run(self):
            while True:
                # If there is any text, kill dida and itself.
                if self.text['text']:
                    # set the value as True, and then the dida thread will suicide.
                    with LOCK:
                        self.flag_kill_dida['value'] = True
                    LOGGER.debug(f"monitor is exit.") if OUTPUT_LOG_DEBUG else None
                    break
                elif self.flag_kill_monitor['value']:
                    LOGGER.debug(f"monitor is exit.") if OUTPUT_LOG_DEBUG else None
                    break
                else:
                    time.sleep(0.01)
    
    class Dida(threading.Thread):
        global LOCK
        def __init__(self,flag_kill_dida:dict, flag_kill_monitor:dict, flag_kill_mfw:dict,  main_work_flow:multiprocessing.Process, dida_time:float=30):
            super().__init__(daemon=True)
            self.flag_kill_dida = flag_kill_dida
            self.dida_time = dida_time
            self.flag_kill_monitor = flag_kill_monitor
            self.mwf = main_work_flow
            self.flag_kill_mfw = flag_kill_mfw
            
            def _kill_dida(flag_dida, flag_monitor, flag_kill_mfw):
                with LOCK:
                    # 如果就在刚刚，monitor检测到输入了，而此时dida也刚好触发了这个函数（还没来得及kill掉self.dida），那么就要停止这个函数的运行，否则会kill掉main work flow
                    if flag_dida['value']:
                        return
                    else:
                        LOGGER.debug(f"I will kill main work flow soon") if OUTPUT_LOG_DEBUG else None
                        LOGGER.debug(f"I will kill monitor soon") if OUTPUT_LOG_DEBUG else None
                        LOGGER.debug(f"I will kill dida soon") if OUTPUT_LOG_DEBUG else None
                        flag_dida['value'] = True
                        flag_monitor['value'] = True
                        flag_kill_mfw['value'] = True
                        
            self.dida = threading.Timer(self.dida_time, _kill_dida, args=[self.flag_kill_dida, self.flag_kill_monitor, self.flag_kill_mfw])
            self.dida.start()
        
        def run(self,):
            while True:
                # If monitor thread set the flag to True, then kill dida.
                if self.flag_kill_dida['value'] and not self.flag_kill_mfw['value']:
                    LOGGER.debug(f"Dida is killed but main workflow is still running.") if OUTPUT_LOG_DEBUG else None
                    self.dida.cancel()
                    break
                # or if itself did so(be silent more than dida_time), 
                elif self.flag_kill_dida['value'] and self.flag_kill_mfw['value']:
                    LOGGER.debug(f"Dida and main work flow are killed.") if OUTPUT_LOG_DEBUG else None
                    if self.mwf.is_alive():
                        self.mwf.terminate()
                    break
                else:
                    time.sleep(0.01)

    def __init__(self, awake_words:str, time_to_sleep:float=30, *args, **kwargs):
        """
        语音唤醒
        """
        super().__init__()
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')) as F:
            _args = json.load(F)
            self._ollama_model_name = _args['model_name']
            self._ollama_base_url = _args['llm_url']
            for key,value in _args.items():
                os.environ[key] = value
        
        self.manager = multiprocessing.Manager()
        # for key words
        self.key_word = awake_words
        self.key_word_text = self.manager.dict({"text":""})
        # for monitor: create an area of shared memory for {"text": None}
        self.text_main_work_flow = self.manager.dict({"text":None})
        
        self.time_to_sleep = time_to_sleep

        self.flag_kill_dida = {"value": False}
        self.flag_kill_monitor = {"value": False}
        self.flag_kill_mfw = {"value":False}
        
        self.welcome_audio_path = None

    def run(self):
        while True:
            self.key_word_stt = multiprocessing.Process(target=self.__kw_detector, kwargs={"text":self.key_word_text})
            self.key_word_stt.start()
            self.key_word_stt.join()
            if self.is_kw_detected():
                self.key_word_text["text"] = ""
                
                while True:
                    # 如果STT模块给出的结果里含有唤醒词，那么就激活后面的Main Work Flow，同时激活Monitor和Dida。
                    # If the result of STT module contains the wake up word, then activate the main work flow, monitor and dida.
                    self.main_work_flow = multiprocessing.Process(target=self.create_main_work_flow, kwargs={"text":self.text_main_work_flow})
                    self.main_work_flow.start()

                    self.monitor = self.Monitor(self.text_main_work_flow, self.flag_kill_dida, self.flag_kill_monitor)
                    self.dida = self.Dida(self.flag_kill_dida, self.flag_kill_monitor, self.flag_kill_mfw, self.main_work_flow, self.time_to_sleep)
                    self.monitor.start()
                    self.dida.start()

                    self.monitor.join()
                    self.dida.join()
                    self.main_work_flow.join()

                    # go to sleep
                    if self.flag_kill_dida['value'] and self.flag_kill_mfw['value'] and self.flag_kill_mfw['value']:
                        self.flag_kill_dida["value"] = False
                        self.flag_kill_monitor["value"] = False
                        self.flag_kill_mfw["value"] = False
                        self.text_main_work_flow["text"] = None
                        LOGGER.info(f"Be silent over {self.time_to_sleep}s, turn to sleep mode.")
                        break
                    else:
                        self.flag_kill_dida["value"] = False
                        self.flag_kill_monitor["value"] = False
                        self.flag_kill_mfw["value"] = False
                        self.text_main_work_flow["text"] = None
            else:
                time.sleep(0.01)
    
    def create_main_work_flow(self, text):
        self.backend = ContextMonitorBackend(text=text)
        self.backend.start()
        self.backend.join()

    def is_kw_detected(self,):
        try:
            transcript = self.key_word_text['text']
            if "你好" in transcript:
                self.__play_welcome_audio()
                LOGGER.info("Wake word detected!")
                return True
        except Exception as e:
            print(f"Error occurred: {e}")

    def __play_welcome_audio(self):
        if self.welcome_audio_path is None:
            self.welcome_audio_path = tts("诶！")
        # 使用音频需要在一个新的进程里播放，否则其他进程将无法使用音频设备。
        play_audio = multiprocessing.Process(target=self.__play_audio, args=(self.welcome_audio_path,))
        play_audio.daemon=True
        play_audio.start()
        play_audio.join()

    def __play_audio(self, audio_path):
        mixer.init()
        mixer.music.load(audio_path)
        mixer.music.play()
        while mixer.music.get_busy():
            time.sleep(0.001)
        
        mixer.music.unload()
        mixer.quit()  

    def __kw_detector(self, text):
        stt = STT(zijie_stt_gradio, text)
        stt.start()
        stt.join()


if __name__ == "__main__":
    
    # main_thread = VoiceAwakeBackend("你好", time_to_sleep=5)
    # main_thread = Backend()
    # main_thread = ContextMonitorBackend()
    # main_thread = PureEnglishChatBackend(input_type="zh")
    # main_thread = PureEnglishChatBackend()
    main_thread = Backend4AliTTSSpeaker()
    main_thread.start()
    main_thread.join()
    