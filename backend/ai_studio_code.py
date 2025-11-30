import google.generativeai as genai
import os

# Load Key
key_path = os.path.join(os.path.dirname(__file__), '..', 'gemini_api_key.txt')
with open(key_path, 'r') as f:
    api_key = f.read().strip()

genai.configure(api_key=api_key)

print("Available Models:")
for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        print(m.name)