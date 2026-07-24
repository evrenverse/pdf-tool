# Compatibility

| Area | Supported |
| --- | --- |
| Python | 3.12, 3.13, 3.14 |
| Operating systems | Linux |
| Document format | PDF files supported by the locked parser stack |
| Optional integration | Poppler for `read --image` |
| Package installation | Git checkout or release wheel through `uv tool` |

CI tests all supported Python minors on Linux, including a job without the
optional integration installed. The primary job installs Poppler and runs formatting, linting, mypy,
branch-coverage enforcement, the agent eval, package build, and metadata check.

Pages are always zero-based. Overlay coordinates default to a top-left origin;
PDF-space coordinates and rendered-image scaling are explicit. Encrypted PDFs,
OCR, full complex-script font coverage, and preservation of every proprietary
extension are not promised.
