from datetime import date
from time import monotonic, sleep

import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.auditor import AuditorAlert, AuditorRuleSet, AuditorRun
from app.schemas.auditor import AlertKind, RuleType
from app.services import auditor_service
from app.services.auditor_detection import compare_rules
from app.services.auditor_rules import extract_rules
from tests.conftest import auth_headers
from tests.test_organizations import create_external_user


AS_OF = date(2026, 11, 11)


@pytest.fixture(autouse=True)
def freeze_auditor_date(monkeypatch):
    class CaseDate(date):
        @classmethod
        def today(cls):
            return AS_OF

    monkeypatch.setattr(auditor_service, "date", CaseDate)
    monkeypatch.setattr("app.api.auditor.date", CaseDate)


def policy(amount, *, department="Operações", period="01/01/2026 a 31/12/2027", extra=""):
    return (f"Assunto: reembolso de viagens\nDepartamento: {department}\nVigência: {period}\n"
            f"O limite de reembolso é R$ {amount},00.\n{extra}").rstrip()


def upload(client, headers, filename, content, **data):
    response = client.post("/api/documents", headers=headers, data=data,
                           files={"file": (filename, content.encode(), "text/plain")})
    assert response.status_code == 201, response.text
    doc = response.json()
    assert doc["status"] == "READY", doc
    return doc


def wait_for_run(client, headers, key):
    deadline = monotonic() + 10
    while monotonic() < deadline:
        response = client.get(f"/api/auditor/runs/{key}", headers=headers)
        assert response.status_code == 200, response.text
        row = response.json()
        if row["status"] not in ("queued", "running"):
            return row
        sleep(0.03)
    raise AssertionError("A auditoria não concluiu no tempo previsto")


def start(client, headers, doc, previous=None):
    response = client.post("/api/auditor/runs", headers=headers,
                           json={"document_id": doc["id"], "previous_document_id": previous})
    assert response.status_code == 202, response.text
    return response.json()["id"]


def list_alerts(client, headers, **params):
    response = client.get("/api/auditor/alerts", headers=headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()["items"]


def test_extracts_amount_deadline_percent_obligation_and_literal_evidence():
    sections = [{"page": 3, "location": "Página 3", "text": policy(150, extra=(
        "O prazo de entrega é 14 dias úteis.\nA taxa de reembolso é 5,5%.\n"
        "É obrigatório registrar o protocolo PR-437.\nÉ proibido divulgar credenciais."))}]
    rules, limited = extract_rules(41, 2, sections)
    assert not limited
    by_kind = {rule.kind: rule for rule in rules}
    assert by_kind[RuleType.FINANCIAL_LIMIT].value == "150"
    assert by_kind[RuleType.DEADLINE].unit == "dia_uteis"
    assert by_kind[RuleType.PERCENTAGE].value == "5.5"
    assert by_kind[RuleType.OBLIGATION].policy_id == "PR-437"
    assert RuleType.PROHIBITION in by_kind
    assert by_kind[RuleType.VALIDITY].valid_from == date(2026, 1, 1)
    for rule in rules:
        source = rule.evidence
        assert source.document_id == 41 and source.version == 2 and source.page == 3
        assert sections[source.section_index]["text"][source.start:source.end] == source.excerpt


@pytest.mark.parametrize(("kwargs", "expected"), [
    ({}, AlertKind.POSSIBLE_CONTRADICTION),
    ({"department": "Jurídico"}, None),
    ({"period": "01/01/2028 a 31/12/2029"}, None),
    ({"extra": "Exceção: viagens emergenciais"}, None),
    ({"extra": "Condição: aprovação excepcional"}, AlertKind.NEEDS_CLARIFICATION),
])
def test_comparison_distinguishes_periods_departments_and_exceptions(kwargs, expected):
    first, _ = extract_rules(1, 1, [{"text": policy(150)}])
    second, _ = extract_rules(2, 1, [{"text": policy(200, **kwargs)}])
    left = next(rule for rule in first if rule.kind == RuleType.FINANCIAL_LIMIT)
    right = next(rule for rule in second if rule.kind == RuleType.FINANCIAL_LIMIT)
    result = compare_rules(left, right, AS_OF)
    assert (result.kind if result else None) == expected


def test_full_workflow_review_versions_and_existing_rag(client):
    user = auth_headers(client)
    original = upload(client, user, "reembolso.txt", policy(150))
    peer = upload(client, user, "politica-corporativa.txt", policy(200))
    benign = upload(client, user, "politica-juridico.txt", policy(300, department="Jurídico"))
    key = start(client, user, original)
    assert wait_for_run(client, user, key)["outcome"] == "ALERTS_FOUND"
    assert start(client, user, original) == key
    mirror = start(client, user, peer)
    assert wait_for_run(client, user, mirror)["status"] == "done"
    alerts = list_alerts(client, user, kind="POSSIBLE_CONTRADICTION", q="reembolso")
    assert len(alerts) == 1 and {item["id"] for item in alerts[0]["documents"]} == {original["id"], peer["id"]}
    assert all(benign["id"] not in {doc["id"] for doc in alert["documents"]} for alert in alerts)
    alert_id = alerts[0]["id"]
    alert_path = f"/api/auditor/alerts/{alert_id}"
    result = client.get(alert_path + "/evidence", headers=user).json()
    assert {item["value"] for item in result} == {"150", "200"}
    for item in result:
        ref = item["evidence"]
        document = f"/api/documents/{ref['document_id']}"
        original_text = client.get(document + "/file", headers=user)
        preview = client.get(document + "/preview", headers=user).json()["sections"]
        assert original_text.status_code == 200
        assert preview[ref["section_index"]]["text"][ref["start"]:ref["end"]] == ref["excerpt"]

    decisions = [("FALSE_POSITIVE", "Conferência inicial para demonstração."),
                 ("CONFIRMED", "Os dois limites se aplicam ao mesmo departamento.")]
    for state, reason in decisions:
        updated = client.post(alert_path + "/reviews", headers=user, json={"state": state, "justification": reason})
        assert updated.status_code == 200 and updated.json()["state"] == state
    duplicate = client.post(alert_path + "/reviews", headers=user,
                            json={"state": decisions[-1][0], "justification": decisions[-1][1]})
    assert len(duplicate.json()["reviews"]) == 2

    newer = upload(client, user, "reembolso.txt", policy(200, extra="É obrigatório guardar o recibo."))
    assert newer["version"] == 2
    assert client.get(f"/api/auditor/documents/{newer['id']}/versions", headers=user).json()[0]["id"] == original["id"]
    revised_key = start(client, user, newer)
    assert wait_for_run(client, user, revised_key)["outcome"] == "ALERTS_FOUND"
    assert list_alerts(client, user, kind="POSSIBLE_CONTRADICTION") == []
    historical = list_alerts(client, user, kind="POSSIBLE_CONTRADICTION", include_historical=True)
    assert historical[0]["historical"] and historical[0]["state"] == "CONFIRMED"
    changes = client.get(f"/api/auditor/documents/{newer['id']}/changes", headers=user).json()["items"]
    assert any({item["value"] for item in row["evidence"]} == {"150", "200"} for row in changes)
    assert any("sem equivalente" in row["explanation"] for row in changes)
    resolved = client.post(alert_path + "/reviews", headers=user,
                           json={"state": "RESOLVED", "justification": "A versão 2 harmonizou os limites."})
    assert resolved.json()["state"] == "RESOLVED"
    cid = client.post("/api/chats", headers=user, json={"document_ids": [newer["id"]]}).json()["id"]
    answer = client.post(f"/api/chats/{cid}/messages", headers=user, json={"message": "Qual é o limite de reembolso?"})
    assert answer.status_code == 200 and answer.json()["sources"][0]["document_id"] == newer["id"]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(AuditorRuleSet)) == 4


def test_team_org_revocation_and_delete_protect_all_auditor_reads(client):
    owner = auth_headers(client, "outro@aiup.local")
    member = auth_headers(client)
    admin = auth_headers(client, "admin@aiup.local")
    member_id = client.get("/api/auth/me", headers=member).json()["id"]
    owner_id = client.get("/api/auth/me", headers=owner).json()["id"]
    team = client.post("/api/organizations/teams", headers=admin, json={"name": "Viagens"}).json()
    members = f"/api/organizations/teams/{team['id']}/members"
    assert client.put(members, headers=admin, json={"user_ids": [owner_id, member_id]}).status_code == 200
    private = upload(client, owner, "sigiloso.txt", policy(500), visibility="PRIVATE")
    shared = upload(client, owner, "projeto-reservado.txt", policy(200), visibility="TEAM", team_id=str(team["id"]))
    own = upload(client, member, "despesas.txt", policy(150))
    _, external_email = create_external_user()
    external = auth_headers(client, external_email)
    key = start(client, member, own)
    assert wait_for_run(client, member, key)["outcome"] == "ALERTS_FOUND"
    alerts = list_alerts(client, member)
    assert len(alerts) == 1 and {item["id"] for item in alerts[0]["documents"]} == {shared["id"], own["id"]}
    assert private["id"] not in {item["id"] for item in alerts[0]["documents"]}
    path = f"/api/auditor/alerts/{alerts[0]['id']}"
    for endpoint in (path, path + "/evidence", f"/api/auditor/runs/{key}"):
        assert client.get(endpoint, headers=external).status_code == 404
    assert client.post("/api/auditor/runs", headers=external, json={"document_id": shared["id"]}).status_code == 404
    assert client.put(members, headers=admin, json={"user_ids": [owner_id]}).status_code == 200
    assert client.get(path, headers=member).status_code == 404
    assert client.get(path + "/evidence", headers=member).status_code == 404
    assert client.get(f"/api/auditor/runs/{key}", headers=member).status_code == 404
    assert client.post(path + "/reviews", headers=member, json={"state": "CONFIRMED", "justification": "Tentativa."}).status_code == 404
    export = client.get("/api/auditor/alerts/export?include_historical=true&q=projeto-reservado", headers=member)
    assert export.json()["total"] == 0 and "projeto-reservado" not in export.text
    assert list_alerts(client, member, include_historical=True) == []
    assert client.delete(f"/api/documents/{shared['id']}", headers=owner).status_code == 204
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(AuditorAlert)) == 0


def test_automatic_audit_after_indexing_and_cooperative_cancel(client, monkeypatch):
    headers = auth_headers(client)
    monkeypatch.setattr(get_settings(), "auditor_automatic", True)
    first = upload(client, headers, "despesas.txt", policy(150))
    key = start(client, headers, first)
    assert wait_for_run(client, headers, key)["status"] == "done"
    assert len(client.get("/api/auditor/runs", headers=headers).json()) == 1
    monkeypatch.setattr(get_settings(), "auditor_automatic", False)
    second = upload(client, headers, "reembolso.txt", policy(200))
    real_execute = auditor_service.execute
    with monkeypatch.context() as isolated:
        isolated.setattr(auditor_service, "execute", lambda *_: None)
        key = start(client, headers, second)
        cancel = client.post(f"/api/auditor/runs/{key}/cancel", headers=headers)
        assert cancel.status_code == 200 and cancel.json()["status"] == "cancelled"
    with SessionLocal() as db:
        attempt = db.get(AuditorRun, key).attempt
    real_execute(key, attempt)
    assert list_alerts(client, headers) == []
    with monkeypatch.context() as isolated:
        isolated.setattr(auditor_service, "execute", lambda *_: None)
        assert start(client, headers, second) == key
        real_execute(key, attempt)
        with SessionLocal() as db:
            run = db.get(AuditorRun, key)
            assert run.status == "queued" and run.attempt != attempt
            retry_attempt = run.attempt
    real_execute(key, retry_attempt)
    assert wait_for_run(client, headers, key)["outcome"] == "ALERTS_FOUND"


def test_auditor_evidence_opens_the_original_pdf_page(client):
    import pymupdf

    headers = auth_headers(client)
    def upload_pdf(name, value):
        with pymupdf.open() as pdf:
            cover = pdf.new_page()
            cover.insert_text((72, 72), "Capa de demonstracao. Este documento descreve uma politica de viagens corporativas.")
            source = pdf.new_page()
            source.insert_text((72, 72), f"O limite de reembolso de viagens corporativas e R$ {value},00.")
            data = pdf.tobytes()
        response = client.post("/api/documents", headers=headers, files={"file": (name, data, "application/pdf")})
        assert response.status_code == 201
        return response.json()

    anchor = upload_pdf("manual-viagem.pdf", 150)
    upload_pdf("circular-viagem.pdf", 200)
    assert wait_for_run(client, headers, start(client, headers, anchor))["outcome"] == "ALERTS_FOUND"
    evidence = list_alerts(client, headers)[0]["evidence"]
    assert len(evidence) == 2 and all(item["evidence"]["page"] == 2 for item in evidence)
    for item in evidence:
        ref = item["evidence"]
        page = client.get(f"/api/documents/{ref['document_id']}/pages/{ref['page']}", headers=headers)
        assert page.status_code == 200 and page.content.startswith(b"\x89PNG")


def test_restart_marks_unfinished_audit_retriable(client, monkeypatch):
    import asyncio
    from app.main import app, lifespan

    user = auth_headers(client)
    anchor = upload(client, user, "despesa.txt", policy(150))
    upload(client, user, "politica.txt", policy(200))
    with monkeypatch.context() as isolated:
        isolated.setattr(auditor_service, "execute", lambda *_: None)
        key = start(client, user, anchor)

    async def restart():
        async with lifespan(app):
            pass

    asyncio.run(restart())
    stopped = client.get(f"/api/auditor/runs/{key}", headers=user).json()
    assert stopped["status"] == "error" and "reiniciado" in stopped["error"]
    assert start(client, user, anchor) == key
    assert wait_for_run(client, user, key)["outcome"] == "ALERTS_FOUND"
