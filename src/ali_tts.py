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

import pyaudio
import dashscope
import threading
import queue
import time
from dashscope.audio.tts_v2 import *


from http import HTTPStatus
from dashscope import Generation
# from AsyncAudioChat_test import load_config, END
END = None
# 若没有将API Key配置到环境变量中，需将下面这行代码注释放开，并将apiKey替换为自己的API Key
dashscope.api_key = "sk-8deaaacf2fb34929a076dfc993273195"
model = "cosyvoice-v1"
voice = "longxiaocheng"


class Callback(ResultCallback):
    _player = None
    _stream = None

    def on_open(self):
        print("websocket is open.")
        self._player = pyaudio.PyAudio()
        self._stream = self._player.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=22050,
            output=True,
            frames_per_buffer=1024,
        )

    def on_complete(self):
        print("speech synthesis task complete successfully.")

    def on_error(self, message: str):
        print(f"speech synthesis task failed, {message}")

    def on_close(self):
        print("websocket is closed.")
        # stop player
        self._stream.stop_stream()
        self._stream.close()
        self._player.terminate()

    def on_event(self, message):
        print(f"recv speech synthsis message {message}")

    def on_data(self, data: bytes) -> None:
        print("audio result length:", len(data))
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
        self.synthesizer = SpeechSynthesizer(
            model=model,
            voice=voice,
            format=AudioFormat.PCM_22050HZ_MONO_16BIT,
            callback=self.callback,
        )
        self.running = True
    
    def run(self):
        """Main thread method that processes messages from the queue"""
        while self.running:
            try:
                # Get message from queue, with a timeout to allow checking self.running
                message = self.text_queue.get(timeout=0.5)
                
                if message["type"] == "end":
                    # End of message stream
                    self.synthesizer.streaming_complete()
                    print('TTS Request completed. RequestId:', self.synthesizer.get_last_request_id())
                elif message["type"] == "message":
                    # Process a text chunk
                    content = message["content"]
                    if content:
                        print(f"TTS processing: {content}")
                        self.synthesizer.streaming_call(content)
                
                # Mark task as complete
                # 告诉队列一个消息已经被处理完毕，但不关心具体是哪个消息
                self.text_queue.task_done()
                
            except queue.Empty:
                # Queue timeout, just continue and check running status
                continue
            except Exception as e:
                print(f"Error in TTS speaker: {str(e)}")
    
    def stop(self):
        """Stop the speaker thread"""
        self.running = False
        if self.is_alive():
            self.join(timeout=2)


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
    text_queue.put({"type": "end", "content": END})
    
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