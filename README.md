# CreatorForge AI — Working MVP

A small web app that creates a script draft, voice-over, designed scene cards, and downloadable MP4. It is a real MVP, not a fake AI video claim.

## What works
- Topic input and video format selection (9:16 or 16:9)
- Template-based script draft without API key
- Optional OpenAI-generated script when an API key is configured
- gTTS voice-over (requires network access)
- Scene-card video assembly and MP4 download

## What is not included
The MVP does **not** generate cinematic AI video footage. It assembles designed text cards with narration. True text-to-video generation requires a separate paid video API, which is intentionally not enabled by default to protect a small budget.

## Run locally
Use Python 3.10 or 3.11.

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
streamlit run app.py
```

Open the local URL Streamlit prints (usually http://localhost:8501).

## Optional OpenAI script generation
Set an API key as an environment variable; do not put it directly into `app.py` or commit it to Git.

macOS/Linux:
```bash
export OPENAI_API_KEY="your-key"
streamlit run app.py
```

Windows PowerShell:
```powershell
$env:OPENAI_API_KEY="your-key"
streamlit run app.py
```

You may set `OPENAI_MODEL` to a model available to your account. API use is billed separately and is not included in a ChatGPT subscription.

## Deploy for testing
1. Create a GitHub repository and upload these files.
2. Create a Streamlit Community Cloud app (or another Python app host).
3. Select `app.py` as the main file.
4. If using OpenAI, add `OPENAI_API_KEY` in the host's Secrets settings.
5. Test script generation, voice generation, MP4 playback and download.

Free hosting has limitations and can sleep or reset temporary files. Do not promise permanent storage or production-grade availability from a free instance.

## Before public launch
Add authentication, rate limits, cost caps, privacy policy, terms, abuse protection, storage for finished videos, and payment handling. Never expose API keys in frontend code. Add a separate video-generation provider only after testing its current pricing and commercial-use terms.
