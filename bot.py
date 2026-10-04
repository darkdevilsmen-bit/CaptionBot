import os
import subprocess
from faster_whisper import WhisperModel

def format_timestamp(seconds: float) -> str:
    """Soniyalarni SRT formatiga (HH:MM:SS,mmm) o'tkazadi."""
    millis = int(round(seconds * 1000))
    hours = millis // 3_600_000
    millis %= 3_600_000
    minutes = millis // 60_000
    millis %= 60_000
    secs = millis // 1_000
    millis %= 1_000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

def generate_subtitles(video_path: str, srt_path: str, model_size: str = "base"):
    """Audiodan faqat toza matnni olib, SRT fayl yaratadi."""
    model = WhisperModel(model_size, device="cuda", compute_type="float16")
    segments, _ = model.transcribe(video_path, vad_filter=True)

    with open(srt_path, "w", encoding="utf-8") as srt_file:
        index = 1
        for segment in segments:
            # XATONI OLDINI OLISH: Butun segment emas, faqat toza matn olinadi
            clean_text = segment.text.strip()
            
            # Bo'sh qatorlarni o'tkazib yuborish
            if not clean_text:
                continue

            start_time = format_timestamp(segment.start)
            end_time = format_timestamp(segment.end)

            srt_file.write(f"{index}\n")
            srt_file.write(f"{start_time} --> {end_time}\n")
            srt_file.write(f"{clean_text}\n\n")
            index += 1

def burn_subtitles(video_path: str, srt_path: str, output_path: str):
    """FFmpeg orqali subtitrni videoga qorishtiradi (hardcode)."""
    # Windows yo'llaridagi "\" belgilarini FFmpeg uchun to'g'rilash
    clean_srt_path = srt_path.replace("\\", "/").replace(":", "\\:")
    
    cmd = [
        "ffmpeg",
        "-y",
        "-i", video_path,
        "-vf", f"subtitles='{clean_srt_path}':force_style='FontSize=18,PrimaryColour=&H00FFFF,OutlineColour=&H000000,BorderStyle=3'",
        "-c:a", "copy",
        output_path
    ]
    subprocess.run(cmd, check=True)

if __name__ == "__main__":
    input_video = "input.mp4"
    output_srt = "subtitles.srt"
    final_video = "output.mp4"

    if os.path.exists(input_video):
        print("Subtitrlar yaratilmoqda...")
        generate_subtitles(input_video, output_srt)
        print("Videoga yozilmoqda...")
        burn_subtitles(input_video, output_srt, final_video)
        print("Tayyor!")
    else:
        print(f"{input_video} fayli topilmadi.")
