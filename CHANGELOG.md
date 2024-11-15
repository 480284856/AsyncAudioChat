# Update Log for `AsyncAudioChat.py`

#### Date: 2024-11-12

**New Features:**
1. **RemoteSTT Integration:**
   - Introduced the `RemoteSTT` class which combines the functionalities of "remote microphone" and `STT`.
   - `RemoteSTT` starts a Flask server to handle `/upload` route for receiving audio data via HTTP POST requests, which is called `RemoteMicrophone` by me.
   - Audio data received is added to a multiprocessing queue for processing.
   - `RemoteSTT` processes audio data from the queue, performs speech-to-text conversion using the provided STT API, and logs the transcribed text.
   - Added a method to generate random filenames for received audio files to avoid conflicts and ensure unique file names.


**Bug Fixes:**
1. **Queue Handling:**
   - Fixed issues related to sharing the queue between processes by using `multiprocessing.Queue` instead of `queue.Queue`.

**Usage:**
- To use `RemoteSTT`, initialize it with the STT API function and text dictionary, and start the process. The Flask server will handle incoming audio data, and the STT processing will convert it to text.

```python
import os
import sys
import time
import random
import string

from src.AsyncAudioChat import Backend,RemoteSTT,LOGGER
from src.zijie_stt import lingji_stt_gradio_va


class Backend(Backend):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stt_thread = RemoteSTT(lingji_stt_gradio_va, self.text)

if __name__ == '__main__':
    backend = Backend()
    backend.start()
    backend.join()
```
It should be noticed that a `config.json` with a structure written below should exist in the same directory of a .py file containing the demo above.
```json
{
    "lingji_key": "sk-",          
    "llm_url": "http://172.17.0.3:11434",
    "model_name": "llama3.1:latest",
    "zijie_tts_app_id": "xx",
    "zijie_tts_access_token": "xx-",
    
    "embedding_model_url": "http://172.17.0.3:11434",
    "name_embedding_model": "nomic-embed-text",

    "zijie_stt_appid": "xx",
    "zijie_stt_token": "xx-",
    "zijie_stt_cluster": "xx"
}
```
This update makes it more efficient and easier to be incorporated into the `Backend`.