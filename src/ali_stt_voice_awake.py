# # For prerequisites running the following sample, visit https://help.aliyun.com/document_detail/611472.html
# import os
# import time
# import json
# import logging
# import pyaudio
# import threading
# import dashscope
# import speech_recognition as sr

# from http import HTTPStatus
# from typing import Any, Dict, List
# from dashscope.api_entities.dashscope_response import RecognitionResponse
# from dashscope.audio.asr import (Recognition, RecognitionCallback, RecognitionResult)


# stream = None                              # 音频流对象，用于读取音频数据。
# mic = None                                 # 麦克风对象
# transform_res = {'sentence':None}                       # 转写结果记录,记录每一次转写结果.
# recognition_active = False                 # 是否开始实时语音识别的标志,第一次点击麦克风按钮会设置为True,第二次点击会设置为False
# stt_thread = None                          # 语音识别运行线程, 得当作全局变量,否则第二次运行的时候,会识别不到这个变量,因为其只在lingji_stt_gradio函数的if语句中被初始化了,第二次运行的时候(即第二次点击的时候),会进入else分支,然后发生找不到这个变量的错误,设置为全局变量可以解决这个问题.
# sentence_lock = threading.Lock()           # 锁对象，用于控制在句子结束时暂停发送音频数据


# def get_logger(logger_name=__name__):
#     # 日志收集器
#     logger = logging.getLogger(logger_name)
#     logger.setLevel(logging.DEBUG)
    
#     # Avoid passing messages to the root logger
#     logger.propagate = False
    
#     # If the logger already has handlers, avoid adding duplicate ones
#     if not logger.hasHandlers():
#         # 设置控制台处理器，当logger被调用时，控制台处理器额外输出被调用的位置。
#         # 创建一个控制台处理器并设置级别为DEBUG
#         ch = logging.StreamHandler()
#         ch.setLevel(logging.DEBUG)
#         # 创建一个格式化器，并设置格式包括文件名和行号
#         formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(pathname)s:%(lineno)d - %(message)s')
#         ch.setFormatter(formatter)

#         # 将处理器添加到logger
#         logger.addHandler(ch)

#     return logger


# class Recognition(Recognition):
#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)
    
#     def _Recognition__receive_worker(self):
#         """Asynchronously, initiate a real-time speech recognition request and
#            obtain the result for parsing.
#         """
#         global sentence_lock
#         responses = self._Recognition__launch_request()
#         for part in responses:
#             if part.status_code == HTTPStatus.OK:
#                 is_output_empty = len(part.output)==0
#                 is_sentence_end = RecognitionResponse.is_sentence_end(part.output['sentence']) if 'sentence' in part.output else False
                
#                 # 当句子结束时，获取锁，此时要判断是否是句子结束了，
#                 # 防止再准备结束时，还有语音进入，导致覆盖之前的句子。
                
#                 if is_output_empty or is_sentence_end:
#                     logging.info("获取锁")
#                     sentence_lock.acquire()
#                     if is_sentence_end:
                        
#                         usage: Dict[str, Any] = None
#                         useags: List[Any] = None
#                         if 'sentence' in part.output and part.usage is not None:
#                             usage = {
#                                 'end_time': part.output['sentence']['end_time'],
#                                 'usage': part.usage
#                             }
#                             useags = [usage]

#                         self._callback.on_event(
#                             RecognitionResult(
#                                 RecognitionResponse.from_api_response(part),
#                                 usages=useags))
#                         self._callback.on_complete()
                        
#                         # on_complete执行完毕后，释放锁，允许继续发送音频数据
#                         sentence_lock.release()
#                 else:
#                     sentence_lock.release()
#                     usage: Dict[str, Any] = None
#                     useags: List[Any] = None
#                     if 'sentence' in part.output and part.usage is not None:
#                         usage = {
#                             'end_time': part.output['sentence']['end_time'],
#                             'usage': part.usage
#                         }
#                         useags = [usage]

#                     self._callback.on_event(
#                         RecognitionResult(
#                             RecognitionResponse.from_api_response(part),
#                             usages=useags))
#             else:
#                 self._running = False
#                 self._stream_data.clear()
#                 self._callback.on_error(
#                     RecognitionResult(
#                         RecognitionResponse.from_api_response(part)))
#                 self._callback.on_close()
#                 break

# # 回调函数，在某个条件下会调用其成员函数
# class Callback(RecognitionCallback):
#     def on_open(self) -> None:
#         global stream, mic
        
#         # 创建一个Pyaudio实例，用于与音频接口交互，比如打开、关闭音频流和获取设备信息。
#         mic = pyaudio.PyAudio()
#         # 创建一个音频流，用于从麦克风或其他音频源获取音频数据。
#         stream = mic.open(
#             format=pyaudio.paInt16,  # 音频数据格式,pyaudio.paInt16表示16位深度
#             channels=1,              # 指定音频的声道数，1表示单声道Mono
#             rate=16000,              # 指定音频的采样率，16000表示每秒采样1600次
#             input=True)              # 指定该流用于输入，用于从麦克风或其他音频源获取音频数据
    
#     def on_close(self) -> None:
#         global stream, mic

#         if stream:
#             # 关闭音频流，防止继续读取数据
#             stream.stop_stream()
#             stream.close()
#             stream = None
#         if mic:
#             # 关闭PyAudio实例，释放资源
#             mic.terminate()
#             mic = None
    
#     def on_event(self, result: RecognitionResult) -> None:
#         # 处理每一次转写结果

#         transform_res['sentence'] = result.get_sentence()['text']
#         print("RecognitionCallback sentence: ", result.get_sentence())

#     def on_complete(self) -> None:
#         # 当识别全部完成时调用
#         global transform_res

#         print("RecognitionCallback on_complete：", transform_res.get_sentence()['text'])

# class CallbackVoiceAwake(Callback):
#     def on_complete(self) -> None:
#         global recognition_active,transform_res,recognition

#         recognition_active = False  # 识别结束，将标志设置为False，这样主线程就可以关闭录音实例了。
#         recognition.stop()          # 停止语音识别
#         del recognition
#         recognition = None

#         print("RecognitionCallback on_complete：", transform_res['sentence'])

# class AudioRecognitionThread(threading.Thread):
#     def __init__(self):
#         # 设置为守护进程，当主程序崩溃时，其也会自动结束。
#         super().__init__(daemon=True)

#         self.logger = logging.getLogger(__name__)

#         if not self.logger.handlers:
#             logging.basicConfig(level=logging.INFO)

#     def run(self):
#         """覆盖Thread类的run方法，用于定义线程执行的任务。"""
#         global stream, recognition, recognition_active, sentence_lock

#         # 先进行监听，如果没有声音，则不进发送音频数据

#         while not stream:                     # 等待stream,麦克风等设备初始化好,再进行语音识别.
#             time.sleep(0.001)
#             continue

#         while recognition_active:
#             try:
#                 # 尝试获取锁，如果获取不到（句子结束时锁被占用），则跳过发送音频数据
#                 if sentence_lock.acquire(blocking=False):
#                     try:
#                         if recognition_active:  # 如果on_complete运行完了，而sentence_lock刚好被拿到，则会运行发送frame的代码，虽然可以无视报错，但使用if语句可以避免报错的发生。
#                             data = stream.read(3200, exception_on_overflow=False)
#                             recognition.send_audio_frame(data)
#                     except Exception as e:
#                         print(e)
#                         pass
#                     finally:
#                         # 释放锁，允许其他线程获取锁
#                         sentence_lock.release()
#             except Exception as e:
#                 print(f"Lock error: {e}")
#                 pass
#             time.sleep(0.01)  # 控制循环频率，减少CPU占用
#         logging.log(level=logging.INFO, msg="语音帧发送线程已结束...")

# def lingji_stt_gradio_va(*args, **kwargs) -> str:
#     '''
#     拥有语音唤醒功能的实时文本转语音函数
#     '''
#     global recognition, recognition_active, stream, stt_thread,transform_res
    
#     dashscope.api_key=os.environ.get('lingji_key')
    
#     # 麦克风准备
#     # Recognition.SILENCE_TIMEOUT_S = 200      
#     # kwargs = {REQUEST_TIMEOUT_KEYWORD: 120}
#     recognition= Recognition(
#         model="paraformer-realtime-v1",   # 语音识别模型
#         format='pcm',                     # 音频格式
#         sample_rate=16000,                # 指定音频的采样率，16000表示每秒采样16000次。
#         callback=CallbackVoiceAwake(),
#         # **kwargs
#         )

#     recognition.start()
    
#     stt_thread = AudioRecognitionThread() # 发送语音帧的线程
#     recognition_active = True             # 可以进行录音了
#     stt_thread.start()                    # 开始识音
#     # 关闭录音实例
#     while recognition_active:             # 等待Callback的on_complete回调函数把recognition_active设置为False
#         time.sleep(0.01)
#     stt_thread.join()                     # 此时stt线程应该是要结束运行的.
    


#     result = transform_res['sentence']
#     transform_res['sentence'] = None
#     return result


# if __name__ == "__main__":
#     if os.environ.get('lingji_key', "sk-8deaaacf2fb34929a076dfc993273195") is None:
#         logger = get_logger("api_key_checker")
#         logger.error("Please set your DashScope API key in the environment variable DASH_SCOPE_API_KEY")
#         exit(1)
#     lingji_stt_gradio_va()


