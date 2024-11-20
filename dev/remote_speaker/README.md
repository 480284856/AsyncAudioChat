# Remote Speaker

## Background of demand
We need to send the audio file to the dev board, and the dev board will process the audio file and return the result.

## Demand decompose
- remote speaker: send the audio file to the dev board.
  - Implement RemoteSpeaker class that inherits from Speaker
  - Set up Flask server to handle audio transmission
  - Expose endpoints for audio retrieval

## Implementation Details
1. **RemoteSpeaker Class**:
   - Inherits from base Speaker class
   - Uses Flask to serve audio over HTTP
   - Runs on port 5001 (separate from RemoteSTT's port 5000)
   - Provides `/audio` endpoint for clients to retrieve processed audio

2. **Audio Flow**:
   ```
   Client -> RemoteSTT (port 5000) -> Processing -> RemoteSpeaker (port 5001) -> Client
   ```

3. **Key Features**:
   - Asynchronous audio processing
   - Event-based coordination between processing and serving
   - Clean file management (auto-deletion after serving)

## API Endpoints
1. **STT Endpoint** (Port 5000):
   - POST `/upload`: Upload audio for processing
   
2. **Speaker Endpoint** (Port 5001):
   - GET `/audio`: Retrieve processed audio response

## Usage Example
```python
# Server side
speaker = RemoteSpeaker(audio_queue)
speaker.start()

# Client side
# 1. Send audio for processing
requests.post('http://device:5000/upload', data=audio_data)
#2. Get processed audio
response = requests.get('http://device:5001/audio')
if response.status_code == 200:
# Handle audio data
    audio_data = response.content
```