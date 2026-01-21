# =======================
# IMPORTS
# =======================
import os
import uuid
import threading
import subprocess
import numpy as np
import cv2

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, FileResponse

# =======================
# PATH SETUP
# =======================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
CLIPS_DIR = os.path.join(BASE_DIR, "clips")

os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(CLIPS_DIR, exist_ok=True)

# =======================
# FASTAPI APP
# =======================
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# =======================
# JOB STORE
# =======================
jobs = {}

# =======================
# PEAK DETECTION
# =======================
def detect_visual_peaks(video_path):
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30

    ret, frame = cap.read()
    cap.release()

    if not ret:
        return [5]

    return [5]   # ONE clip for now (stable)

# =======================
# VIDEO PROCESSING
# =======================
def process_video(job_id, input_video):
    try:
        jobs[job_id]["status"] = "processing"

        peaks = detect_visual_peaks(input_video)
        clips = []

        for i, start in enumerate(peaks):
            clip_name = f"{job_id}_clip{i+1}.mp4"
            output_path = os.path.join(CLIPS_DIR, clip_name)

            cmd = [
                "ffmpeg", "-y",
                "-ss", str(start),
                "-t", "8",
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

            clips.append({
                "name": f"Clip {i+1}",
                "url": f"https://ai-clip-gen-4.onrender.com/stream/{clip_name}"
            })

        jobs[job_id] = {
            "status": "done",
            "clips": clips
        }

        os.remove(input_video)

    except Exception as e:
        print("PROCESS ERROR:", e)
        jobs[job_id] = {"status": "error"}

# =======================
# API ENDPOINTS
# =======================
@app.post("/process")
async def process(
    video: UploadFile = File(None),
    url: str = Form(None)
):
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "starting"}

    input_path = os.path.join(UPLOADS_DIR, f"{job_id}.mp4")

    if video:
        with open(input_path, "wb") as f:
            while chunk := await video.read(1024 * 1024):
                f.write(chunk)

        threading.Thread(
            target=process_video,
            args=(job_id, input_path),
            daemon=True
        ).start()

    else:
        jobs[job_id]["status"] = "error"

    return RedirectResponse(
        url=f"https://aipeakclips.netlify.app/result.html?job={job_id}",
        status_code=303
    )

@app.get("/status/{job_id}")
def status(job_id: str):
    return jobs.get(job_id, {"status": "not_found"})

@app.get("/stream/{file_name}")
def stream(file_name: str):
    path = os.path.join(CLIPS_DIR, file_name)
    if not os.path.exists(path):
        raise HTTPException(status_code=404)
    return FileResponse(path, media_type="video/mp4")

# =======================
# RUN
# =======================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
