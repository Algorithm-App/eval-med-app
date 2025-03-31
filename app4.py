import streamlit as st
import json
import tempfile
import os
import sqlite3
from docx import Document
from datetime import datetime
from openai import OpenAI
import pandas as pd
import re

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
rubric_json = st.file_uploader("📋 Charger la grille d'évaluation (.json)", type=["json"])

rubric = []
if rubric_json is not None:
    try:
        rubric_data = json.load(rubric_json)
        rubric = rubric_data.get("grille_observation", [])
        synthese_options = rubric_data.get("synthese", {})
        prise_en_charge_options = rubric_data.get("prise_en_charge", {})

        with st.expander("📊 Grille d'évaluation (critères)", expanded=False):
            st.json(rubric)

        with st.expander("📚 Barème - Synthèse & Prise en charge", expanded=False):
            st.markdown("### Synthèse")
            for k, v in synthese_options.items():
                st.markdown(f"- **{k}** : {v}")
            st.markdown("### Prise en charge")
            for k, v in prise_en_charge_options.items():
                st.markdown(f"- **{k}** : {v}")

    except Exception as e:
        st.error(f"Erreur lors du chargement du fichier JSON : {e}")

# GPT-4 : évaluation
if st.button("🧠 Évaluation"):
    if not (clinical_text and rubric and st.session_state.transcript):
        st.warning("⚠️ Remplis tous les champs nécessaires.")
    else:
        prompt = f"""
Tu es un examinateur médical rigoureux. Voici :
- ID étudiant : {student_id}
- Cas clinique : {clinical_text}
- Réponse de l'étudiant : {st.session_state.transcript}
- Grille d'évaluation : {json.dumps(rubric, ensure_ascii=False)}

Ta tâche est d'évaluer la réponse de l'étudiant selon les critères suivants :
1. Évalue chaque critère individuellement avec justification sans inventer de données.
2. Donne un score total (sur 18).
3. Évalue la qualité de la synthèse (0 à 1) et de la prise en charge (0 à 1).
4. Donne un score final sur 20.
5. Rédige un commentaire global (maximum 5 lignes).
N'invente jamais d'informations absentes de la réponse de l'étudiant.

Voici un exemple de format JSON strict que tu dois retourner :
```json
{{
  "notes": [
    {{
      "critère": "Recueille les antécédents",
      "score": 1,
      "justification": "L'étudiant a bien mentionné les antécédents familiaux et médicaux."
    }},
    {{
      "critère": "Recherche les signes fonctionnels",
      "score": 0,
      "justification": "L'étudiant n’a pas évoqué les symptômes urinaires."
    }}
  ],
  "synthese": 0.5,
  "prise_en_charge": 1.0,
  "note_finale": 16.5,
  "commentaire": "Bonne réponse globale mais quelques oublis notables."
}}
```
NE RAJOUTE AUCUN AUTRE TEXTE. Retourne uniquement ce JSON.
"""
        try:
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=1500
            )

            result_raw = response.choices[0].message.content.strip()
            json_match = re.search(r"\{.*\}", result_raw, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
            else:
                raise ValueError("Aucun JSON valide détecté dans la réponse.")

            st.subheader(f"🧠 Note finale : {result['note_finale']} / 20")
            st.markdown("### 🧩 Détail des critères évalués par l'IA")
            for critere in result["notes"]:
                st.markdown(f"- **{critere['critère']}** — Score : `{critere['score']}`")
                st.markdown(f"  > _Justification_ : {critere['justification']}")

            st.session_state['note_ia'] = result['note_finale']

            eval1 = st.number_input("Note évaluateur 1 (sur 20)", 0.0, 20.0, step=0.25)
            eval2 = st.number_input("Note évaluateur 2 (sur 20)", 0.0, 20.0, step=0.25)

            if st.button("💾 Sauvegarder les résultats"):
                c.execute("""
                    INSERT OR REPLACE INTO evaluations (id_etudiant, note_ia, eval1, eval2)
                    VALUES (?, ?, ?, ?)
                """, (student_id, result['note_finale'], eval1, eval2))
                conn.commit()
                st.success("✅ Résultats enregistrés avec succès dans SQLite !")

        except Exception as e:
            st.error(f"❌ Erreur GPT-4 ou parsing : {e}")
