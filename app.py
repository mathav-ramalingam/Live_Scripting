# Corrected app.py
import os
import uuid
from flask import Flask, render_template, request, jsonify, send_from_directory
from pydub import AudioSegment
from pydub.exceptions import CouldntDecodeError
import whisper
from googletrans import Translator
from flask_socketio import SocketIO, emit
from deep_translator import GoogleTranslator
import io
import torch

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key_here'
socketio = SocketIO(app, cors_allowed_origins="*")

UPLOAD_FOLDER = 'uploads'
TRANSCRIPTS_FOLDER = 'transcripts'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['TRANSCRIPTS_FOLDER'] = TRANSCRIPTS_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(TRANSCRIPTS_FOLDER, exist_ok=True)

device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Using device: {device}")


# whisper_model = whisper.load_model("small", device=device)
whisper_model = whisper.load_model("medium", device=device)
# whisper_model = whisper.load_model("small", device=device)

# Dictionary to store audio chunks and other session data
session_data = {}

# --- Helper Functions (No changes needed) ---
def transcribe_audio(audio_path: str, language: str) -> str:
    """Transcribes audio using Whisper."""
    try:
        # Pass the detected language code to the transcribe model
        result = whisper_model.transcribe(audio_path, language=language, fp16=False)
        return result["text"]
    except Exception as e:
        print(f"Transcription failed: {e}")
        return ""

# def translate_text(text: str, src_lang: str, dest_lang: str) -> str:
#     translator = Translator()
#     try:
#         src = src_lang.split('-')[0]
#         dest = dest_lang.split('-')[0]
#         translation = translator.translate(text, src=src, dest=dest)
#         return translation.text
#     except Exception as e:
#         print(f"Translation failed: {e}")
#         return "Translation Error."
    

def translate_text(text: str, src_lang: str, dest_lang: str) -> str:
    """Translates text from source to target language."""
    try:
        translation = GoogleTranslator(source=src_lang, target=dest_lang).translate(text)
        return translation
    except Exception as e:
        print(f"Translation failed: {e}")
        return "Translation Error."

def save_text_to_file(text: str) -> str:
    filename = f"script_{uuid.uuid4().hex[:6]}.txt"
    filepath = os.path.join(app.config['TRANSCRIPTS_FOLDER'], filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(text)
    return filename

# --- Page Routes (No changes needed) ---
@app.route('/')
def home():
    return render_template('home.html')

@app.route('/upload_transcribe')
def upload_transcribe_page():
    return render_template('upload.html')

@app.route('/live_scripting')
def live_scripting_page():
    return render_template('live.html')

# Updated process_audio_file function in app.py

# Updated process_audio_file function in app.py

@app.route('/process_file', methods=['POST'])
def process_audio_file():
    if 'audio' not in request.files or 'language' not in request.form or 'source_language' not in request.form:
        return jsonify({'error': 'Missing audio file or language'}), 400
    
    file = request.files['audio']
    target_lang = request.form['language']
    # Get the user-selected source language
    source_lang_code = request.form['source_language']
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    temp_wav_path = None
    try:
        # Step 1: Read the uploaded audio into memory
        audio_stream = io.BytesIO(file.read())
        
        # Step 2: Use pydub to handle decoding and resampling to a compatible format
        try:
            audio_segment = AudioSegment.from_file(audio_stream)
        except CouldntDecodeError:
            return jsonify({'error': 'Could not decode audio file. Please ensure it is a valid format (e.g., MP3, WAV, M4A).'}), 400
            
        audio_segment = audio_segment.set_frame_rate(16000).set_channels(1)
        
        # Step 3: Export the corrected audio data to a temporary WAV file
        temp_wav_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{uuid.uuid4().hex}.wav")
        audio_segment.export(temp_wav_path, format="wav")
        
        # Step 4: Load the correctly formatted WAV file using Whisper's utility
        audio = whisper.load_audio(temp_wav_path)

        # Step 5: Transcribe the audio using the user-selected source language
        if source_lang_code == "ta":
            result = whisper_model.transcribe(
            audio,
            language=source_lang_code,   # Lock source language (Tamil = "ta")
            task="transcribe",           # Don’t auto-translate
            fp16=False,                  # Prevent slowdown on CPU
            initial_prompt="இது தமிழ் உரையாடல்." if source_lang_code == "ta" else None
            )
            transcription = result["text"]
            print("transcribe success(ta)")
        else:
            transcription = transcribe_audio(audio, source_lang_code)
            print("transcribe success")

        
        # Step 6: Translate the transcription to the user's selected target language
        if source_lang_code != target_lang:
            translation = translate_text(transcription, source_lang_code, target_lang)
        else:
            translation = transcription

        # Combine original and translated text for the file
        combined_text = f"Original ({source_lang_code}): {transcription}\n\nTranslated ({target_lang}): {translation}"
        saved_filename = save_text_to_file(combined_text)

        return jsonify({
            'transcription': translation,
            'download_link': f"/download/{saved_filename}"
        })
    except Exception as e:
        print(f"Error processing audio file: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        # Step 7: Clean up the temporary file
        if temp_wav_path and os.path.exists(temp_wav_path):
            os.remove(temp_wav_path)

@app.route('/download/<filename>')
def download_file(filename):
    return send_from_directory(app.config['TRANSCRIPTS_FOLDER'], filename, as_attachment=True)

# --- Live Scripting with Socket.IO ---
@socketio.on('connect')
def handle_connect():
    sid = request.sid
    print(f'Client connected: {sid}')
    session_data[sid] = {'audio_chunks': [], 'source_lang': None, 'target_lang': None}

@socketio.on('start_live_session')
def handle_start_session(data):
    sid = request.sid
    session_data[sid]['source_lang'] = data.get('source_lang')
    session_data[sid]['target_lang'] = data.get('target_lang')
    print(f"Session {sid} started with languages: {session_data[sid]['source_lang']} -> {session_data[sid]['target_lang']}")
    # Emit a confirmation to the client
    emit('session_started', {'status': 'Session started successfully'})

@socketio.on('audio_chunk')
def handle_audio_chunk(data):
    sid = request.sid
    # Simply append the new audio chunk to the session's list
    # Processing happens only when the session ends
    if sid in session_data:
        session_data[sid]['audio_chunks'].append(data)

@socketio.on('end_live_session')
def handle_end_session():
    sid = request.sid
    if sid not in session_data or not session_data[sid]['audio_chunks']:
        print("No audio chunks to process for session:", sid)
        emit('download_ready', {'download_link': ''})
        return

    print("End of session received. Processing audio...")
    
    # Combine all accumulated audio chunks
    combined_audio_stream = io.BytesIO(b"".join(session_data[sid]['audio_chunks']))
    
    try:
        audio_segment = AudioSegment.from_file(combined_audio_stream)
        audio_segment = audio_segment.set_frame_rate(16000).set_channels(1)
        
        temp_wav_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{sid}_temp.wav")
        audio_segment.export(temp_wav_path, format="wav")
        
        source_lang = session_data[sid]['source_lang']
        target_lang = session_data[sid]['target_lang']
        
        # Perform transcription and translation once at the end
        final_transcription = transcribe_audio(temp_wav_path, source_lang)
        final_translation = translate_text(final_transcription, source_lang, target_lang)

        # Emit the final translation back to the client
        emit('final_translation_update', {'translated_text': final_translation})
        
        # Save to file
        final_text = f"Original ({source_lang}): {final_transcription}\n\nTranslated ({target_lang}): {final_translation}"
        saved_filename = save_text_to_file(final_text)
        
        # Send the download link to the client
        emit('download_ready', {'download_link': f"/download/{saved_filename}"})

        # Clean up temporary file
        os.remove(temp_wav_path)
        
    except Exception as e:
        print(f"Error processing audio on end session: {e}")
        emit('download_ready', {'download_link': ''})
    finally:
        # Clean up session data
        if sid in session_data:
            del session_data[sid]

@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    print(f'Client disconnected: {sid}')
    if sid in session_data:
        del session_data[sid]

if __name__ == '__main__':
    socketio.run(app, debug=True)