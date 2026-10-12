# STT Core Structure

Offline terminal speech-to-text using Parakeet Redux.

## Setup

```powershell
git clone -b feature https://github.com/ABhattacharya-dev/stt-core-structure.git
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

Answer `y` to enable smart cleanup, or press Enter / answer `n` for normal transcription. Press Enter to start recording. Press Enter again to stop and print the transcript.

To diagnose an incorrect result from the same recording, run `python stt.py --show-raw` and answer `y`. This also prints `Raw transcript: ...` before cleanup. History still saves only the final result. Missing words in the raw transcript cannot be reliably recovered by cleanup.

## Optional smart cleanup (Windows NVIDIA)

Download the llama.cpp CUDA runtime and Qwen3 4B Instruct Q4 model (about 2.5 GB) once:

```powershell
New-Item -ItemType Directory -Force runtime\smart | Out-Null
$release = "https://github.com/ggml-org/llama.cpp/releases/download/b11564"
curl.exe -L --fail "$release/llama-b11564-bin-win-cuda-12.4-x64.zip" -o "$env:TEMP\stt-llama.zip"
Expand-Archive "$env:TEMP\stt-llama.zip" -DestinationPath runtime\smart -Force
curl.exe -L --fail "$release/cudart-llama-bin-win-cuda-12.4-x64.zip" -o "$env:TEMP\stt-cudart.zip"
Expand-Archive "$env:TEMP\stt-cudart.zip" -DestinationPath runtime\smart -Force
curl.exe -L --fail "https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF/resolve/main/Qwen3-4B-Instruct-2507-Q4_K_M.gguf?download=true" -o runtime\Qwen3-4B-Instruct-2507-Q4_K_M.gguf
```

After setup, everything runs offline. Answering `y` loads and warms the model before recording and uses the NVIDIA GPU for cleanup. This uses about 3.1 GB of GPU memory on the tested GTX 1650. The local server closes when the script exits. Answering `n` does not load it.

Cleanup fixes grammar and punctuation and resolves corrections such as “meet at eight, sorry, seven.” Start with **“write in JSON format”** to dictate JSON, including nested objects, arrays and explicit numbers/booleans/null. Say “end user object” (using your object's name) to make nesting boundaries explicit. Ambiguous values and phone numbers stay strings. Personal shortcuts keep their exact saved values.

Only the final result is printed and saved in history. Missing runtime/model, failed cleanup, invalid JSON, changed shortcuts or a 10-second request timeout fall back to the normal transcript with a short warning. Long dictations that exceed the conservative context limit also use normal transcription. Cleanup can misinterpret meaning; valid JSON does not guarantee correct values.

Run the offline fixture benchmark without recording or changing history:

```powershell
python -m unittest test_smart
python benchmark_smart.py --runs 3
```

The benchmark measures model startup separately and writes outputs, fixture checks and cleanup timings to ignored `benchmark-results.json`. Alternative GGUF models can be measured with `--model path\to\model.gguf`.

### Measured results

Initial benchmark before prompt refinement: GTX 1650 4 GB / Ryzen 7 4800H, 25 text fixtures repeated three times, October 12, 2026. These are cleanup checks, not a general speech-recognition accuracy score. All models used the same prompts and fixtures in this comparison.

| Model | Checks passed | Median cleanup | Slowest cleanup |
| --- | ---: | ---: | ---: |
| Qwen3 4B Instruct Q4 (selected) | 69/75 | 1.30 s | 2.02 s |
| Qwen3 1.7B Q8 | 39/75 | 0.63 s | 0.95 s |
| Qwen2.5 1.5B Instruct Q4 | 30/75 | 0.51 s | 0.79 s |

The selected model passed all grammar and meaning-preservation fixtures. Two cases failed consistently: “Monday, sorry Tuesday” retained Monday, and a JSON quantity correction from eight to six retained eight. Review corrected dates and numbers. JSON validation checks structure, not meaning.

Selected-model startup including warmup took 4.92 seconds in the final run, before recording; first-time GPU initialization took tens of seconds. The 1–3-second target applies to short-text cleanup after transcription, not startup or long dictations.

Six focused unit tests, 12 live shortcut checks (including escaped JSON values), and the full fixture-audio-to-history flow passed. The live microphone was not retested.

After refining the text prompt to apply replacements in place, a 29-case run passed 27 strict checks, with 1.47-second median and 1.87-second maximum cleanup. “A new card—actually, a new phone” now keeps only the phone, and “tomorrow not tomorrow make it today” becomes “Let's see you today.” The Monday-to-Tuesday case also passed. Remaining failures were awkward “at sharp 7 PM” wording and the unchanged JSON quantity error. The JSON prompt was not changed in this refinement.

## History

Final transcripts, including expanded shortcuts, are saved locally in `history/YYYY-MM-DD.jsonl` beside `stt.py`. Each date has its own file, containing one JSON record per transcription:

```json
{"time": "14:30:05+05:30", "text": "Your transcribed text."}
```

Dates and times use your computer's local timezone; the time includes its UTC offset. Blank transcripts are skipped. New entries are appended without reading older history, after the transcript is printed. If saving fails, a short error is shown and the transcript remains available in the terminal. History includes any inserted personal details and is ignored by Git.
