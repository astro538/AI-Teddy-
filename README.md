# 🧸 AI Teddy — Coco

**AI Teddy** is an AI-powered talking teddy bear designed to be an interactive, friendly voice companion for children. The project combines **ESP32-based hardware**, **Python**, speech recognition, text-to-speech, and generative AI to turn a physical teddy bear into a conversational companion.

Coco listens to a child, understands what they say, generates a child-friendly response using AI, and speaks the response aloud.

##  Features

-  **Voice interaction** — listens to spoken questions and commands.
-  **AI-powered conversation** — uses Google's Gemini model to generate natural responses.
-  **Text-to-speech** — converts Coco's responses into spoken audio using Edge TTS.
-  **English and Hindi support** — can respond in English or Hindi depending on the language used by the child.
-  **Conversation memory** — stores recent conversation history for more continuous interactions.
-  **User profile support** — can remember profile information such as the child's preferred name.
-  **Multiple personalities** — supports playful, storyteller, teacher, and bedtime modes.
-  **ESP32 integration** — communicates with an ESP32 to reflect states such as listening, thinking, speaking, and idle using LEDs.
-  **Flask-based interface** — Python backend exposes endpoints for communication and control.

##  How It Works

```text
Child speaks
     ↓
Microphone / Speech Recognition
     ↓
Python Application
     ↓
Google Gemini AI
     ↓
Child-friendly response
     ↓
Edge Text-to-Speech
     ↓
Speaker → Coco talks!

          ↕
       ESP32
   LED status feedback
```
[![Watch the demo video](https://youtu.be/B8djrWJRRiA?si=ASHInP3lYlE9o-Qi)](https://youtu.be/B8djrWJRRiA?si=ASHInP3lYlE9o-Qi)

##  Tech Stack

### Hardware
- ESP32
- Microphone
- Speaker / audio output
- LEDs / status indicators
- Teddy bear enclosure

### Software
- Python
- Flask
- Google Gemini API (`google-genai`)
- SpeechRecognition
- Edge TTS
- Requests
- ESP32 firmware / Arduino ecosystem

##  Coco's Personalities

Coco can operate with different conversational personalities:

| Mode | Behaviour |
| --- | --- |
| **Playful** | Fun, energetic and encouraging |
| **Storyteller** | Tells gentle, imaginative stories |
| **Teacher** | Explains concepts simply and patiently |
| **Bedtime** | Uses a calm and soothing conversational style |

## 🚦 ESP32 Status Feedback

The Python application can send Coco's current state to the ESP32:

```text
Listening → Thinking → Speaking → Idle
```

This allows LEDs or other hardware indicators to visually represent what the teddy is doing.

##  Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/astro538/AI-Teddy-.git
cd AI-Teddy-
```

### 2. Create a Python virtual environment

```bash
python -m venv .venv
```

Activate it on Windows:

```bash
.venv\Scripts\activate
```

On macOS/Linux:

```bash
source .venv/bin/activate
```

### 3. Install dependencies

Install the Python packages used by the project, including:

```bash
pip install google-genai flask SpeechRecognition edge-tts playsound requests
```

Depending on your microphone setup, an additional audio input package such as PyAudio may also be required.

### 4. Configure the Gemini API key

Set your API key as an environment variable instead of placing it directly in the source code.

Windows PowerShell:

```powershell
$env:GEMINI_API_KEY="YOUR_API_KEY"
```

macOS/Linux:

```bash
export GEMINI_API_KEY="YOUR_API_KEY"
```

### 5. Configure ESP32 connectivity

The application supports environment variables for ESP32 communication:

```text
ESP32_IP
ESP32_ENABLED
```

For example:

```bash
ESP32_IP=<your-esp32-ip>
```

Make sure the computer running the Python application and the ESP32 can communicate over the network.

### 6. Run Coco

```bash
python Finalteddy.py
```

Coco can then listen for speech, send the conversation to the AI model, generate a response, and speak it aloud.

##  Project Structure

```text
AI-Teddy-/
├── Finalteddy.py          # Main Python voice-assistant application
├── teddy_history.json    # Conversation history (generated at runtime)
├── teddy_profile.json    # User/profile preferences (generated at runtime)
└── README.md
```

Additional ESP32/Arduino firmware and hardware resources can be kept alongside the Python application as the hardware side of the project evolves.

##  Security

Do **not** commit Gemini API keys or other credentials to the repository. Store secrets in environment variables or a local `.env` file that is excluded through `.gitignore`.

##  Future Improvements

Possible improvements include:

- Fully self-contained teddy hardware
- Improved child-specific speech recognition
- Wake-word detection such as **“Hey Coco”**
- Offline speech processing
- More expressive LED and physical responses
- Parent-configurable controls
- Expanded educational and storytelling modes

##  Project Goal

The goal of AI Teddy is to explore how **embedded systems, voice interfaces, and generative AI** can be combined to create an engaging physical AI companion for children while keeping interactions simple, friendly, and age-appropriate.

## 👩‍💻 Creator

Created by **Aashna Suri**.

---

>  *Turning a traditional teddy bear into an interactive AI companion.*
