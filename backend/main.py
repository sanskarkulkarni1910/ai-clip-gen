# =======================
# IMPORTS
# =======================
import sys
import os
import uuid
import subprocess
import threading
import numpy as np
import cv2

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

# =======================
# PATH SETUP
# =======================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
CLIPS_DIR = os.path.join(BASE_DIR, "clips")

# uploads fix
if not os.path.isdir(UPLOADS_DIR):
    if os.path.exists(UPLOADS_DIR):
        os.remove(UPLOADS_DIR)
    os.makedirs(UPLOADS_DIR)

# clips fix
if not os.path.isdir(CLIPS_DIR):
    if os.path.exists(CLIPS_DIR):
        os.remove(CLIPS_DIR)
    os.makedirs(CLIPS_DIR)



sys.path.append(BASE_DIR)

# =======================
# OPTIONAL URL HANDLER
# =======================
try:
    from url_handler import download_video
except ImportError:
    def download_video(url, folder):
        return None

# =======================
# FASTAPI APP SETUP
# =======================
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/clips_static", StaticFiles(directory=CLIPS_DIR), name="clips")

# =======================
# JOB STATUS STORE
# =======================
jobs = {}

# =======================
# VISUAL PEAK DETECTION
# =======================
def detect_visual_peaks(video_path, num_clips=4):
    """
    Detects high-action moments using frame difference technique.
    Returns timestamps for clip creation.
    """
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    scores = []
    step = max(1, int(fps * 2))  # analyze every 2 seconds

    ret, prev_frame = cap.read()
    if not ret:
        cap.release()
        return [5, 15, 25, 35]

    prev_gray = cv2.cvtColor(
        cv2.resize(prev_frame, (40, 40)),
        cv2.COLOR_BGR2GRAY
    )

    for frame_no in range(0, total_frames, step):
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
        ret, frame = cap.read()
        if not ret:
            break

        gray = cv2.cvtColor(
            cv2.resize(frame, (40, 40)),
            cv2.COLOR_BGR2GRAY
        )

        diff = cv2.absdiff(prev_gray, gray)
        score = np.sum(diff)

        scores.append((frame_no / fps, score))
        prev_gray = gray

    cap.release()

    # Pick top peaks
    scores.sort(key=lambda x: x[1], reverse=True)
    peaks = []

    for timestamp, _ in scores:
        if len(peaks) >= num_clips:
            break
        if all(abs(timestamp - p) > 30 for p in peaks):
            peaks.append(max(0, timestamp - 1))

    return sorted(peaks) if peaks else [5, 15, 25, 35]

# =======================
# VIDEO PROCESSING
# =======================
def process_video(job_id, input_video):
    try:
        jobs[job_id]["status"] = "processing"

        peaks = detect_visual_peaks(input_video)
        generated_clips = []

        for index, start in enumerate(peaks):
            jobs[job_id]["status"] = f"Processing clip {index+1}"

            clip_name = f"{job_id}_clip{index + 1}.mp4"
            output_path = os.path.join(CLIPS_DIR, clip_name)

            cmd = [
                "ffmpeg", "-y",
                "-ss", str(start),
                "-t", "10",
                "-i", input_video,
                "-vf", "crop=ih*(9/16):ih,scale=720:1280",
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-crf", "28",
                "-c:a", "aac",
                output_path
            ]

            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if result.returncode != 0:
                print(result.stderr.decode())
                raise Exception("FFmpeg failed")

            generated_clips.append({
                "name": f"Clip {index + 1}",
                "url": f"https://ai-clip-gen-3.onrender.com/stream/{clip_name}"
            })

        jobs[job_id] = {"status": "done", "clips": generated_clips}
        os.remove(input_video)

    except Exception as e:
        print("ERROR:", e)
        jobs[job_id] = {"status": "error"}


# =======================
# API ENDPOINTS
# =======================
@app.post("/process")
async def handle_process(
    video: UploadFile = File(None),
    url: str = Form(None)
):
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "starting"}

    input_path = os.path.join(UPLOADS_DIR, f"{job_id}.mp4")

    # Upload video
    if video and video.filename:
        with open(input_path, "wb") as f:
            while chunk := await video.read(1024 * 1024):
                f.write(chunk)

        threading.Thread(
            target=process_video,
            args=(job_id, input_path),
            daemon=True
        ).start()

    # URL based video
    elif url:
        def download_and_process():
            path = download_video(url, UPLOADS_DIR)
            if path:
                os.rename(path, input_path)
                process_video(job_id, input_path)
            else:
                jobs[job_id]["status"] = "error"

        threading.Thread(target=download_and_process, daemon=True).start()

    return RedirectResponse(
        url=f"https://aipeakclips.netlify.app/result.html?job={job_id}",
        status_code=303
    )

@app.get("/status/{job_id}")
def get_status(job_id: str):
    return jobs.get(job_id, {"status": "not_found"})

@app.get("/stream/{file_name}")
def stream_video(file_name: str):
    file_path = os.path.join(CLIPS_DIR, file_name)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path, media_type="video/mp4")

# =======================
# RUN SERVER
# =======================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
