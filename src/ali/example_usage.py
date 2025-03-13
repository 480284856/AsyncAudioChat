#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Example script demonstrating how to use the get_transcript function from the
realtime_speech_recognition module.

Before running this script, make sure to set the following environment variables:
- ALIBABA_APPKEY: Your Alibaba Cloud AppKey
- ALIBABA_TOKEN: Your Alibaba Cloud Token

Example setup:
export ALIBABA_APPKEY=your_appkey_here
export ALIBABA_TOKEN=your_token_here
"""

import os
import time
from realtime_speech_recognition import get_transcript

def main():
    # Check if environment variables are set
    if not os.environ.get("ALIBABA_APPKEY") or not os.environ.get("ALIBABA_TOKEN"):
        print("Please set ALIBABA_APPKEY and ALIBABA_TOKEN environment variables")
        print("Example:")
        print("export ALIBABA_APPKEY=your_appkey_here")
        print("export ALIBABA_TOKEN=your_token_here")
        return
    
    print("This script will record audio for 10 seconds and then return the transcription.")
    print("Please speak into your microphone after the recording starts...")
    print("Recording will start in 3 seconds...")
    
    import time
    for i in range(3, 0, -1):
        print(f"{i}...")
        time.sleep(1)
    
    print("Recording started! Please speak now...")
    
    # Call the get_transcript function that takes no parameters
    transcript = get_transcript()
    
    print("\n--- Transcription Results ---")
    if transcript:
        print(transcript)
    else:
        print("No speech detected or an error occurred during transcription.")
    
    return transcript

if __name__ == "__main__":
    main() 