#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import json
import argparse
import sys

def get_token(access_key_id, access_key_secret):
    """
    Request a token from Alibaba Cloud NLS service using AccessKey ID and Secret.
    
    Args:
        access_key_id (str): Alibaba Cloud AccessKey ID
        access_key_secret (str): Alibaba Cloud AccessKey Secret
        
    Returns:
        str: The token if successful, None otherwise
    """
    url = "https://nls-meta.cn-shanghai.aliyuncs.com/pop/2018-05-18/tokens"
    
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    
    payload = {
        "accessKeyId": access_key_id,
        "accessKeySecret": access_key_secret
    }
    
    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        response.raise_for_status()  # Raise an exception for HTTP errors
        
        data = response.json()
        if "Token" in data and "Id" in data["Token"]:
            token = data["Token"]["Id"]
            expiry_time = data["Token"]["ExpireTime"]
            
            print(f"Token obtained successfully: {token}")
            print(f"Token will expire at: {expiry_time}")
            
            return token
        else:
            print(f"Error in response format: {data}")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"Error requesting token: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description='Get a token from Alibaba Cloud NLS service')
    parser.add_argument('--key', required=True, help='Your Alibaba Cloud AccessKey ID')
    parser.add_argument('--secret', required=True, help='Your Alibaba Cloud AccessKey Secret')
    args = parser.parse_args()
    
    token = get_token(args.key, args.secret)
    if token:
        print("\nUse this token with the speech recognition script:")
        print(f"python realtime_speech_recognition.py --appkey YOUR_APPKEY --token {token}")
    else:
        print("Failed to obtain token.")
        sys.exit(1)

if __name__ == "__main__":
    main() 