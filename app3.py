import streamlit as st
import json
import tempfile
import os
import sqlite3
from docx import Document
from datetime import datetime
from openai import OpenAI
import pandas as pd

# Configuration de la page
st.set_page_config(page_title="Évaluation Médicale IA", page_icon="🧠")
st.title("Évaluation ECOS IA")

# Création dossier audios
AUDIO_DIR = "audios"
os.makedirs(AUDIO_DIR, exist_ok=True)

# Connexion base SQLite
DB_PATH = "evaluation.db"
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute('''
CREATE TABLE IF NOT EXISTS evaluations (
    id_etudiant TEXT PRIMARY KEY,
    note_ia REAL,
    eval1 REAL,
    eval2 REAL
)
''')
conn.commit()



# Barre latérale : identifiants
with st.sidebar:
    st.header("🔐 Identifiants OpenAI")
    openai_api_key = st.text_input("Clé API OpenAI", type="password")
    openai_org = st.text_input("ID Organisation", help="ex: org-xxxxx")
    openai_project = st.text_input("ID Projet", help="ex: proj_xxxx")
    if st.button("🧹 Réinitialiser la session"):
        for key in ["transcript", "result_json", "student_id"]:
            if key in st.session_state:
                del st.session_state[key]
        st.success("✅ Session réinitialisée. Saisis un nouvel étudiant.")

with st.sidebar:
    st.markdown("---")
    st.header("⚠️ Administration de la base SQLite")

    if st.button("🗑️ Effacer toutes les données"):
        st.session_state["confirm_delete"] = True

    if st.session_state.get("confirm_delete"):
        confirm = st.checkbox("Je confirme vouloir effacer toutes les données définitivement.")
        if confirm and st.button("✅ Confirmer la suppression"):
            try:
                c.execute("DELETE FROM evaluations")
                c.execute("DELETE FROM etudiants")
                c.execute("DELETE FROM evaluateurs")
                conn.commit()
                st.success("✅ Toutes les données ont été effacées avec succès.")
                st.session_state["confirm_delete"] = False  # réinitialisation
                st.rerun()
            except Exception as e:
                st.error(f"❌ Erreur lors de l'effacement : {e}")



# OpenAI client
client = None
if openai_api_key and openai_org and openai_project:
    client = OpenAI(api_key=openai_api_key, organization=openai_org, project=openai_project)

# Initialiser les states
st.session_state.setdefault("transcript", "")
st.session_state.setdefault("result_json", "")
st.session_state.setdefault("student_id", "")

# ID étudiant
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

# 🎙️ Enregistrement audio (HTML5)

st.markdown("## 🎤 Enregistrement audio avec Chronomètre (max 8 min)")

# Injection de l'ID étudiant directement dans le HTML
html_code = f"""
<script>
let mediaRecorder;
let audioChunks = [];
let audioContext;
let analyser;
let dataArray;
let animationId;
let timerInterval;
let startTime;
let maxDuration = 480000; // 8 minutes en millisecondes

function startRecording() {{
    navigator.mediaDevices.getUserMedia({{ audio: true }}).then(stream => {{
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

        function draw() {{
            animationId = requestAnimationFrame(draw);
            analyser.getByteFrequencyData(dataArray);
            canvasCtx.fillStyle = 'rgb(255, 255, 255)';
            canvasCtx.fillRect(0, 0, canvas.width, canvas.height);
            const barWidth = (canvas.width / bufferLength) * 2.5;
            let barHeight;
            let x = 0;
            for(let i = 0; i < bufferLength; i++) {{
                barHeight = dataArray[i];
                canvasCtx.fillStyle = 'rgb(' + (barHeight+100) + ',50,50)';
                canvasCtx.fillRect(x, canvas.height - barHeight/2, barWidth, barHeight/2);
                x += barWidth + 1;
            }}
        }}

        draw();

        mediaRecorder = new MediaRecorder(stream);
        mediaRecorder.start();
        audioChunks = [];
        mediaRecorder.addEventListener("dataavailable", event => {{
            audioChunks.push(event.data);
        }});

        // Chronomètre
        startTime = Date.now();
        timerInterval = setInterval(() => {{
            const elapsedTime = Date.now() - startTime;
            const minutes = String(Math.floor(elapsedTime / 60000)).padStart(2, '0');
            const seconds = String(Math.floor((elapsedTime % 60000) / 1000)).padStart(2, '0');
            document.getElementById("timer").innerText = `${{minutes}}:${{seconds}}`;

            if (elapsedTime >= maxDuration) {{
                stopRecording();
            }}
        }}, 1000);

        mediaRecorder.addEventListener("stop", () => {{
            clearInterval(timerInterval);
            cancelAnimationFrame(animationId);
            const audioBlob = new Blob(audioChunks, {{ type: 'audio/wav' }});
            const audioUrl = URL.createObjectURL(audioBlob);
            const downloadLink = document.getElementById("download");
            downloadLink.href = audioUrl;
            downloadLink.download = "audio_{student_id}.wav"; // Nom dynamique ici
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
<div style="margin-top:10px;font-size:20px;">
    ⏱️ Durée : <span id="timer">00:00</span> / 08:00
</div>
<canvas id="visualizer" width="300" height="100" style="margin-top:10px; border:1px solid #ccc;"></canvas>
<a id="download" style="display:none; margin-top:10px">📥 Télécharger l'enregistrement</a>
"""

st.components.v1.html(html_code, height=350)


# 📤 Upload audio manuel
audio_file = st.file_uploader("📤 Charger un fichier audio (.wav, .mp3, .m4a)", type=["wav", "mp3", "m4a"])
if audio_file and client and st.button("🔈 Transcrire avec Whisper"):
    ext = os.path.splitext(audio_file.name)[1]
    save_path = os.path.join(AUDIO_DIR, f"{student_id}{ext}")
    with open(save_path, "wb") as f_out:
        f_out.write(audio_file.read())
    try:
        with open(save_path, "rb") as f:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                language="fr"
            )
        st.session_state.transcript = transcript.text
        st.success("✅ Transcription réussie")
    except Exception as e:
        st.error(f"Erreur Whisper : {e}")

if st.session_state.transcript:
    st.text_area("📝 Transcription", value=st.session_state.transcript, height=200)

# GPT-4 : évaluation
if st.button("🧠 Évaluer avec GPT-4 (JSON)"):
    if not (clinical_text and rubric and st.session_state.transcript):
        st.warning("⚠️ Remplis tous les champs nécessaires.")
    else:
        prompt = f"""
        Tu es un examinateur médical rigoureux et impartial.

        Voici les éléments à considérer :
        - ID étudiant : {student_id}
        - Cas clinique : {clinical_text}
        - Réponse de l'étudiant : {st.session_state.transcript}
        - Grille d'évaluation : {json.dumps(rubric, ensure_ascii=False)}

        Ta mission est d'évaluer la réponse orale de l'étudiant selon les règles suivantes :

        1. Pour chaque critère de la grille, indique clairement s'il est observé (score positif) ou non observé (score nul), en justifiant uniquement à partir des propos précis de l'étudiant.
        2. Calcule le score total sur 18 points selon la grille fournie.
        3. Attribue une note de synthèse (0 à 1) et une note de prise en charge (0 à 1).
        4. Calcule une note finale sur 20.
        5. Fournis un commentaire global justifiant la note finale (maximum 5 lignes).

        ⚠️ N'invente aucune information absente de la réponse de l'étudiant. Si une information n'est pas explicitement mentionnée, considère-la comme absente.

        Retourne STRICTEMENT et EXCLUSIVEMENT un JSON conforme à ce format :
        {{
          "notes": [{{"critère": "...", "score": 1, "justification": "..."}}],
          "synthese": 0.5,
          "prise_en_charge": 1.0,
          "note_finale": 19,
          "commentaire": "Très bonne réponse."
        }}

        Aucun texte supplémentaire hors du JSON ne doit être ajouté.
        """

        try:
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=1000
            )

            result_json = response.choices[0].message.content.strip()
            result = json.loads(result_json)

            # Afficher la note finale de l'IA
            st.subheader(f"🧠 Note finale GPT-4 : {result['note_finale']} / 20")

            # Stockage temporaire dans session_state
            st.session_state['note_ia'] = result['note_finale']

            # Champs pour notes évaluateurs
            eval1 = st.number_input("Note évaluateur 1 (sur 20)", 0.0, 20.0, step=0.25)
            eval2 = st.number_input("Note évaluateur 2 (sur 20)", 0.0, 20.0, step=0.25)

            # Bouton de sauvegarde en SQLite
            if st.button("💾 Sauvegarder les résultats"):
                c.execute("""
                    INSERT OR REPLACE INTO evaluations (id_etudiant, note_ia, eval1, eval2)
                    VALUES (?, ?, ?, ?)
                """, (student_id, result['note_finale'], eval1, eval2))
                conn.commit()
                st.success("✅ Résultats enregistrés avec succès dans SQLite !")

        except json.JSONDecodeError:
            st.error("❌ GPT-4 n'a pas retourné un JSON valide. Réessaie.")
        except Exception as e:
            st.error(f"❌ Erreur GPT-4 : {e}")
            

# Résultat IA + sauvegarde
if st.session_state.result_json:
    try:
        result = json.loads(st.session_state.result_json)
        st.subheader("📊 Résultat IA :")
        st.json(result)

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

# Historique
st.markdown("### 🧾 Historique des évaluations")
if st.checkbox("📂 Afficher le tableau des résultats"):
    df_eval = pd.read_sql_query("SELECT * FROM evaluations", conn)
    st.dataframe(df_eval)
    st.download_button("⬇️ Télécharger les évaluations", df_eval.to_csv(index=False), file_name="evaluations.csv")
