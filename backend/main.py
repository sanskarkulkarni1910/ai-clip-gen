import os
import uuid
import threading
import subprocess

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, FileResponse

# =======================
# PATHS
# =======================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
CLIPS_DIR = os.path.join(BASE_DIR, "clips")

os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(CLIPS_DIR, exist_ok=True)

# =======================
# APP
# =======================
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

jobs = {}

# =======================
# VIDEO PROCESSING
# =======================
def process_video(job_id, input_video):
    try:
        jobs[job_id]["status"] = "processing"

        clip_name = f"{job_id}_clip1.mp4"
        output_path = os.path.join(CLIPS_DIR, clip_name)

        cmd = [
            "ffmpeg", "-y",
            "-i", input_video,
            "-ss", "2",
            "-t", "8",
            "-vf", "scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "28",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            output_path
        ]

        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        if result.returncode != 0:
            print(result.stderr.decode())
            raise Exception("FFmpeg failed")

        jobs[job_id] = {
            "status": "done",
            "clips": [{
                "name": "Clip 1",
                "url": f"{BASE_URL}/stream/{clip_name}"
            }]
        }

        os.remove(input_video)

    except Exception as e:
        print("ERROR:", e)
        jobs[job_id] = {"status": "error"}

# =======================
# API
# =======================
BASE_URL = os.environ.get("BASE_URL", "").rstrip("/")

@app.post("/process")
async def process(video: UploadFile = File(...)):
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "starting"}

    input_path = os.path.join(UPLOADS_DIR, f"{job_id}.mp4")

    with open(input_path, "wb") as f:
        while chunk := await video.read(1024 * 1024):
            f.write(chunk)

    threading.Thread(
        target=process_video,
        args=(job_id, input_path),
        daemon=True
    ).start()

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
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
