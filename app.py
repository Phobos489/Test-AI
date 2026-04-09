from flask import Flask, request, jsonify, render_template, session
import main
import json
import os
from datetime import datetime
import speech_recognition as sr
import tempfile
import base64

app = Flask(__name__)
app.secret_key = '6598e01a2c5a5782d3241892e1fb99997a1dd6b043a4171e224bfe539184c7b0'

# File untuk menyimpan data user
USERS_FILE = 'users.json'

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=2)

# ─── Fungsi Ekstraksi Teks dari File ───────────────────────────────────────────

def extract_text_from_pdf(file_path):
    """Ekstrak teks dari file PDF menggunakan pdfplumber (lebih akurat) atau PyPDF2."""
    text = ""
    try:
        import pdfplumber
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        return text.strip()
    except ImportError:
        pass

    try:
        import PyPDF2
        with open(file_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        return text.strip()
    except Exception as e:
        return f"[Gagal membaca PDF: {str(e)}]"


def extract_text_from_docx(file_path):
    """Ekstrak teks dari file Word (.docx)."""
    try:
        from docx import Document
        doc = Document(file_path)
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]

        # Juga ambil teks dari tabel
        for table in doc.tables:
            for row in table.rows:
                row_texts = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if row_texts:
                    paragraphs.append(" | ".join(row_texts))

        return "\n".join(paragraphs)
    except Exception as e:
        return f"[Gagal membaca DOCX: {str(e)}]"


def extract_text_from_excel(file_path):
    """Ekstrak teks dari file Excel (.xlsx/.xls)."""
    try:
        import openpyxl
        wb = openpyxl.load_workbook(file_path, data_only=True)
        result = []
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            result.append(f"=== Sheet: {sheet_name} ===")
            for row in ws.iter_rows(values_only=True):
                row_data = [str(cell) if cell is not None else "" for cell in row]
                if any(cell.strip() for cell in row_data):
                    result.append(" | ".join(row_data))
        return "\n".join(result)
    except Exception:
        pass

    try:
        import pandas as pd
        xl = pd.ExcelFile(file_path)
        result = []
        for sheet_name in xl.sheet_names:
            df = xl.parse(sheet_name)
            result.append(f"=== Sheet: {sheet_name} ===")
            result.append(df.to_string(index=False))
        return "\n".join(result)
    except Exception as e:
        return f"[Gagal membaca Excel: {str(e)}]"


def extract_text_from_file(file_path, filename):
    """Deteksi tipe file dan ekstrak teks."""
    ext = os.path.splitext(filename)[1].lower()

    if ext == '.pdf':
        return extract_text_from_pdf(file_path)
    elif ext in ('.docx', '.doc'):
        return extract_text_from_docx(file_path)
    elif ext in ('.xlsx', '.xls'):
        return extract_text_from_excel(file_path)
    elif ext in ('.txt', '.csv', '.md'):
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
    else:
        return None  # Tipe tidak didukung

# ─── Routes ────────────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")

@app.route("/generate", methods=["POST"])
def generate():
    data = request.get_json()
    prompt = data.get("prompt", "")

    if not prompt:
        return jsonify({"error": "prompt tidak boleh kosong"}), 400

    result = main.generate_text(prompt)
    return jsonify({"prompt": prompt, "result": result})


@app.route("/generate-with-file", methods=["POST"])
def generate_with_file():
    """Endpoint untuk menghasilkan respons berdasarkan file + prompt."""
    prompt = request.form.get("prompt", "").strip()
    file = request.files.get("file")

    if not prompt:
        return jsonify({"error": "Prompt tidak boleh kosong"}), 400

    if not file or file.filename == "":
        return jsonify({"error": "Tidak ada file yang dikirim"}), 400

    filename = file.filename
    ext = os.path.splitext(filename)[1].lower()
    allowed_exts = {'.pdf', '.docx', '.doc', '.xlsx', '.xls', '.txt', '.csv', '.md'}

    if ext not in allowed_exts:
        return jsonify({
            "error": f"Tipe file '{ext}' tidak didukung. Format yang diizinkan: PDF, Word, Excel, TXT, CSV"
        }), 400

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            file.save(tmp.name)
            tmp_path = tmp.name

        file_text = extract_text_from_file(tmp_path, filename)
        os.unlink(tmp_path)

        if file_text is None:
            return jsonify({"error": "Tipe file tidak didukung"}), 400

        if not file_text.strip():
            return jsonify({"error": "File tidak mengandung teks yang dapat dibaca"}), 400

        # Batasi panjang teks agar tidak melebihi batas token model
        MAX_CHARS = 30000
        truncated = len(file_text) > MAX_CHARS
        if truncated:
            file_text = file_text[:MAX_CHARS] + "\n\n[... Teks dipotong karena terlalu panjang ...]"

        # Buat prompt gabungan
        combined_prompt = (
            f"Berikut adalah isi file '{filename}':\n\n"
            f"---\n{file_text}\n---\n\n"
            f"Pertanyaan/Perintah pengguna: {prompt}"
        )

        result = main.generate_text(combined_prompt)
        return jsonify({
            "prompt": prompt,
            "filename": filename,
            "result": result,
            "truncated": truncated
        })

    except Exception as e:
        return jsonify({"error": f"Terjadi kesalahan saat memproses file: {str(e)}"}), 500


@app.route("/api/speech-to-text", methods=["POST"])
def speech_to_text():
    try:
        if 'audio' not in request.files:
            return jsonify({"error": "Tidak ada file audio"}), 400

        audio_file = request.files['audio']
        recognizer = sr.Recognizer()

        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as temp_audio:
            audio_file.save(temp_audio.name)
            with sr.AudioFile(temp_audio.name) as source:
                audio_data = recognizer.record(source)
                text = recognizer.recognize_google(audio_data, language='id-ID')
                os.unlink(temp_audio.name)
                return jsonify({"text": text})

    except sr.UnknownValueError:
        return jsonify({"error": "Tidak dapat memahami audio"}), 400
    except sr.RequestError as e:
        return jsonify({"error": f"Error dari service speech recognition: {e}"}), 500
    except Exception as e:
        return jsonify({"error": f"Terjadi kesalahan: {str(e)}"}), 500


@app.route("/api/register", methods=["POST"])
def register():
    data = request.get_json()
    name = data.get("name", "").strip()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    if not name or not email or not password:
        return jsonify({"error": "Semua field harus diisi"}), 400

    users = load_users()
    if email in users:
        return jsonify({"error": "Email sudah terdaftar"}), 400

    users[email] = {
        "id": f"user_{datetime.now().timestamp()}",
        "name": name,
        "email": email,
        "password": password,
        "created_at": datetime.now().isoformat()
    }
    save_users(users)
    return jsonify({"message": "Pendaftaran berhasil", "user": users[email]}), 201


@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    if not email or not password:
        return jsonify({"error": "Email dan password harus diisi"}), 400

    users = load_users()
    user = users.get(email)

    if not user or user["password"] != password:
        return jsonify({"error": "Email atau password salah"}), 401

    session["user_id"] = user["id"]
    session["user_email"] = user["email"]
    return jsonify({"message": "Login berhasil", "user": user})


@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"message": "Logout berhasil"})


@app.route("/api/user", methods=["GET"])
def get_user():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401

    users = load_users()
    user = users.get(session["user_email"])

    if not user:
        return jsonify({"error": "User not found"}), 404

    return jsonify({"user": user})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)