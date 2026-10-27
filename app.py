import os, re, tempfile, textwrap
from pathlib import Path

import streamlit as st
from PIL import Image, ImageDraw, ImageFont
from gtts import gTTS
from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips

st.set_page_config(page_title="CreatorForge AI", page_icon="🎬", layout="wide")

CSS = """
<style>
.stApp {background: #0b1020; color: #f4f6fb;}
[data-testid="stSidebar"] {background: #10182b;}
.hero {padding: 24px; border: 1px solid #273654; border-radius: 18px; background: linear-gradient(120deg,#151f39,#101426);}
.small {color:#aab7d4}
div.stButton > button {border-radius: 10px; font-weight: 700;}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

st.markdown("""
<div class="hero">
<h1>🎬 CreatorForge AI</h1>
<p>Turn a topic into a narrated video draft — script, scenes, voice-over and MP4 export.</p>
<p class="small">MVP • Vertical Shorts and landscape videos • Optional AI script generation</p>
</div>
""", unsafe_allow_html=True)

def get_openai_script(topic, duration, style, language):
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    prompt = f"""Write a video script in {language} about: {topic}.
Target duration: {duration}. Style: {style}.
Return plain text only with a strong hook, narration in short paragraphs, and 5-10 scene headings.
Avoid fabricated facts. If the topic concerns a real person, use cautious factual wording."""
    response = client.responses.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        input=prompt
    )
    return response.output_text.strip()

def fallback_script(topic, duration, style, language):
    if language == "English":
        return (f"HOOK: What makes {topic} worth understanding?\n\n"
                f"Today, we explore {topic} through a {style.lower()} lens. "
                "First, understand the background and the problem this story is trying to solve. "
                "Next, look at the key decisions, the challenges, and the lessons that can be learned. "
                "Every meaningful result comes from a series of choices, experiments, and adjustments. "
                f"As you think about {topic}, ask what you can apply to your own life or work. "
                "Thanks for watching. Follow for more stories and practical ideas.")
    return (f"HOOK: {topic} ke bare mein aisi kya baat hai jo samajhna zaroori hai?\n\n"
            f"Aaj hum {topic} ko {style} ke andaaz mein samjhenge. "
            "Sab se pehle background aur asal maslay ko dekhein. Phir important decisions, challenges "
            "aur un se milne wale lessons par baat karein. Har result ke peeche kai choices, tests "
            "aur improvements hoti hain. Sochiye ke aap is topic se apni zindagi ya kaam mein kya "
            "apply kar sakte hain. Video dekhne ka shukriya.")

def split_scenes(script, max_scenes=8):
    chunks = [x.strip() for x in re.split(r'\n\s*\n|(?<=[.!?])\s+', script) if x.strip()]
    chunks = [x for x in chunks if len(x) > 18]
    if not chunks:
        chunks = [script.strip()]
    return chunks[:max_scenes]

def load_font(size):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/Library/Fonts/Arial.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for p in candidates:
        if Path(p).exists():
            try: return ImageFont.truetype(p, size)
            except Exception: pass
    return ImageFont.load_default()

def make_slide(text, index, total, size):
    w, h = size
    img = Image.new("RGB", (w, h), (13, 19, 39))
    d = ImageDraw.Draw(img)
    # decorative accent bars
    d.rounded_rectangle((int(w*.07), int(h*.09), int(w*.93), int(h*.91)), radius=28,
                        outline=(61, 91, 150), width=3)
    d.rounded_rectangle((int(w*.10), int(h*.14), int(w*.22), int(h*.155)), radius=8,
                        fill=(90, 225, 190))
    d.text((int(w*.10), int(h*.19)), f"SCENE {index+1:02d} / {total:02d}",
           font=load_font(max(18, int(w*.025))), fill=(139, 160, 201))
    max_chars = 25 if w < h else 42
    lines = textwrap.wrap(text, width=max_chars)
    lines = lines[:7]
    font = load_font(max(24, int(w*.045)))
    # vertically center block
    line_h = int(h*.075)
    y = int(h*.36) - (len(lines)*line_h)//2
    for line in lines:
        bbox = d.textbbox((0,0), line, font=font)
        tw = bbox[2] - bbox[0]
        d.text(((w-tw)//2, y), line, font=font, fill=(246, 248, 255))
        y += line_h
    d.text((int(w*.10), int(h*.83)), "CREATORFORGE AI  •  VIDEO DRAFT",
           font=load_font(max(14, int(w*.018))), fill=(139,160,201))
    return img

def build_video(script, format_choice, voice_lang):
    scenes = split_scenes(script)
    if format_choice == "YouTube Shorts / Reels (9:16)":
        size, fps = (720, 1280), 24
    else:
        size, fps = (1280, 720), 24

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        narration_path = td / "voice.mp3"
        # gTTS is a network-based TTS service; language selection is explicit.
        lang_code = "ur" if voice_lang == "Urdu" else "en"
        gTTS(text=script[:4500], lang=lang_code, slow=False).save(str(narration_path))
        audio = AudioFileClip(str(narration_path))
        per_scene = max(3.0, audio.duration / max(1, len(scenes)))
        clips = []
        image_paths = []
        for i, scene in enumerate(scenes):
            img_path = td / f"scene_{i:02d}.jpg"
            make_slide(scene, i, len(scenes), size).save(img_path, quality=90)
            image_paths.append(img_path)
            clips.append(ImageClip(str(img_path)).set_duration(per_scene))
        video = concatenate_videoclips(clips, method="compose")
        video = video.set_audio(audio)
        # Match video length to narration exactly.
        video = video.set_duration(audio.duration)
        out_path = td / "creatorforge_video.mp4"
        video.write_videofile(str(out_path), fps=fps, codec="libx264",
                              audio_codec="aac", preset="ultrafast",
                              logger=None)
        data = out_path.read_bytes()
        video.close()
        audio.close()
        for c in clips: c.close()
    return data, len(scenes)

with st.sidebar:
    st.header("Video settings")
    format_choice = st.selectbox("Format", ["YouTube Shorts / Reels (9:16)", "YouTube landscape (16:9)"])
    duration = st.selectbox("Target length", ["30–60 seconds", "1–3 minutes", "5–10 minutes"])
    style = st.selectbox("Style", ["Motivational documentary", "Educational explainer", "Storytelling", "Business / success story"])
    language = st.selectbox("Script language", ["English", "Roman Urdu"])
    voice_lang = st.selectbox("Voice language", ["English", "Urdu"])
    st.caption("For long videos, test a short draft first. Current MVP uses title-card scenes, not generated cinematic footage.")

topic = st.text_input("What should your video be about?", placeholder="Example: Elon Musk's early entrepreneurial journey")
st.caption("Tip: Use a specific topic. AI-generated facts should be checked before publishing.")

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
                if os.getenv("OPENAI_API_KEY"):
                    st.session_state.script = get_openai_script(topic.strip(), duration, style, language)
                    st.success("Script generated with your configured OpenAI API.")
                else:
                    st.session_state.script = fallback_script(topic.strip(), duration, style, language)
                    st.info("Template-based draft created. Add an OpenAI API key in deployment secrets for AI-written scripts.")
            except Exception as e:
                st.error(f"AI script request failed: {e}")
                st.stop()

st.subheader("2. Edit your narration")
script = st.text_area("Script (you can edit this before exporting)", key="script", height=260,
                      placeholder="Your script will appear here...")
st.caption(f"{len(script.split())} words • Voice-over and video export use this text.")

if st.button("🎞️ Create narrated MP4", type="primary", use_container_width=True):
    if len(script.strip()) < 30:
        st.warning("Please generate or enter a longer script first.")
    else:
        try:
            with st.spinner("Generating voice-over and assembling the MP4. This can take a few minutes..."):
                mp4, scene_count = build_video(script.strip(), format_choice, voice_lang)
            st.success(f"Video created successfully with {scene_count} title-card scenes.")
            st.video(mp4)
            st.download_button("⬇️ Download MP4", data=mp4, file_name="creatorforge_video.mp4",
                               mime="video/mp4", use_container_width=True)
        except Exception as e:
            st.error("Video export failed. Check internet access for text-to-speech and that all dependencies installed correctly.")
            st.exception(e)

with st.expander("What this MVP does — and does not do"):
    st.markdown("""
- **Works now:** script draft, editable narration, network TTS voice-over, scene title cards, MP4 export.
- **Optional:** OpenAI API can generate a more tailored script when `OPENAI_API_KEY` is configured.
- **Not included yet:** AI-generated cinematic video clips, user accounts, cloud project storage, payments, or public multi-user quotas.
- This app does not pretend to create cinematic AI footage. Scene visuals are designed title cards. AI video generation requires a separate video-generation API and usage budget.
""")
