import streamlit as st
import json
import tempfile
import os
from docx import Document
from datetime import datetime
from openai import OpenAI
from streamlit_webrtc import webrtc_streamer, AudioProcessorBase, WebRtcMode
import av
import numpy as np
import queue
from scipy.io.wavfile import write

# Configuration page
st.set_page_config(page_title="Évaluation Médicale IA", page_icon="🧠")
st.title("🧠 Évaluation Médicale IA Automatisée")

# API KEY + ORG + PROJECT
openai_api_key = st.text_input("🔐 Clé API OpenAI (Whisper + GPT-4)", type="password")
openai_org = st.text_input("🏢 ID d'organisation OpenAI (org-...)")
openai_project = st.text_input("📁 ID de projet OpenAI (proj_...)")

client = None
if openai_api_key and openai_org and openai_project:
    client = OpenAI(
        api_key=openai_api_key,
        organization=openai_org,
        project=openai_project
    )

# Initialiser les states
if "transcript" not in st.session_state:
    st.session_state.transcript = ""
if "evaluation" not in st.session_state:
    st.session_state.evaluation = ""

# ID étudiant
student_id = st.text_input("🆔 Identifiant de l'étudiant")

# Cas clinique
clinical_file = st.file_uploader("📄 Charger le cas clinique (.txt)", type=["txt"])
clinical_text = ""
if clinical_file is not None:
    clinical_text = clinical_file.read().decode("utf-8")
    with st.expander("📘 Cas clinique", expanded=True):
        st.markdown(f"```\n{clinical_text}\n```)" )

# Grille d'évaluation
rubric_docx = st.file_uploader("📋 Charger la grille d'évaluation (.docx)", type=["docx"])
rubric = []
if rubric_docx is not None:
    doc = Document(rubric_docx)
    for para in doc.paragraphs:
        text = para.text.strip()
        if text and any(char.isdigit() for char in text[:2]):
            parts = text.split(" ", 1)
            if len(parts) == 2:
                points = 2 if "2" in parts[0] else 1
                rubric.append({"critère": parts[1], "points": points})
    with st.expander("📊 Grille d'évaluation", expanded=False):
        st.json(rubric)

# 🎙️ Réponse orale - WebRTC
st.subheader("🎤 Enregistrement direct (WebRTC)")

class AudioProcessor(AudioProcessorBase):
    def __init__(self) -> None:
        self.recorded_frames = []
        self.level = 0

    def recv(self, frame: av.AudioFrame) -> av.AudioFrame:
        pcm = frame.to_ndarray()
        self.level = min(np.linalg.norm(pcm) / 10000, 1.0)
        self.recorded_frames.append(pcm)
        return frame

    def get_wav(self):
        if self.recorded_frames:
            audio = np.concatenate(self.recorded_frames, axis=1).flatten()
            tmp_path = tempfile.mktemp(suffix=".wav")
            write(tmp_path, 48000, audio)
            return tmp_path
        return None

ctx = webrtc_streamer(
    key="audio",
    mode=WebRtcMode.SENDONLY,
    audio_receiver_size=1024,
    audio_processor_factory=AudioProcessor,
)

if ctx.audio_processor:
    st.progress(ctx.audio_processor.level)
    if st.button("🔈 Transcrire l'enregistrement WebRTC"):
        wav_path = ctx.audio_processor.get_wav()
        if wav_path and client:
            with open(wav_path, "rb") as f:
                try:
                    transcript = client.audio.transcriptions.create(
                        model="whisper-1",
                        file=f,
                        language="fr"
                    )
                    st.session_state.transcript = transcript.text
                    st.success("✅ Transcription réussie (WebRTC)")
                except Exception as e:
                    st.error(f"❌ Erreur Whisper : {e}")

# 📥 Téléchargement manuel fichier audio
st.subheader("📁 Ou charger un fichier audio")
audio_file = st.file_uploader("Charger un fichier (.mp3, .wav, .m4a)", type=["mp3", "wav", "m4a"])

if audio_file and client and st.button("🎧 Transcrire le fichier audio"):
    ext = os.path.splitext(audio_file.name)[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp_file:
        tmp_file.write(audio_file.read())
        tmp_path = tmp_file.name
    try:
        with open(tmp_path, "rb") as f:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                language="fr"
            )
        st.session_state.transcript = transcript.text
        os.remove(tmp_path)
        st.success("✅ Transcription réussie (fichier audio)")
    except Exception as e:
        st.error(f"❌ Erreur : {e}")

if st.session_state.transcript:
    st.text_area("📝 Texte transcrit :", value=st.session_state.transcript, height=200)

# Évaluation GPT-4
if st.button("🧠 Évaluer la réponse avec GPT-4"):
    if not (clinical_text and rubric and st.session_state.transcript):
        st.warning("Merci de remplir tous les champs requis avant l'évaluation.")
    elif not client:
        st.warning("Veuillez entrer votre clé API OpenAI.")
    else:
        prompt = f"""
Tu es examinateur médical. Voici :
- ID étudiant : {student_id}
- Cas clinique : {clinical_text}
- Réponse de l'étudiant : {st.session_state.transcript}
- Grille d'évaluation : {json.dumps(rubric, ensure_ascii=False)}

Ta tâche :
1. Évalue chaque critère individuellement avec justification.
2. Donne un score total (sur 18).
3. Évalue la qualité de la synthèse (0 à 1) et de la prise en charge (0 à 1).
4. Donne un score final sur 20.
5. Rédige un commentaire global (max 5 lignes).
"""
        with st.spinner("GPT-4 réfléchit..."):
            try:
                response = client.chat.completions.create(
                    model="gpt-4",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3
                )
                st.session_state.evaluation = response.choices[0].message.content
                st.success("✅ Évaluation terminée")
            except Exception as e:
                st.error(f"Erreur GPT-4 : {e}")

if st.session_state.evaluation:
    st.markdown(f"### 🧾 Résultat de l'évaluation de l'étudiant **{student_id}**")
    st.write(st.session_state.evaluation)
    st.markdown("### 📝 Transcription de l'étudiant")
    st.text_area("Texte transcrit :", value=st.session_state.transcript, height=200)

    if st.download_button("⬇️ Télécharger le résultat (CSV)",
                          data=f"id,date,transcription,evaluation\n{student_id},{datetime.now().isoformat()},{st.session_state.transcript},{st.session_state.evaluation}",
                          file_name=f"Evaluation_{student_id}.csv",
                          mime="text/csv"):
        st.success("Export CSV généré ✅")
