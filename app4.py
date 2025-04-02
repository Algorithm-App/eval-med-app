"""
Évaluation Médicale par IA - Streamlit
Auteur : Votre nom
Version : 2.0
"""

# ---------------------------
# IMPORTS & CONFIGURATION
# ---------------------------
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

# Configuration de la page
st.set_page_config(
    page_title="Évaluation Médicale IA", 
    page_icon="🏥",
    layout="wide"
)

# ---------------------------
# MODÈLES DE VALIDATION
# ---------------------------
class EvaluationResult(BaseModel):
    """Modèle Pydantic pour valider la réponse de GPT-4"""
    notes: list[dict]
    synthese: float 
    prise_en_charge: float
    note_finale: float
    commentaire: str

# ---------------------------
# BASE DE DONNÉES
# ---------------------------
DB_PATH = "evaluations.db"

def init_db():
    """Initialisation sécurisée de la base de données"""
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        
        # Table Étudiants
        c.execute('''
        CREATE TABLE IF NOT EXISTS etudiants (
            id_etudiant TEXT PRIMARY KEY,
            date_evaluation DATETIME,
            hash_identification TEXT
        )''')
        
        # Table Évaluations IA
        c.execute('''
        CREATE TABLE IF NOT EXISTS evaluations_ia (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_etudiant TEXT,
            critère TEXT,
            score REAL,
            justification TEXT,
            synthese REAL,
            prise_en_charge REAL,
            note_finale REAL,
            commentaire TEXT,
            FOREIGN KEY(id_etudiant) REFERENCES etudiants(id_etudiant)
        )''')
        
        # Table Évaluateurs Humains
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
# FONCTIONS UTILITAIRES
# ---------------------------
def safe_filename(student_id: str) -> str:
    """Génère un nom de fichier sécurisé"""
    return secure_filename(f"student_{student_id}")

def hash_identification(raw_id: str) -> str:
    """Hachage SHA-256 des identifiants sensibles"""
    return hashlib.sha256(raw_id.encode()).hexdigest()

# ---------------------------
# INTERFACE UTILISATEUR
# ---------------------------
def sidebar_management():
    """Gestion de la barre latérale"""
    with st.sidebar:
        st.header("🔐 Configuration OpenAI")
        api_key = st.text_input("Clé API", type="password")
        org_id = st.text_input("ID Organisation")
        project_id = st.text_input("ID Projet")
        
        st.markdown("---")
        st.header("🛠️ Administration")
        
        if st.button("🗑️ Purger les données", help="Supprime toutes les évaluations"):
            purge_database()
            
        st.markdown("---")
        st.download_button(
            label="📥 Exporter les données",
            data=pd.read_sql("SELECT * FROM evaluations_ia", sqlite3.connect(DB_PATH)).to_csv(),
            file_name="evaluations.csv"
        )
    
    return api_key, org_id, project_id

def purge_database():
    """Nettoyage sécurisé de la base de données"""
    if st.session_state.get("confirm_purge"):
        if st.checkbox("✅ Confirmer la suppression COMPLÈTE de toutes les données"):
            try:
                with sqlite3.connect(DB_PATH) as conn:
                    conn.execute("DELETE FROM evaluations_ia")
                    conn.execute("DELETE FROM evaluations_humaines")
                    conn.execute("DELETE FROM etudiants")
                    st.success("Base de données réinitialisée")
                    st.session_state.confirm_purge = False
            except Exception as e:
                st.error(f"Erreur : {str(e)}")
    else:
        st.session_state.confirm_purge = True
        st.warning("Cette action est irréversible !")

# ---------------------------
# CORE FUNCTIONALITY
# ---------------------------
def audio_recorder_component(student_id: str):
    """Composant d'enregistrement audio avec visualisation"""
    sanitized_id = safe_filename(student_id)
    
    js_code = f"""
    // [JavaScript code similaire à votre version originale]
    // Avec sanitization des IDs et gestion d'erreurs
    """
    
    st.components.v1.html(js_code, height=350)

def evaluate_with_gpt4(client: OpenAI, prompt: str) -> dict:
    """Appel sécurisé à l'API OpenAI avec validation"""
    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            response_format={"type": "json_object"},
            max_tokens=1500
        )
        result = json.loads(response.choices[0].message.content)
        validated_result = EvaluationResult(**result)
        return validated_result.dict()
    except ValidationError as e:
        st.error(f"Erreur de validation : {str(e)}")
        st.stop()
    except Exception as e:
        st.error(f"Erreur OpenAI : {str(e)}")
        st.stop()

# ---------------------------
# MAIN APP
# ---------------------------
def main():
    api_key, org_id, project_id = sidebar_management()
    
    # Section étudiant
    student_id = st.text_input("🆔 Identifiant Étudiant (8 caractères)", max_chars=8)
    if student_id and (len(student_id) != 8 or not student_id.isalnum()):
        st.error("ID invalide ! Doit contenir 8 caractères alphanumériques")
        st.stop()
    
    # Section fichiers
    clinical_case = st.file_uploader("📄 Cas clinique (PDF/TXT)", type=["pdf", "txt"])
    rubric_file = st.file_uploader("📋 Grille d'évaluation (JSON)", type=["json"])
    
    # Enregistrement audio
    with st.expander("🎙️ Enregistrement Audio", expanded=True):
        audio_recorder_component(student_id)
        uploaded_audio = st.file_uploader("📤 Fichier audio existant", type=["wav", "mp3"])
    
    # Évaluation
    if st.button("🏁 Lancer l'évaluation complète") and all([api_key, org_id, project_id]):
        with st.status("🔍 Analyse en cours...", expanded=True) as status:
            try:
                # Initialisation client OpenAI
                client = OpenAI(api_key=api_key, organization=org_id, project=project_id)
                
                # Transcriptions
                with tempfile.NamedTemporaryFile(suffix=".wav") as tmp_audio:
                    tmp_audio.write(uploaded_audio.getvalue())
                    transcript = client.audio.transcriptions.create(
                        model="whisper-1",
                        file=tmp_audio,
                        language="fr"
                    )
                
                # Construction du prompt
                evaluation_prompt = f"""
                [Votre prompt détaillé ici...]
                """
                
                # Appel GPT-4
                result = evaluate_with_gpt4(client, evaluation_prompt)
                
                # Sauvegarde base de données
                with sqlite3.connect(DB_PATH) as conn:
                    # Enregistrement étudiant
                    conn.execute(
                        "INSERT OR IGNORE INTO etudiants VALUES (?, ?, ?)",
                        (student_id, datetime.now(), hash_identification(student_id))
                    )
                    
                    # Enregistrement résultats IA
                    for critere in result['notes']:
                        conn.execute(
                            """INSERT INTO evaluations_ia VALUES 
                            (NULL, ?, ?, ?, ?, ?, ?, ?)""",
                            (
                                student_id,
                                critere['critère'],
                                critere['score'],
                                critere['justification'],
                                result['synthese'],
                                result['prise_en_charge'],
                                result['note_finale'],
                                result['commentaire']
                            )
                        )
                
                status.update(label="✅ Évaluation terminée", state="complete")
                st.balloons()
                
            except Exception as e:
                st.error(f"Échec de l'analyse : {str(e)}")
                st.stop()
    
    # Affichage résultats
    if 'result' in locals():
        display_results(result)

def display_results(result: dict):
    """Affichage interactif des résultats"""
    st.subheader(f"📊 Note finale : {result['note_finale']}/20")
    
    with st.expander("🔍 Détail des critères"):
        for critere in result['notes']:
            st.markdown(f"""
            **{critere['critère']}**  
            Score : `{critere['score']}`  
            *Justification* : {critere['justification']}
            """)
    
    # Comparaison avec évaluateurs humains
    with st.form("comparaison_evaluateurs"):
        eval1 = st.slider("Évaluateur 1", 0.0, 20.0, step=0.5)
        eval2 = st.slider("Évaluateur 2", 0.0, 20.0, step=0.5)
        
        if st.form_submit_button("💾 Enregistrer comparaison"):
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute(
                    """INSERT INTO evaluations_humaines VALUES 
                    (NULL, ?, ?, ?, ?)""",
                    (student_id, eval1, eval2, datetime.now())
                )
            st.success("Données enregistrées !")

if __name__ == "__main__":
    main()
