"""Shared test fixtures for pdf-tool tests."""

from io import BytesIO
from pathlib import Path

import pytest
from PyPDFForm import Fields, PdfWrapper
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def simple_pdf(fixtures_dir: Path) -> Path:
    """Create a simple PDF with text at known positions."""
    path = fixtures_dir / "simple.pdf"
    c = canvas.Canvas(str(path), pagesize=A4)
    _, height = A4

    # Page 1: some labels
    c.setFont("Helvetica", 12)
    c.drawString(50, height - 100, "Organization:")
    c.drawString(200, height - 100, "Stadt München")
    c.drawString(50, height - 150, "Contact:")
    c.drawString(50, height - 200, "Date:")
    c.showPage()

    # Page 2: more text
    c.setFont("Helvetica", 12)
    c.drawString(50, height - 100, "Seite 2")
    c.drawString(50, height - 150, "Unterschrift:")
    c.showPage()

    c.save()
    return path


@pytest.fixture
def form_pdf(fixtures_dir: Path) -> Path:
    """Create a PDF with AcroForm fields."""
    path = fixtures_dir / "form.pdf"

    packet = BytesIO()
    c = canvas.Canvas(packet, pagesize=A4)
    _, height = A4
    c.setFont("Helvetica", 12)
    c.drawString(50, height - 100, "Company:")
    c.drawString(50, height - 150, "Date:")
    c.save()
    packet.seek(0)

    wrapper = PdfWrapper(packet)
    wrapper.bulk_create_fields(
        [
            Fields.TextField(
                name="Company",
                page_number=1,
                x=200,
                y=height - 115,
                width=200,
                height=20,
            ),
            Fields.TextField(
                name="Date",
                page_number=1,
                x=200,
                y=height - 165,
                width=200,
                height=20,
            ),
            Fields.CheckBoxField(
                name="TermsAccepted",
                page_number=1,
                x=200,
                y=height - 215,
                size=15,
            ),
        ]
    )
    wrapper.write(str(path))
    return path


@pytest.fixture
def multipage_pdf(fixtures_dir: Path) -> Path:
    """Create a 5-page PDF for page range testing."""
    path = fixtures_dir / "multipage.pdf"
    c = canvas.Canvas(str(path), pagesize=A4)
    _, height = A4

    for i in range(5):
        c.setFont("Helvetica", 14)
        c.drawString(50, height - 100, f"Page {i + 1} Title")
        c.setFont("Helvetica", 10)
        c.drawString(50, height - 130, f"Content on page {i + 1}")
        c.showPage()

    c.save()
    return path


@pytest.fixture
def acroform_pdf(fixtures_dir: Path) -> Path:
    """PDF with a real document-level /AcroForm (reportlab acroForm API).

    Unlike the PyPDFForm-built form_pdf, fields here are registered in the
    catalog's /AcroForm /Fields array — what standard tools resolve.
    """
    path = fixtures_dir / "acroform.pdf"
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setFont("Helvetica", 12)
    c.drawString(50, 700, "Company:")
    c.acroForm.textfield(name="Company", x=200, y=600, width=200, height=20)
    c.acroForm.checkbox(name="Terms", x=200, y=550, size=15)
    c.save()
    return path


@pytest.fixture
def encrypted_pdf(fixtures_dir: Path) -> Path:
    """Create a password-encrypted single-page PDF."""
    from pypdf import PdfWriter

    path = fixtures_dir / "encrypted.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    writer.encrypt("secret")
    with open(path, "wb") as f:
        writer.write(f)
    return path


@pytest.fixture
def p12_certificate(fixtures_dir: Path) -> Path:
    """Self-signed PKCS#12 certificate (passphrase 'test') for crypto signing."""
    import datetime

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import pkcs12
    from cryptography.x509.oid import NameOID

    path = fixtures_dir / "signer.p12"
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test Signer")])
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    blob = pkcs12.serialize_key_and_certificates(
        b"signer", key, cert, None, serialization.BestAvailableEncryption(b"test")
    )
    path.write_bytes(blob)
    return path


@pytest.fixture
def signature_png(fixtures_dir: Path) -> Path:
    """Create a simple transparent PNG for signature testing."""
    from PIL import Image, ImageDraw

    path = fixtures_dir / "signature.png"
    img = Image.new("RGBA", (300, 100), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    draw.text((10, 30), "Max Mustermann", fill=(0, 0, 0, 255))
    img.save(str(path))
    return path
