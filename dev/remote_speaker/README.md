# Remote Speaker

## Background
Need to enable remote audio processing and transmission between client and dev board, with asynchronous handling of audio files.

## Implementation Details

### 1. RemoteSpeaker Class
```python
class RemoteSpeaker(Speaker):
    def __init__(self, audio_queue: queue.Queue):
        """Initialize RemoteSpeaker with an audio queue and set up Flask endpoints"""
        super().__init__(audio_queue)
        self.current_audio = None
        self.audio_ready = threading.Event()
        
        @app.route('/audio', methods=['GET'])
        def serve_audio():
            # Wait for audio to be ready
            if self.audio_ready.wait(timeout=300):  # 30 second timeout
                if self.current_audio:
                    with open(self.current_audio, 'rb') as f:
                        audio_data = f.read()
                    # Clean up after serving
                    os.remove(self.current_audio)
                    self.current_audio = None
                    self.audio_ready.clear()
                    return audio_data, 200
            return 'No audio available', 404

    def _run(self, *args, **kwargs):
        # Start Flask server in a separate thread
        # the container only exposes port 5000, and the RemoteSTT is terminated after before this thread is started, so we can reuse the port.
        server_thread = Thread(target=lambda: app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False), daemon=True)
        server_thread.start()

        # Process audio files from queue
        while True:
            audio = self.audio_queue.get()
            if audio is None:
                break
                
            self.current_audio = audio
            self.audio_ready.set()  # Signal that new audio is ready
            
            # Wait until audio is served before processing next file
            while self.current_audio:
                LOGGER.debug(f"RemoteSpeaker: Audio file {audio} ready for serving")
                time.sleep(0.1)
            os.remove(audio)
        
        LOGGER.debug("RemoteSpeaker: All audio files processed")
```

Key features:
- Inherits from base Speaker class
- Manages audio queue with threading
- Serves audio files via HTTP
- Auto-cleanup after serving

### 2. System Architecture
```
Client -> RemoteSTT (5000) -> Processing -> RemoteSpeaker (5000) -> Client
```

### 3. Audio Flow
1. Audio queued from LLM/TTS pipeline
2. RemoteSpeaker picks up file from queue
3. File served via HTTP endpoint
4. File cleaned up after successful transmission

### 4. API Endpoints

#### Audio Upload (Port 5000)
- `POST /upload`: Submit audio for processing

#### Audio Retrieval (Port 5000) 
- `GET /audio`: Retrieve processed audio file
- Returns:
  - 200: Audio data on success
  - 404: When no audio available

### 5. Implementation Notes
- Threaded design ensures continuous processing
- Event-based coordination prevents race conditions
- 30-second timeout on audio retrieval
- Automatic file cleanup post-serving