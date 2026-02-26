"""
LADX - Knowledge Base Builder
=======================================
Run this script after you've added your PLC documentation
and code examples to the knowledge/ directory.

Usage: python build_knowledge_base.py
"""

import os
import sys
from pathlib import Path
from config import KNOWLEDGE_DIR, CHROMA_DB_DIR

def build():
    """Build the vector database from your PLC documentation."""

    print("=" * 60)
    print("  PLC Knowledge Base Builder")
    print("=" * 60)

    # Check if knowledge directory has files
    if not KNOWLEDGE_DIR.exists():
        KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
        print(f"\nCreated {KNOWLEDGE_DIR}/ directory.")
        print("Please add your PLC documentation and code examples, then run again.")
        print("\nRecommended structure:")
        print("  knowledge/")
        print("  ├── siemens/")
        print("  │   ├── manuals/      (PDF manuals)")
        print("  │   └── examples/     (your .scl code files)")
        print("  ├── allen_bradley/")
        print("  │   ├── manuals/      (PDF manuals)")
        print("  │   └── examples/     (your .st and .L5X files)")
        print("  ├── standards/        (IEC 61131-3 references)")
        print("  └── templates/        (your code templates)")
        return

    # Count files
    all_files = list(KNOWLEDGE_DIR.rglob("*"))
    all_files = [f for f in all_files if f.is_file()]

    if len(all_files) == 0:
        print(f"\nNo files found in {KNOWLEDGE_DIR}/")
        print("Add your PLC docs and code examples, then run again.")
        return

    print(f"\nFound {len(all_files)} files in {KNOWLEDGE_DIR}/")

    # Import dependencies (only after checking files exist)
    try:
        from langchain_community.document_loaders import (
            DirectoryLoader,
            TextLoader,
        )
        from langchain.text_splitter import RecursiveCharacterTextSplitter
        from langchain_community.vectorstores import Chroma
        from langchain_community.embeddings import HuggingFaceEmbeddings
    except ImportError:
        print("\nMissing dependencies. Install them with:")
        print("  pip install langchain langchain-community chromadb sentence-transformers")
        return

    # Define file loaders for different types
    print("\nLoading documents...")

    documents = []

    # Load text-based files (.scl, .st, .txt, .csv, .xml)
    text_extensions = [
        "*.scl", "*.st", "*.txt", "*.csv", "*.xml",
        "*.l5x", "*.json", "*.md", "*.py", "*.awl"
    ]

    for ext in text_extensions:
        files = list(KNOWLEDGE_DIR.rglob(ext))
        for file_path in files:
            try:
                loader = TextLoader(str(file_path), encoding="utf-8")
                docs = loader.load()
                # Add metadata
                for doc in docs:
                    doc.metadata["source"] = str(file_path)
                    doc.metadata["file_type"] = file_path.suffix
                    # Determine platform from path
                    if "siemens" in str(file_path).lower():
                        doc.metadata["platform"] = "siemens"
                    elif "allen" in str(file_path).lower() or "ab" in str(file_path).lower():
                        doc.metadata["platform"] = "allen_bradley"
                    else:
                        doc.metadata["platform"] = "general"
                documents.extend(docs)
                print(f"  Loaded: {file_path.name}")
            except Exception as e:
                print(f"  Warning: Could not load {file_path.name}: {e}")

    # Load PDF files
    try:
        from langchain_community.document_loaders import PyPDFLoader
        pdf_files = list(KNOWLEDGE_DIR.rglob("*.pdf"))
        for pdf_path in pdf_files:
            try:
                loader = PyPDFLoader(str(pdf_path))
                docs = loader.load()
                for doc in docs:
                    doc.metadata["source"] = str(pdf_path)
                    doc.metadata["file_type"] = ".pdf"
                documents.extend(docs)
                print(f"  Loaded: {pdf_path.name} ({len(docs)} pages)")
            except Exception as e:
                print(f"  Warning: Could not load {pdf_path.name}: {e}")
    except ImportError:
        print("  Note: Install pypdf for PDF support: pip install pypdf")

    if len(documents) == 0:
        print("\nNo documents could be loaded. Check file formats.")
        return

    print(f"\nLoaded {len(documents)} document chunks")

    # Split into searchable chunks
    print("Splitting into search chunks...")
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1500,
        chunk_overlap=200,
        separators=[
            "\nFUNCTION_BLOCK",  # Siemens SCL block boundaries
            "\nFUNCTION",
            "\nPROGRAM",
            "\nVAR",
            "\nEND_VAR",
            "\nEND_FUNCTION_BLOCK",
            "\n\n",
            "\n",
            " "
        ]
    )
    chunks = splitter.split_documents(documents)
    print(f"Created {len(chunks)} searchable chunks")

    # Create embeddings and vector store
    print("\nBuilding vector database (this may take a few minutes on first run)...")
    print("Downloading embedding model...")

    embeddings = HuggingFaceEmbeddings(
        model_name="all-MiniLM-L6-v2",
        model_kwargs={"device": "cpu"}
    )

    # Clear existing database
    if CHROMA_DB_DIR.exists():
        import shutil
        shutil.rmtree(CHROMA_DB_DIR)
        print("Cleared existing database")

    # Build new database
    vectorstore = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=str(CHROMA_DB_DIR)
    )

    print(f"\nKnowledge base built successfully!")
    print(f"  Location: {CHROMA_DB_DIR}/")
    print(f"  Documents: {len(documents)}")
    print(f"  Chunks: {len(chunks)}")
    print(f"\nYou can now use the agent — it will search this knowledge base")
    print(f"when answering your questions.")

    # Test with a sample query
    print("\n--- Test Query ---")
    results = vectorstore.similarity_search("motor control function block", k=3)
    if results:
        print(f"Found {len(results)} results for 'motor control function block':")
        for i, r in enumerate(results):
            preview = r.page_content[:100].replace('\n', ' ')
            print(f"  {i+1}. [{r.metadata.get('source', 'unknown')}] {preview}...")
    else:
        print("No results yet — add more documentation for better results.")


if __name__ == "__main__":
    build()
