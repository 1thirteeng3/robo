"""Gardener: CPU-optimized RAG indexing for Obsidian Vault."""

import os
import json
import time
import re
from pathlib import Path
from loguru import logger

import chromadb
from sentence_transformers import SentenceTransformer

WORKSPACE_DIR = Path(os.environ.get("WORKSPACE_DIR", "."))
VAULT_DIR = Path(os.environ.get("OBSIDIAN_VAULT_PATH", str(Path.home() / "Documents" / "Vault")))
CHROMA_DB_PATH = WORKSPACE_DIR / "chroma_db"
STATE_FILE = WORKSPACE_DIR / ".gardener_state.json"

CHUNK_SIZE = 1000  # Characters target for chunking
CHUNK_OVERLAP = 200

def load_state() -> float:
    """Load the last execution timestamp."""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, 'r') as f:
                return float(json.load(f).get("last_run", 0))
        except Exception as e:
            logger.warning(f"Could not load state: {e}")
    return 0.0

def save_state():
    """Save the current timestamp."""
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump({"last_run": time.time()}, f)
    except Exception as e:
        logger.warning(f"Could not save state: {e}")

def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Basic text chunking sliding window."""
    if not text:
        return []
    chunks = []
    start = 0
    text_len = len(text)
    while start < text_len:
        end = start + chunk_size
        chunks.append(text[start:end])
        if end >= text_len:
            break
        start += (chunk_size - overlap)
    return chunks

def run():
    logger.info("Starting Gardener...")
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    
    last_run = load_state()
    
    logger.info("Initializing ChromaDB persistent client...")
    client = chromadb.PersistentClient(path=str(CHROMA_DB_PATH))
    collection = client.get_or_create_collection(
        name="obsidian_vault",
        metadata={"hnsw:space": "cosine"}
    )
    
    logger.info("Loading sentence-transformers (all-MiniLM-L6-v2) on CPU...")
    # This model is ~90MB and runs fine on CPU
    model = SentenceTransformer('all-MiniLM-L6-v2', device='cpu')

    new_or_modified_files = []
    
    logger.info(f"Scanning vault: {VAULT_DIR}")
    for root, _, files in os.walk(VAULT_DIR):
        for file in files:
            if file.endswith('.md'):
                filepath = Path(root) / file
                mtime = os.path.getmtime(filepath)
                
                # Check if modified since last run
                if mtime > last_run:
                    new_or_modified_files.append(filepath)

    if not new_or_modified_files:
        logger.info("No modified files found. Exiting.")
        save_state()
        return

    logger.info(f"Found {len(new_or_modified_files)} modified files to process.")

    # Phase 1: Indexing
    for filepath in new_or_modified_files:
        try:
            content = filepath.read_text(encoding='utf-8')
            chunks = chunk_text(content, CHUNK_SIZE, CHUNK_OVERLAP)
            
            if not chunks:
                continue
                
            embeddings = model.encode(chunks, convert_to_numpy=True).tolist()
            
            ids = [f"{filepath.name}_{i}" for i in range(len(chunks))]
            metadatas = [{"source": filepath.name, "path": str(filepath)} for _ in chunks]
            
            # Upsert into ChromaDB
            collection.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=chunks,
                metadatas=metadatas
            )
            logger.info(f"Indexed {filepath.name} ({len(chunks)} chunks)")
        except Exception as e:
            logger.error(f"Error indexing {filepath.name}: {e}")

    # Phase 2: Reverse RAG (Auto-linking)
    for filepath in new_or_modified_files:
        try:
            content = filepath.read_text(encoding='utf-8')
                
            # Use the first 500 chars as query
            query_text = content[:500]
            if not query_text.strip():
                continue
                
            query_embedding = model.encode([query_text], convert_to_numpy=True).tolist()[0]
            
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=4  # Get top 4, skip the document itself
            )
            
            similar_notes = set()
            for metadata in results.get("metadatas", [[]])[0]:
                source = metadata.get("source")
                if source and source != filepath.name:
                    # Remove .md for obsidian internal links
                    similar_notes.add(source.replace(".md", ""))
            
            if similar_notes:
                # Get max 3 similar notes
                linked_notes = list(similar_notes)[:3]
                
                refs = "\n".join([f"- [[{note}]]" for note in linked_notes])
                append_text = f"\n\n## Referências Automáticas (Gardener)\n{refs}\n"
                
                # Regex to search for the block and replace it, or append if it doesn't exist
                pattern = r'\n+## Referências Automáticas \(Gardener\)[\s\S]*?(?=\n## |\Z)'
                if re.search(pattern, content):
                    new_content = re.sub(pattern, append_text, content)
                else:
                    new_content = content + append_text
                
                filepath.write_text(new_content, encoding='utf-8')
                logger.info(f"Auto-linked {filepath.name} to: {', '.join(linked_notes)}")
                
        except Exception as e:
            logger.error(f"Error auto-linking {filepath.name}: {e}")

    save_state()
    logger.info("Gardener finished successfully.")

if __name__ == "__main__":
    run()
