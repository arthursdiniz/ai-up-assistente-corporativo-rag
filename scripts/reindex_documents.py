"""Rebuild indexes offline after verifying a backup; original files/IDs stay intact."""
import argparse
from pathlib import Path
import socket
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts._environment import load_user_environment
load_user_environment()
from scripts.backup import verify
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.document import Document
from app.services.document_service import DocumentService
from sqlalchemy import select


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup",required=True,type=Path)
    parser.add_argument("--all",action="store_true")
    args=parser.parse_args()
    verify(args.backup)
    with socket.socket() as sock:
        if sock.connect_ex(("127.0.0.1",8000)) == 0:
            raise SystemExit("Encerre o servidor antes da reindexação em lote.")
    settings=get_settings();service=DocumentService(settings)
    with SessionLocal() as db:
        documents=list(db.scalars(select(Document).order_by(Document.id)))
        selected=[d for d in documents if args.all or d.index_version != service.index_version(settings)]
        failures=0
        for index,doc in enumerate(selected,1):
            service.process(db,doc)
            failures+=bool(doc.error_message)
            print(f"{index}/{len(selected)} · documento #{doc.id}: {doc.processing_stage}",flush=True)
        print(f"Concluídos: {len(selected)-failures}; com erro: {failures}.")
        if failures:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
