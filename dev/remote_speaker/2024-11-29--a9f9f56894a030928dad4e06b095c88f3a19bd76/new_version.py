class RemoteSpeaker(Speaker):
    def __init__(self, audio_queue: queue.Queue):
        """Initialize RemoteSpeaker with an audio queue and set up Flask endpoints"""
        super().__init__(audio_queue)
        self.current_audio = None
        self.audio_ready = threading.Event()
        self.end_of_audio = False
        self.final_request_received = threading.Event()
        self.workflow_started = threading.Event()  # New event for workflow control
        self.last_heartbeat = time.time()
        self.heartbeat_timeout = 2500  # 25 second timeout
        self.should_terminate = threading.Event()  # New event for graceful termination
        
        app.url_map._rules.clear()
        app.url_map._rules_by_endpoint.clear()

        # @app.route('/start', methods=['POST'])
        # def receive_start_signal():
        #     """Endpoint to receive the initial greeting message"""
        #     self.workflow_started.set()
        #     # regarded as a heartbeat
        #     self.last_heartbeat = time.time()
        #     LOGGER.debug("RemoteSpeaker: Received start signal")
        #     return 'Workflow started', 200

        @app.route('/heartbeat', methods=['POST', 'GET'])
        def heartbeat():
            """Endpoint to receive heartbeat from client"""
            self.last_heartbeat = time.time()
            return 'Heartbeat received', 200

        @app.route('/audio', methods=['GET'])
        def serve_audio():
            # # Only serve audio after receiving start signal
            # if not self.workflow_started.is_set():
            #     return 'Workflow not started', 403
            
            if self.audio_ready.wait(timeout=300):

                if self.current_audio:
                    with open(self.current_audio, 'rb') as f:
                        audio_data = f.read()
                    self.current_audio = None
                    self.audio_ready.clear()
                    return audio_data, 200
                elif self.end_of_audio:
                    @after_this_request
                    def set_final_received(response):
                        # This return is for Flask's middleware chain
                        # Not for sending to client (already sent)
                        # to confirm that the code after the response to client is worked

                        self.final_request_received.set()   # Do task after serving client
                        return response  # Tell Flask "Yes, I did my after-serving task"
                    return 'END', 204
                
            return 'No audio available', 404

    def _run(self, *args, **kwargs):
        server_thread = Thread(target=lambda: app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False, threaded=True), daemon=True)
        server_thread.start()

        flag_first_audio = True

        while not self.should_terminate.is_set():
            audio = self.audio_queue.get()

            # we can't start heartbeat monitor thread before the first audio is received,
            # because the first audio may be available for a long time at the first time because of the LLM loading time.
            if flag_first_audio:
                # Start heartbeat monitor thread
                heartbeat_thread = Thread(target=self._monitor_heartbeat, daemon=True)
                heartbeat_thread.start()
                flag_first_audio = False

            self.current_audio = audio
            self.audio_ready.set()

            if audio is None:
                self.end_of_audio = True
                # Wait for final request with timeout
                if self.final_request_received.wait(timeout=30):
                    LOGGER.debug("RemoteSpeaker: Final END status sent to client")
                else:
                    LOGGER.warning("RemoteSpeaker: Timeout waiting for final request")
                break
            
            while self.current_audio and not self.should_terminate.is_set():
                LOGGER.debug(f"RemoteSpeaker: Audio file {audio} ready for serving")
                time.sleep(0.5)
        
        LOGGER.debug("RemoteSpeaker: All audio files processed")

    def _monitor_heartbeat(self):
        """Monitor heartbeat and terminate if client is unresponsive"""
        while not self.should_terminate.is_set():
            time.sleep(1)
            if time.time() - self.last_heartbeat > self.heartbeat_timeout:
                LOGGER.error("RemoteSpeaker: Client heartbeat timeout, terminating thread")
                self.should_terminate.set()
                break