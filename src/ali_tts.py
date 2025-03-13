# coding=utf-8
# Installation instructions for pyaudio:
# APPLE Mac OS X
#   brew install portaudio
#   pip install pyaudio
# Debian/Ubuntu
#   sudo apt-get install python-pyaudio python3-pyaudio
#   or
#   pip install pyaudio
# CentOS
#   sudo yum install -y portaudio portaudio-devel && pip install pyaudio
# Microsoft Windows
#   python -m pip install pyaudio

import logging
import os
import pyaudio
import dashscope
import threading
import queue
import time
from dashscope.audio.tts_v2 import *


from http import HTTPStatus
from dashscope import Generation
# END = None
dashscope.api_key = os.environ.get("ALI_TTSSPEAKER")
if dashscope.api_key==None:
    raise "没有提供密钥，请参考https://bailian.console.aliyun.com/?apiKey=1#/api-key"
model = "cosyvoice-v1"
# voice = "longxiaocheng"
voice = "longxiaochun"
# voice = "longyue"

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

class Callback(ResultCallback):
    _player = None
    _stream = None

    def on_open(self):
        LOGGER.info("websocket is open.")
        self._player = pyaudio.PyAudio()
        self._stream = self._player.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=22050,
            output=True,
            frames_per_buffer=1024,
        )

    def on_complete(self):
        LOGGER.info("speech synthesis task complete successfully.")

    def on_error(self, message: str):
        LOGGER.error(f"speech synthesis task failed, {message}")

    def on_close(self):
        LOGGER.info("websocket is closed.")
        # stop player
        self._stream.stop_stream()
        self._stream.close()
        self._player.terminate()

    def on_event(self, message):
        LOGGER.info(f"recv speech synthsis message {message}")

    def on_data(self, data: bytes) -> None:
        LOGGER.info(f"audio result length: {len(data)}")
        # Write data in smaller chunks to prevent underruns
        chunk_size = 1024
        for i in range(0, len(data), chunk_size):
            chunk = data[i:i+chunk_size]
            self._stream.write(chunk)
            # Small sleep to allow buffer to process
            import time
            time.sleep(0.001)  # 1ms sleep between chunks


class AliTTSSpeaker(threading.Thread):
    """
    A speaker class that continuously reads from a text queue and converts text to speech
    using Aliyun's TTS API.
    """
    def __init__(self, text_queue, *args, **kwargs):
        super().__init__(daemon=True)
        self.text_queue = text_queue
        self.callback = Callback()
        self.synthesizer = None  # Initialize as None
        self.running = True
    
    def connect(self):
        """Explicitly establish the TTS connection"""
        try:
            # Close any existing connection first
            if self.synthesizer:
                try:
                    self.synthesizer.streaming_complete()
                except Exception as e:
                    LOGGER.warning(f"Error closing existing synthesizer: {str(e)}")
                    
            # Create a new synthesizer instance
            self.synthesizer = SpeechSynthesizer(
                model=model,
                voice=voice,
                format=AudioFormat.PCM_22050HZ_MONO_16BIT,
                callback=self.callback,
            )
            return True
        except Exception as e:
            LOGGER.error(f"Failed to connect TTS service: {str(e)}")
            return False

    def run(self):
        """Main thread method that processes messages from the queue"""
        # Ensure connection is established before processing
        if not self.connect():
            LOGGER.error("Failed to establish TTS connection, exiting thread")
            return
            
        while self.running:
            try:
                # Process messages as before
                message = self.text_queue.get(timeout=0.01)
                
                if message["type"] == "end":
                    # End of message stream
                    self.synthesizer.streaming_complete()
                    print('TTS Request completed. RequestId:', self.synthesizer.get_last_request_id())
                elif message["type"] == "message":
                    # Process a text chunk
                    content = message["content"]
                    if content:
                        print(f"TTS processing: {content}")
                        # Try to reconnect if connection is lost
                        try:
                            self.synthesizer.streaming_call(content)
                        except Exception as e:
                            LOGGER.error(f"TTS connection error: {str(e)}")
                            if "synthesizer has not been started" in str(e) or "socket is already closed" in str(e):
                                LOGGER.info("Attempting to reconnect TTS service...")
                                if self.connect():
                                    # Try again with the reconnected service
                                    self.synthesizer.streaming_call(content)
                
                self.text_queue.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                LOGGER.error(f"Error in TTS speaker: {str(e)}")
    
    def stop(self):
        """Stop the speaker thread and clean up resources"""
        self.running = False
        
        # Explicitly close the connection
        if self.synthesizer:
            try:
                self.synthesizer.streaming_complete()
            except Exception as e:
                LOGGER.warning(f"Error during synthesizer shutdown: {str(e)}")
                
        if self.is_alive():
            self.join()


def synthesizer_with_llm():
    callback = Callback()
    synthesizer = SpeechSynthesizer(
        model=model,
        voice=voice,
        format=AudioFormat.PCM_22050HZ_MONO_16BIT,
        callback=callback,
    )

    messages = [{"role": "user", "content": "请介绍一下你自己"}]
    responses = Generation.call(
        model="qwen-turbo",
        messages=messages,
        result_format="message",  # set result format as 'message'
        stream=True,  # enable stream output
        incremental_output=True,  # enable incremental output 
    )
    for response in responses:
        if response.status_code == HTTPStatus.OK:
            print(response.output.choices[0]["message"]["content"], end="")
            synthesizer.streaming_call(response.output.choices[0]["message"]["content"])
        else:
            print(
                "Request id: %s, Status code: %s, error code: %s, error message: %s"
                % (
                    response.request_id,
                    response.status_code,
                    response.code,
                    response.message,
                )
            )
    synthesizer.streaming_complete()
    print('requestId: ', synthesizer.get_last_request_id())


# Example usage with a text queue
def tts_speaker_example():
    text_queue = queue.Queue()
    speaker = AliTTSSpeaker(text_queue)
    speaker.start()
    
    # Add some test messages
    text_queue.put({"type": "message", "content": "你好，我是一个AI助手。"})
    text_queue.put({"type": "message", "content": "我可以帮助你回答问题，提供信息。"})
    text_queue.put({"type": "message", "content": "需要什么帮助吗？"})
    text_queue.put({"type": "end", "content": None})
    
    # Wait for queue to be processed
    text_queue.join()
    
    # Give some time for the last audio to finish playing
    time.sleep(2)
    speaker.stop()


if __name__ == "__main__":
    # load_config()
    # Choose which example to run
    # synthesizer_with_llm()
    tts_speaker_example()