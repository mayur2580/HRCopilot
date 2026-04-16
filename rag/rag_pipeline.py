
import os
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from dotenv import load_dotenv
from langsmith import traceable
load_dotenv()

# -------------------------
# CONFIG
# -------------------------
# rag/rag_pipeline.py
# Project root = parent of the "rag" folder
BASE_DIR = Path(__file__).resolve().parent.parent
INDEX_PATH = BASE_DIR / "faiss_index"

# -------------------------
# EMBEDDINGS
# -------------------------

embeddings = HuggingFaceEmbeddings(
    model_name="BAAI/bge-base-en-v1.5"
)

# -------------------------
# RETRIEVER
# -------------------------
@traceable(run_type="retriever", name="faiss_retriever")
def get_retriever():
    if not INDEX_PATH.exists():
        raise Exception(f"❌ FAISS index not found at: {INDEX_PATH}. Run build_index.py")

    db = FAISS.load_local(
        str(INDEX_PATH),
        embeddings,
        allow_dangerous_deserialization=True
    )

    return db.as_retriever(
        search_type="similarity",
        search_kwargs={"k": 10, "score_threshold": 0.80}
    )

# -------------------------
# FORMAT DOCS + METADATA
# -------------------------
def format_docs_with_sources(docs):
    context = []
    sources = []

    for doc in docs:
        context.append(doc.page_content)

        source_name = doc.metadata.get("source", "Unknown Document")
        source_link = doc.metadata.get("link", "No link available")

        sources.append({
            "name": source_name,
            "link": source_link
        })

    return {
        "context": "\n\n".join(context),
        "sources": sources
    }

# -------------------------
# LLM
# -------------------------
llm = ChatOpenAI(
    base_url="https://router.huggingface.co/v1",
    api_key=os.environ.get("HF_TOKEN"),
    model="openai/gpt-oss-120b:novita",
    temperature=0.3
)

# -------------------------
# PROMPT
# -------------------------
prompt = PromptTemplate(
    template="""
    You are a professional HR Assistant.
    Use the provided context to answer the question.
        - leave policy
        - salary
        - attendance
        - benefits
        - company rules
        - company policies

    Returns concise and accurate answers from HR documents with sources and links.

---------------------
Context:
{context}

---------------------
Question:
{question}

---------------------
Answer:
""",
    input_variables=["context", "question"]
)

parser = StrOutputParser()

# -------------------------
# MAIN TOOL FUNCTION
# -------------------------
@traceable(run_type="chain", name="rag_pipeline")
def hr_policy_tool(query: str) -> str:
    retriever = get_retriever()

    docs = retriever.invoke(query)
    formatted = format_docs_with_sources(docs)

    chain = prompt | llm | parser

    answer = chain.invoke({
        "context": formatted["context"],
        "question": query
    })

    source_text = "\n\n📄 Sources:\n"

    unique_sources = {}
    for s in formatted["sources"]:
        unique_sources[s["name"]] = s["link"]

    for name, link in unique_sources.items():
        source_text += f"- {name}\n  🔗 {link}\n"

    return answer + source_text


if __name__ == "__main__":
    while True:
        q = input("\nAsk HR: ")

        if q.lower() in ["exit", "quit"]:
            break

        print("\n", hr_policy_tool(q))