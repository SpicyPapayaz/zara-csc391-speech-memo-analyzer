import os
import uuid
import base64
import wave
import time
import html
import statistics

import requests
from flask import Flask, request, jsonify, render_template_string
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024

AZURE_SPEECH_KEY = os.getenv("AZURE_SPEECH_KEY")
AZURE_SPEECH_REGION = os.getenv("AZURE_SPEECH_REGION", "eastus")
AZURE_LANGUAGE_KEY = os.getenv("AZURE_LANGUAGE_KEY")
AZURE_LANGUAGE_ENDPOINT = os.getenv("AZURE_LANGUAGE_ENDPOINT")

TEMP_DIR = "temp_audio"
os.makedirs(TEMP_DIR, exist_ok=True)

session_log = []

HTML_PAGE = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Voice-Powered Memo Analyzer</title>
  <style>
    body { font-family: Arial, sans-serif; max-width: 900px; margin: 40px auto; padding: 0 20px; }
    button { padding: 10px 14px; margin-top: 10px; cursor: pointer; }
    .box { border: 1px solid #ddd; border-radius: 10px; padding: 16px; margin: 16px 0; }
    .tag { display: inline-block; background: #eee; padding: 5px 8px; border-radius: 12px; margin: 3px; }
    table { width: 100%; border-collapse: collapse; margin-top: 10px; }
    th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
    pre { background: #f7f7f7; padding: 12px; overflow-x: auto; white-space: pre-wrap; }
  </style>
</head>
<body>
  <h1>Voice-Powered Memo Analyzer</h1>

  <div class="box">
    <h2>Option 1: Upload a WAV Memo</h2>
    <input type="file" id="audioFile" accept=".wav,audio/wav">
    <br>
    <button onclick="submitAudio()">Submit Uploaded Audio</button>
  </div>

  <div class="box">
    <h2>Option 2: Record in Browser</h2>
    <button onclick="startRecording()">Start Recording</button>
    <button onclick="stopRecording()">Stop Recording</button>
    <button onclick="submitRecording()">Submit Recording</button>
    <p><strong>Recording status:</strong> <span id="recordingStatus">Not recording.</span></p>
    <audio id="recordingPreview" controls></audio>
  </div>

  <div class="box">
    <p><strong>Status:</strong> <span id="status">Waiting...</span></p>

    <h2>Results</h2>

    <h3>Transcript</h3>
    <p id="transcript"></p>

    <h3>Key Phrases</h3>
    <div id="keyPhrases"></div>

    <h3>Sentiment</h3>
    <p id="sentiment"></p>

    <h3>Entities</h3>
    <div id="entities"></div>

    <h3>Spoken Summary</h3>
    <p id="summaryText"></p>
    <audio id="audioPlayer" controls></audio>
  </div>

  <details>
    <summary>Raw JSON</summary>
    <pre id="rawJson"></pre>
  </details>

<script>
let audioContext;
let mediaStream;
let sourceNode;
let processorNode;
let recordedBuffers = [];
let recordedBlob = null;
let isRecording = false;

async function startRecording() {
  recordedBuffers = [];
  recordedBlob = null;
  isRecording = true;

  mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });

  audioContext = new (window.AudioContext || window.webkitAudioContext)();
  sourceNode = audioContext.createMediaStreamSource(mediaStream);
  processorNode = audioContext.createScriptProcessor(4096, 1, 1);

  processorNode.onaudioprocess = function(event) {
    if (!isRecording) return;
    const input = event.inputBuffer.getChannelData(0);
    recordedBuffers.push(new Float32Array(input));
  };

  sourceNode.connect(processorNode);
  processorNode.connect(audioContext.destination);

  document.getElementById("recordingStatus").textContent = "Recording...";
  document.getElementById("status").textContent = "Recording in browser...";
}

function stopRecording() {
  if (!isRecording) return;

  isRecording = false;

  if (processorNode) processorNode.disconnect();
  if (sourceNode) sourceNode.disconnect();
  if (mediaStream) mediaStream.getTracks().forEach(track => track.stop());

  const merged = mergeBuffers(recordedBuffers);
  const downsampled = downsampleBuffer(merged, audioContext.sampleRate, 16000);
  const wavArrayBuffer = encodeWAV(downsampled, 16000);

  recordedBlob = new Blob([wavArrayBuffer], { type: "audio/wav" });

  const preview = document.getElementById("recordingPreview");
  preview.src = URL.createObjectURL(recordedBlob);

  document.getElementById("recordingStatus").textContent = "Recording saved as WAV. Ready to submit.";
  document.getElementById("status").textContent = "Recording ready.";
}

async function submitRecording() {
  if (!recordedBlob) {
    alert("Record audio first.");
    return;
  }

  const recordedFile = new File([recordedBlob], "browser_recording.wav", { type: "audio/wav" });
  await sendAudio(recordedFile);
}

async function submitAudio() {
  const fileInput = document.getElementById("audioFile");

  if (!fileInput.files.length) {
    alert("Choose a WAV audio file first.");
    return;
  }

  await sendAudio(fileInput.files[0]);
}

async function sendAudio(file) {
  document.getElementById("status").textContent = "Processing...";
  document.getElementById("rawJson").textContent = "";

  const formData = new FormData();
  formData.append("audio", file);

  try {
    const response = await fetch("/process", {
      method: "POST",
      body: formData
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || "Request failed.");
    }

    showResults(data);
    document.getElementById("status").textContent = "Done.";
  } catch (err) {
    document.getElementById("status").textContent = "Error: " + err.message;
  }
}

function showResults(data) {
  document.getElementById("rawJson").textContent = JSON.stringify(data, null, 2);

  const transcription = data.transcription || {};
  const analysis = data.analysis || {};
  const summary = data.summary || {};

  document.getElementById("transcript").textContent = transcription.transcript || "";

  const keyPhrasesDiv = document.getElementById("keyPhrases");
  keyPhrasesDiv.innerHTML = "";
  (analysis.key_phrases || []).forEach(phrase => {
    const span = document.createElement("span");
    span.className = "tag";
    span.textContent = phrase;
    keyPhrasesDiv.appendChild(span);
  });

  const sentiment = analysis.sentiment || {};
  document.getElementById("sentiment").textContent =
    sentiment.label ? `${sentiment.label} ${JSON.stringify(sentiment.confidence_scores || {})}` : "";

  const entitiesDiv = document.getElementById("entities");
  const entities = analysis.entities || [];

  if (!entities.length) {
    entitiesDiv.innerHTML = "<p>No named entities detected.</p>";
  } else {
    let table = "<table><tr><th>Text</th><th>Category</th><th>Confidence</th></tr>";
    entities.forEach(e => {
      table += `<tr><td>${e.text || ""}</td><td>${e.category || ""}</td><td>${e.confidenceScore || ""}</td></tr>`;
    });
    table += "</table>";
    entitiesDiv.innerHTML = table;
  }

  document.getElementById("summaryText").textContent = summary.summary_text || "";

  if (summary.tts_audio_base64) {
    document.getElementById("audioPlayer").src =
      "data:audio/mp3;base64," + summary.tts_audio_base64;
  }
}

function mergeBuffers(buffers) {
  let totalLength = 0;
  buffers.forEach(buffer => totalLength += buffer.length);

  const result = new Float32Array(totalLength);
  let offset = 0;

  buffers.forEach(buffer => {
    result.set(buffer, offset);
    offset += buffer.length;
  });

  return result;
}

function downsampleBuffer(buffer, inputSampleRate, outputSampleRate) {
  if (outputSampleRate === inputSampleRate) return buffer;

  const sampleRateRatio = inputSampleRate / outputSampleRate;
  const newLength = Math.round(buffer.length / sampleRateRatio);
  const result = new Float32Array(newLength);

  let offsetResult = 0;
  let offsetBuffer = 0;

  while (offsetResult < result.length) {
    const nextOffsetBuffer = Math.round((offsetResult + 1) * sampleRateRatio);
    let accumulator = 0;
    let count = 0;

    for (let i = offsetBuffer; i < nextOffsetBuffer && i < buffer.length; i++) {
      accumulator += buffer[i];
      count++;
    }

    result[offsetResult] = accumulator / count;
    offsetResult++;
    offsetBuffer = nextOffsetBuffer;
  }

  return result;
}

function encodeWAV(samples, sampleRate) {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);

  writeString(view, 0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  writeString(view, 8, "WAVE");
  writeString(view, 12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeString(view, 36, "data");
  view.setUint32(40, samples.length * 2, true);

  floatTo16BitPCM(view, 44, samples);

  return view;
}

function floatTo16BitPCM(output, offset, input) {
  for (let i = 0; i < input.length; i++, offset += 2) {
    let sample = Math.max(-1, Math.min(1, input[i]));
    output.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7FFF, true);
  }
}

function writeString(view, offset, string) {
  for (let i = 0; i < string.length; i++) {
    view.setUint8(offset + i, string.charCodeAt(i));
  }
}
</script>
</body>
</html>
"""

def require_env():
    missing = []
    for name, value in {
        "AZURE_SPEECH_KEY": AZURE_SPEECH_KEY,
        "AZURE_SPEECH_REGION": AZURE_SPEECH_REGION,
        "AZURE_LANGUAGE_KEY": AZURE_LANGUAGE_KEY,
        "AZURE_LANGUAGE_ENDPOINT": AZURE_LANGUAGE_ENDPOINT,
    }.items():
        if not value:
            missing.append(name)

    if missing:
        raise RuntimeError("Missing environment variables: " + ", ".join(missing))


def save_uploaded_audio():
    if "audio" not in request.files:
        return None, (jsonify({"error": "No audio uploaded. Field name must be audio."}), 400)

    audio_file = request.files["audio"]

    if not audio_file.filename:
        return None, (jsonify({"error": "Empty filename."}), 400)

    filename = f"{uuid.uuid4()}_{audio_file.filename}"
    input_path = os.path.join(TEMP_DIR, filename)
    audio_file.save(input_path)

    return input_path, None


def get_wav_info(path):
    try:
        with wave.open(path, "rb") as wav_file:
            frames = wav_file.getnframes()
            rate = wav_file.getframerate()
            channels = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            duration = frames / float(rate)

            return {
                "duration_seconds": round(duration, 2),
                "sample_rate": rate,
                "channels": channels,
                "sample_width": sample_width
            }
    except wave.Error:
        raise ValueError("This deployed version accepts real WAV files only. Use harvard.wav.")


def ticks_to_seconds(ticks):
    return round(ticks / 10_000_000, 3)


def transcribe_audio_rest(wav_path):
    require_env()

    info = get_wav_info(wav_path)

    speech_url = (
        f"https://{AZURE_SPEECH_REGION}.stt.speech.microsoft.com/"
        "speech/recognition/conversation/cognitiveservices/v1"
        "?language=en-US&format=detailed"
    )

    headers = {
        "Ocp-Apim-Subscription-Key": AZURE_SPEECH_KEY,
        "Content-Type": f"audio/wav; codecs=audio/pcm; samplerate={info['sample_rate']}",
        "Accept": "application/json"
    }

    with open(wav_path, "rb") as audio:
        response = requests.post(speech_url, headers=headers, data=audio, timeout=90)

    if not response.ok:
        raise RuntimeError(f"Azure Speech REST error {response.status_code}: {response.text}")

    data = response.json()

    if data.get("RecognitionStatus") not in ["Success", "EndOfDictation"]:
        raise RuntimeError(f"Speech recognition failed: {data}")

    transcript = data.get("DisplayText", "")

    confidence = 0.0
    words = []

    nbest = data.get("NBest", [])
    if nbest:
        best = nbest[0]
        transcript = best.get("Display", transcript)
        confidence = round(float(best.get("Confidence", 0.0)), 3)

        for item in best.get("Words", []):
            words.append({
                "word": item.get("Word", ""),
                "offset": ticks_to_seconds(item.get("Offset", 0)),
                "duration": ticks_to_seconds(item.get("Duration", 0)),
                "confidence": item.get("Confidence", confidence)
            })

    return {
        "transcript": transcript,
        "language": "en-US",
        "duration_seconds": info["duration_seconds"],
        "confidence": confidence,
        "words": words,
        "audio_info": info
    }


def language_request(path, text):
    require_env()

    url = AZURE_LANGUAGE_ENDPOINT.rstrip("/") + path

    headers = {
        "Ocp-Apim-Subscription-Key": AZURE_LANGUAGE_KEY,
        "Content-Type": "application/json"
    }

    body = {
        "documents": [
            {
                "id": "1",
                "language": "en",
                "text": text
            }
        ]
    }

    response = requests.post(url, headers=headers, json=body, timeout=30)

    if not response.ok:
        raise RuntimeError(f"Azure Language error {response.status_code}: {response.text}")

    return response.json()


def analyze_text(text):
    if not text.strip():
        return {
            "key_phrases": [],
            "entities": [],
            "sentiment": {"label": "neutral", "confidence_scores": {}},
            "linked_entities": []
        }

    keyphrases_data = language_request("/text/analytics/v3.1/keyPhrases", text)
    entities_data = language_request("/text/analytics/v3.1/entities/recognition/general", text)
    sentiment_data = language_request("/text/analytics/v3.1/sentiment", text)
    linked_data = language_request("/text/analytics/v3.1/entities/linking", text)

    sentiment_doc = sentiment_data["documents"][0]

    return {
        "key_phrases": keyphrases_data["documents"][0].get("keyPhrases", []),
        "entities": entities_data["documents"][0].get("entities", []),
        "sentiment": {
            "label": sentiment_doc.get("sentiment", "neutral"),
            "confidence_scores": sentiment_doc.get("confidenceScores", {})
        },
        "linked_entities": linked_data["documents"][0].get("entities", [])
    }


def build_summary(analysis_result):
    key_phrases = analysis_result.get("key_phrases", [])
    entities = analysis_result.get("entities", [])
    sentiment = analysis_result.get("sentiment", {}).get("label", "neutral")

    entity_counts = {}

    for entity in entities:
        category = entity.get("category", "Unknown")
        entity_counts[category] = entity_counts.get(category, 0) + 1

    topics = ", ".join(key_phrases[:5]) if key_phrases else "no major topics"

    if entity_counts:
        entity_summary = ", ".join([f"{count} {name}" for name, count in entity_counts.items()])
    else:
        entity_summary = "no named entities"

    return (
        f"Your memo mentions {len(key_phrases)} key topics: {topics}. "
        f"The overall tone is {sentiment}. "
        f"I detected {entity_summary}."
    )


def synthesize_summary_rest(summary_text):
    require_env()

    tts_url = f"https://{AZURE_SPEECH_REGION}.tts.speech.microsoft.com/cognitiveservices/v1"

    ssml = f"""
    <speak version='1.0' xml:lang='en-US'>
      <voice xml:lang='en-US' xml:gender='Female' name='en-US-JennyNeural'>
        {html.escape(summary_text)}
      </voice>
    </speak>
    """

    headers = {
        "Ocp-Apim-Subscription-Key": AZURE_SPEECH_KEY,
        "Content-Type": "application/ssml+xml",
        "X-Microsoft-OutputFormat": "audio-16khz-32kbitrate-mono-mp3",
        "User-Agent": "csc391-speech-app"
    }

    response = requests.post(tts_url, headers=headers, data=ssml.encode("utf-8"), timeout=60)

    if not response.ok:
        raise RuntimeError(f"Azure TTS REST error {response.status_code}: {response.text}")

    return {
        "summary_text": summary_text,
        "tts_audio_base64": base64.b64encode(response.content).decode("utf-8"),
        "char_count": len(summary_text)
    }


@app.route("/")
def home():
    return render_template_string(HTML_PAGE)


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/transcribe", methods=["POST"])
def transcribe_endpoint():
    input_path, error = save_uploaded_audio()
    if error:
        return error

    try:
        return jsonify(transcribe_audio_rest(input_path))
    except ValueError as e:
        return jsonify({"error": str(e)}), 415
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if input_path and os.path.exists(input_path):
            os.remove(input_path)


@app.route("/analyze", methods=["POST"])
def analyze_endpoint():
    data = request.get_json()

    if not data or "text" not in data:
        return jsonify({"error": "Missing JSON field: text"}), 400

    try:
        return jsonify(analyze_text(data["text"]))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/process", methods=["POST"])
def process_endpoint():
    input_path, error = save_uploaded_audio()
    if error:
        return error

    try:
        audio_format = os.path.splitext(input_path)[1].replace(".", "").lower()

        start = time.perf_counter()
        stt_result = transcribe_audio_rest(input_path)
        stt_ms = round((time.perf_counter() - start) * 1000, 2)

        if not stt_result["transcript"]:
            return jsonify({"error": "No speech detected."}), 400

        start = time.perf_counter()
        analysis_result = analyze_text(stt_result["transcript"])
        language_ms = round((time.perf_counter() - start) * 1000, 2)

        summary_text = build_summary(analysis_result)

        start = time.perf_counter()
        tts_result = synthesize_summary_rest(summary_text)
        tts_ms = round((time.perf_counter() - start) * 1000, 2)

        timings = {
            "stt_ms": stt_ms,
            "language_ms": language_ms,
            "tts_ms": tts_ms
        }

        session_log.append({
            "confidence": stt_result["confidence"],
            "entity_count": len(analysis_result["entities"]),
            "sentiment": analysis_result["sentiment"]["label"],
            "timings": timings
        })

        return jsonify({
            "audio_format": audio_format,
            "transcription": stt_result,
            "analysis": analysis_result,
            "summary": tts_result,
            "timings": timings
        })

    except ValueError as e:
        return jsonify({"error": str(e)}), 415
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if input_path and os.path.exists(input_path):
            os.remove(input_path)


@app.route("/telemetry-summary")
def telemetry_summary():
    if not session_log:
        return jsonify({"message": "No calls yet."})

    confidences = [entry["confidence"] for entry in session_log]

    return jsonify({
        "total_calls": len(session_log),
        "avg_confidence": round(statistics.mean(confidences), 3),
        "min_confidence": round(min(confidences), 3),
        "latest_call": session_log[-1]
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
