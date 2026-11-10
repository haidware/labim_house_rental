(() => {
  const chunkSize = 6 * 1024 * 1024;
  const retryDelays = [1000, 3000, 5000, 10000, 20000];
  const videoTypes = {
    m4v: "video/x-m4v",
    mov: "video/quicktime",
    mp4: "video/mp4",
    webm: "video/webm"
  };

  function tusRequest(method, url, headers, body, onProgress) {
    return new Promise((resolve, reject) => {
      const request = new XMLHttpRequest();
      request.open(method, url);
      request.timeout = 600000;
      Object.entries(headers).forEach(([name, value]) => {
        request.setRequestHeader(name, value);
      });
      if (onProgress) request.upload.onprogress = onProgress;
      request.onload = () => {
        if (request.status >= 200 && request.status < 300) {
          resolve(request);
          return;
        }
        let detail = "";
        try {
          const response = JSON.parse(request.responseText);
          detail = response.message || response.error || response.details || "";
        } catch {
          detail = request.responseText.trim().slice(0, 240);
        }
        const error = new Error(
          `Upload failed (HTTP ${request.status})${detail ? `: ${detail}` : "."}`
        );
        error.status = request.status;
        reject(error);
      };
      request.onerror = () => reject(new Error("Network connection interrupted."));
      request.ontimeout = () => reject(new Error("Upload request timed out."));
      request.onabort = () => reject(new Error("Upload was cancelled."));
      request.send(body);
    });
  }

  function encodeMetadata(value) {
    return btoa(new TextEncoder().encode(value).reduce(
      (encoded, byte) => encoded + String.fromCharCode(byte),
      ""
    ));
  }

  async function uploadVideo(file, details, bucket, progress, status, key) {
    const headers = {
      "Tus-Resumable": "1.0.0",
      "x-signature": details.token
    };
    let uploadUrl = details.upload_url || "";
    let offset = 0;
    if (uploadUrl) {
      try {
        const resumed = await tusRequest("HEAD", uploadUrl, headers);
        offset = Number(resumed.getResponseHeader("Upload-Offset"));
        if (!Number.isFinite(offset) || offset < 0 || offset > file.size) {
          throw new Error("Storage returned an invalid upload position.");
        }
        progress.value = Math.floor(offset * 100 / file.size);
      } catch {
        uploadUrl = "";
        offset = 0;
      }
    }

    if (!uploadUrl) {
      const contentType = videoTypes[file.name.split(".").pop().toLowerCase()];
      const metadata = [
        ["bucketName", bucket],
        ["objectName", details.path],
        ["contentType", contentType],
        ["cacheControl", "3600"]
      ].map(([name, value]) => `${name} ${encodeMetadata(value)}`).join(",");
      const created = await tusRequest(
        "POST",
        details.resumable_endpoint,
        {
          ...headers,
          "Upload-Length": file.size.toString(),
          "Upload-Metadata": metadata
        }
      );
      const location = created.getResponseHeader("Location");
      if (!location) throw new Error("Storage did not return an upload URL.");
      uploadUrl = new URL(location, details.resumable_endpoint).toString();
      details.upload_url = uploadUrl;
      sessionStorage.setItem(key, JSON.stringify(details));
    }

    while (offset < file.size) {
      const chunkEnd = Math.min(offset + chunkSize, file.size);
      let attempts = 0;
      while (true) {
        try {
          const patched = await tusRequest(
            "PATCH",
            uploadUrl,
            {
              ...headers,
              "Upload-Offset": offset.toString(),
              "Content-Type": "application/offset+octet-stream"
            },
            file.slice(offset, chunkEnd),
            (event) => {
              if (!event.lengthComputable) return;
              progress.value = Math.floor(
                Math.min(offset + event.loaded, file.size) * 100 / file.size
              );
              status.textContent = `Uploading video... ${progress.value}%`;
            }
          );
          const nextOffset = Number(patched.getResponseHeader("Upload-Offset"));
          if (nextOffset !== chunkEnd) {
            throw new Error("Storage confirmed an unexpected upload position.");
          }
          offset = nextOffset;
          break;
        } catch (error) {
          if (attempts >= retryDelays.length) throw error;
          status.textContent =
            `Connection interrupted. Resuming upload (${attempts + 1}/` +
            `${retryDelays.length})...`;
          await new Promise((resolve) => setTimeout(resolve, retryDelays[attempts]));
          attempts += 1;
          const resumed = await tusRequest("HEAD", uploadUrl, headers);
          const serverOffset = Number(resumed.getResponseHeader("Upload-Offset"));
          if (!Number.isFinite(serverOffset) || serverOffset < 0 || serverOffset > file.size) {
            throw new Error("Storage returned an invalid upload position.");
          }
          offset = serverOffset;
          progress.value = Math.floor(offset * 100 / file.size);
          if (offset >= file.size) break;
        }
      }
    }
    sessionStorage.removeItem(key);
  }

  document.querySelectorAll("[data-rental-video-upload]").forEach((form) => {
    let formAction = form.getAttribute("action") || window.location.href;
    const videoInput = form.querySelector('input[name="video"]');
    const pathInput = form.querySelector('input[name="video_path"]');
    const durationInput = form.querySelector('input[name="video_duration"]');
    const progress = form.querySelector("progress");
    const status = form.querySelector(".video-upload-status");
    const submit = form.querySelector('button[type="submit"]');
    const photoInput = form.querySelector('input[name="photos"]');
    const csrfToken = form.querySelector('input[name="csrfmiddlewaretoken"]')?.value || "";
    if (!videoInput || !pathInput || !durationInput || !progress || !status || !submit) {
      return;
    }

    videoInput.addEventListener("change", () => {
      pathInput.value = "";
      durationInput.value = "";
      form.dataset.videoPrepared = "false";
      status.textContent = "";
      progress.hidden = true;
    });

    form.addEventListener("submit", async (event) => {
      const file = videoInput.files[0];
      if (!file || form.dataset.videoPrepared === "true") return;
      event.preventDefault();
      if (form.dataset.uploading === "true") return;

      const extension = file.name.split(".").pop().toLowerCase();
      const contentType = videoTypes[extension];
      if (!contentType || file.size <= 0 || file.size > 100 * 1024 * 1024) {
        status.textContent =
          "Choose an MP4, MOV, M4V, or WEBM video up to 100 MB.";
        return;
      }

      form.dataset.uploading = "true";
      submit.disabled = true;
      progress.hidden = false;
      progress.value = 0;
      let objectUrl;
      const uploadKey = [
        "rental-video-tus",
        formAction,
        file.name,
        file.size,
        file.lastModified
      ].join(":");
      try {
        status.textContent = "Checking video duration...";
        const duration = await new Promise((resolve, reject) => {
          const probe = document.createElement("video");
          objectUrl = URL.createObjectURL(file);
          probe.preload = "metadata";
          probe.onloadedmetadata = () => resolve(probe.duration);
          probe.onerror = () => reject(
            new Error("This browser could not read the video duration.")
          );
          probe.src = objectUrl;
        });
        if (!Number.isFinite(duration) || duration <= 0 || duration > 180) {
          throw new Error("The video must be no longer than 3 minutes.");
        }

        status.textContent = "Saving listing details...";
        const listingData = new FormData(form);
        listingData.delete("video");
        listingData.delete("video_path");
        listingData.delete("video_duration");
        listingData.set("action", "save");
        const keepNewListingDraft =
          form.dataset.newListing === "true"
          || form.dataset.pendingNewVideo === "true";
        if (keepNewListingDraft) {
          listingData.set("status", "draft");
        }
        const saved = await fetch(formAction, {
          method: "POST",
          headers: {"Accept": "application/json"},
          body: listingData
        });
        const listingResult = await saved.json();
        if (!saved.ok) {
          throw new Error(listingResult.error || "Could not save listing details.");
        }
        form.setAttribute("action", listingResult.edit_url);
        formAction = form.getAttribute("action");
        if (form.dataset.newListing === "true") {
          form.dataset.pendingNewVideo = "true";
        }
        form.dataset.newListing = "false";
        form.dataset.videoUploadUrl = listingResult.upload_url;
        if (photoInput) photoInput.value = "";

        status.textContent = "Preparing secure video upload...";
        let uploadDetails;
        try {
          uploadDetails = JSON.parse(sessionStorage.getItem(uploadKey));
        } catch {
          uploadDetails = null;
        }
        if (!uploadDetails) {
          const prepared = await fetch(form.dataset.videoUploadUrl, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-CSRFToken": csrfToken
            },
            body: JSON.stringify({
              filename: file.name,
              content_type: contentType,
              size: file.size
            })
          });
          uploadDetails = await prepared.json();
          if (!prepared.ok) {
            throw new Error(
              uploadDetails.error || "Could not prepare the video upload."
            );
          }
          sessionStorage.setItem(uploadKey, JSON.stringify(uploadDetails));
        }

        await uploadVideo(
          file,
          uploadDetails,
          "rental-listing-videos",
          progress,
          status,
          uploadKey
        );
        pathInput.value = uploadDetails.path;
        durationInput.value = duration.toString();
        videoInput.value = "";
        form.dataset.videoPrepared = "true";
        form.dataset.pendingNewVideo = "false";
        status.textContent = "Video uploaded. Saving listing...";
        form.dataset.uploading = "false";
        submit.disabled = false;
        form.requestSubmit(submit);
      } catch (error) {
        if (error.status === 400) sessionStorage.removeItem(uploadKey);
        status.textContent = error.message || "Video upload failed. Please retry.";
        form.dataset.uploading = "false";
        submit.disabled = false;
      } finally {
        if (objectUrl) URL.revokeObjectURL(objectUrl);
      }
    });
  });
})();
