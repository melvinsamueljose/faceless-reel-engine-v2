import os
import sys
import json
import re
import subprocess
import requests

def clean_token(token_str):
    if not token_str:
        return ""
    token = re.sub(r'[\[\]\'"\s]', '', str(token_str))
    if token.startswith("bot"):
        token = token[3:]
    return token

def build_synced_audio(vo_timeline, output_final_audio="final_synced_vo.mp3"):
    print("[STAGE 2] Generating Edge-TTS clips and applying timestamp delays...")
    
    valid_clips = []
    
    for i, item in enumerate(vo_timeline):
        start_ms = int(item["start_sec"] * 1000)
        text = item["text"].strip()
        if not text:
            text = "Automated video clip generated."
            
        part_filename = f"vo_part_{i}.mp3"
        
        tts_cmd = ["edge-tts", "--text", text, "--write-media", part_filename, "--voice", "en-US-ChristopherNeural"]
        try:
            subprocess.run(tts_cmd, check=True)
        except Exception as err:
            print(f"[STAGE 2 WARNING] Edge-TTS failed for segment {i}: {err}. Creating fallback silent audio.")
            subprocess.run([
                "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", 
                "-t", "1", "-c:a", "libmp3lame", part_filename
            ], check=True)
        
        if os.path.exists(part_filename):
            valid_clips.append((part_filename, start_ms))

    if not valid_clips:
        print("[STAGE 2 ERROR] No audio clips could be generated.")
        sys.exit(1)

    inputs = []
    filter_complex_parts = []
    
    for idx, (filename, delay) in enumerate(valid_clips):
        inputs.extend(["-i", filename])
        filter_complex_parts.append(f"[{idx}:a]adelay={delay}|{delay}[a{idx}]")

    concat_inputs = "".join([f"[a{idx}]" for idx in range(len(valid_clips))])
    filter_complex = ";".join(filter_complex_parts) + f";{concat_inputs}amix=inputs={len(valid_clips)}:normalize=0[aout]"
    
    ffmpeg_cmd = ["ffmpeg", "-y"] + inputs + ["-filter_complex", filter_complex, "-map", "[aout]", "-c:a", "libmp3lame", output_final_audio]
    
    try:
        subprocess.run(ffmpeg_cmd, check=True)
        print(f"[STAGE 2] Synced audio generated successfully: {output_final_audio}")
    except subprocess.CalledProcessError as e:
        print(f"[STAGE 2 WARNING] Multi-clip audio mix failed ({e}). Using first available segment.")
        if os.path.exists(valid_clips[0][0]):
            os.rename(valid_clips[0][0], output_final_audio)

def render_hyperframes():
    print("[STAGE 2] Executing Render Engine...")
    
    downloaded_images = [f for f in os.listdir('.') if f.startswith('image_') and f.endswith('.jpg')]
    
    if downloaded_images:
        print(f"[STAGE 2] Stitching {len(downloaded_images)} screenshots with standardized 1080x1920 scaling...")
        inputs = []
        filter_prep = []
        concat_str = ""
        
        for i, img in enumerate(sorted(downloaded_images)):
            inputs.extend(["-loop", "1", "-t", "3", "-i", img])
            # Force uniform resolution (1080x1920) with black padding to handle varying screenshot sizes
            filter_prep.append(f"[{i}:v]scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1[v{i}]")
            concat_str += f"[v{i}]"
        
        filter_str = ";".join(filter_prep) + f";{concat_str}concat=n={len(downloaded_images)}:v=1:a=0[v]"
        
        ffmpeg_cmd = ["ffmpeg", "-y"] + inputs + [
            "-i", "final_synced_vo.mp3",
            "-filter_complex", filter_str,
            "-map", "[v]", "-map", f"{len(downloaded_images)}:a",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-shortest", "final_reel.mp4"
        ]
        subprocess.run(ffmpeg_cmd, check=True)
        print("[STAGE 2] Video stitched successfully: final_reel.mp4")
    else:
        print("[STAGE 2 WARNING] No custom images found. Running default video pipeline...")
        ffmpeg_cmd = [
            "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=1080x1920:r=30",
            "-i", "final_synced_vo.mp3", "-c:v", "libx264", "-c:a", "aac",
            "-shortest", "final_reel.mp4"
        ]
        subprocess.run(ffmpeg_cmd, check=True)

def dispatch_to_telegram():
    raw_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    bot_token = clean_token(raw_bot_token)
    chat_id = clean_token(os.getenv("TELEGRAM_CHAT_ID", ""))

    if not bot_token or not chat_id:
        print("[STAGE 2 ERROR] Missing Telegram Bot credentials.")
        sys.exit(1)

    video_path = "final_reel.mp4"
    if not os.path.exists(video_path):
        print("[STAGE 2 ERROR] Video file final_reel.mp4 was not generated.")
        sys.exit(1)

    caption = "🚀 *Your Stitched HyperFrames Reel is Ready!*"
    api_endpoint = f"https://api.telegram.org/bot{bot_token}/sendVideo"
    
    print(f"[STAGE 2] Uploading video binary to Telegram...")
    with open(video_path, "rb") as vf:
        resp = requests.post(
            api_endpoint,
            data={"chat_id": chat_id, "caption": caption, "parse_mode": "Markdown"},
            files={"video": vf},
            timeout=120
        )
    
    if resp.status_code == 200:
        print("[STAGE 2 SUCCESS] Final video sent to Telegram successfully!")
    else:
        print(f"[STAGE 2 ERROR] Telegram post failed ({resp.status_code}): {resp.text}")

if __name__ == "__main__":
    if os.path.exists("script.json"):
        with open("script.json", "r") as f:
            data = json.load(f)
        
        vo_timeline = data.get("vo_timeline", [])
        build_synced_audio(vo_timeline)
        render_hyperframes()
        dispatch_to_telegram()
    else:
        print("[STAGE 2 ERROR] script.json not found. Run stage1_capture.py first.")
        sys.exit(1)
