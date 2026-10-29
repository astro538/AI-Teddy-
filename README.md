# AI Teddy — Coco, a Voice-Based AI Companion Prototype

AI Teddy explores a talking teddy-bear companion that combines speech recognition, a generative AI response, text-to-speech, a Python/Flask application, and ESP32 LED status feedback.

This is a prototype for learning and demonstration. It should not be presented as a substitute for adult supervision, a validated educational product, or a secure system for storing children's information.

## How it works

```text
Child speaks
    |
    v
SpeechRecognition microphone capture
    |
    v
Python application --> Google Gemini API
    |                       |
    |<----- text response --+
    v
Edge TTS --> speaker output

Python app -- HTTP status update --> ESP32 --> 12-LED ring
          listening / thinking / speaking / idle
```

## Features in the current code

- Speech recognition and voice-driven interaction.
- Responses generated through Google's Gemini API using the `google-genai` client.
- Spoken responses through Edge TTS and audio playback.
- English/Hindi response behaviour in the system prompt.
- Conversation history and a local profile file created at runtime.
- Several conversational personality modes.
- Optional ESP32 status updates over HTTP.
- Flask endpoints for local application integration.

## Repository structure

```text
AI-Teddy-/
├── Finalteddy.py      # Python application, speech, Gemini, TTS, Flask, and status updates
├── teddy_esp.ino      # ESP32 HTTP server and WS2812B status ring
└── README.md
```

The application may create `teddy_history.json` and `teddy_profile.json` beside the Python script at runtime.

## Requirements

- Python 3.10+ recommended; use versions compatible with the selected packages
- Working microphone and speaker/audio output
- Internet access for the Gemini API and Edge TTS
- Google Gemini API key
- ESP32 with Wi-Fi and a WS2812B-compatible 12-LED ring for hardware feedback
- Arduino IDE, ESP32 board support, and FastLED for the firmware

Install the core Python packages in a virtual environment:

```bash
git clone https://github.com/astro538/AI-Teddy-.git
cd AI-Teddy-
python -m venv .venv
```

**Windows PowerShell**
```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install google-genai flask SpeechRecognition edge-tts playsound requests
```

**macOS / Linux**
```bash
source .venv/bin/activate
python -m pip install --upgrade pip
pip install google-genai flask SpeechRecognition edge-tts playsound requests
```

SpeechRecognition microphone support may require an additional audio input dependency such as PyAudio. Installation steps differ by operating system.

## Configure the Gemini API

Set the key as an environment variable. Do not hard-code it or commit it to Git.

**Windows PowerShell**
```powershell
$env:GEMINI_API_KEY = "YOUR_GEMINI_API_KEY"
```

**macOS / Linux**
```bash
export GEMINI_API_KEY="YOUR_GEMINI_API_KEY"
```

The checked-in Python code also accepts `GOOGLE_API_KEY` or the legacy `teddy` environment variable. Prefer `GEMINI_API_KEY` for clarity.

## Configure ESP32 status feedback

1. Open `teddy_esp.ino` in Arduino IDE.
2. Install the ESP32 board package and FastLED library.
3. Set Wi-Fi credentials locally in the sketch; use placeholders in any shared copy.
4. Upload the sketch and read the ESP32's IP address from Serial Monitor at 115200 baud.
5. Set the Python environment variable `ESP32_IP` to that address on the computer running `Finalteddy.py`.

For Windows PowerShell:

```powershell
$env:ESP32_IP = "192.168.x.x"
$env:ESP32_ENABLED = "true"
```

For macOS/Linux:

```bash
export ESP32_IP="192.168.x.x"
export ESP32_ENABLED="true"
```

The computer and ESP32 must be able to reach one another on the same network. The Python code sends status to `http://<ESP32_IP>/status`.

## Run the application

After setting the API key and any hardware settings:

```bash
python Finalteddy.py
```

The program starts its configured listener and uses the Gemini API when a speech input is processed. The Flask app is configured to bind to all interfaces on port 5000; only run it on a trusted network unless you add authentication and restrict access.

## Privacy and child safety

- The application sends recognized user input to an external generative-AI service for response generation.
- Conversation history and profile preferences may be written to local JSON files.
- Tell users/caregivers what is recorded, obtain appropriate consent, and provide a way to delete stored history.
- Do not commit real conversation histories, profile data, API keys, Wi-Fi credentials, or other personal information.
- Do not expose the Flask server to the public Internet without authentication, input limits, and appropriate privacy/security review.
- Adult supervision is necessary; the model can make mistakes and should not be treated as an authority for medical, emergency, or other high-stakes questions.

## Troubleshooting

**Gemini initialization fails:** check that `GEMINI_API_KEY` is set and valid, and that the key has access to the selected model.

**No speech is detected:** check operating-system microphone permissions, the selected input device, and any required audio dependencies.

**No speech output:** verify Internet access for Edge TTS, audio playback permissions, and speaker selection.

**ESP32 LEDs do not change:** verify the board is connected to Wi-Fi, the IP address is correct, the computer can reach the device, and the sketch has started its HTTP server.

## Current limitations and future work

This repository does not include an automated end-to-end test suite, a benchmark for speech recognition quality, or a deployment-grade privacy/authentication design. Useful next steps include explicit caregiver controls, a wake-word workflow, offline speech options, persistent secure storage, network authentication, and tests for reconnection and API failures.

## License

No explicit license file was identified when this README was prepared. Add a license before inviting reuse or redistribution.
