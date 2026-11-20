// AI Voice Studio Application Logic
let currentMode = 'clone';
let uploadedSampleFilename = null;
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;

// Presets
const SCRIPT_PRESETS = {
  intro: "Hey everyone, welcome back to the channel! Today we're diving into something really exciting that you won't want to miss. Make sure to hit subscribe and let's jump right in.",
  tutorial: "In this step-by-step guide, I'll walk you through the entire process from start to finish. Follow along closely, and you'll have this working in less than five minutes.",
  podcast: "Welcome to today's episode. We have a lot of ground to cover, from emerging technologies to real-world lessons you can apply right away.",
  commercial: "Looking to take your workflow to the next level? Discover how effortless creation can be with next-generation tools designed for creators like you."
};

// Initialize
document.addEventListener('DOMContentLoaded', () => {
  setupEventListeners();
  loadHistory();
  updateWordCount();
});

function setupEventListeners() {
  const dropzone = document.getElementById('dropzone');
  const fileInput = document.getElementById('audio-input');
  const scriptArea = document.getElementById('script-text');

  // File dropzone events
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

  // Script text counter
  scriptArea.addEventListener('input', updateWordCount);
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
  // Estimate ~140 words per minute average speaking rate
  const estSeconds = Math.round((words / 140) * 60);
  document.getElementById('script-counter').innerText = `${words} words | ~${estSeconds}s`;
}

// Quick Presets
function applyPreset(key) {
  if (SCRIPT_PRESETS[key]) {
    document.getElementById('script-text').value = SCRIPT_PRESETS[key];
    updateWordCount();
  }
}

function updateSpeedVal(val) {
  document.getElementById('speed-val').innerText = `${parseFloat(val).toFixed(2)}x`;
}

// Upload Audio Sample
async function handleAudioUpload(file) {
  const formData = new FormData();
  formData.append('file', file);

  showStatus('Uploading voice sample...', 'info');

  try {
    const res = await fetch('/api/upload-sample', {
      method: 'POST',
      body: formData
    });

    const data = await res.json();
    if (res.ok && data.status === 'success') {
      uploadedSampleFilename = data.file.filename;
      
      // Update UI with uploaded sample
      document.getElementById('sample-filename').innerText = data.file.filename;
      document.getElementById('sample-meta').innerText = `${data.file.format} • ${data.file.size_mb} MB • Ready to clone`;
      const player = document.getElementById('sample-audio-player');
      player.src = data.file.url;
      
      document.getElementById('active-sample-card').classList.remove('hidden');
      showStatus('Voice sample uploaded successfully! Ready to synthesize.', 'info');
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
      showStatus('Recording your voice... Speak clearly for 15-30 seconds.', 'info');
    } catch (err) {
      showStatus(`Microphone access error: ${err.message}`, 'error');
    }
  } else {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
      mediaRecorder.stop();
    }
    isRecording = false;
    recordBtn.classList.remove('recording');
    recordText.innerText = 'Record Voice';
  }
}

// Generate Voiceover
async function generateVoiceover() {
  const scriptText = document.getElementById('script-text').value.trim();
  const speed = parseFloat(document.getElementById('speed-slider').value);
  const removeSilence = document.getElementById('remove-silence-chk').checked;

  if (!scriptText) {
    showStatus('Please enter some text in the script box first.', 'warning');
    return;
  }

  if (currentMode === 'clone' && !uploadedSampleFilename) {
    showStatus('Please upload or record a voice sample first to clone your voice.', 'warning');
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
    neural_voice: document.getElementById('neural-voice-select').value,
    remove_silence: removeSilence
  };

  try {
    const res = await fetch('/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const data = await res.json();

    if (data.status === 'success') {
      // Show output player
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
      showStatus('Voiceover successfully synthesized!', 'info');
      setTimeout(hideStatus, 4000);
    } else if (data.status === 'warning') {
      showStatus(data.message, 'warning');
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
  btnText.innerText = isGenerating ? 'Synthesizing Audio via Cloud...' : '✨ Generate Studio Voiceover';
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
