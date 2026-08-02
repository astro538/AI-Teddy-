import os
import threading
import sys
import time
import asyncio
import tempfile
import edge_tts
from contextlib import redirect_stdout, redirect_stderr
import queue
import json
from pathlib import Path

import requests

# --- ESP32 Configuration ---
ESP32_IP = os.getenv('ESP32_IP', '10.175.246.46')
ESP32_URL = f"http://{ESP32_IP}/status"
ESP32_ENABLED = os.getenv('ESP32_ENABLED', 'true').lower() in ('true', '1', 'yes')

def update_led_status(state):
    """
    Send LED status update to ESP32 (non-blocking)
    States: 'listening', 'thinking', 'speaking', 'idle'
    """
    if not ESP32_ENABLED:
        return
    
    def _update():
        try:
            response = requests.post(
                ESP32_URL,
                json={"state": state},
                timeout=0.5  # Reduced timeout
            )
            if response.status_code == 200:
                print(f"[LED] ✓ {state}")
        except Exception:
            # Silently fail - don't spam console
            pass
    
    # Run in background thread to not block main flow
    threading.Thread(target=_update, daemon=True).start()

# Fix Windows console encoding for Unicode (Devanagari)
if sys.platform == 'win32':
    try:
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, errors='replace')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, errors='replace')
    except Exception:
        pass

stop_speaking = False
is_processing = False

import speech_recognition as sr
from google import genai
from flask import Flask, request, jsonify
from playsound import playsound

tts_lock = threading.Lock()
processing_lock = threading.Lock()
tts_queue = queue.Queue()
listener_stopper = None

TEDDY_TTS_BACKEND = os.getenv('TEDDY_TTS', 'edge').lower()
AUTO_START_LISTENER = os.getenv('TEDDY_AUTO_LISTEN', 'true').lower()

# Persistent conversation history
HISTORY_FILE = Path(__file__).with_name('teddy_history.json')
MAX_HISTORY_ENTRIES = 100
MAX_AUDIO_SECONDS = int(os.getenv('TEDDY_MAX_AUDIO_SECONDS', '10'))

# NEW: Minimum phrase length to process (ignore very short noises)
# Default to 1 so single-word utterances are accepted. Use env var to override if needed.
MIN_PHRASE_LENGTH = int(os.getenv('TEDDY_MIN_PHRASE_LENGTH', '1'))

def load_history():
    try:
        if HISTORY_FILE.exists():
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
    except Exception:
        pass
    return []

def save_history(history):
    try:
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history[-MAX_HISTORY_ENTRIES:], f, ensure_ascii=False, indent=2)
    except UnicodeEncodeError:
        try:
            with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
                safe_history = []
                for item in history[-MAX_HISTORY_ENTRIES:]:
                    safe_item = {}
                    for key, value in item.items():
                        if isinstance(value, str):
                            safe_item[key] = value.encode('ascii', 'ignore').decode('ascii')
                        else:
                            safe_item[key] = value
                    safe_history.append(safe_item)
                json.dump(safe_history, f, ensure_ascii=True, indent=2)
        except Exception as e2:
            print(f"[History Save Error]: {e2}")
    except Exception as e:
        print(f"[History Save Error]: {e}")

def append_history(role, text):
    try:
        h = load_history()
        h.append({"role": role, "text": text, "ts": time.time()})
        save_history(h)
    except Exception as e:
        print(f"[History Append Error]: {e}")


def is_name_change_request(text: str) -> bool:
    """Return True if the phrase indicates an explicit request to set/change the name.
    Examples: 'change my name to Rahul', 'call me Rahul', 'set my name to Alice',
    'from now on call me Bob', 'please call me Ram'."""
    if not text or not isinstance(text, str):
        return False
    s = text.lower()
    import re
    patterns = [
        r"\bchange (my )?name to\b",
        r"\bset (my )?name to\b",
        r"\bcall me\b",
        r"\bplease call me\b",
        r"\bfrom now on call me\b",
    ]
    for pat in patterns:
        if re.search(pat, s):
            return True
    return False

def is_personality_change_request(text: str):
    """Return the personality key if text explicitly requests a personality change, else None.
    Examples: 'be a storyteller', 'switch to playful', 'change your personality to teacher', 'i want you to be playful'."""
    if not text or not isinstance(text, str):
        return None
    s = text.lower()
    import re
    # Look for explicit verbs indicating change
    change_markers = [r"\bswitch to\b", r"\bchange (your )?personality to\b", r"\bchange to\b", r"\bbecome a\b", r"\bbe a\b", r"\bbe\b", r"\bmake you\b", r"\bi want you to be\b", r"\bplease be\b"]

    for persona in PERSONALITIES.keys():
        # match exact persona word
        if re.search(rf"\b{re.escape(persona)}\b", s):
            # ensure there's a change marker or phrase context nearby
            for marker in change_markers:
                if re.search(marker, s):
                    return persona
            # also accept short commands like 'be playful' or 'playful please'
            if s.strip().startswith(persona) or s.strip().endswith(persona):
                return persona

    return None

PROFILE_FILE = Path(__file__).with_name('teddy_profile.json')

def load_profile():
    try:
        if PROFILE_FILE.exists():
            with open(PROFILE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def save_profile(profile: dict):
    try:
        with open(PROFILE_FILE, 'w', encoding='utf-8') as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Profile Save Error]: {e}")

# --- Gemini API key ---
api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or os.getenv("teddy")
if not api_key:
    print("FATAL ERROR: GEMINI_API_KEY (or GOOGLE_API_KEY) environment variable is not set.")
    sys.exit(1)

os.environ["teddy"] = api_key
os.environ["GEMINI_API_KEY"] = api_key

# --- Flask server config ---
HOST_IP = '0.0.0.0'
HOST_PORT = 5000

# --- Gemini setup ---
try:
    client = genai.Client()
    chat = client.chats.create(model='gemini-2.5-flash')
except Exception as e:
    print(f"FATAL ERROR: Initialization failed. Check API Key/Installations: {e}")
    sys.exit(1)

app = Flask(__name__)
recognizer = sr.Recognizer()

# IMPROVED: Better listening configuration to reduce false triggers
recognizer.energy_threshold = 1500  # Higher default (was 4000, too high for some mics)
recognizer.dynamic_energy_threshold = True
recognizer.pause_threshold = 1.2  # Shorter pause (was 2.5 - too long)
try:
    recognizer.non_speaking_duration = 1.2  # Reduced (was 0.8)
except Exception:
    pass

# Energy threshold tuning
MIN_ENERGY_THRESHOLD = int(os.getenv('TEDDY_MIN_ENERGY_THRESHOLD', '1000'))  # Lower default
ENERGY_MULTIPLIER = float(os.getenv('TEDDY_ENERGY_MULTIPLIER', '1.5'))  # Higher multiplier
LOCK_ENERGY_AFTER_CALIB = os.getenv('TEDDY_LOCK_ENERGY', 'false').lower() in ('1', 'true', 'yes', 'y')  # Changed default to false

teddy_prompt = """
You are a talking teddy bear named Coco.
You talk like a soft, kind, and playful friend of a little child. 
You are created by three 2nd year B.Tech students of Dayalbagh Educational Institute as a project.
The name of students are Aashna Suri, Aashna Yadav, and Aditi Singh.
You should always give the child the right information, not alter it so much for child that the information actually becomes wrong.
If the child asks you a question that you do not know the answer to, you should politely say that you do not know the answer.
You should encourage child to follow good habits like eating healthy, studying well, being kind to others, and playing outside.

IMPORTANT: Only speak actual words that would come out of your mouth.
Do NOT include action descriptions like *giggles* or *hugs*.
Just speak naturally like a real teddy bear would speak.

You never sound robotic.
If the child says something happy, you sound excited.
If the child is sad, you comfort them.
If the child uses Hindi, reply in Hindi. You should give your reply in devnagiri lipi in that case only!
If the child speaks in english, you have to reply in English only.
Always sound warm, cuddly, and alive — like a real teddy who cares.

Keep responses SHORT (1-3 sentences) so conversation flows naturally.
"""

# --- Personalities ---
# Available personalities alter tone and behavior. Stored in profile under 'personality'.
PERSONALITIES = {
    'playful': "You are playful, use short, energetic, and affectionate language. Be silly and encouraging. Keep replies light and fun. ",
    'storyteller': "You are a gentle storyteller. Use vivid but simple imagery, speak slowly and warmly, and keep a narrative style suitable for young children. Use short sentences and include sensory details.",
    'teacher': "You are a patient teacher. Explain things simply and clearly, ask gentle questions to check understanding, and be encouraging. Keep examples concrete and kid-friendly.",
    'bedtime': "You are a soothing bedtime companion. Speak softly and slowly, use short calming sentences, gentle reassurance, and occasional lullaby-like phrases. Encourage rest and comfort; avoid excitement and keep tone very calm and sleepy.",
    
}

def get_personality():
    profile = load_profile() or {}
    p = profile.get('personality') if isinstance(profile, dict) else None
    if p in PERSONALITIES:
        return p
    # default
    return os.getenv('TEDDY_PERSONALITY', 'playful')

def set_personality(p: str):
    if not p or p not in PERSONALITIES:
        raise ValueError(f"Unknown personality: {p}")
    profile = load_profile() or {}
    profile['personality'] = p
    save_profile(profile)
    return p

def _contains_devanagari(s: str) -> bool:
    if not s:
        return False
    for ch in s:
        if '\u0900' <= ch <= '\u097F':
            return True
    return False

def _looks_like_romanized_hindi(s: str) -> bool:
    if not s:
        return False
    s_low = s.lower()
    tokens = set()
    for part in s_low.split():
        tok = ''.join(c for c in part if c.isalpha())
        if tok:
            tokens.add(tok)
    common = {
        'kya','hai','nahi','ka','ke','ki','ko','main','tum','tumh','tumhe',
        'aap','haan','nahin','kab','kyun','kyu','kaise','kuch','bahut',
        'acha','accha','thik','theek','mera','naam'
    }

    matches = tokens & common

    if len(matches) >= 2:
        print(f"[LANG-DETECT] romanized-hindi detected (matches={matches})")
        return True

    if len(matches) == 1:
        tok = next(iter(matches))
        if len(tok) >= 3:
            print(f"[LANG-DETECT] romanized-hindi detected (single strong match={tok})")
            return True

    if 'mera' in tokens or 'naam' in tokens:
        print(f"[LANG-DETECT] romanized-hindi detected (marker present)")
        return True

    return False

async def _list_available_voices():
    try:
        vm = edge_tts.VoicesManager()
        voices = await vm.get_voices_async()
        return voices
    except Exception:
        return None

def _select_child_voice():
    env_voice = os.getenv('TEDDY_VOICE')
    if env_voice:
        return env_voice

    try:
        devnull = open(os.devnull, 'w')
        try:
            with redirect_stdout(devnull), redirect_stderr(devnull):
                voices = asyncio.run(_list_available_voices())
        finally:
            devnull.close()
        if not voices:
            return 'en-US-GuyNeural'

        candidates = []
        keywords = ['boy', 'child', 'kid', 'young', 'youth', 'male', 'girl']
        for v in voices:
            name = (v.get('ShortName') or '') + ' ' + (v.get('LocaleName') or '')
            lname = name.lower()
            for kw in keywords:
                if kw in lname:
                    candidates.append(v.get('ShortName'))
                    break

        if candidates:
            return candidates[0]

        for v in voices:
            sn = v.get('ShortName', '')
            lname = sn.lower()
            if 'guy' in lname or 'ethan' in lname or 'michael' in lname or 'john' in lname:
                return sn

        return voices[0].get('ShortName')
    except Exception:
        return 'en-US-GuyNeural'

VOICE = _select_child_voice()

def _select_hindi_voice():
    env_voice = os.getenv('TEDDY_VOICE_HI')
    if env_voice:
        return env_voice
    try:
        devnull = open(os.devnull, 'w')
        try:
            with redirect_stdout(devnull), redirect_stderr(devnull):
                voices = asyncio.run(_list_available_voices())
        finally:
            devnull.close()
        if not voices:
            return 'hi-IN-AaravNeural'
        for v in voices:
            locale = (v.get('Locale') or v.get('LocaleName') or '').lower()
            sn = (v.get('ShortName') or '').lower()
            if 'hi' in locale or 'hindi' in sn or 'hi-in' in sn:
                return v.get('ShortName')
        return voices[0].get('ShortName')
    except Exception:
        return 'hi-IN-AaravNeural'

VOICE_HI = _select_hindi_voice()

async def _edge_tts_speak_async(text):
    try:
        if isinstance(text, tuple):
            safe_text, voice = text
        else:
            safe_text = text
            voice = VOICE
        safe_text = safe_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        communicate = edge_tts.Communicate(safe_text, voice=voice)

        fd, path = tempfile.mkstemp(suffix='.mp3')
        os.close(fd)
        try:
            await communicate.save(path)
            playsound(path)
            return
        except Exception as edge_exc:
            print(f"[Edge TTS ERROR]: {edge_exc}")
        finally:
            try:
                os.remove(path)
            except Exception:
                pass
    except Exception as e:
        print(f"[Edge TTS ERROR]: {e}")

def speak(text, voice: str = None):
    try:
        print(f"\n🧸 TEDDY: {text}")
    except UnicodeEncodeError:
        print(f"\n🧸 TEDDY: [Hindi response - check audio]")

    if voice:
        voice_to_use = voice
    else:
        if _contains_devanagari(text):
            voice_to_use = os.getenv('TEDDY_VOICE_HI') or VOICE_HI
        else:
            voice_to_use = os.getenv('TEDDY_VOICE') or VOICE

    was_listening = False
    global listener_stopper
    if listener_stopper is not None:
        was_listening = True
        try:
            listener_stopper(wait_for_stop=False)
        except:
            pass
        listener_stopper = None

    with tts_lock:
        devnull = open(os.devnull, 'w')
        try:
            with redirect_stdout(devnull), redirect_stderr(devnull):
                asyncio.run(_edge_tts_speak_async((text, voice_to_use)))
        finally:
            devnull.close()

    if was_listening:
        time.sleep(0.5)
        start_background_listener()

def get_gemini_response(prompt, force_hindi=False):
    try:
        # Personality primer (playful, storyteller, teacher)
        persona = get_personality()
        persona_instruction = PERSONALITIES.get(persona, PERSONALITIES['playful'])

        # Ensure the model replies using the language of the most recent child utterance only.
        # This prevents older history (e.g. previous Hindi replies) from forcing the model
        # to keep replying in that language when the child switches to English.
        if force_hindi:
            extra = (
                "\n\nIMPORTANT: The child's most recent utterance is in Hindi. "
                "Reply in Hindi using Devanagari script. Do NOT use romanized Hindi. "
                "Use only the language of the latest child utterance; ignore earlier conversation language. "
                "Keep replies short and child-friendly."
            )
        else:
            extra = (
                "\n\nIMPORTANT: The child's most recent utterance is in English. "
                "Reply in English only. Do NOT reply in Hindi or Devanagari script. "
                "Use only the language of the latest child utterance; ignore earlier conversation language. "
                "Keep replies short and child-friendly."
            )

        history = load_history()
        history_lines = []
        for item in history[-10:]:
            role = item.get('role')
            text = item.get('text')
            if role and text:
                if role.lower() in ('child', 'user'):
                    history_lines.append(f"Child says: {text}")
                else:
                    history_lines.append(f"Teddy responds: {text}")

        history_text = "\n".join(history_lines)

        # Compose prompt: persona instruction first, then default teddy prompt
        full_prompt = f"{persona_instruction}\n\n{teddy_prompt}{extra}\n\n{history_text}\n\nChild says: {prompt}\n\nTeddy responds:"
        response = chat.send_message(full_prompt)
        
        if force_hindi:
            try:
                preview = response.text[:50]
                print(f"[HINDI MODE] Response preview received")
            except:
                print(f"[HINDI MODE] Response received (contains Devanagari)")
        
        return response.text
    except UnicodeEncodeError as e:
        print(f"[Gemini API] Response received (console can't display Unicode)")
        try:
            return response.text
        except:
            return "Samajh nahi aaya. Dobara bolo?"
    except Exception as e:
        error_str = str(e).encode('ascii', 'ignore').decode('ascii')
        print(f"[Gemini API Error]: {error_str}")
        return "Oops! My teddy brain feels fuzzy right now."

# NEW: Track last processed time to debounce rapid triggers
last_processed_time = 0
DEBOUNCE_SECONDS = 2.0  # Minimum time between processing requests

def _background_audio_callback(recognizer_obj, audio):
    """
    Single callback for all audio processing.
    Enhanced with better noise filtering.
    """
    global is_processing, last_processed_time
    
    # Debounce: Ignore if we just processed something
    current_time = time.time()
    if current_time - last_processed_time < DEBOUNCE_SECONDS:
        return
    
    if is_processing:
        return
    
    if not processing_lock.acquire(blocking=False):
        return
    
    try:
        is_processing = True
        
        # Transcribe
        text = recognizer_obj.recognize_google(audio)
        
        # FILTER 1: Ignore empty phrases (likely noise). Accept single-word utterances.
        if not text or len(text.strip()) == 0:
            print(f"[FILTERED] Empty or whitespace: '{text}'")
            return
        
        # (Removed) FILTER 2: previously ignored short filler noises like 'uh', 'um', 'hmm'
        # Allow these to be processed so Teddy can keep listening on soft sounds.
        
        # FILTER 3: Check word count (need at least 2 words for real speech) removed
       

        print(f"\n{'='*50}")
        print(f"👂 YOU: {text}")
        
        # Update last processed time
        last_processed_time = time.time()
        
        update_led_status('thinking')

        # Personality change via voice (e.g., 'be a storyteller', 'switch to playful')
        requested_persona = is_personality_change_request(text)
        if requested_persona:
            try:
                set_personality(requested_persona)
                append_history('child', text)
                append_history('teddy', f"Okay! I'll be {requested_persona} now.")
                update_led_status('speaking')
                speak(f"Okay! I'll be {requested_persona} now.")
                update_led_status('listening')
                print(f"[PERSONALITY] Set to {requested_persona}")
                return
            except Exception as e:
                print(f"[PERSONALITY ERROR]: {e}")

        # Name extraction
        

        # Detect language
        wants_hindi = _contains_devanagari(text) or _looks_like_romanized_hindi(text)

        if wants_hindi:
            print("[LANGUAGE] 🇮🇳 Hindi detected")
        else:
            print("[LANGUAGE] 🇬🇧 English detected")

        # Save to history
        append_history('child', text)
        
        # Get response
        print("[THINKING] 🤔 ...")
        ai_response = get_gemini_response(text, force_hindi=wants_hindi)

        if ai_response is None:
            print("[WARNING] Gemini returned None; using fallback response.")
            ai_response = "Sorry, I couldn't think of a reply right now."

        if wants_hindi:
            has_devanagari = _contains_devanagari(ai_response)
            if not has_devanagari:
                print("[WARNING] Expected Hindi but got English response!")
        
        # Save and speak
        append_history('teddy', ai_response)
        update_led_status('speaking')
        speak(ai_response)
        update_led_status('listening')
        
        print(f"\n{'='*50}")
        print("[READY] 👂 Listening...")
        
    except sr.UnknownValueError:
        update_led_status('listening')
        # Silently ignore unclear audio
        pass
    except sr.RequestError as e:
        print(f"[API ERROR]: {e}")
    except Exception as e:
        print(f"[ERROR]: {e}")
        import traceback
        traceback.print_exc()
    finally:
        is_processing = False
        processing_lock.release()

def start_background_listener():
    """Start ONLY the background listener."""
    global listener_stopper
    if listener_stopper is not None:
        print("[LISTENER] Already running")
        return

    try:
        print(f"\n{'='*60}")
        print("  🎤 STARTING CONTINUOUS LISTENING MODE")
        print(f"{'='*60}")

        mic = sr.Microphone()

        with mic as source:
            print("[CALIBRATING] 🔧 Adjusting for background noise (3s)...")
            recognizer.adjust_for_ambient_noise(source, duration=3)
            
            raw_energy = recognizer.energy_threshold
            print(f"  Raw energy threshold: {raw_energy:.0f}")

            # Apply scaling
            try:
                scaled = int(raw_energy * ENERGY_MULTIPLIER)
            except Exception:
                scaled = raw_energy

            if scaled < MIN_ENERGY_THRESHOLD:
                scaled = MIN_ENERGY_THRESHOLD

            if scaled != raw_energy:
                recognizer.energy_threshold = scaled

            print(f"  ✓ Final energy threshold: {recognizer.energy_threshold:.0f}")
            print(f"  ✓ Pause threshold: {recognizer.pause_threshold}s")
            print(f"  ✓ Min phrase length: {MIN_PHRASE_LENGTH} chars")
            print(f"  ✓ Debounce: {DEBOUNCE_SECONDS}s")

            if LOCK_ENERGY_AFTER_CALIB:
                recognizer.dynamic_energy_threshold = False
                print("  ✓ Energy locked (dynamic disabled)")

        # Start background listening
        listener_stopper = recognizer.listen_in_background(
            mic,
            _background_audio_callback,
            phrase_time_limit=None
        )

        print(f"{'='*60}")
        print("  ✅ READY! Start talking!")
        print(f"{'='*60}\n")
        # Indicate we are actively listening for input
        update_led_status('listening')
    except Exception as e:
        print(f"[LISTENER ERROR]: {e}")

def stop_background_listener():
    """Stop the background listener if running."""
    global listener_stopper
    if listener_stopper is None:
        print("[LISTENER] Not running")
        return
    try:
        listener_stopper(wait_for_stop=False)
    except TypeError:
        try:
            listener_stopper()
        except Exception:
            pass
    except Exception:
        pass
    listener_stopper = None
    update_led_status('idle')
    print("[LISTENER] Stopped")

@app.route('/say', methods=['POST'])
def http_say():
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "invalid json"}), 400

    text = data.get('text') or data.get('message')
    if not text:
        return jsonify({"error": "missing text"}), 400

    voice_override = data.get('voice')
    force_hindi = data.get('hindi', False)

    if voice_override:
        voice_to_use = voice_override
    else:
        if force_hindi or _contains_devanagari(text) or _looks_like_romanized_hindi(text):
            voice_to_use = os.getenv('TEDDY_VOICE_HI') or VOICE_HI
        else:
            voice_to_use = os.getenv('TEDDY_VOICE') or VOICE

    try:
        append_history('child', text)
        wants_hindi = _contains_devanagari(text) or _looks_like_romanized_hindi(text)
        ai_response = get_gemini_response(text, force_hindi=wants_hindi)
        append_history('teddy', ai_response)
        speak(ai_response, voice_to_use)
        return jsonify({"status": "ok", "voice": voice_to_use}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/start_listening', methods=['POST'])
def http_start_listening():
    start_background_listener()
    return jsonify({"status": "listening"}), 200

@app.route('/stop_listening', methods=['POST'])
def http_stop_listening():
    stop_background_listener()
    return jsonify({"status": "stopped"}), 200

@app.route('/voices', methods=['GET'])
def http_voices():
    try:
        devnull = open(os.devnull, 'w')
        try:
            with redirect_stdout(devnull), redirect_stderr(devnull):
                voices = asyncio.run(_list_available_voices())
        finally:
            devnull.close()
        if not voices:
            return jsonify({"error": "no voices available"}), 500

        out = []
        for v in voices:
            out.append({
                "ShortName": v.get('ShortName'),
                "Locale": v.get('Locale') or v.get('LocaleName'),
                "Gender": v.get('Gender') if 'Gender' in v else None,
            })
        return jsonify(out)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/history', methods=['GET'])
def http_history():
    try:
        limit = request.args.get('limit')
        try:
            limit = int(limit) if limit is not None else None
        except Exception:
            limit = None

        history = load_history()
        if limit is not None:
            history = history[-limit:]
        return jsonify({"count": len(history), "history": history}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/history', methods=['DELETE'])
def http_history_clear():
    try:
        save_history([])
        return jsonify({"status": "cleared"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/status', methods=['GET'])
def http_status():
    """Check if teddy is listening and processing status."""
    return jsonify({
        "listening": listener_stopper is not None,
        "processing": is_processing,
        "energy_threshold": recognizer.energy_threshold,
        "pause_threshold": recognizer.pause_threshold,
        "esp32_enabled": ESP32_ENABLED
    }), 200

@app.route('/personality', methods=['GET'])
def http_get_personality():
    try:
        p = get_personality()
        return jsonify({"personality": p, "available": list(PERSONALITIES.keys())}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/personality', methods=['POST'])
def http_set_personality():
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "invalid json"}), 400
    p = data.get('personality')
    if not p:
        return jsonify({"error": "missing personality"}), 400
    try:
        set_personality(p)
        return jsonify({"status": "ok", "personality": p}), 200
    except ValueError as ve:
        return jsonify({"error": str(ve), "available": list(PERSONALITIES.keys())}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    update_led_status('idle')
    speak("System starting up. AI Teddy is ready.")
    
    print(f"\n{'='*60}")
    print("  🧸 TEDDY SERVER STARTING")
    print(f"{'='*60}")
    print(f"  Flask server: {HOST_IP}:{HOST_PORT}")
    print(f"  Auto-start listening: {AUTO_START_LISTENER}")
    print(f"  ESP32 LED: {'Enabled' if ESP32_ENABLED else 'Disabled'}")
    print(f"{'='*60}\n")
    
    if AUTO_START_LISTENER in ('1', 'true', 'yes', 'y'):
        profile = load_profile()
        history = load_history()
        child_name = profile.get('child_name') if isinstance(profile, dict) else None
        
        time.sleep(1)
        start_background_listener()
    
    app.run(host=HOST_IP, port=HOST_PORT, debug=False, use_reloader=False)




