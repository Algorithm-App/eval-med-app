import streamlit as st
import json
import openai
import tempfile
from docx import Document
from streamlit.components.v1 import html

st.set_page_config(page_title="Évaluation Médicale IA", page_icon="🧠")
st.title("🧠 Évaluation Médicale IA Automatisée")

st.markdown("""
Cette page vous permet de :
1. Saisir l'identité de l'étudiant
2. Charger un cas clinique (.txt)
3. Charger une grille de réponse (.docx)
4. Enregistrer ou charger la réponse orale de l'étudiant
5. Transcrire automatiquement la réponse avec Whisper (OpenAI)
6. Évaluer la réponse avec GPT-4
""")

# 1. ID Étudiant
student_id = st.text_input("🆔 Identifiant de l'étudiant")

# 2. Cas clinique
clinical_file = st.file_uploader("📄 Charger le cas clinique (.txt)", type=["txt"])
clinical_text = ""
if clinical_file is not None:
    clinical_text = clinical_file.read().decode("utf-8")
    st.text_area("Contenu du cas clinique :", value=clinical_text, height=200)

# 3. Grille de réponse
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
    st.json(rubric)

# 4. Clé API OpenAI
openai_api_key = st.text_input("🔐 Clé API OpenAI (Whisper + GPT-4)", type="password")

# 5. Audio de l'étudiant
st.markdown("## 🎤 Réponse orale de l'étudiant")
audio_file = st.file_uploader("📤 Charger un fichier audio (.mp3, .wav, .m4a)", type=["mp3", "wav", "m4a"])

st.markdown("### 🎙️ Ou enregistrer directement depuis le navigateur :")
html('''
<script>
let mediaRecorder;
let audioChunks = [];

function startRecording() {
  navigator.mediaDevices.getUserMedia({ audio: true })
    .then(stream => {
      mediaRecorder = new MediaRecorder(stream);
      mediaRecorder.start();

      mediaRecorder.addEventListener("dataavailable", event => {
        audioChunks.push(event.data);
      });

      mediaRecorder.addEventListener("stop", () => {
        const audioBlob = new Blob(audioChunks);
        const audioUrl = URL.createObjectURL(audioBlob);
        const downloadLink = document.getElementById("download");
        downloadLink.href = audioUrl;
        downloadLink.download = "reponse_etudiant.wav";
        downloadLink.style.display = "block";
      });
    });
}

function stopRecording() {
  mediaRecorder.stop();
}
</script>
<button onclick="startRecording()">🎙️ Démarrer l'enregistrement</button>
<button onclick="stopRecording()">⏹️ Arrêter l'enregistrement</button>
<a id="download" style="display:none; margin-top:10px">📥 Télécharger l'enregistrement</a>
''', height=200)

student_response = ""
if audio_file and openai_api_key and st.button("🔈 Transcrire l'audio"):
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
            st.text_area("📝 Texte transcrit :", student_response, height=200)
        except Exception as e:
            st.error(f"Erreur lors de la transcription : {e}")

# 6. Évaluation GPT-4
if st.button("🧠 Évaluer avec GPT-4"):
    if not (clinical_text and rubric and student_response):
        st.warning("Merci de remplir tous les champs : cas, grille et transcription.")
    elif not openai_api_key:
        st.warning("Merci de fournir une clé API OpenAI valide.")
    else:
        prompt = f"""
Tu es examinateur médical. Voici :
- ID étudiant : {student_id}
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
                st.markdown(f"### ✅ Résultat de l'évaluation de l'étudiant {student_id}")
                st.write(result)
            except Exception as e:
                st.error(f"Erreur GPT-4 : {e}")
