import warnings
warnings.filterwarnings("ignore")

import json
import os
import re
import shutil
import time
import gc
import stat

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings

from drive_loader.google_drive_loader import fetch_files_from_folder


# -------------------------
# 🔹 CONFIG
# -------------------------
FOLDER_ID = "1OQVILYMdPwOSU7Pj_4yxbp5DEsDQmI0x"
INDEX_PATH = "faiss_index"


# -------------------------
# 🔹 CLEAN TEXT
# -------------------------
def clean_text(text):
    text = re.sub(r'endobj.*?obj', ' ', text, flags=re.DOTALL)
    text = re.sub(r'stream.*?endstream', ' ', text, flags=re.DOTALL)
    text = re.sub(r'[^a-zA-Z0-9.,()\-\n ]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# -------------------------
# 🔹 VALIDATION
# -------------------------
def is_valid(text):
    if len(text) < 300:
        return False

    junk_words = ["endobj", "xref", "stream", "obj", "fGS"]
    return not any(word in text.lower() for word in junk_words)


# -------------------------
# 🔹 WINDOWS SAFE DELETE
# -------------------------
def remove_readonly(func, path, excinfo):
    os.chmod(path, stat.S_IWRITE)
    func(path)


def safe_delete(path):
    if not os.path.exists(path):
        return

    for i in range(5):
        try:
            shutil.rmtree(path, onerror=remove_readonly)
            print("🗑️ Old index deleted")
            return
        except PermissionError:
            print(f"⚠️ Attempt {i+1}: Folder in use, retrying...")
            gc.collect()
            time.sleep(2)

    raise Exception("❌ Could not delete faiss_index (still locked)")


# -------------------------
# 🔹 BUILD INDEX
# -------------------------
def build_index():
    print("📂 Fetching files from Google Drive...")
    docs = fetch_files_from_folder(FOLDER_ID)

    if not docs:
        print("❌ No documents found in Drive. Check folder access!")
        return

    cleaned_docs = []

    print("\n🧹 Cleaning documents...\n")

    for doc in docs:
        raw_content = doc.get("content", "")
        cleaned = clean_text(raw_content)

        if not is_valid(cleaned):
            print(f"⚠️ Skipping low-quality doc: {doc.get('file_name')}")
            continue

        cleaned_docs.append(
            Document(
                page_content=cleaned,
                metadata={
                    "source": doc.get("file_name"),
                    "file_id": doc.get("file_id"),
                    "link": doc.get("link")
                }
            )
        )

    print(f"\n✅ Clean documents: {len(cleaned_docs)}")

    if not cleaned_docs:
        raise Exception("❌ No valid documents after cleaning!")

    # -------------------------
    # 🔹 SPLIT
    # -------------------------
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=150
    )

    texts = splitter.split_documents(cleaned_docs)
    print(f"🔹 Total chunks: {len(texts)}")

    # -------------------------
    # 🔹 EMBEDDINGS
    # -------------------------
    embeddings = HuggingFaceEmbeddings(
        model_name="BAAI/bge-base-en-v1.5",
        encode_kwargs={"normalize_embeddings": True}
    )

    # -------------------------
    # 🔥 SAFE DELETE OLD INDEX
    # -------------------------
    print("\n🧹 Cleaning old index...")
    gc.collect()   # VERY IMPORTANT

    safe_delete(INDEX_PATH)

    # -------------------------
    # 🔹 CREATE INDEX
    # -------------------------
    print("\n⚡ Creating FAISS index...")
    db = FAISS.from_documents(texts, embeddings)
    db.save_local(INDEX_PATH)

    print("\n✅ Index built successfully!")

    # -------------------------
    # 🔹 SAVE METADATA
    # -------------------------
    file_ids = [doc.get("file_id") for doc in docs]

    with open("index_meta.json", "w") as f:
        json.dump(file_ids, f)

    print("📦 Metadata saved (index_meta.json)")


# -------------------------
# 🔹 MAIN
# -------------------------
if __name__ == "__main__":
    build_index()