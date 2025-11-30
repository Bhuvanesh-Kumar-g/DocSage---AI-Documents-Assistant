import os
import uuid
import logging
import json
import time
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
import PyPDF2

# Import our RAG Engine
# (Make sure rag_engine.py is in the same folder!)
from rag_engine import RAGEngine

# 1. Setup Logging & Environment
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 2. Setup Paths for Frontend
current_dir = os.path.dirname(os.path.abspath(__file__))
frontend_folder = os.path.join(current_dir, '..', 'frontend')

# 3. Initialize Flask
# We must tell Flask where the 'static' folder (frontend) is
app = Flask(__name__, static_folder=frontend_folder, static_url_path='')
CORS(app)

# 4. Load API Key
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    try:
        key_path = os.path.join(current_dir, '..', 'gemini_api_key.txt')
        if os.path.exists(key_path):
            with open(key_path, 'r') as f:
                API_KEY = f.read().strip()
    except Exception as e:
        logger.error(f"Error reading key file: {e}")

if not API_KEY:
    logger.critical("No API Key found! The agent will not work.")

# 5. Initialize RAG Engine
rag_engine = RAGEngine(api_key=API_KEY)

# --- ROUTES ---

# Serve the Frontend (The "Home Page")
@app.route('/')
def home():
    return send_from_directory(app.static_folder, 'index.html')

# API: Upload Document
@app.route('/upload', methods=['POST'])
def upload_document():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Empty filename"}), 400

    start_time = time.time()
    doc_id = str(uuid.uuid4()) # Create a unique ID for this session
    
    try:
        full_text = ""
        
        # Read PDF
        if file.filename.endswith('.pdf'):
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                text = page.extract_text()
                if text: full_text += text + "\n"
        
        # Read Text
        elif file.filename.endswith('.txt'):
            full_text = file.read().decode('utf-8')
        
        else:
            return jsonify({"error": "Unsupported file type"}), 400

        if not full_text.strip():
            return jsonify({"error": "Document is empty or scanned image."}), 400

        # Process with RAG Engine
        num_chunks = rag_engine.process_document(doc_id, full_text)
        
        process_time = round(time.time() - start_time, 2)
        
        return jsonify({
            "message": "Document processed successfully",
            "doc_id": doc_id,
            "filename": file.filename,
            "stats": {
                "chunks": num_chunks,
                "process_time_seconds": process_time
            }
        })

    except Exception as e:
        logger.error(f"Upload failed: {e}")
        return jsonify({"error": str(e)}), 500

# API: Ask Question
@app.route('/ask', methods=['POST'])
def ask():
    data = request.json
    question = data.get('question')
    # For now, we use the last uploaded doc_id if not sent (simplified for hackathon)
    # In a real app, frontend should send doc_id back.
    # Here we just grab the most recent one from the engine store for simplicity
    doc_id = list(rag_engine.store.keys())[-1] if rag_engine.store else None

    if not question:
        return jsonify({"error": "Missing question"}), 400
    
    if not doc_id:
         return jsonify({"answer": "Please upload a document first!"})

    try:
        start_time = time.time()
        
        # Get Answer from RAG Engine
        # The engine returns a JSON string, so we parse it
        json_response_str = rag_engine.generate_answer(doc_id, question)
        
        # Clean up Markdown json block if Gemini adds it (```json ... ```)
        clean_json = json_response_str.replace("```json", "").replace("```", "").strip()
        
        response_data = json.loads(clean_json)
        
        return jsonify(response_data)

    except Exception as e:
        logger.error(f"QA failed: {e}")
        # Fallback if JSON parsing fails
        return jsonify({"answer": f"Error processing answer: {str(e)}"}), 500

if __name__ == '__main__':
    print(f"Backend running. Frontend serving from: {frontend_folder}")
    app.run(debug=True, port=5000)