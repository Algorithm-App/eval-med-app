import streamlit as st
import json

st.title("🎓 Évaluation médicale automatisée")

# 1. Cas clinique
clinical_file = st.file_uploader("📄 Charger le cas clinique (.txt)", type=["txt"])
if clinical_file:
    clinical_text = clinical_file.read().decode("utf-8")
    st.text_area("📘 Cas clinique", clinical_text, height=250)

# 2. Grille d’évaluation
rubric_file = st.file_uploader("📋 Charger la grille d’évaluation (.json)", type=["json"])
if rubric_file:
    rubric = json.load(rubric_file)
    st.json(rubric)

# 3. Réponse étudiante simulée
student_response = st.text_area("🎤 Réponse de l’étudiant (texte transcrit)", height=200)

# 4. Évaluation automatique
if st.button("🧠 Évaluer la réponse"):
    if not (clinical_file and rubric_file and student_response):
        st.warning("Merci de charger le cas, la grille et une réponse.")
    else:
        prompt = f"""
Tu es examinateur. Voici :
- Le cas clinique : {clinical_text}
- La réponse de l'étudiant : {student_response}
- La grille d’évaluation : {json.dumps(rubric, ensure_ascii=False)}

Analyse la réponse et donne :
1. Un score détaillé pour chaque critère
2. Le score total (sur 18)
3. Un commentaire global de 5 lignes maximum
        """
        st.markdown("⏳ Envoi à l'IA...")
        st.info("👉 Ici tu peux appeler OpenAI GPT si tu ajoutes ta clé API")

        # Simule une réponse (remplacer plus tard par openai.ChatCompletion)
        st.success("✅ Évaluation terminée")
        st.write("🧾 Exemple de retour :")
        st.markdown("""
- **Critère 1** : ✅ (2 points)  
- **Critère 2** : ❌ (0 point)  
- ...  
**Total** : 14/18  
**Commentaire** : Bonne prise en charge, bien structurée. L'étudiant évoque le sepsis mais oublie la nécessité du drainage chirurgical.
        """)

