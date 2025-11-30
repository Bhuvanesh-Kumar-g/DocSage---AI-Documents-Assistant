import google.generativeai as genai
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
import logging
import json

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RAGEngine:
    def __init__(self, api_key):
        # Configure the API key provided by app.py (from os.getenv)
        if api_key:
            genai.configure(api_key=api_key)
        
        # UPDATED: Using the model version you requested
        self.model = genai.GenerativeModel('gemini-2.0-flash')
        
        self.store = {} 

    def chunk_text(self, text, chunk_size=1000, overlap=200):
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            if end < len(text):
                newline_pos = text.find('\n', end - 50, end + 50)
                if newline_pos != -1:
                    end = newline_pos
            
            chunk = text[start:end]
            if chunk.strip():
                chunks.append(chunk)
            start += (chunk_size - overlap)
        return chunks

    def create_embeddings(self, chunks):
        try:
            result = genai.embed_content(
                model="models/text-embedding-004",
                content=chunks,
                task_type="retrieval_document",
                title="Document Chunks"
            )
            return np.array(result['embedding'])
        except Exception:
             logger.warning("text-embedding-004 failed, trying embedding-001")
             result = genai.embed_content(
                model="models/embedding-001",
                content=chunks,
                task_type="retrieval_document",
                title="Document Chunks"
            )
             return np.array(result['embedding'])

    def process_document(self, doc_id, full_text):
        logger.info(f"Processing document {doc_id}...")
        chunks = self.chunk_text(full_text)
        if not chunks:
             raise ValueError("No text could be extracted.")

        embeddings = self.create_embeddings(chunks)
        
        self.store[doc_id] = {
            "chunks": chunks,
            "embeddings": embeddings,
            "full_text": full_text
        }
        return len(chunks)

    def retrieve(self, doc_id, query, top_k=5):
        if doc_id not in self.store:
            raise ValueError("Document ID not found.")
        
        doc_data = self.store[doc_id]
        if len(doc_data['chunks']) == 0:
            return []
            
        try:
            query_embedding = genai.embed_content(
                model="models/text-embedding-004",
                content=query,
                task_type="retrieval_query"
            )['embedding']
        except:
            query_embedding = genai.embed_content(
                model="models/embedding-001",
                content=query,
                task_type="retrieval_query"
            )['embedding']
        
        query_vec = np.array(query_embedding).reshape(1, -1)
        doc_vecs = doc_data['embeddings']
        similarities = cosine_similarity(query_vec, doc_vecs)[0]
        
        actual_top_k = min(top_k, len(doc_data['chunks']))
        top_indices = np.argsort(similarities)[-actual_top_k:][::-1]
        
        results = []
        for idx in top_indices:
            results.append({
                "text": doc_data['chunks'][idx],
                "score": float(similarities[idx]),
                "chunk_id": int(idx)
            })
        
        return results

    def generate_answer(self, doc_id, query):
        relevant_chunks = self.retrieve(doc_id, query)
        
        if not relevant_chunks:
             return json.dumps({ 
                 "mode": "qa", 
                 "answer": "I could not find any relevant information in the document to answer that.", 
                 "sources": [] 
             })

        context_text = "\n\n".join([f"[Chunk {c['chunk_id']}] {c['text']}" for c in relevant_chunks])
        
        system_prompt = """
        You are 'DocSage', an expert document assistant. Analyze documents and answer based ONLY on the context.

        OUTPUT FORMAT: Return valid JSON only.
        
        MODE 1: NORMAL Q&A
        Format: { "mode": "qa", "answer": "Human-friendly response.", "sources": [{"snippet": "..."}] }
        Guidelines: Be concise. If it's sample data, say so.
        
        MODE 2: VISUALIZATION
        Trigger: User asks to plot/chart/visualize data.
        Format: {
            "mode": "visualization",
            "answer": "Short explanation.",
            "chart_config": {
                "type": "bar",
                "data": { "labels": ["A", "B"], "datasets": [{ "label": "Data", "data": [10, 20] }] },
                "options": { "responsive": true }
            }
        }
        """
        
        user_prompt = f"CONTEXT:\n{context_text}\n\nUSER QUESTION: {query}\n\nJSON OUTPUT:"
        
        response = self.model.generate_content(system_prompt + user_prompt)
        
        raw_text = response.text
        clean_text = raw_text.replace("```json", "").replace("```", "").strip()
        
        try:
            start_idx = clean_text.find('{')
            end_idx = clean_text.rfind('}')
            if start_idx != -1 and end_idx != -1:
                clean_text = clean_text[start_idx:end_idx+1]
            json.loads(clean_text)
            return clean_text
        except json.JSONDecodeError:
            logger.error(f"JSON Parse Error. Raw: {raw_text}")
            return json.dumps({
                "mode": "qa", 
                "answer": "Error formatting response. Raw: " + raw_text[:200], 
                "sources": []
            })
