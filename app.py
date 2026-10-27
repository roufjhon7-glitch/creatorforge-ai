import os, re, tempfile, textwrap, requests
from pathlib import Path
import streamlit as st
from PIL import Image, ImageDraw, ImageFont
from gtts import gTTS
from moviepy.editor import (
    ImageClip, AudioFileClip, VideoFileClip, concatenate_videoclips
)
from moviepy.video.fx.all import crop

st.set_page_config(page_title="CreatorForge AI", page_icon="🎬", layout="wide")
st.markdown("""
<style>
.stApp {background:#0b1020;color:#f4f6fb}
[data-testid="stSidebar"] {background:#10182b}
.hero {padding:24px;border:1px solid #273654;border-radius:18px;background:linear-gradient(120deg,#151f39,#101426)}
.small {color:#aab7d4}
div.stButton > button {border-radius:10px;font-weight:700}
</style>
""", unsafe_allow_html=True)
st.markdown("""
<div class="hero">
<h1>🎬 CreatorForge AI</h1>
<p>Turn a topic into a narrated video draft — script, stock-video scenes, voice-over and MP4 export.</p>
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
    response = client.responses.create(model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"), input=prompt)
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
    candidates = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                  "/Library/Fonts/Arial.ttf", "C:/Windows/Fonts/arial.ttf"]
    for p in candidates:
        if Path(p).exists():
            try: return ImageFont.truetype(p, size)
            except Exception: pass
    return ImageFont.load_default()

def make_slide(text, index, total, size):
    w, h = size
    img = Image.new("RGB", (w, h), (13, 19, 39))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((int(w*.07), int(h*.09), int(w*.93), int(h*.91)),
                        radius=28, outline=(61, 91, 150), width=3)
    d.rounded_rectangle((int(w*.10), int(h*.14), int(w*.22), int(h*.155)),
                        radius=8, fill=(90, 225, 190))
    d.text((int(w*.10), int(h*.19)), f"SCENE {index+1:02d} / {total:02d}",
           font=load_font(max(18, int(w*.025))), fill=(139, 160, 201))
    lines = textwrap.wrap(text, width=25 if w < h else 42)[:7]
    font = load_font(max(24, int(w*.045)))
    line_h = int(h*.075)
    y = int(h*.36) - (len(lines)*line_h)//2
    for line in lines:
        bbox = d.textbbox((0, 0), line, font=font)
        d.text(((w-(bbox[2]-bbox[0]))//2, y), line, font=font, fill=(246, 248, 255))
        y += line_h
    d.text((int(w*.10), int(h*.83)), "CREATORFORGE AI  •  VIDEO DRAFT",
           font=load_font(max(14, int(w*.018))), fill=(139,160,201))
    return img

def pixabay_video_url(query, api_key, orientation):
    """Return one direct Pixabay stock-video URL and its source page."""
    endpoint = "https://pixabay.com/api/videos/"
    params = {"key": api_key, "q": query[:100], "per_page": 5, "safesearch": "true"}
    response = requests.get(endpoint, params=params, timeout=25)
    response.raise_for_status()
    payload = response.json()
    hits = payload.get("hits", [])
    if not hits:
        return None, None
    # Prefer the desired aspect ratio, otherwise use first usable result.
    for hit in hits:
        variants = hit.get("videos", {})
        preferred = variants.get("large") or variants.get("medium") or variants.get("small")
        if not preferred or not preferred.get("url"):
            continue
        width, height = preferred.get("width", 0), preferred.get("height", 0)
        if orientation == "portrait" and height > width:
            return preferred["url"], hit.get("pageURL")
        if orientation == "landscape" and width >= height:
            return preferred["url"], hit.get("pageURL")
    for hit in hits:
        variants = hit.get("videos", {})
        for quality in ("medium", "small", "large", "tiny"):
            item = variants.get(quality, {})
            if item.get("url"):
                return item["url"], hit.get("pageURL")
    return None, None

def fit_video(clip, size):
    target_w, target_h = size
    # Resize to fill target canvas, then center-crop.
    scale = max(target_w / clip.w, target_h / clip.h)
    clip = clip.resize(scale)
    return crop(clip, width=target_w, height=target_h,
                x_center=clip.w / 2, y_center=clip.h / 2)

def build_video(script, format_choice, voice_lang, use_stock, api_key):
    scenes = split_scenes(script)
    if format_choice == "YouTube Shorts / Reels (9:16)":
        size, fps, orientation = (720, 1280), 24, "portrait"
    else:
        size, fps, orientation = (1280, 720), 24, "landscape"
    with tempfile.TemporaryDirectory() as temp_dir:
        td = Path(temp_dir)
        narration_path = td / "voice.mp3"
        lang_code = "ur" if voice_lang == "Urdu" else "en"
        gTTS(text=script[:4500], lang=lang_code, slow=False).save(str(narration_path))
        audio = AudioFileClip(str(narration_path))
        per_scene = max(3.0, audio.duration / max(1, len(scenes)))
        clips, opened = [], []
        sources = []
        try:
            for i, scene in enumerate(scenes):
                clip = None
                if use_stock and api_key:
                    # Use the scene sentence as a query; short keywords work better for stock search.
                    query = re.sub(r'[^A-Za-z0-9 ]', ' ', scene)
                    query = " ".join(query.split()[:7]) or "cinematic business"
                    try:
                        url, source_page = pixabay_video_url(query, api_key, orientation)
                        if url:
                            local_path = td / f"stock_{i:02d}.mp4"
                            with requests.get(url, stream=True, timeout=60) as r:
                                r.raise_for_status()
                                with open(local_path, "wb") as f:
                                    for block in r.iter_content(chunk_size=1024*1024):
                                        if block: f.write(block)
                            stock = VideoFileClip(str(local_path), audio=False)
                            opened.append(stock)
                            clip = fit_video(stock, size).subclip(0, min(per_scene, stock.duration))
                            sources.append(source_page)
                    except Exception:
                        clip = None
                if clip is None:
                    img_path = td / f"scene_{i:02d}.jpg"
                    make_slide(scene, i, len(scenes), size).save(img_path, quality=90)
                    clip = ImageClip(str(img_path)).set_duration(per_scene)
                else:
                    clip = clip.set_duration(min(per_scene, clip.duration))
                clips.append(clip)
            video = concatenate_videoclips(clips, method="compose")
            video = video.set_audio(audio).set_duration(audio.duration)
            out_path = td / "creatorforge_video.mp4"
            video.write_videofile(str(out_path), fps=fps, codec="libx264",
                                  audio_codec="aac", preset="ultrafast", logger=None)
            data = out_path.read_bytes()
            video.close()
            return data, len(scenes), len(sources), list(dict.fromkeys(sources))
        finally:
            audio.close()
            for c in clips:
                try: c.close()
                except Exception: pass
            for c in opened:
                try: c.close()
                except Exception: pass

with st.sidebar:
    st.header("Video settings")
    format_choice = st.selectbox("Format", ["YouTube Shorts / Reels (9:16)", "YouTube landscape (16:9)"])
    duration = st.selectbox("Target length", ["30–60 seconds", "1–3 minutes", "5–10 minutes"])
    style = st.selectbox("Style", ["Motivational documentary", "Educational explainer", "Storytelling", "Business / success story"])
    language = st.selectbox("Script language", ["English", "Roman Urdu"])
    voice_lang = st.selectbox("Voice language", ["English", "Urdu"])
    use_stock = st.checkbox("Use Pixabay stock videos", value=True)
    st.caption("Stock footage is retrieved from Pixabay. If a matching clip cannot be found, the scene uses a title card.")
    st.markdown("Stock footage: [Pixabay](https://pixabay.com/)")
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
            secret_key = st.secrets.get("PIXABAY_API_KEY", os.getenv("PIXABAY_API_KEY", ""))
            if use_stock and not secret_key:
                st.warning("Pixabay API key is not configured. The video will use title-card scenes. Add PIXABAY_API_KEY in Streamlit Secrets to enable stock footage.")
            with st.spinner("Generating voice-over and assembling the MP4. This can take a few minutes..."):
                mp4, scene_count, stock_count, source_pages = build_video(
                    script.strip(), format_choice, voice_lang, use_stock, secret_key
                )
            if stock_count:
                st.success(f"Video created: {stock_count} stock-video scene(s) and {scene_count-stock_count} title-card scene(s).")
                st.caption("Stock video source: Pixabay. Review the source pages and licensing before publishing.")
                for source in source_pages:
                    if source: st.markdown(f"- [Pixabay clip source]({source})")
            else:
                st.success(f"Video created with {scene_count} title-card scenes.")
            st.video(mp4)
            st.download_button("⬇️ Download MP4", data=mp4, file_name="creatorforge_video.mp4",
                               mime="video/mp4", use_container_width=True)
        except Exception as e:
            st.error("Video export failed. Check the API key, internet access for text-to-speech, and installed dependencies.")
            st.exception(e)

with st.expander("What this MVP does — and does not do"):
    st.markdown("""
- **Works:** editable script, voice-over, subtitles/script text, stock-video scene assembly when clips are available, MP4 export.
- **Stock footage:** fetched from Pixabay's video API using your own API key.
- **Fallback:** title cards are used if a stock search returns no suitable video.
- **Optional:** OpenAI API can generate a more tailored script when `OPENAI_API_KEY` is configured.
- **Not included:** AI-generated original footage, user accounts, cloud project storage, payments, or public multi-user quotas.
""")
