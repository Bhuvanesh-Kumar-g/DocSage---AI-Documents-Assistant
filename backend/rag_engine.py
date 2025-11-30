import google.generativeai as genai
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
import logging
import json
import re

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RAGEngine:
    def __init__(self, api_key):
        genai.configure(api_key=api_key)
        # Using 2.5-flash as confirmed working
        self.model = genai.GenerativeModel('gemini-2.5-flash')
        
        # In-memory storage: { doc_id: { 'chunks': [], 'embeddings': np.array, 'full_text': str } }
        self.store = {} 

    def chunk_text(self, text, chunk_size=1000, overlap=200):
        """Splits text into overlapping chunks."""
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
        """Generates embeddings for chunks."""
        try:
            result = genai.embed_content(
                model="models/text-embedding-004",
                content=chunks,
                task_type="retrieval_document",
                title="Document Chunks"
            )
            return np.array(result['embedding'])
        except Exception:
             # Fallback
             logger.warning("text-embedding-004 failed, trying embedding-001")
             result = genai.embed_content(
                model="models/embedding-001",
                content=chunks,
                task_type="retrieval_document",
                title="Document Chunks"
            )
             return np.array(result['embedding'])

    def process_document(self, doc_id, full_text):
        """Pipeline: Chunk -> Embed -> Store"""
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
        """Finds the most relevant chunks."""
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
        """RAG Generation with Visualization Support"""
        
        # 1. Retrieve Context
        relevant_chunks = self.retrieve(doc_id, query)
        
        if not relevant_chunks:
             return json.dumps({ 
                 "mode": "qa", 
                 "answer": "I could not find any relevant information in the document to answer that.", 
                 "sources": [] 
             })

        context_text = "\n\n".join([f"[Chunk {c['chunk_id']}] {c['text']}" for c in relevant_chunks])
        
        # 2. System Prompt
        system_prompt = """
        You are 'DocSage', an expert document assistant. You analyze documents and answer questions based ONLY on the provided context.

        OUTPUT FORMAT INSTRUCTIONS:
        You must return a valid JSON object. Do not include markdown formatting (like ```json).
        
        MODE 1: NORMAL Q&A
        Trigger: When the user asks a general question, summarization, or lookup.
        Response Format:
        {
            "mode": "qa",
            "answer": "Your natural, human-friendly response here.",
            "sources": [{"snippet": "...", "page": "..."}]
        }
        
        Guidelines for 'answer':
        1. Be Concise & Human: Do not list every detail. Synthesize the information.
        2. Sample Data: If the document contains Lorem Ipsum, placeholder text, or generic sample data, clearly state: "This appears to be a sample document containing placeholder text." Do not repeat Lorem Ipsum.
        3. Structure: Use bullet points for lists.
        4. "Tell me about this": Provide a high-level summary (purpose, document type, key sections) rather than a row-by-row description.

        MODE 2: VISUALIZATION
        Trigger: When the user explicitly asks to "plot", "chart", "graph", or "visualize" data found in the context.
        Response Format:
        {
            "mode": "visualization",
            "answer": "A short sentence explaining what this chart shows.",
            "chart_config": {
                "type": "bar", // or 'line', 'pie', 'doughnut'
                "data": {
                    "labels": ["Category A", "Category B"],
                    "datasets": [{
                        "label": "Dataset Name",
                        "data": [10, 20],
                        "backgroundColor": ["#4a90e2", "#50e3c2"] 
                    }]
                },
                "options": {
                    "responsive": true,
                    "plugins": {
                        "title": { "display": true, "text": "Chart Title" }
                    }
                }
            }
        }
        NOTE: Extract numerical data from the context to populate 'labels' and 'data'. If data is insufficient, revert to MODE 1 and explain why.
        """
        
        user_prompt = f"CONTEXT:\n{context_text}\n\nUSER QUESTION: {query}\n\nJSON OUTPUT:"
        
        # 3. Generation
        response = self.model.generate_content(system_prompt + user_prompt)
        
        # 4. Cleaning the Output (Crucial step)
        raw_text = response.text
        
        # Remove markdown code blocks if present
        clean_text = raw_text.replace("```json", "").replace("```", "").strip()
        
        # Attempt to find the first '{' and last '}' to strip extra text
        try:
            start_idx = clean_text.find('{')
            end_idx = clean_text.rfind('}')
            if start_idx != -1 and end_idx != -1:
                clean_text = clean_text[start_idx:end_idx+1]
                
            # Verify it parses
            json.loads(clean_text)
            return clean_text
            
        except json.JSONDecodeError:
            # Fallback if model fails to generate valid JSON
            logger.error(f"JSON Parse Error. Raw: {raw_text}")
            return json.dumps({
                "mode": "qa", 
                "answer": "I found information, but I had trouble formatting it correctly. Here is the raw text: " + raw_text[:500], 
                "sources": []
            })