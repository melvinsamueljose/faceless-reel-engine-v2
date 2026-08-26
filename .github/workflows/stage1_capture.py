import os
import sys
import json
import re
import requests

def clean_token(token_str):
    if not token_str:
        return ""
    token = re.sub(r'[\[\]\'"\s]', '', str(token_str))
    if token.startswith("bot"):
        token = token[3:]
    return token

def parse_telegram_payload():
    raw_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    bot_token = clean_token(raw_bot_token)
    chat_id = clean_token(os.getenv("TELEGRAM_CHAT_ID", ""))

    if not bot_token:
        print("[STAGE 1 ERROR] TELEGRAM_BOT_TOKEN is missing or invalid.")
        sys.exit(1)

    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
    
    try:
        resp = requests.get(url, timeout=15).json()
    except Exception as e:
        print(f"[STAGE 1 ERROR] Failed to connect to Telegram API: {e}")
        sys.exit(1)

    if not resp.get("ok"):
        print(f"[STAGE 1 ERROR] Telegram API returned error: {resp}")
        sys.exit(1)

    updates = resp.get("result", [])
    user_prompt_text = ""
    photo_file_ids = []

    for result in reversed(updates):
        msg = result.get("message", {})
        text = msg.get("text", "") or msg.get("caption", "")
        if "/create_reel" in text or "HOOK:" in text or "VOICEOVER_TIMELINE:" in text or "VOICEOVER:" in text:
            user_prompt_text = text
            break

    for result in reversed(updates):
        msg = result.get("message", {})
        if "photo" in msg:
            photo_file_ids.append(msg["photo"][-1]["file_id"])
            if len(photo_file_ids) >= 5:
                break

    photo_file_ids.reverse()

    hook = "STOP MAKING CAROUSELS MANUALLY!"
    caption_style = "energetic_yellow_highlight"
    vo_timeline = []

    if user_prompt_text:
        print("[STAGE 1] Parsing Telegram text prompt...")
        lines = user_prompt_text.split("\n")
        
        simple_vo = ""
        for line in lines:
            line_str = line.strip()
            if line_str.startswith("HOOK:"):
                hook = line_str.replace("HOOK:", "").strip()
            elif line_str.startswith("CAPTION_STYLE:"):
                caption_style = line_str.replace("CAPTION_STYLE:", "").strip()
            elif line_str.startswith("VOICEOVER:"):
                simple_vo = line_str.replace("VOICEOVER:", "").strip()

        if "VOICEOVER_TIMELINE:" in user_prompt_text:
            timeline_block = user_prompt_text.split("VOICEOVER_TIMELINE:")[-1].split("PROMPT:")[0]
            matches = re.findall(r'(\d+(?:\.\d+)?)\s*s\s*-\s*(.+)', timeline_block)
            for match in matches:
                vo_timeline.append({
                    "start_sec": float(match[0]),
                    "text": match[1].strip()
                })
        
        if not vo_timeline and simple_vo:
            vo_timeline.append({"start_sec": 0.0, "text": simple_vo})

    if not vo_timeline:
        vo_timeline.append({
            "start_sec": 0.0, 
            "text": "Creating social media carousels manually takes hours of design work."
        })

    payload = {
        "hook": hook,
        "caption_style": caption_style,
        "vo_timeline": vo_timeline,
        "media_count": len(photo_file_ids)
    }

    with open("script.json", "w") as f:
        json.dump(payload, f, indent=2)

    if photo_file_ids:
        print(f"[STAGE 1] Downloading {len(photo_file_ids)} attached screenshots...")
        for idx, file_id in enumerate(photo_file_ids, start=1):
            file_info_url = f"https://api.telegram.org/bot{bot_token}/getFile?file_id={file_id}"
            file_info = requests.get(file_info_url).json()
            
            if file_info.get("ok"):
                file_path = file_info["result"]["file_path"]
                download_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
                out_name = f"image_{idx}.jpg"
                
                res = requests.get(download_url)
                with open(out_name, "wb") as f:
                    f.write(res.content)
                print(f"[STAGE 1] Saved {out_name}")

def send_ack():
    raw_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    bot_token = clean_token(raw_bot_token)
    chat_id = clean_token(os.getenv("TELEGRAM_CHAT_ID", ""))
    
    if not bot_token or not chat_id:
        return

    with open("script.json", "r") as f:
        data = json.load(f)

    msg = (
        "⚙️ *Payload Ingestion Complete*\n\n"
        f"🖼️ *Downloaded Media:* {data['media_count']} screenshots\n"
        f"📌 *Hook:* {data['hook']}\n"
        f"🎨 *Style:* {data['caption_style']}\n"
        f"🎙️ *Voiceover Clips:* {len(data['vo_timeline'])} timing markers\n\n"
        "⚡ *Executing Stage 2 Render Engine...*"
    )
    
    api_endpoint = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        requests.post(api_endpoint, data={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"})
    except Exception as e:
        print(f"[STAGE 1 WARNING] Failed to send Telegram ACK: {e}")

if __name__ == "__main__":
    parse_telegram_payload()
    send_ack()
