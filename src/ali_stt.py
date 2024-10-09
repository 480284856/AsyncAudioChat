# For prerequisites running the following sample, visit https://help.aliyun.com/document_detail/611472.html
import os
import pyaudio
import dashscope
import multiprocessing
from dashscope.audio.asr import (Recognition, RecognitionCallback,
                                 RecognitionResult)

mic = None
stream = None

class Callback(RecognitionCallback):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__()
        
    def on_open(self) -> None:
        global mic
        global stream
        print('RecognitionCallback open.')
        mic = pyaudio.PyAudio()
        stream = mic.open(format=pyaudio.paInt16,
                          channels=1,
                          rate=16000,
                          input=True)

    def on_close(self) -> None:
        global mic
        global stream
        print('RecognitionCallback close.')
        stream.stop_stream()
        stream.close()
        mic.terminate()
        stream = None
        mic = None

    def on_event(self, result: RecognitionResult) -> None:
        print('RecognitionCallback sentence: ', result.get_sentence())

class AliSTT(multiprocessing.Process):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
    def run(self,):
        dashscope.api_key=os.environ.get('lingji_key')
        callback = Callback()
        recognition = Recognition(model='paraformer-realtime-v2',
                                format='pcm',
                                sample_rate=16000,
                                callback=callback)
        recognition.start()

        while True:
            if stream:
                data = stream.read(3200, exception_on_overflow = False)
                recognition.send_audio_frame(data)
            else:
                break

        recognition.stop()

def ali_stt():
    temp = AliSTT()
    temp.start()
    temp.join()
    
if __name__ == "__main__":
    ali_stt = AliSTT()
    ali_stt.start()
    ali_stt.join()