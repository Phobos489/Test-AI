import google.generativeai as phobosai

# Konfigurasi API Key
phobosai.configure(api_key="")  

# Pilih model
model = phobosai.GenerativeModel("models/gemini-3.1-pro-preview")

def generate_text(prompt: str):
    response = model.generate_content(prompt)
    return response.text