import os, re, tempfile, textwrap, random
from pathlib import Path

import requests
import streamlit as st
from PIL import Image, ImageDraw, ImageFont
from gtts import gTTS
from moviepy.editor import (
    VideoFileClip, ImageClip, AudioFileClip, CompositeVideoClip,
    concatenate_videoclips
)

st.set_page_config(page_title="CreatorForge AI Cinematic", page_icon="🎬", layout="wide")

CSS = """
<style>
.stApp {background: #080d18; color: #f4f6fb;}
[data-testid="stSidebar"] {background: #10182b;}
.hero {padding: 24px; border: 1px solid #273654; border-radius: 18px; background: linear-gradient(120deg,#17233e,#101426);}
.small {color:#aab7d4}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)
st.markdown("""
<div class="hero">
<h1>🎬 CreatorForge AI Cinematic</h1>
<p>Turn a topic into a narrated video using real stock-footage clips, captions, and MP4 export.</p>
<p class="small">Cinematic stock-footage MVP • 9:16 Shorts and 16:9 landscape • English/Urdu narration</p>
</div>
""", unsafe_allow_html=True)

PEXELS_API = os.getenv("PEXELS_API_KEY", "")
try:
    if not PEXELS_API:
        PEXELS_API = st.secrets.get("PEXELS_API_KEY", "")
except Exception:
    pass

def get_openai_script(topic, duration, style, language):
    from openai import OpenAI
    api_key = os.getenv("OPENAI_API_KEY", "")
    try:
        api_key = api_key or st.secrets.get("OPENAI_API_KEY", "")
    except Exception:
        pass
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured.")
    client = OpenAI(api_key=api_key)
    prompt = f"""Write a documentary narration script in {language} about: {topic}.
Target duration: {duration}. Style: {style}.
Use a strong opening hook, concrete scene-friendly paragraphs, and factual cautious wording.
Do not invent quotes or facts. Return narration only, with paragraphs separated by blank lines."""
    response = client.responses.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        input=prompt
    )
    return response.output_text.strip()

def fallback_script(topic, duration, style, language):
    if language == "English":
        return (f"HOOK: What makes {topic} a story worth exploring?\n\n"
                f"In this {style.lower()}, we look at {topic} and the forces behind the story. "
                "Every major achievement begins with a problem, a bold idea, and a series of difficult decisions. "
                "Progress rarely happens in a straight line: there are setbacks, experiments, and lessons along the way. "
                "The most useful question is not simply what happened, but why it mattered and what we can learn from it. "
                "As you watch, consider how persistence, teamwork, timing, and thoughtful risk-taking shape big outcomes. "
                "This is a starting point for research, so verify specific dates and claims before publishing. "
                "Thanks for watching. Follow for more stories and practical ideas.")
    return (f"HOOK: {topic} ki kahani kyun important hai?\n\n"
            f"Is {style} mein hum {topic} aur is ke peechay ke ideas ko samjhenge. "
            "Har bari kamyabi ke peechay aik masla, aik idea aur mushkil faislay hotay hain. "
            "Taraqqi hamesha seedhi line mein nahi hoti; setbacks, experiments aur lessons bhi hotay hain. "
            "Asal sawal sirf yeh nahi ke kya hua, balkeh yeh hai ke kyun hua aur hum kya seekh sakte hain. "
            "Publish karne se pehle dates aur specific facts verify zaroor karein. Video dekhne ka shukriya.")

def split_scenes(script, max_scenes=8):
    chunks = [x.strip() for x in re.split(r'\n\s*\n|(?<=[.!?])\s+', script) if x.strip()]
    chunks = [x for x in chunks if len(x) > 18]
    if not chunks:
        chunks = [script.strip()]
    return chunks[:max_scenes]

def load_font(size, bold=False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/Library/Fonts/Arial.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for p in candidates:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()

def query_for_scene(topic, scene, index):
    # Keep search prompts generic and safe; Pexels returns licensed stock footage.
    clean_topic = re.sub(r"[^a-zA-Z0-9 ]", " ", topic).strip()
    clean_scene = re.sub(r"[^a-zA-Z0-9 ]", " ", scene).strip()
    generic = ["cinematic city at night", "technology close up", "business person working",
               "space rocket launch", "modern factory production", "dramatic landscape"]
    if len(clean_scene.split()) >= 3:
        return (clean_topic + " " + " ".join(clean_scene.split()[:5]) + " cinematic").strip()[:90]
    return (clean_topic + " " + generic[index % len(generic)]).strip()[:90]

def fetch_pexels_video(query, target_w, target_h, folder, index):
    if not PEXELS_API:
        raise RuntimeError("Pexels API key missing. Add PEXELS_API_KEY in Streamlit Secrets to enable stock footage.")
    headers = {"Authorization": PEXELS_API}
    response = requests.get(
        "https://api.pexels.com/videos/search",
        headers=headers,
        params={"query": query, "per_page": 8, "orientation": "portrait" if target_h > target_w else "landscape"},
        timeout=25
    )
    response.raise_for_status()
    videos = response.json().get("videos", [])
    if not videos:
        # Retry with a broad cinematic search.
        response = requests.get(
            "https://api.pexels.com/videos/search",
            headers=headers,
            params={"query": "cinematic documentary technology", "per_page": 8},
            timeout=25
        )
        response.raise_for_status()
        videos = response.json().get("videos", [])
    if not videos:
        raise RuntimeError(f"No stock clips found for: {query}")
    random.shuffle(videos)
    chosen = None
    for video in videos:
        files = sorted(video.get("video_files", []), key=lambda f: (f.get("width", 0) * f.get("height", 0)))
        # Choose a reasonably sized MP4, preferring resolution at/above target when possible.
        mp4s = [f for f in files if f.get("file_type") == "video/mp4" and f.get("link")]
        if mp4s:
            chosen = min(mp4s, key=lambda f: abs((f.get("width", target_w) / max(1, f.get("height", target_h))) - (target_w / target_h)))
            break
    if not chosen:
        raise RuntimeError("Pexels returned no downloadable MP4 file.")
    path = Path(folder) / f"stock_{index:02d}.mp4"
    with requests.get(chosen["link"], stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                if chunk:
                    f.write(chunk)
    return path

def make_caption_overlay(text, size, duration):
    w, h = size
    # A translucent dark lower-third with readable caption text.
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    font = load_font(max(24, int(w * 0.043)), bold=True)
    lines = textwrap.wrap(text, width=25 if h > w else 46)[:4]
    line_height = int(font.size * 1.28)
    box_h = line_height * len(lines) + int(h * 0.035)
    top = int(h * 0.70)
    d.rounded_rectangle((int(w*.06), top, int(w*.94), min(h-int(h*.06), top+box_h)),
                        radius=max(10, int(w*.018)), fill=(3, 7, 16, 190))
    y = top + int(h * 0.018)
    for line in lines:
        bbox = d.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        d.text(((w-tw)//2, y), line, font=font, fill=(255,255,255,255),
               stroke_width=max(0, int(w*.0015)), stroke_fill=(0,0,0,255))
        y += line_height
    return ImageClip(img).set_duration(duration)

def build_video(script, topic, format_choice, voice_lang):
    if not PEXELS_API:
        raise RuntimeError("Cinematic mode needs a free Pexels API key. Add PEXELS_API_KEY in Streamlit app Secrets, then retry.")
    scenes = split_scenes(script, max_scenes=8)
    if format_choice == "YouTube Shorts / Reels (9:16)":
        size, fps = (720, 1280), 24
    else:
        size, fps = (1280, 720), 24

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        narration_path = td / "voice.mp3"
        lang_code = "ur" if voice_lang == "Urdu" else "en"
        gTTS(text=script[:4500], lang=lang_code, slow=False).save(str(narration_path))
        audio = AudioFileClip(str(narration_path))
        total = max(1, len(scenes))
        per_scene = audio.duration / total
        clips = []
        overlays = []
        try:
            for i, scene in enumerate(scenes):
                query = query_for_scene(topic, scene, i)
                stock_path = fetch_pexels_video(query, size[0], size[1], td, i)
                source = VideoFileClip(str(stock_path), audio=False)
                # Center crop to target aspect ratio, then resize.
                target_ratio = size[0] / size[1]
                source_ratio = source.w / source.h
                if source_ratio > target_ratio:
                    new_w = int(source.h * target_ratio)
                    x1 = max(0, (source.w - new_w)//2)
                    source = source.crop(x1=x1, y1=0, x2=x1+new_w, y2=source.h)
                else:
                    new_h = int(source.w / target_ratio)
                    y1 = max(0, (source.h - new_h)//2)
                    source = source.crop(x1=0, y1=y1, x2=source.w, y2=y1+new_h)
                source = source.resize(newsize=size)
                # Use a short, varied segment from each clip.
                start = 0 if source.duration <= per_scene else min(max(0, source.duration * 0.2), source.duration - per_scene)
                end = min(source.duration, start + per_scene)
                clip = source.subclip(start, end)
                if clip.duration < per_scene:
                    clip = clip.set_duration(per_scene)
                caption = make_caption_overlay(scene, size, per_scene).set_position(("center", "center"))
                composed = CompositeVideoClip([clip, caption], size=size).set_duration(per_scene)
                clips.append(composed)
            video = concatenate_videoclips(clips, method="compose").set_audio(audio).set_duration(audio.duration)
            out_path = td / "creatorforge_cinematic.mp4"
            video.write_videofile(str(out_path), fps=fps, codec="libx264", audio_codec="aac",
                                  preset="ultrafast", logger=None)
            data = out_path.read_bytes()
            video.close()
            for clip in clips:
                try: clip.close()
                except Exception: pass
            audio.close()
        except Exception:
            for clip in clips:
                try: clip.close()
                except Exception: pass
            audio.close()
            raise
    return data, len(scenes)

with st.sidebar:
    st.header("Video settings")
    format_choice = st.selectbox("Format", ["YouTube Shorts / Reels (9:16)", "YouTube landscape (16:9)"])
    duration = st.selectbox("Target length", ["30–60 seconds", "1–3 minutes", "5–10 minutes"])
    style = st.selectbox("Style", ["Cinematic documentary", "Motivational documentary", "Educational explainer", "Storytelling", "Business / success story"])
    language = st.selectbox("Script language", ["English", "Roman Urdu"])
    voice_lang = st.selectbox("Voice language", ["English", "Urdu"])
    st.caption("Cinematic visuals use Pexels stock footage. This is real stock footage, not custom AI-generated scenes.")

topic = st.text_input("What should your video be about?", placeholder="Example: Elon Musk's early entrepreneurial journey")
st.caption("For factual documentaries, verify dates and claims before publishing.")

if not PEXELS_API:
    st.info("Cinematic footage is not enabled yet. Add a free Pexels API key in Streamlit app Secrets to enable stock clips. The app will not pretend to create cinematic footage without it.")

if "script" not in st.session_state:
    st.session_state.script = ""

col1, col2 = st.columns([1, 1])
with col1:
    generate = st.button("✨ Generate script", type="primary", use_container_width=True)
with col2:
    clear = st.button("Clear", use_container_width=True)

if clear:
    st.session_state.script = ""
    st.rerun()

if generate:
    if not topic.strip():
        st.warning("Please enter a topic first.")
    else:
        with st.spinner("Creating your script..."):
            try:
                api_key = os.getenv("OPENAI_API_KEY", "")
                try:
                    api_key = api_key or st.secrets.get("OPENAI_API_KEY", "")
                except Exception:
                    pass
                if api_key:
                    st.session_state.script = get_openai_script(topic.strip(), duration, style, language)
                    st.success("Script generated with your configured OpenAI API.")
                else:
                    st.session_state.script = fallback_script(topic.strip(), duration, style, language)
                    st.warning("Template-based draft created. Add OPENAI_API_KEY in Streamlit Secrets for real AI-written scripts.")
            except Exception as e:
                st.error(f"AI script request failed: {e}")

st.subheader("2. Edit your narration")
script = st.text_area("Script (you can edit this before exporting)", key="script", height=260,
                       placeholder="Your script will appear here...")
st.caption(f"{len(script.split())} words • Voice-over and video export use this text.")

if st.button("🎞️ Create cinematic MP4", type="primary", use_container_width=True):
    if len(script.strip()) < 30:
        st.warning("Please generate or enter a longer script first.")
    else:
        try:
            with st.spinner("Finding stock footage, creating voice-over, and rendering the MP4. This may take several minutes..."):
                mp4, scene_count = build_video(script.strip(), topic.strip() or "cinematic documentary", format_choice, voice_lang)
            st.success(f"Cinematic stock-footage video created with {scene_count} scenes.")
            st.video(mp4)
            st.download_button("⬇️ Download cinematic MP4", data=mp4, file_name="creatorforge_cinematic.mp4",
                               mime="video/mp4", use_container_width=True)
        except Exception as e:
            st.error("Cinematic export could not finish.")
            st.warning(str(e))
            st.caption("Check that PEXELS_API_KEY is saved in Streamlit Secrets and that the app has internet access.")

with st.expander("What this version does — and does not do"):
    st.markdown("""
- **When configured:** searches Pexels for real stock video clips, adds narration and on-screen captions, then exports MP4.
- **Optional:** OpenAI API can generate a more tailored script when `OPENAI_API_KEY` is configured.
- **Not included:** custom AI-generated footage of the exact person/event, user accounts, payments, or cloud project storage.
- Pexels stock footage may be illustrative and may not depict the named person or exact event. Review clips and usage terms before publishing.
- Never paste API keys into this code or a public GitHub file. Use Streamlit app Secrets.
""")
