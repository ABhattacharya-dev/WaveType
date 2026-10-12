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

## Personal shortcuts

Create `personal_terms.json` beside `stt.py` and edit its values:

```json
{
  "name": "Your Full Name",
  "email": "you@example.com",
  "second email": "you.second@example.com",
  "address": "Your Street Address",
  "phone number": "+1 555 0100"
}
```

Each JSON key is a spoken shortcut: say “insert my” followed by the key, such as “insert my phone number.” Add any key you want, including names with several words. Longer configured keys take priority when names overlap. Ordinary phrases such as “my name, that's my name” remain unchanged. The file is ignored by Git so your personal details stay local. If a configured value is blank, the command stays in the transcript and a short error is printed.

## Run

```powershell
python stt.py
```

Press Enter to start recording. Press Enter again to stop and print the transcript.
