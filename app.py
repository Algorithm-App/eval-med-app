import streamlit as st
import json
import openai

st.set_page_config(page_title="Évaluation Médicale IA", page_icon="🧠")
st.title("🧠 Application d'Évaluation Médicale Automatisée avec GPT-4")

st.markdown("""
Cette application permet à l'opérateur de :
1. Charger un cas clinique
2. Charger une grille d'évaluation (format JSON)
3. Charger la réponse de l'étudiant (transcrite)
4. Générer une évaluation automatisée à l'aide de GPT-4
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

# 2. Réponse étudiante
st.markdown("## 🎤 Réponse de l'étudiant")
student_response_file = st.file_uploader("Charger la réponse transcrite de l'étudiant (.txt)", type=["txt"])
student_response = ""
if student_response_file is not None:
    student_response = student_response_file.read().decode("utf-8")
    st.text_area("Réponse étudiante :", value=student_response, height=250)

# 3. Clé API OpenAI
openai_api_key = st.text_input("Clé API OpenAI (GPT-4)", type="password")

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
