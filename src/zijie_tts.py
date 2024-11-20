import os
import uuid
import json
import time
import base64
import random
import string
import pyaudio
import logging
import requests
import threading

from pathlib import Path
from pygame import mixer
from collections import deque
from typing import Optional, List, Dict, Any, Union

def get_logger(logger_name=__name__):
    # 日志收集器
    logger = logging.getLogger(logger_name)
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

def generate_random_filename(length=30, extension=".txt"):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length)) + extension

def tts(
        text,
        *args,
        **kwargs
):
    # 填写平台申请的appid, access_token以及cluster
    appid = os.environ.get("zijie_tts_app_id")
    access_token= os.environ.get("zijie_tts_access_token")

    cluster = "volcano_tts"

    voice_type = kwargs.get("voice_type")
    if not voice_type:
        voice_type="BV005_streaming"
        
    host = "openspeech.bytedance.com"
    api_url = f"https://{host}/api/v1/tts"

    header = {"Authorization": f"Bearer;{access_token}"}

    request_json = {
        "app": {
            "appid": appid,
            "token": "access_token",
            "cluster": cluster
        },
        "user": {
            "uid": "388808087185088"
        },
        "audio": {
            "voice_type": voice_type,
            "encoding": "wav",
            "speed_ratio": 1.0,
            "volume_ratio": 1.0,
            "pitch_ratio": 1.0,
        },
        "request": {
            "reqid": str(uuid.uuid4()),
            "text": text,
            "text_type": "plain",
            "operation": "query",
            "with_frontend": 1,
            "frontend_type": "unitTson"

        }
    }

    try:
        resp = requests.post(api_url, json.dumps(request_json), headers=header)
        # print(f"resp body: \n{resp.json()}")
        if "data" in resp.json():
            data = resp.json()["data"]
            file_to_save = generate_random_filename(extension=".wav")
            file_to_save = os.path.join(os.path.dirname(__file__), file_to_save)
            file_to_save = open(file_to_save, "wb")
            file_to_save.write(base64.b64decode(data))
            file_to_save.close()
            file_to_save:str
            return file_to_save.name
    except Exception as e:
        e.with_traceback()

class AudioProducer(threading.Thread):
    def __init__(self, text_queue, audio_queue, daemon=True):
        '''不停地从text队列中拿出sentence，然后进行语音合成，放入到audio队列中，直到拿到None时停止，然后再往audio队列中放入一个None，表示合成完毕。'''
        self.text_queue:deque = text_queue.value
        self.audio_queue:deque = audio_queue.value
        super().__init__(daemon=daemon)
    
    def run(self) -> None:
        while True:
            # 这里得判断队列是否为空，如果为空，则等待，直到有新的句子进入队列
            while len(self.text_queue)==0:
                time.sleep(0.01)
            sentence = self.text_queue.popleft()
            if sentence is None:
                self.audio_queue.append(None)
                break
            self.audio_queue.append(tts(sentence))

class AudioConsumer(threading.Thread):
    def __init__(self, audio_queue:deque, daemon=True):
        '''
        不停地从audio队列中拿出audio，进行播放，直到拿到None时，停止运行。
        '''
        super().__init__(daemon=daemon)
        self.audio_queue:deque = audio_queue.value

    def run(self):
        # 使用mixer类进行播放         
        mixer.init()
        while True:
            while len(self.audio_queue)==0:
                time.sleep(0.01)
            audio = self.audio_queue.popleft()
            if audio is None:
                break
            
            mixer.music.load(audio)
            mixer.music.play()
            while mixer.music.get_busy():
                time.sleep(0.001)
            
            mixer.music.unload()
            os.remove(audio)
        mixer.quit()

if __name__ == '__main__':
    os.environ["zijie_tts_app_id"] = "3065693124"
    os.environ["zijie_tts_access_token"] = "OBINUyUlD0ZnrMA10zh6ykOvISm2SRN-"
    if not os.environ.get("zijie_tts_app_id"):
        logger = get_logger("tts_key_checker")
        logger.error("Please set your APP ID and access token in the environment variables zijie_tts_app_id and tts_key_checker")
        exit(1)
    # print(tts("中国，全称中华人民共和国，位于亚洲东部，太平洋西岸，是世界上人口最多的国家之一，拥有超过五千年的悠久历史和灿烂文化。中国疆域辽阔，陆地面积约为960万平方千米，地域多样，从东部的平原、丘陵到西部的高原、山脉，自然景观丰富。"))
    print(tts("hello, how can i help you."))