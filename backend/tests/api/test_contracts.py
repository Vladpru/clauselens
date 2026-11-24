import pytest
from sqlmodel import select

from app.ingest.pdf import MAX_BYTES
from app.models import Contract
from tests.scripted import FILLER, PAGES


def upload(client, data: bytes, name="c.pdf"):
    return client.post("/api/contracts", files={"file": (name, data, "application/pdf")})


def test_upload_valid_pdf_returns_id_and_page_count(client, services, make_pdf):
    response = upload(client, make_pdf(PAGES[:3]))
    assert response.status_code == 200
    body = response.json()
    assert body["page_count"] == 3
    pages_file = services.settings.data_dir / "contracts" / body["contract_id"] / "pages.json"
    assert pages_file.exists()


@pytest.mark.parametrize(
    ("kind", "status"),
    [("not_pdf", 415), ("oversized", 413), ("too_many_pages", 422), ("scanned", 422)],
)
def test_upload_rejections(client, db, make_pdf, kind, status):
    data = {
        "not_pdf": lambda: b"hello world",
        "oversized": lambda: b"%PDF-" + b"0" * (MAX_BYTES + 1),
        "too_many_pages": lambda: make_pdf([FILLER] * 101),
        "scanned": lambda: make_pdf(["", ""], blank=True),
    }[kind]()
    response = upload(client, data)
    assert response.status_code == status
    assert response.json()["detail"]
    assert db.exec(select(Contract)).all() == []


def test_get_pdf_serves_original(client, make_pdf):
    data = make_pdf(PAGES[:3])
    contract_id = upload(client, data).json()["contract_id"]
    response = client.get(f"/api/contracts/{contract_id}/pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content == data
    assert client.get("/api/contracts/unknown/pdf").status_code == 404
