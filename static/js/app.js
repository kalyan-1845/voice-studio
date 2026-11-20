// AI Voice Studio Application Logic
let currentMode = 'clone';
let uploadedSampleFilename = null;
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;

// Multi-Paragraph Presets (Telugu, Hindi, English)
const SCRIPT_PRESETS = {
  telugu_story: "నమస్కారం! నా పేరు కళ్యాణ్. ఆర్టిఫిషియల్ ఇంటెలిజెన్స్ మరియు వాయిస్ టెక్నాలజీతో మనం ఏదైనా సాధించవచ్చు. ఇది మన సొంత స్వరాన్ని ఖచ్చితంగా పోలి ఉంటుంది. ప్రతి వాక్యం ఎంతో స్పష్టంగా, సహజమైన గమనంతో వినిపిస్తుంది.",
  hindi_story: "नमस्ते! मेरा नाम कल्याण है। आधुनिक तकनीक और एआई की मदद से हम अपनी आवाज़ को पूरी तरह से प्राकृतिक बना सकते हैं। यह बिना किसी रुकावट के बिल्कुल साफ़ और स्पष्ट सुनाई देती है। आप इसे किसी भी लंबे पैराग्राफ के लिए आसानी से इस्तेमाल कर सकते हैं।",
  english_story: "Welcome to today's episode. Voice synthesis has evolved dramatically, allowing us to generate full paragraphs with natural pacing, clear pauses, and high vocal fidelity. Every sentence flows seamlessly without rushing or robotic artifacts."
};

// Initialize
document.addEventListener('DOMContentLoaded', () => {
  setupEventListeners();
  checkTokenStatus();
  loadSamples();
  loadHistory();
  updateWordCount();
});

function setupEventListeners() {
  const dropzone = document.getElementById('dropzone');
  const fileInput = document.getElementById('audio-input');
  const scriptArea = document.getElementById('script-text');

  dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropzone.classList.add('dragover');
  });

  dropzone.addEventListener('dragleave', () => {
    dropzone.classList.remove('dragover');
  });

  dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.classList.remove('dragover');
    if (e.dataTransfer.files.length > 0) {
      handleAudioUpload(e.dataTransfer.files[0]);
    }
  });

  fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
      handleAudioUpload(e.target.files[0]);
    }
  });

  scriptArea.addEventListener('input', updateWordCount);
}

// Token Management
async function checkTokenStatus() {
  try {
    const res = await fetch('/api/token');
    const data = await res.json();
    const btnText = document.getElementById('token-status-text');
    if (data.has_token) {
      btnText.innerText = `Token Connected (${data.masked_token})`;
    } else {
      btnText.innerText = 'Add Free HF Token';
    }
  } catch (err) {
    console.error('Failed to check token:', err);
  }
}

function toggleTokenModal() {
  const modal = document.getElementById('token-modal');
  modal.classList.toggle('hidden');
}

async function saveHfToken() {
  const token = document.getElementById('hf-token-input').value.trim();
  if (!token) {
    showStatus('Please enter a valid token.', 'warning');
    return;
  }

  try {
    const res = await fetch('/api/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token: token })
    });
    const data = await res.json();
    if (res.ok) {
      toggleTokenModal();
      checkTokenStatus();
      showStatus('Hugging Face Token saved successfully! ZeroGPU quota unlocked.', 'info');
      setTimeout(hideStatus, 4000);
    }
  } catch (err) {
    showStatus(`Failed to save token: ${err.message}`, 'error');
  }
}

// Mode Switcher
function switchMode(mode) {
  currentMode = mode;
  document.getElementById('tab-clone').classList.toggle('active', mode === 'clone');
  document.getElementById('tab-neural').classList.toggle('active', mode === 'neural');

  document.getElementById('clone-section').classList.toggle('hidden', mode !== 'clone');
  document.getElementById('neural-section').classList.toggle('hidden', mode !== 'neural');
}

// Word / Duration Counter
function updateWordCount() {
  const text = document.getElementById('script-text').value.trim();
  const words = text ? text.split(/\s+/).length : 0;
  const estSeconds = Math.round((words / 130) * 60);
  document.getElementById('script-counter').innerText = `${words} words | ~${estSeconds}s`;
}

// Presets
function applyPreset(key) {
  if (SCRIPT_PRESETS[key]) {
    document.getElementById('script-text').value = SCRIPT_PRESETS[key];
    updateWordCount();
  }
}

function updateSpeedVal(val) {
  document.getElementById('speed-val').innerText = `${parseFloat(val).toFixed(2)}x`;
}

function updatePitchVal(val) {
  const num = parseInt(val, 10);
  document.getElementById('pitch-val').innerText = `${num >= 0 ? '+' : ''}${num} Hz`;
}

// Load and Display Saved Voice Samples
async function loadSamples() {
  const listEl = document.getElementById('samples-list');
  try {
    const res = await fetch('/api/samples');
    const data = await res.json();

    if (data.samples && data.samples.length > 0) {
      if (!uploadedSampleFilename) {
        selectSample(data.samples[0].filename, data.samples[0].url, `${data.samples[0].size_mb} MB`, false);
      }

      listEl.innerHTML = data.samples.map(s => {
        const isSelected = uploadedSampleFilename === s.filename;
        return `
          <div class="sample-item ${isSelected ? 'selected' : ''}">
            <div class="sample-item-info">
              <strong title="${s.filename}">${s.filename}</strong>
              <span>${s.size_mb} MB</span>
            </div>
            <audio controls src="${s.url}" class="sample-item-player"></audio>
            <button class="btn btn-sm ${isSelected ? 'btn-primary' : 'btn-secondary'}" onclick="selectSample('${s.filename}', '${s.url}', '${s.size_mb} MB', true)">
              ${isSelected ? '✓ Active' : 'Use Voice'}
            </button>
          </div>
        `;
      }).join('');
    } else {
      listEl.innerHTML = '<p class="empty-state-sm">No saved voice profiles yet. Record or upload one above!</p>';
    }
  } catch (err) {
    console.error('Failed to load voice samples:', err);
  }
}

// Select a sample to use for cloning
function selectSample(filename, url, meta, showToast = true) {
  uploadedSampleFilename = filename;
  document.getElementById('sample-filename').innerText = filename;
  document.getElementById('sample-meta').innerText = `${meta} • Ready to clone`;
  const player = document.getElementById('sample-audio-player');
  player.src = url;
  document.getElementById('active-sample-card').classList.remove('hidden');

  const listEl = document.getElementById('samples-list');
  const items = listEl.querySelectorAll('.sample-item');
  items.forEach(item => {
    const title = item.querySelector('.sample-item-info strong');
    const btn = item.querySelector('button');
    if (title && title.innerText === filename) {
      item.classList.add('selected');
      if (btn) {
        btn.className = 'btn btn-sm btn-primary';
        btn.innerText = '✓ Active';
      }
    } else {
      item.classList.remove('selected');
      if (btn) {
        btn.className = 'btn btn-sm btn-secondary';
        btn.innerText = 'Use Voice';
      }
    }
  });

  if (showToast) {
    showStatus(`Voice "${filename}" is now active in "Clone My Voice"!`, 'info');
    setTimeout(hideStatus, 3000);
  }
}

// Upload Audio Sample
async function handleAudioUpload(file) {
  const formData = new FormData();
  formData.append('file', file);

  showStatus('Uploading & analyzing voice (auto-detecting pitch & speech)...', 'info');

  try {
    const res = await fetch('/api/upload-sample', {
      method: 'POST',
      body: formData
    });

    const data = await res.json();
    if (res.ok && data.status === 'success') {
      selectSample(data.file.filename, data.file.url, `${data.file.size_mb} MB`, false);
      
      // Auto-populate transcript if speech recognized
      if (data.file.transcript) {
        document.getElementById('sample-transcript').value = data.file.transcript;
      }
      
      await loadSamples();
      const pitchMsg = data.file.pitch_hz ? ` (Vocal pitch: ${data.file.pitch_hz} Hz)` : '';
      showStatus(`Voice analyzed & calibrated${pitchMsg}! Ready to synthesize.`, 'info');
      setTimeout(hideStatus, 4000);
    } else {
      showStatus(`Upload error: ${data.detail || 'Could not upload audio.'}`, 'error');
    }
  } catch (err) {
    showStatus(`Network error uploading file: ${err.message}`, 'error');
  }
}

// Live Microphone Recording
async function toggleRecording() {
  const recordBtn = document.getElementById('record-btn');
  const recordText = document.getElementById('record-text');

  if (!isRecording) {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunks = [];
      mediaRecorder = new MediaRecorder(stream);

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) audioChunks.push(event.data);
      };

      mediaRecorder.onstop = () => {
        const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
        const recordedFile = new File([audioBlob], `recording_${Date.now()}.wav`, { type: 'audio/wav' });
        handleAudioUpload(recordedFile);
        stream.getTracks().forEach(track => track.stop());
      };

      mediaRecorder.start();
      isRecording = true;
      recordBtn.classList.add('recording');
      recordText.innerText = 'Stop Recording';
      showStatus('Recording your clean voice... Speak naturally for 15-30 seconds.', 'info');
    } catch (err) {
      showStatus(`Microphone access error: ${err.message}`, 'error');
    }
  } else {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
      mediaRecorder.stop();
    }
    isRecording = false;
    recordBtn.classList.remove('recording');
    recordText.innerText = 'Record Clean Voice';
  }
}

// Generate Voiceover
async function generateVoiceover() {
  const scriptText = document.getElementById('script-text').value.trim();
  const speed = parseFloat(document.getElementById('speed-slider').value);
  const pitch = parseInt(document.getElementById('pitch-slider').value, 10);
  const style = document.getElementById('style-select').value;

  if (!scriptText) {
    showStatus('Please enter some text in the script box first.', 'warning');
    return;
  }

  if (currentMode === 'clone' && !uploadedSampleFilename) {
    showStatus('Please select or upload a voice sample first to clone your voice.', 'warning');
    return;
  }

  setGeneratingState(true);
  hideStatus();

  const payload = {
    mode: currentMode,
    sample_filename: uploadedSampleFilename,
    sample_transcript: document.getElementById('sample-transcript').value.trim(),
    script_text: scriptText,
    speed: speed,
    pitch: pitch,
    style: style,
    neural_voice: document.getElementById('neural-voice-select').value,
    remove_silence: false
  };

  try {
    const res = await fetch('/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const data = await res.json();

    if (data.status === 'success') {
      const outCard = document.getElementById('output-container');
      const outPlayer = document.getElementById('output-audio-player');
      const dlBtn = document.getElementById('download-btn');
      const engineBadge = document.getElementById('output-engine');

      outPlayer.src = data.url;
      dlBtn.href = data.url;
      dlBtn.download = data.filename;
      engineBadge.innerText = data.engine;

      outCard.classList.remove('hidden');
      outPlayer.play().catch(() => {});
      loadHistory();
      showStatus('Voiceover successfully synthesized with natural sentence flow!', 'info');
      setTimeout(hideStatus, 4000);
    } else if (data.status === 'warning') {
      showStatus(`${data.message}`, 'warning');
    } else {
      showStatus(`Synthesis error: ${data.detail || 'Generation failed'}`, 'error');
    }
  } catch (err) {
    showStatus(`Connection error: ${err.message}`, 'error');
  } finally {
    setGeneratingState(false);
  }
}

function setGeneratingState(isGenerating) {
  const btn = document.getElementById('generate-btn');
  const spinner = document.getElementById('gen-spinner');
  const btnText = document.getElementById('btn-text');

  btn.disabled = isGenerating;
  spinner.classList.toggle('hidden', !isGenerating);
  btnText.innerText = isGenerating ? 'Synthesizing Paragraphs via Cloud...' : '✨ Generate Studio Voiceover';
}

function showStatus(msg, type = 'info') {
  const banner = document.getElementById('status-banner');
  banner.className = `status-banner ${type}`;
  banner.innerText = msg;
  banner.classList.remove('hidden');
}

function hideStatus() {
  document.getElementById('status-banner').classList.add('hidden');
}

function copyShareLink() {
  const player = document.getElementById('output-audio-player');
  if (player.src) {
    navigator.clipboard.writeText(player.src);
    showStatus('Audio link copied to clipboard!', 'info');
    setTimeout(hideStatus, 3000);
  }
}

// Load Production History
async function loadHistory() {
  const container = document.getElementById('history-list');
  try {
    const res = await fetch('/api/history');
    const data = await res.json();

    if (data.history && data.history.length > 0) {
      container.innerHTML = data.history.map(item => `
        <div class="history-card">
          <div class="history-card-header">
            <strong>${item.filename}</strong>
            <span style="color: var(--text-dim);">${item.size_mb} MB</span>
          </div>
          <audio controls src="${item.url}" class="mini-player"></audio>
          <div style="display: flex; justify-content: flex-end; gap: 0.5rem;">
            <a href="${item.url}" download="${item.filename}" class="btn btn-ghost" style="font-size: 0.75rem;">Download</a>
          </div>
        </div>
      `).join('');
    } else {
      container.innerHTML = '<p class="empty-state">No voice clips generated yet. Create your first master voiceover above!</p>';
    }
  } catch (err) {
    console.error('History load error:', err);
  }
}
