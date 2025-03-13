#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import json
import uuid
import argparse
import pyaudio
import websockets
import numpy as np
import sys
from datetime import datetime
import os

class SpeechRecognizer:
    def __init__(self, appkey, token, *args, **kwargs):
        self.appkey = appkey
        self.token = token
        self.websocket = None
        self.audio_stream = None
        self.pyaudio_instance = None
        self.running = False
        self.task_id = str(uuid.uuid4()).replace('-', '')
        self.message_id = None
        self.sample_rate = 16000
        self.channels = 1
        self.chunk_size = 2048  # Matches the demo's scriptProcessor buffer size
        self.format = pyaudio.paInt16
        # Store the transcript results
        self.transcript_results = []
        self.complete_transcript = ""

        self.text:dict = kwargs.get("stt_text", None)
        
    def generate_message_id(self):
        """Generate a unique message ID."""
        return str(uuid.uuid4()).replace('-', '')
    
    def create_start_message(self):
        """Create StartTranscription message."""
        return {
            "header": {
                "appkey": self.appkey,
                "namespace": "SpeechTranscriber",
                "name": "StartTranscription",
                "task_id": self.task_id,
                "message_id": self.generate_message_id()
            },
            "payload": {
                "format": "pcm",
                "sample_rate": self.sample_rate,
                "enable_intermediate_result": True,
                "enable_punctuation_prediction": True,
                "enable_inverse_text_normalization": True
            }
        }
    
    def create_stop_message(self):
        """Create StopTranscription message."""
        return {
            "header": {
                "appkey": self.appkey,
                "namespace": "SpeechTranscriber",
                "name": "StopTranscription",
                "task_id": self.task_id,
                "message_id": self.generate_message_id()
            },
            "payload": {}
        }
    
    async def connect(self):
        """Connect to the WebSocket server."""
        ws_url = f"wss://nls-gateway.cn-shanghai.aliyuncs.com/ws/v1?token={self.token}"
        print(f"Connecting to {ws_url}")
        
        try:
            self.websocket = await websockets.connect(ws_url)
            print("Connected to WebSocket server")
            
            # Send StartTranscription message
            start_message = self.create_start_message()
            await self.websocket.send(json.dumps(start_message))
            print("StartTranscription message sent")
            
            return True
        except Exception as e:
            print(f"Connection error: {e}")
            return False
    
    async def receive_messages(self):
        """Receive and process messages from the WebSocket server."""
        try:
            while self.running:
                message = await self.websocket.recv()
                
                if isinstance(message, str):
                    # JSON message
                    data = json.loads(message)
                    header = data.get("header", {})
                    name = header.get("name", "")
                    
                    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                    print(f"[{timestamp}] Received: {name}")
                    
                    if name == "TranscriptionStarted":
                        print("Transcription started, begin capturing audio...")
                        await self.start_audio_capture()
                    
                    elif name == "TranscriptionResultChanged":
                        result = data.get("payload", {}).get("result", "")
                        print(f"Intermediate result: {result}")

                    elif name == "SentenceEnd":
                        result = data.get("payload", {}).get("result", "")
                        print(f"Final sentence: {result}")
                        # Add to transcript results
                        self.text['text'] = result
                        self.transcript_results.append(result)
                    
                    elif name == "TranscriptionCompleted":
                        print("Transcription completed")
                        # Combine all transcript results
                        self.complete_transcript = " ".join(self.transcript_results)
                        self.running = False
                
        except websockets.exceptions.ConnectionClosed:
            print("Connection closed")
        except Exception as e:
            print(f"Error receiving messages: {e}")
    
    def audio_callback(self, in_data, frame_count, time_info, status):
        """Callback for audio stream, sends audio data over WebSocket."""
        asyncio.run_coroutine_threadsafe(self.send_audio_data(in_data), self.loop)
        return (in_data, pyaudio.paContinue)
    
    async def send_audio_data(self, audio_data):
        """Send audio data over WebSocket."""
        if self.websocket and self.running:
            try:
                await self.websocket.send(audio_data)
            except Exception as e:
                print(f"Error sending audio data: {e}")
    
    async def start_audio_capture(self):
        """Start capturing audio from the microphone."""
        self.pyaudio_instance = pyaudio.PyAudio()
        self.audio_stream = self.pyaudio_instance.open(
            format=self.format,
            channels=self.channels,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=self.chunk_size,
            stream_callback=self.audio_callback
        )
        print("Audio capturing started")
        
    async def stop_audio_capture(self):
        """Stop capturing audio."""
        if self.audio_stream:
            self.audio_stream.stop_stream()
            self.audio_stream.close()
            self.audio_stream = None
        
        if self.pyaudio_instance:
            self.pyaudio_instance.terminate()
            self.pyaudio_instance = None
        
        print("Audio capturing stopped")
    
    async def stop_transcription(self):
        """Send StopTranscription message and close the connection."""
        if self.websocket:
            try:
                stop_message = self.create_stop_message()
                await self.websocket.send(json.dumps(stop_message))
                print("StopTranscription message sent")
                
                # Wait for final results
                await asyncio.sleep(2)
                
                await self.websocket.close()
                print("WebSocket connection closed")
            except Exception as e:
                print(f"Error stopping transcription: {e}")
    
    async def run(self):
        """Run the speech recognition process."""
        self.running = True
        self.loop = asyncio.get_event_loop()
        
        if not await self.connect():
            return ""
        
        # Create tasks for message receiving
        receive_task = asyncio.create_task(self.receive_messages())
        
        try:
            print("Press Ctrl+C to stop the transcription...")
            while self.running:
                await asyncio.sleep(0.1)
        except KeyboardInterrupt:
            print("Stopping...")
        finally:
            self.running = False
            await self.stop_audio_capture()
            await self.stop_transcription()
            await receive_task
            
        return self.complete_transcript

async def main():
    parser = argparse.ArgumentParser(description='Real-time speech recognition using Alibaba Cloud API')
    parser.add_argument('--appkey', required=True, help='Your Alibaba Cloud AppKey')
    parser.add_argument('--token', required=True, help='Your Alibaba Cloud Token')
    parser.add_argument('--max_duration', type=int, default=30, help='Maximum recording duration in seconds')
    args = parser.parse_args()
    
    recognizer = SpeechRecognizer(args.appkey, args.token)
    transcript = await recognizer.run()
    print("\nFinal Transcript:", transcript)
    return transcript

async def async_get_transcript(*args, **kwargs):
    """Async function to get transcript with default credentials and 10 second recording."""
    # Try to get appkey and token from environment variables
    appkey = os.environ.get("ALIBABA_APPKEY")
    token = os.environ.get("ALIBABA_TOKEN")
    
    if not appkey or not token:
        print("Error: Environment variables ALIBABA_APPKEY and ALIBABA_TOKEN are required")
        return ""
    
    recognizer = SpeechRecognizer(appkey, token, *args, **kwargs)
    
    # Add a timeout to automatically stop after 10 seconds
    async def stop_after_timeout(timeout):
        await asyncio.sleep(timeout)
        recognizer.running = False
    
    # Start timeout task
    timeout_task = asyncio.create_task(stop_after_timeout(10))
    
    # Run recognition
    transcript = await recognizer.run()
    
    # Cancel timeout if it hasn't triggered yet
    timeout_task.cancel()
    
    return transcript

def get_transcript(*args, **kwargs):
    """
    Function that takes no parameters and returns the final transcript result.
    It records audio for 10 seconds and returns the transcription.
    
    Returns:
        str: The final transcript of the recorded audio
    """
    try:
        return asyncio.run(async_get_transcript(*args, **kwargs))
    except Exception as e:
        print(f"Error in transcription: {e}")
        return ""

def ali_rstt(*args, **kwargs):
    return get_transcript(*args, **kwargs)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Program terminated by user")
    except Exception as e:
        print(f"Error: {e}") 