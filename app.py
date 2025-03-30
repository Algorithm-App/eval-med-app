import streamlit as st
import json
import openai
import tempfile
from streamlit_webrtc import webrtc_streamer, AudioProcessorBase
import av
import os

st.set_page_config(page_title="Évaluation Médicale IA", page_icon="🧠")
st.title("🧠 Application d'Évaluation Médicale Automatisée avec GPT-4 et Transcription Audio")

st.markdown("""
Cette application permet à l'opérateur de :
1. Charger un cas clinique
2. Charger une grille d'évaluation (format JSON)
3. Enregistrer ou charger la réponse orale de l'étudiant
4. Transcrire automatiquement l'audio avec Whisper (OpenAI)
5. Évaluer la réponse avec GPT-4
""")

# 1. Cas clinique
tab1, tab2 = st.tabs(["📄 Cas clinique", "📋 Grille d'évaluation"])

with tab1:
    clinical_file = st.file_uploader("Charger le cas clinique (.txt ou .docx)", type=["txt"])
    clinical_text = ""
    if clinical_file is not None:
        clinical_text = clinical_file.read().decode("utf-8")
        st.text_area("Contenu du cas clinique :", value=clinical_text, height=300)

with tab2:
    rubric_file = st.file_uploader("Charger la grille d'évaluation (.json)", type=["json"])
    rubric = None
    if rubric_file is not None:
        rubric = json.load(rubric_file)
        st.markdown("**Grille chargée :**")
        st.json(rubric)

# 2. Clé API OpenAI
openai_api_key = st.text_input("Clé API OpenAI (GPT-4 & Whisper)", type="password")

# 3. Audio de l'étudiant
st.markdown("## 🎤 Réponse orale de l'étudiant")
audio_file = st.file_uploader("Charger un fichier audio (.mp3, .wav, .m4a)", type=["mp3", "wav", "m4a"])

st.markdown("### 🔴 Ou enregistrer directement depuis le navigateur :")
class AudioProcessor(AudioProcessorBase):
    def recv(self, frame: av.AudioFrame) -> av.AudioFrame:
        return frame

webrtc_ctx = webrtc_streamer(
    key="audio",
    mode="SENDONLY",
    in_audio=True,
    audio_processor_factory=AudioProcessor,
    media_stream_constraints={"audio": True, "video": False},
    async_processing=True,
)

recorded_audio_path = None
student_response = ""

if audio_file and openai_api_key and st.button("🔈 Transcrire l'audio téléchargé"):
    with st.spinner("Transcription en cours..."):
        openai.api_key = openai_api_key
        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            tmp_file.write(audio_file.read())
            tmp_path = tmp_file.name

        try:
            audio_file_for_api = open(tmp_path, "rb")
            transcript = openai.Audio.transcribe("whisper-1", audio_file_for_api, language="fr")
            student_response = transcript["text"]
            st.success("Transcription terminée ✅")
            st.text_area("Texte transcrit :", student_response, height=250)
        except Exception as e:
            st.error(f"Erreur lors de la transcription : {e}")

# 4. Évaluation GPT-4
if st.button("🧠 Générer l'évaluation avec GPT-4"):
    if not (clinical_text and rubric and student_response):
        st.warning("Merci de charger le cas, la grille et la réponse de l'étudiant.")
    elif not openai_api_key:
        st.warning("Merci d'entrer votre clé API OpenAI.")
    else:
        prompt = f"""
Tu es examinateur médical. Voici :
- Cas clinique : {clinical_text}
- Réponse de l'étudiant : {student_response}
- Grille d'évaluation : {json.dumps(rubric, ensure_ascii=False)}

Ta tâche :
1. Évalue chaque critère individuellement avec justification.
2. Donne un score total (sur 18).
3. Rédige un commentaire global concis (max 5 lignes).
"""

        with st.spinner("Évaluation en cours avec GPT-4..."):
            openai.api_key = openai_api_key
            try:
                response = openai.ChatCompletion.create(
                    model="gpt-4",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3
                )
                result = response['choices'][0]['message']['content']
                st.markdown("### ✅ Résultat de l'évaluation")
                st.write(result)
            except Exception as e:
                st.error(f"Erreur lors de l'appel à l'API OpenAI : {e}")
