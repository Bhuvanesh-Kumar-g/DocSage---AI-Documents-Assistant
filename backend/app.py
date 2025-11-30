import os
import uuid
import logging
import json
import time
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
# We keep dotenv for local testing, but Render ignores it
from dotenv import load_dotenv 
import PyPDF2

# Import our RAG Engine
from rag_engine import RAGEngine

# 1. Setup Logging & Environment
load_dotenv() # This loads .env locally. Render uses its own dashboard variables.
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 2. Setup Paths for Frontend
current_dir = os.path.dirname(os.path.abspath(__file__))
frontend_folder = os.path.join(current_dir, '..', 'frontend')

# 3. Initialize Flask
app = Flask(__name__, static_folder=frontend_folder, static_url_path='')
CORS(app)

# 4. Load API Key from Environment Variable (Render Safe)
API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    logger.critical("No GEMINI_API_KEY found in Environment Variables! App will fail.")

# 5. Initialize RAG Engine
# We pass the key explicitly to the engine
rag_engine = RAGEngine(api_key=API_KEY)

# --- ROUTES ---

@app.route('/')
def home():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/upload', methods=['POST'])
def upload_document():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Empty filename"}), 400

    start_time = time.time()
    doc_id = str(uuid.uuid4())
    
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

@app.route('/ask', methods=['POST'])
def ask():
    data = request.json
    question = data.get('question')
    # Use last uploaded doc if doc_id missing (hackathon simplicity)
    doc_id = data.get('doc_id')
    if not doc_id and rag_engine.store:
        doc_id = list(rag_engine.store.keys())[-1]

    if not question:
        return jsonify({"error": "Missing question"}), 400
    
    if not doc_id:
         return jsonify({"answer": "Please upload a document first!"})

    try:
        # Get Answer from RAG Engine
        json_response_str = rag_engine.generate_answer(doc_id, question)
        
        # Clean up Markdown json block if Gemini adds it
        clean_json = json_response_str.replace("```json", "").replace("```", "").strip()
        
        response_data = json.loads(clean_json)
        return jsonify(response_data)

    except Exception as e:
        logger.error(f"QA failed: {e}")
        return jsonify({"answer": f"Error processing answer: {str(e)}"}), 500

if __name__ == '__main__':
    # PORT env var is required by Render
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
