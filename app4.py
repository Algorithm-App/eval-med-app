# Évaluation Médicale IA - Fusion des versions pro et audio

import streamlit as st
import json
import sqlite3
import hashlib
import tempfile
import os
from datetime import datetime
from openai import OpenAI
from werkzeug.utils import secure_filename
from pydantic import BaseModel, ValidationError
import pandas as pd
import re

# ---------------------------
# CONFIGURATION
# ---------------------------
AUDIO_DIR = "audios"
os.makedirs(AUDIO_DIR, exist_ok=True)
DB_PATH = "evaluations.db"

st.set_page_config(
    page_title="Évaluation Médicale IA",
    page_icon="🧠",
    layout="wide"
)

st.title("📋 Évaluation ECOS par Intelligence Artificielle")

# ---------------------------
# BASE DE DONNÉES
# ---------------------------
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('''
        CREATE TABLE IF NOT EXISTS etudiants (
            id_etudiant TEXT PRIMARY KEY,
            date_evaluation DATETIME,
            hash_identification TEXT
        )''')

        c.execute('''
        CREATE TABLE IF NOT EXISTS evaluations_ia (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_etudiant TEXT,
            critere TEXT,
            score REAL,
            justification TEXT,
            synthese REAL,
            prise_en_charge REAL,
            note_finale REAL,
            commentaire TEXT,
            FOREIGN KEY(id_etudiant) REFERENCES etudiants(id_etudiant)
        )''')

        c.execute('''
        CREATE TABLE IF NOT EXISTS evaluations_humaines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_etudiant TEXT,
            eval1 REAL,
            eval2 REAL,
            timestamp DATETIME,
            FOREIGN KEY(id_etudiant) REFERENCES etudiants(id_etudiant)
        )''')
        conn.commit()

init_db()

# ---------------------------
# VALIDATION
# ---------------------------
class EvaluationResult(BaseModel):
    notes: list[dict]
    synthese: float
    prise_en_charge: float
    note_finale: float
    commentaire: str

# ---------------------------
# OUTILS
# ---------------------------
def hash_identification(raw_id):
    return hashlib.sha256(raw_id.encode()).hexdigest()

def safe_filename(student_id: str) -> str:
    return secure_filename(f"student_{student_id}")

# ---------------------------
# SIDEBAR
# ---------------------------
def sidebar():
    with st.sidebar:
        st.header("🔐 OpenAI")
        api_key = st.text_input("Clé API", type="password")
        org = st.text_input("Organisation")
        project = st.text_input("Projet")

        st.header("🛠️ Données")
        if st.button("🗑️ Purger les données"):
            st.session_state.confirm_purge = True

        if st.session_state.get("confirm_purge"):
            if st.checkbox("✅ Confirmer suppression"):
                with sqlite3.connect(DB_PATH) as conn:
                    conn.execute("DELETE FROM evaluations_ia")
                    conn.execute("DELETE FROM evaluations_humaines")
                    conn.execute("DELETE FROM etudiants")
                    st.success("Toutes les données ont été supprimées.")
                    st.session_state.confirm_purge = False

        st.download_button("⬇️ Exporter les évaluations",
                           data=pd.read_sql("SELECT * FROM evaluations_ia", sqlite3.connect(DB_PATH)).to_csv(),
                           file_name="evaluations.csv")

    return api_key, org, project

# ---------------------------
# ENREGISTREMENT AUDIO HTML5
# ---------------------------
def audio_recorder_html(student_id):
    html = f"""
    <script>
    let mediaRecorder;
    let audioChunks = [];
    let maxDuration = 480000;
    let timerInterval;

    function startRecording() {{
        navigator.mediaDevices.getUserMedia({{ audio: true }}).then(stream => {{
            mediaRecorder = new MediaRecorder(stream);
            mediaRecorder.start();
            audioChunks = [];

            mediaRecorder.addEventListener("dataavailable", event => {{
                audioChunks.push(event.data);
            }});

            timerInterval = setTimeout(stopRecording, maxDuration);

            mediaRecorder.addEventListener("stop", () => {{
                clearTimeout(timerInterval);
                const audioBlob = new Blob(audioChunks, {{ type: 'audio/wav' }});
                const audioUrl = URL.createObjectURL(audioBlob);
                const downloadLink = document.getElementById("download");
                downloadLink.href = audioUrl;
                downloadLink.download = "audio_{student_id}.wav";
                downloadLink.style.display = "block";
            }});
        }});
    }}

    function stopRecording() {{
        if (mediaRecorder && mediaRecorder.state !== "inactive") mediaRecorder.stop();
    }}
    </script>
    <button onclick="startRecording()">🎙️ Démarrer</button>
    <button onclick="stopRecording()">⏹️ Arrêter</button>
    <a id="download" style="display:none; margin-top:10px">📥 Télécharger</a>
    """
    st.components.v1.html(html, height=150)

# ---------------------------
# GPT-4 ÉVALUATION
# ---------------------------
def evaluate_with_gpt4(client: OpenAI, prompt: str) -> dict:
    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=1500
        )
        result_json = response.choices[0].message.content.strip()
        json_match = re.search(r"\{.*\}", result_json, re.DOTALL)
        if not json_match:
            raise ValueError("Format JSON manquant")
        parsed = json.loads(json_match.group())
        validated = EvaluationResult(**parsed)
        return validated.dict()
    except Exception as e:
        st.error(f"Erreur GPT/JSON : {str(e)}")
        st.stop()

# ---------------------------
# MAIN
# ---------------------------
def main():
    api_key, org, project = sidebar()

    student_id = st.text_input("🆔 Identifiant étudiant")
    if not student_id:
        st.stop()

    clinical_case = st.file_uploader("📄 Cas clinique (TXT)", type=["txt"])
    rubric_file = st.file_uploader("📋 Grille d'évaluation (JSON)", type=["json"])

    with st.expander("🎙️ Enregistrement audio"):
        audio_recorder_html(student_id)
        audio_file = st.file_uploader("📤 Audio", type=["wav", "mp3"])

    if st.button("🧠 Évaluer") and all([api_key, org, project, audio_file, clinical_case, rubric_file]):
        with st.spinner("Analyse en cours..."):
            client = OpenAI(api_key=api_key, organization=org, project=project)

            clinical_text = clinical_case.read().decode("utf-8")
            rubric = json.load(rubric_file).get("grille_observation", [])

            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                tmp.write(audio_file.read())
                with open(tmp.name, "rb") as f:
                    transcript = client.audio.transcriptions.create(
                        model="whisper-1",
                        file=f,
                        language="fr"
                    )
            transcript_text = transcript.text

            prompt = f"""
            Tu es un examinateur médical. Évalue l'étudiant {student_id}.
            Cas : {clinical_text}
            Réponse : {transcript_text}
            Grille : {json.dumps(rubric, ensure_ascii=False)}

            Donne un JSON strict avec : notes[], synthese, prise_en_charge, note_finale, commentaire.
            """
            result = evaluate_with_gpt4(client, prompt)

            st.subheader(f"📊 Note finale : {result['note_finale']} / 20")
            for crit in result["notes"]:
                st.markdown(f"- **{crit['critère']}** : {crit['score']}\n> _{crit['justification']}_")

            eval1 = st.slider("Évaluateur 1", 0.0, 20.0, step=0.5)
            eval2 = st.slider("Évaluateur 2", 0.0, 20.0, step=0.5)

            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("INSERT OR IGNORE INTO etudiants VALUES (?, ?, ?)",
                             (student_id, datetime.now(), hash_identification(student_id)))
                for note in result["notes"]:
                    conn.execute("""
                        INSERT INTO evaluations_ia VALUES
                        (NULL, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        student_id, note["critère"], note["score"], note["justification"],
                        result["synthese"], result["prise_en_charge"],
                        result["note_finale"], result["commentaire"]
                    ))
                conn.execute("INSERT INTO evaluations_humaines VALUES (NULL, ?, ?, ?, ?)",
                             (student_id, eval1, eval2, datetime.now()))
                conn.commit()
            st.success("✅ Résultats enregistrés")

if __name__ == "__main__":
    main()
