import google.generativeai as phobosai

# Konfigurasi API Key
phobosai.configure(api_key="")  

# Pilih model
model = phobosai.GenerativeModel("models/gemini-3-flash-preview")

def generate_text(prompt: str):
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"[Gagal menghasilkan teks: {e}]"
