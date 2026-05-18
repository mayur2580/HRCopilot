from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaIoBaseDownload
import io
from PyPDF2 import PdfReader
from docx import Document
import warnings
warnings.filterwarnings("ignore")
from langsmith import traceable
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']


def get_drive_service():
    creds = service_account.Credentials.from_service_account_file(
        'drive_loader/credentials.json', scopes=SCOPES
    )
    return build('drive', 'v3', credentials=creds)


# -------------------------------
# 🧾 FILE PARSERS
# -------------------------------

def parse_pdf(file_bytes):
    reader = PdfReader(io.BytesIO(file_bytes))
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""
    return text


def parse_docx(file_bytes):
    doc = Document(io.BytesIO(file_bytes))
    return "\n".join([para.text for para in doc.paragraphs])


def parse_txt(file_bytes):
    return file_bytes.decode("utf-8", errors="ignore")

# -------------------------------
# 🚀 MAIN LOADER
# -------------------------------
@traceable(run_type="retriever", name="drive_loader")
def fetch_files_from_folder(folder_id):
    service = get_drive_service()

    results = service.files().list(
        q=f"'{folder_id}' in parents",
        fields="files(id, name, mimeType)"
    ).execute()

    files = results.get('files', [])
    documents = []

    print(f"\n📁 Found {len(files)} files\n")

    for file in files:
        file_id = file['id']
        file_name = file['name']
        mime_type = file['mimeType']

        print(f"📄 Processing: {file_name} ({mime_type})")

        try:
            request = service.files().get_media(fileId=file_id)

            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)

            done = False
            while not done:
                status, done = downloader.next_chunk()
                if status:
                    print(f"   ⬇️ {int(status.progress() * 100)}%")

            file_bytes = fh.getvalue()

            # -------------------------------
            # 🧠 FILE TYPE HANDLING
            # -------------------------------
            if mime_type == "application/pdf":
                content = parse_pdf(file_bytes)

            elif mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
                content = parse_docx(file_bytes)

            elif mime_type == "text/plain":
                content = parse_txt(file_bytes)

            else:
                print(f"⚠️ Skipping unsupported file: {file_name}")
                continue

            documents.append({
                "file_name": file_name,
                "file_id": file_id,
                "mime_type": mime_type,
                "content": content
            })

            print(f"✅ Loaded: {file_name}\n")

        except Exception as e:
            print(f"❌ Error processing {file_name}: {e}\n")

    print(f"🎯 Total documents loaded: {len(documents)}")

    return documents