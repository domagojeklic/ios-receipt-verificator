# About
Simple iOS receipt validator used for development/educational purposes
# Install instructions
- install python3
- create virtual environment
```sh
python3 -m venv .venv
```
- activate virtual environment
```sh
source .venv/bin/activate
```
- install required packages
```sh
pip3 install -r requirements.txt
```
- set environment variable APP_SHARED_SECRET to your app shared secret
```sh
export APP_SHARED_SECRET="APP_SHARED_SECRET"
```
- run verificator
```sh
python3 verificator.py
```

# Documentation
[Server-side validation](https://developer.apple.com/library/archive/releasenotes/General/ValidateAppStoreReceipt/Chapters/ValidateRemotely.html#//apple_ref/doc/uid/TP40010573-CH104-SW1)
