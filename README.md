# STT Core Structure

Offline terminal speech-to-text using Parakeet Redux.

## Setup

```powershell
git clone -b core-structure https://github.com/ABhattacharya-dev/stt-core-structure.git
cd stt-core-structure

py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Download the model into `runtime`:

```powershell
Invoke-WebRequest `
  -Uri "https://huggingface.co/mudler/parakeet-cpp-gguf/resolve/main/redux-q8_0.gguf?download=true" `
  -OutFile "runtime\redux-q8_0.gguf"
```

The model is about 942 MB and is used locally after download.

## Run

```powershell
python stt.py
```

Press Enter to start recording. Press Enter again to stop and print the transcript.
