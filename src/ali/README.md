# Real-time Speech Recognition Using Alibaba Cloud API

This Python script implements real-time speech recognition using the Alibaba Cloud WebSocket API. It captures audio from your microphone, sends it to Alibaba Cloud's speech recognition service, and displays the transcription results in real-time.

## Prerequisites

- Python 3.7 or later
- An Alibaba Cloud account with access to the Intelligent Speech Interaction service
- AppKey and Token from Alibaba Cloud

## Installation

1. Install the required dependencies:

```bash
pip install pyaudio websockets numpy
```

Note: On some platforms, installing `pyaudio` might require additional system dependencies:

- On Ubuntu/Debian:
  ```bash
  sudo apt-get install portaudio19-dev python3-pyaudio
  ```

- On macOS:
  ```bash
  brew install portaudio
  ```

## Usage

### Command-line Usage

Run the script with your AppKey and Token:

```bash
python realtime_speech_recognition.py --appkey YOUR_APPKEY --token YOUR_TOKEN
```

Where:
- `YOUR_APPKEY` is your Alibaba Cloud AppKey
- `YOUR_TOKEN` is your Alibaba Cloud Token (you can obtain this from the Alibaba Cloud console)

### Using as a Module

You can also use the script as a module in your Python code:

#### Simple Usage

The simplest way is to use the `get_transcript()` function that takes no parameters and returns the final transcript:

```python
from realtime_speech_recognition import get_transcript

# This will record audio for 10 seconds and return the transcript
transcript = get_transcript()
print(transcript)
```

For this to work, you need to set the following environment variables:
- `ALIBABA_APPKEY`: Your Alibaba Cloud AppKey
- `ALIBABA_TOKEN`: Your Alibaba Cloud Token

Example setup:
```bash
export ALIBABA_APPKEY=your_appkey_here
export ALIBABA_TOKEN=your_token_here
```

#### Advanced Usage

For more control over the recognition process:

```python
import asyncio
from realtime_speech_recognition import SpeechRecognizer

async def my_recognition_task():
    recognizer = SpeechRecognizer(appkey="YOUR_APPKEY", token="YOUR_TOKEN")
    transcript = await recognizer.run()
    return transcript

# Run the recognition task
transcript = asyncio.run(my_recognition_task())
```

See the included `example_usage.py` for a complete example.

## How It Works

1. The script establishes a WebSocket connection with the Alibaba Cloud NLS Gateway.
2. It sends a StartTranscription command to initialize the speech recognition session.
3. Upon receiving a TranscriptionStarted event, it begins capturing audio from your microphone.
4. Audio data is continuously sent to the server in real-time.
5. The server processes the audio and returns various events:
   - TranscriptionResultChanged: Intermediate recognition results
   - SentenceBegin: Indication that a new sentence has started
   - SentenceEnd: Final recognition result for a complete sentence
6. The script collects all the final sentence results and combines them into a complete transcript.
7. For the command-line mode, press Ctrl+C to stop the transcription. The script will send a StopTranscription command.
8. For the `get_transcript()` function, recording automatically stops after 10 seconds.

## Troubleshooting

- **Connection Issues**: Ensure your Token is valid and not expired. Tokens typically expire after a few hours.
- **Audio Problems**: Make sure your microphone is properly connected and set as the default input device.
- **Recognition Issues**: Speak clearly and ensure there is minimal background noise.

## References

- [Alibaba Cloud ISI Developer Reference](https://help.aliyun.com/zh/isi/developer-reference/websocket) 