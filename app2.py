import streamlit as st
import json
import tempfile
import os
from docx import Document
from datetime import datetime
from openai import OpenAI
import numpy as np
from scipy.io.wavfile import write

# Configuration page
st.set_page_config(page_title="Évaluation Médicale IA", page_icon="🧠")
st.title("Évaluation Médicale IA Automatisée")

# Barre latérale pour les identifiants OpenAI
with st.sidebar:
    st.header("🔐 Identifiants OpenAI")
    openai_api_key = st.text_input("Clé API OpenAI", type="password")
    openai_org = st.text_input("ID Organisation", help="ex: org-xxxxx")
    openai_project = st.text_input("ID Projet", help="ex: proj_xxxx")

    if st.button("🧹 Réinitialiser la session"):
        st.session_state.transcript = ""
        st.session_state.evaluation = ""
        st.session_state.student_id = ""
        st.experimental_rerun()

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

# 🎙️ Enregistrement HTML5 avec barre de son
def recorder_html():
    return """
    <script>
    let mediaRecorder;
    let audioChunks = [];
    let audioContext;
    let analyser;
    let dataArray;
    let animationId;

    function startRecording() {
        navigator.mediaDevices.getUserMedia({ audio: true }).then(stream => {
            audioContext = new AudioContext();
            const source = audioContext.createMediaStreamSource(stream);
            analyser = audioContext.createAnalyser();
            source.connect(analyser);
            analyser.fftSize = 256;
            const bufferLength = analyser.frequencyBinCount;
            dataArray = new Uint8Array(bufferLength);

            const canvas = document.getElementById("visualizer");
            const canvasCtx = canvas.getContext("2d");
            canvasCtx.clearRect(0, 0, canvas.width, canvas.height);

            function draw() {
                animationId = requestAnimationFrame(draw);
                analyser.getByteFrequencyData(dataArray);

                canvasCtx.fillStyle = 'rgb(255, 255, 255)';
                canvasCtx.fillRect(0, 0, canvas.width, canvas.height);

                const barWidth = (canvas.width / bufferLength) * 2.5;
                let barHeight;
                let x = 0;

                for(let i = 0; i < bufferLength; i++) {
                    barHeight = dataArray[i];
                    canvasCtx.fillStyle = 'rgb(' + (barHeight+100) + ',50,50)';
                    canvasCtx.fillRect(x, canvas.height - barHeight/2, barWidth, barHeight/2);
                    x += barWidth + 1;
                }
            }

            draw();

            mediaRecorder = new MediaRecorder(stream);
            mediaRecorder.start();
            audioChunks = [];
            mediaRecorder.addEventListener("dataavailable", event => {
                audioChunks.push(event.data);
            });

            mediaRecorder.addEventListener("stop", () => {
                cancelAnimationFrame(animationId);
                const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
                const audioUrl = URL.createObjectURL(audioBlob);
                const uploadInput = document.getElementById("upload_input");
                const file = new File([audioBlob], "reponse_etudiant.wav");
                const dt = new DataTransfer();
                dt.items.add(file);
                uploadInput.files = dt.files;
                document.getElementById("download").href = audioUrl;
                document.getElementById("download").style.display = 'block';
            });
        });
    }

    function stopRecording() {
        if (mediaRecorder) mediaRecorder.stop();
    }
    </script>
    <button onclick="startRecording()">🎙️ Démarrer l'enregistrement</button>
    <button onclick="stopRecording()">⏹️ Arrêter</button>
    <br/><canvas id="visualizer" width="300" height="100" style="margin-top:10px; border:1px solid #ccc;"></canvas>
    <a id="download" style="display:none; margin-top:10px" download="reponse_etudiant.wav">📥 Télécharger</a>
    <input type="file" id="upload_input" name="audio" style="display:none" />
    """

st.subheader("🎧 Enregistrement de l'étudiant")
st.components.v1.html(recorder_html(), height=220)

# 📥 Téléverser l'enregistrement manuel ou généré automatiquement
audio_file = st.file_uploader("📤 Charger l'enregistrement généré ci-dessus ou un autre fichier (.wav, .mp3, .m4a)", type=["wav", "mp3", "m4a"])

if audio_file and client and st.button("Transcription"):
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
        st.success("✅ Transcription réussie")
    except Exception as e:
        st.error(f"❌ Erreur : {e}")

if st.session_state.transcript:
    st.text_area("📝 Texte transcrit :", value=st.session_state.transcript, height=200)

# Évaluation 
if st.button("🧠 Évaluer la réponse"):
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
        with st.spinner("Réflexion..."):
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

    note_eval1 = st.text_input("✏️ Note de l'évaluateur 1", help="Sur 20")
    note_eval2 = st.text_input("✏️ Note de l'évaluateur 2", help="Sur 20")

    if st.download_button("⬇️ Télécharger le résultat (CSV)",
                          data=f"id,date,transcription,evaluation\n{student_id},{datetime.now().isoformat()},{st.session_state.transcript},{st.session_state.evaluation}",
                          file_name=f"Evaluation_{student_id}.csv",
                          mime="text/csv"):
        st.success("Export CSV généré ✅")
