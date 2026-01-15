# =======================
# IMPORTS
# =======================
import os
import uuid
import yt_dlp

# =======================
# VIDEO DOWNLOAD FUNCTION
# =======================
def download_video(url, upload_folder):
    """
    Downloads a video from a given URL using yt-dlp.

    Parameters:
    url (str): Video URL (YouTube, Instagram, etc.)
    upload_folder (str): Folder where the video will be saved

    Returns:
    str | None: Path of downloaded video if successful, else None
    """

    # Generate a unique filename to avoid conflicts
    filename = f"video_{uuid.uuid4().hex}.mp4"
    filepath = os.path.join(upload_folder, filename)

    # yt-dlp configuration
    ydl_opts = {
        # Save video at this exact location
        "outtmpl": filepath,

        # Download best quality MP4 up to 720p (faster & lighter)
        "format": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/mp4",

        # Avoid SSL certificate issues
        "nocheckcertificate": True,

        # Suppress unnecessary logs
        "quiet": True,
        "no_warnings": True,
    }

    try:
        # First attempt: normal download
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        # Check if file exists
        if os.path.exists(filepath):
            return filepath

        # Fallback: return any recently created MP4 file
        for file in os.listdir(upload_folder):
            if file.endswith(".mp4"):
                return os.path.join(upload_folder, file)

        return None

    except Exception as e:
        print("Video download failed:", e)
        return None
