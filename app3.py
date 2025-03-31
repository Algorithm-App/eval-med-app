import streamlit as st
import json
import tempfile
import os
import sqlite3
from docx import Document
from datetime import datetime
from openai import OpenAI
import pandas as pd

# Configuration page
st.set_page_config(page_title="Évaluation Médicale IA", page_icon="🧠")
st.title("🧠 Évaluation Médicale IA Automatisée")

# Initialisation de la base SQLite
DB_PATH = "evaluation.db"
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS etudiants (
    id TEXT PRIMARY KEY,
    date_passage TEXT
)''')

c.execute('''CREATE TABLE IF NOT EXISTS evaluations (
    id_etudiant TEXT,
    critere TEXT,
    score INTEGER,
    justification TEXT,
    synthese REAL,
    prise_en_charge REAL,
    note_finale REAL,
    commentaire TEXT
)''')

c.execute('''CREATE TABLE IF NOT EXISTS evaluateurs (
    id_etudiant TEXT,
    eval1 REAL,
    eval2 REAL
)''')

conn.commit()

# Barre latérale pour les identifiants OpenAI
with st.sidebar:
    st.header("🔐 Identifiants OpenAI")
    openai_api_key = st.text_input("Clé API OpenAI", type="password")
    openai_org = st.text_input("ID Organisation", help="ex: org-xxxxx")
    openai_project = st.text_input("ID Projet", help="ex: proj_xxxx")
    if st.button("🧹 Réinitialiser la session"):
        st.session_state.transcript = ""
        st.session_state.result_json = ""
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
st.session_state.setdefault("transcript", "")
st.session_state.setdefault("result_json", "")
st.session_state.setdefault("student_id", "")

# Identifiant de l'étudiant
student_id = st.text_input("🆔 Identifiant de l'étudiant", value=st.session_state.student_id)
st.session_state.student_id = student_id

# Cas clinique
clinical_file = st.file_uploader("📄 Charger le cas clinique (.txt)", type=["txt"])
clinical_text = ""
if clinical_file:
    clinical_text = clinical_file.read().decode("utf-8")
    with st.expander("📘 Cas clinique", expanded=True):
        st.code(clinical_text)

# Grille d’évaluation
rubric_docx = st.file_uploader("📋 Charger la grille d’évaluation (.docx)", type=["docx"])
rubric = []
if rubric_docx:
    doc = Document(rubric_docx)
    for para in doc.paragraphs:
        text = para.text.strip()
        if text and any(char.isdigit() for char in text[:2]):
            parts = text.split(" ", 1)
            if len(parts) == 2:
                points = 2 if "2" in parts[0] else 1
                rubric.append({"critère": parts[1], "points": points})
    with st.expander("📊 Grille d’évaluation"):
        st.json(rubric)

# Audio
audio_file = st.file_uploader("🎤 Charger un fichier audio (.wav, .mp3, .m4a)", type=["wav", "mp3", "m4a"])
if audio_file and client and st.button("🔈 Transcrire avec Whisper"):
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(audio_file.name)[1]) as tmp_file:
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
        st.error(f"Erreur Whisper : {e}")

if st.session_state.transcript:
    st.text_area("📝 Transcription", value=st.session_state.transcript, height=200)

# Évaluation IA en JSON
if st.button("🧠 Évaluer avec GPT-4 (JSON)"):
    if not (clinical_text and rubric and st.session_state.transcript):
        st.warning("⚠️ Remplis tous les champs nécessaires.")
    else:
        prompt = f"""
Tu es un examinateur médical. Voici :
- Cas clinique : {clinical_text}
- Réponse de l’étudiant : {st.session_state.transcript}
- Grille d’évaluation : {json.dumps(rubric, ensure_ascii=False)}

Retourne uniquement un JSON structuré comme ceci :
{{
  "notes": [{{"critère": "...", "score": 1, "justification": "..."}}],
  "synthese": 0.5,
  "prise_en_charge": 1.0,
  "note_finale": 19,
  "commentaire": "Très bonne réponse."
}}

Ne commente rien. Ne donne que le JSON.
"""
        try:
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0
            )
            result_json = response.choices[0].message.content
            st.session_state.result_json = result_json
            st.success("✅ Évaluation réussie")
        except Exception as e:
            st.error(f"Erreur GPT-4 : {e}")

if st.session_state.result_json:
    try:
        result = json.loads(st.session_state.result_json)
        st.subheader("📊 Résultat IA :")
        st.json(result)

        # Notes évaluateurs humains
        eval1 = st.number_input("Note évaluateur 1 (sur 20)", min_value=0.0, max_value=20.0, step=0.25)
        eval2 = st.number_input("Note évaluateur 2 (sur 20)", min_value=0.0, max_value=20.0, step=0.25)

        if st.button("💾 Sauvegarder en base"):
            c.execute("INSERT OR IGNORE INTO etudiants VALUES (?, ?)", (student_id, datetime.now().isoformat()))
            for note in result["notes"]:
                c.execute("""
                INSERT INTO evaluations VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    student_id, note["critère"], note["score"], note["justification"],
                    result.get("synthese", 0), result.get("prise_en_charge", 0),
                    result.get("note_finale", 0), result.get("commentaire", "")
                ))
            c.execute("INSERT OR REPLACE INTO evaluateurs VALUES (?, ?, ?)", (student_id, eval1, eval2))
            conn.commit()
            st.success("✅ Résultats sauvegardés dans la base SQLite.")
    except Exception as e:
        st.error(f"Erreur de parsing JSON : {e}")

# Afficher les étudiants évalués
st.markdown("### 🧾 Historique des évaluations")
if st.checkbox("📂 Afficher le tableau des résultats"):
    df_eval = pd.read_sql_query("SELECT * FROM evaluations", conn)
    st.dataframe(df_eval)
    st.download_button("⬇️ Télécharger toutes les évaluations", df_eval.to_csv(index=False), file_name="evaluations.csv")
