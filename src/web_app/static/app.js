// ── Tab switching ────────────────────────────────────────────────────────
const tabLinks = document.querySelectorAll(".tab-link");
const panels = {
  send: document.getElementById("panel-send"),
  receive: document.getElementById("panel-receive"),
};

tabLinks.forEach((btn) => {
  btn.addEventListener("click", () => {
    tabLinks.forEach((b) => b.classList.remove("is-active"));
    btn.classList.add("is-active");
    Object.values(panels).forEach((p) => p.classList.remove("is-active"));
    panels[btn.dataset.tab].classList.add("is-active");
  });
});

// ── SEND PANEL ───────────────────────────────────────────────────────────
const fileInput = document.getElementById("file-input");
const dropzone = document.getElementById("dropzone");
const dropzoneLabel = document.getElementById("dropzone-label");
const dropzoneFilename = document.getElementById("dropzone-filename");
const uploadForm = document.getElementById("upload-form");
const uploadButton = document.getElementById("upload-button");
const uploadProgress = document.getElementById("upload-progress");
const uploadProgressBar = document.getElementById("upload-progress-bar");
const uploadResult = document.getElementById("upload-result");
const shareCodeEl = document.getElementById("share-code");
const copyCodeButton = document.getElementById("copy-code-button");
const uploadCountdown = document.getElementById("upload-countdown");
const uploadError = document.getElementById("upload-error");

let selectedFile = null;
let countdownInterval = null;

fileInput.addEventListener("change", () => {
  if (fileInput.files.length > 0) {
    setSelectedFile(fileInput.files[0]);
  }
});

["dragover", "dragleave", "drop"].forEach((evt) => {
  dropzone.addEventListener(evt, (e) => e.preventDefault());
});
dropzone.addEventListener("dragover", () => dropzone.classList.add("is-dragover"));
dropzone.addEventListener("dragleave", () => dropzone.classList.remove("is-dragover"));
dropzone.addEventListener("drop", (e) => {
  dropzone.classList.remove("is-dragover");
  const file = e.dataTransfer.files[0];
  if (file) {
    fileInput.files = e.dataTransfer.files;
    setSelectedFile(file);
  }
});

function setSelectedFile(file) {
  selectedFile = file;
  dropzoneFilename.textContent = file.name;
  dropzoneLabel.textContent = "Selected:";
}

function resetUploadUI() {
  uploadError.classList.add("hidden");
  uploadResult.classList.add("hidden");
  uploadProgress.classList.add("hidden");
  uploadProgressBar.style.width = "0%";
  if (countdownInterval) clearInterval(countdownInterval);
}

uploadForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  resetUploadUI();

  if (!selectedFile) {
    uploadError.textContent = "Please choose a file first.";
    uploadError.classList.remove("hidden");
    return;
  }

  const expirationSeconds = document.getElementById("expiration-select").value;
  uploadButton.disabled = true;
  uploadButton.textContent = "Requesting link...";

  try {
    const reqResp = await fetch("/api/upload-request", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        filename: selectedFile.name,
        expiration_seconds: parseInt(expirationSeconds, 10),
      }),
    });
    const reqBody = await reqResp.json();

    if (!reqResp.ok) {
      throw new Error(reqBody.error || "Failed to prepare upload.");
    }

    uploadButton.textContent = "Uploading...";
    uploadProgress.classList.remove("hidden");

    await uploadFileToS3(selectedFile, reqBody.upload_url, (pct) => {
      uploadProgressBar.style.width = `${pct}%`;
    });

    uploadResult.classList.remove("hidden");
    shareCodeEl.textContent = reqBody.file_id;

    const expiresAt = Math.floor(Date.now() / 1000) + reqBody.expires_in_seconds;
    startCountdown(expiresAt);
  } catch (err) {
    uploadError.textContent = err.message || "Something went wrong.";
    uploadError.classList.remove("hidden");
  } finally {
    uploadButton.disabled = false;
    uploadButton.textContent = "Generate Secure Link";
  }
});

function uploadFileToS3(file, url, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url, true);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve();
      else reject(new Error(`Upload failed (status ${xhr.status}).`));
    };
    xhr.onerror = () => reject(new Error("Network error during upload. Check bucket CORS configuration."));
    xhr.send(file);
  });
}

function startCountdown(expiresAt) {
  function tick() {
    const remaining = expiresAt - Math.floor(Date.now() / 1000);
    if (remaining <= 0) {
      uploadCountdown.textContent = "This link has expired.";
      clearInterval(countdownInterval);
      return;
    }
    const mins = Math.floor(remaining / 60);
    const secs = remaining % 60;
    uploadCountdown.textContent = `Expires in ${mins}:${secs.toString().padStart(2, "0")}`;
  }
  tick();
  countdownInterval = setInterval(tick, 1000);
}

copyCodeButton.addEventListener("click", () => {
  navigator.clipboard.writeText(shareCodeEl.textContent).then(() => {
    copyCodeButton.textContent = "Copied!";
    setTimeout(() => (copyCodeButton.textContent = "Copy code"), 1500);
  });
});

// ── RECEIVE PANEL ────────────────────────────────────────────────────────
const downloadForm = document.getElementById("download-form");
const codeInput = document.getElementById("code-input");
const downloadButton = document.getElementById("download-button");
const downloadStatus = document.getElementById("download-status");
const downloadError = document.getElementById("download-error");

codeInput.addEventListener("input", () => {
  codeInput.value = codeInput.value.toUpperCase();
});

downloadForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  downloadStatus.classList.add("hidden");
  downloadError.classList.add("hidden");

  const code = codeInput.value.trim();
  if (!code) {
    downloadError.textContent = "Please enter a code.";
    downloadError.classList.remove("hidden");
    return;
  }

  downloadButton.disabled = true;
  downloadButton.textContent = "Checking...";

  try {
    const resp = await fetch("/api/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code }),
    });
    const body = await resp.json();

    if (!resp.ok) {
      throw new Error(body.error || "Unable to download this file.");
    }

    downloadStatus.textContent = `Starting download: ${body.filename}`;
    downloadStatus.classList.remove("hidden");

    const link = document.createElement("a");
    link.href = body.download_url;
    link.download = body.filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
  } catch (err) {
    downloadError.textContent = err.message || "Something went wrong.";
    downloadError.classList.remove("hidden");
  } finally {
    downloadButton.disabled = false;
    downloadButton.textContent = "Download File";
  }
});
