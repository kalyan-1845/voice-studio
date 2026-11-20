// AI Voice Studio Application Logic
let currentMode = 'clone';
let uploadedSampleFilename = null;
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;

// Presets
const SCRIPT_PRESETS = {
  intro: "Hey everyone, welcome back to the channel! Today we're diving into something really exciting that you won't want to miss. Make sure to hit subscribe and let's jump right in.",
  hindi: "नमस्ते! मेरा नाम कल्याण है। Voice Studio में आपका स्वागत है। यह आवाज़ पूरी तरह से AI और Cloud द्वारा क्लोन की गई है।",
  tutorial: "In this step-by-step guide, I'll walk you through the entire process from start to finish. Follow along closely, and you'll have this working in less than five minutes.",
  podcast: "Welcome to today's episode. We have a lot of ground to cover, from emerging technologies to real-world lessons you can apply right away.",
  commercial: "Looking to take your workflow to the next level? Discover how effortless creation can be with next-generation tools designed for creators like you."
};

// Initialize
document.addEventListener('DOMContentLoaded', () => {
  setupEventListeners();
  loadSamples();
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

// Load and Display Saved Voice Samples
async function loadSamples() {
  const listEl = document.getElementById('samples-list');
  try {
    const res = await fetch('/api/samples');
    const data = await res.json();

    if (data.samples && data.samples.length > 0) {
      // Auto-select first sample if none selected yet
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

  // Refresh sample list badges
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

  showStatus('Uploading voice sample...', 'info');

  try {
    const res = await fetch('/api/upload-sample', {
      method: 'POST',
      body: formData
    });

    const data = await res.json();
    if (res.ok && data.status === 'success') {
      selectSample(data.file.filename, data.file.url, `${data.file.size_mb} MB`, false);
      await loadSamples();
      showStatus('Voice sample saved and activated for cloning!', 'info');
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
