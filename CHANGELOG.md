# Update Log for `AsyncAudioChat.py`

### Date: 2024-11-21

**New Features:**
1. **RemoteSpeaker Class:**
   - Introduced the `RemoteSpeaker` class inheriting from the base `Speaker` class.
   - Implemented Flask server functionality to serve processed audio files via HTTP.
   - Added `/audio` endpoint for audio retrieval.
   - Implemented thread-safe coordination using `threading.Event`.
   - Added automatic cleanup of audio files after serving.
   - Utilized `@after_this_request` to ensure the object of class is terminated after the final response is sent to the client.
   - Modified the `/audio` endpoint to return a `204 No Content` status when the end of the audio stream is reached.

**Key Features:**
- Uses `@after_this_request` to ensure the object of class isn't shutdown before the final response is sent to the client.

**System Architecture:**
```
Client -> RemoteSTT (5000) -> Processing -> RemoteSpeaker (5000) -> Client
```

**API Endpoints:**

**Audio Upload (Port 5000)**
- `POST /upload`: Submit audio for processing

**Audio Retrieval (Port 5000)**
- `GET /audio`: Retrieve processed audio file
- Returns:
  - 200: Audio data on success
  - 404: When no audio available
  - 204: End of audio stream

**Implementation Notes:**
- Threaded design ensures continuous processing.
- Event-based coordination prevents race conditions.
- 30-second timeout on audio retrieval.
- Automatic file cleanup post-serving.

### Date: 2024-11-13

**New Features:**
1. **RemoteSpeaker Integration:**
   - Introduced the `RemoteSpeaker` class inheriting from base `Speaker` class
   - Implemented Flask server functionality to serve processed audio files via HTTP
   - Added `/audio` endpoint for audio retrieval
   - Implemented thread-safe coordination using `threading.Event`
   - Added automatic cleanup of audio files

**Architecture Changes:**
1. **Audio Distribution:**
   - Modified audio playback system to support remote clients
   - Single port design (5000) handling both STT and audio serving
   - RemoteSpeaker reuses port after RemoteSTT termination

**Usage:**
- To use `RemoteSpeaker`, initialize it with an audio queue and start the process. The Flask server will handle sending processed audio back to clients.

```python
from src.AsyncAudioChat import Backend, RemoteSTT, RemoteSpeaker
from src.zijie_stt import lingji_stt_gradio_va


class Backend(Backend):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stt_thread = RemoteSTT(lingji_stt_gradio_va, self.text)
        self.speaker_thread = RemoteSpeaker(self.audio_queue)

if __name__ == '__main__':
    backend = Backend()
    backend.start()
    backend.join()
```

**Client-Side Implementation:**
```python
import requests

# Send audio for processing
with open('input.wav', 'rb') as f:
    audio_data = f.read()
requests.post('http://device:5000/upload', data=audio_data)

# Receive processed audio
response = requests.get('http://device:5001/audio')
if response.status_code == 200:
    with open('output.wav', 'wb') as f:
        f.write(response.content)
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
This update completes the remote audio processing pipeline, allowing for distributed audio processing and playback.


### Date: 2024-11-12

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

