# PocketCFO AI

PocketCFO AI is a local-first finance workspace for freelancers, independent
developers, designers, video editors, and small creative businesses. It helps
people review invoice details, record income and expenses, and see cash flow
without sending invoice text to a hosted AI service.

This is a portfolio MVP, not production accounting software. AI extraction can
be wrong; review source invoices and records yourself. The app does not provide
tax, legal, or accounting advice and does not connect to banks.

## What it does

- Review selectable text from PDFs and prepare an editable invoice draft with
  the local `qwen2.5:3b` Ollama model.
- Save invoices only after explicit review, or enter invoices manually without
  using AI.
- Track unpaid, overdue, and paid invoices. An unpaid invoice is never counted
  as received income.
- Confirm a payment explicitly and create one linked income transaction using
  the invoice total and currency and a payment date you confirm.
- Create, search, filter, edit, and delete transactions and invoices. Deletions
  require an in-app confirmation.
- View date-filtered cash flow, outstanding invoice totals, overdue invoices,
  spending by category, and currency-separated analytics.
- Export filtered transaction and invoice records to CSV in memory.

All monetary summaries keep currencies separate. The app does not convert
currencies or add unlike currencies together.

## Demo

Screenshots and a short demo recording can be added here before publication.
No customer testimonials, benchmark claims, or live demo are included in this
repository.

## Architecture

- `app.py` — Streamlit navigation, forms, dashboard, and charts.
- `pocketcfo/pdf_extractor.py` — PDF size/type checks and selectable-text
  extraction in memory.
- `pocketcfo/ai_extractor.py` — JSON extraction through Ollama on
  `127.0.0.1:11434`; response normalization is handled by validation code.
- `pocketcfo/validation.py` — invoice, transaction, currency, date, and amount
  validation.
- `pocketcfo/database.py` — parameterized SQLite operations, duplicate
  prevention, and payment confirmation transactions.
- `pocketcfo/reports.py` — date filtering, per-currency calculations, invoice
  statuses, charts' source data, and in-memory CSV generation.
- `tests/` — `unittest` coverage using temporary databases, synthetic PDFs, and
  mocked Ollama responses.

## Local AI and data handling

The Python app uses PyMuPDF for PDF text extraction, SQLite for saved invoice
fields and transactions, and a local Ollama service for AI extraction. PDF bytes
are processed in memory and are not saved by the app. SQLite stores the
confirmed invoice fields, transactions, an optional SHA-256 digest for repeat
PDF detection, and payment dates; it does not store the PDF or extracted raw
text. CSV exports are also generated in memory.

When extraction is requested, invoice text is sent to Ollama at
`http://127.0.0.1:11434`; this is intended to be a service on the same machine.
The app code does not configure a hosted AI API or send invoice content to an
external AI provider. Initial Python package/model downloads require network
access. Do not expose the local Ollama or Streamlit ports to an untrusted
network.

The configured Ollama tag is **`qwen2.5:3b`**. Ollama's [Qwen2.5 model
listing](https://ollama.com/library/qwen2.5:3b) says the 3B model is under the
**Qwen license** (the 3B and 72B variants are not Apache 2.0). Review the model's
[license terms](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct/blob/main/LICENSE)
for your intended use, including commercial use, before deployment. This
repository does not select or provide an application license.

### Install Ollama and download the model

1. Install Ollama using its [official download page](https://ollama.com/download).
2. Start Ollama on your computer.
3. In PowerShell, download the configured model once:

   ```powershell
   ollama pull qwen2.5:3b
   ollama list
   ```

The model is several billion parameters, so extraction uses materially more
memory and compute than the database and reporting features. Actual resource
needs and latency vary with the Ollama build, model quantization, operating
system, and hardware. The repository does not claim a minimum hardware
configuration or measured extraction performance. If Ollama or the model is
unavailable, use **Invoices → Add invoice manually** and continue to manage
transactions, reports, and exports without AI.

## Installation and run (Windows)

Open PowerShell in this project directory:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

If `.venv` already exists, skip the `py -m venv .venv` step. No activation is
required when invoking the environment's Python directly. Open the local URL
printed by Streamlit.

## Invoice workflow and status rules

1. Upload a PDF up to 10 MiB. PyMuPDF extracts selectable text without saving
   the file to disk.
2. Ask the local Ollama model for a draft. The request is limited to 40,000
   characters; empty, oversized, malformed, or unreadable input is rejected
   with an actionable message.
3. Review and edit the proposed fields, warnings, and confidence estimates.
   Missing or invalid values are not guessed.
4. Confirm saving, or use the manual invoice form without uploading a PDF or
   using AI. Vendor, currency, and total are required.
5. In **Invoices**, search, filter by status, and correct confirmed fields.
6. An invoice is **Paid** only after the explicit **Mark paid and create income**
   action. That action creates or reconciles one linked income transaction
   using the invoice amount and currency and the confirmed payment date.
7. An invoice is **Overdue** when it is unpaid and its due date is earlier than
   today. Otherwise, an unpaid invoice is **Unpaid**. An invoice without a due
   date remains unpaid rather than being assumed overdue.
8. Deleting a confirmed payment transaction returns its linked invoice to
   unpaid. To correct the total or currency of a paid invoice, delete its linked
   payment first, update the invoice, and confirm payment again if appropriate.

Scanned/image-only PDFs are not OCR'd; use a PDF with selectable text or enter
the invoice manually. AI extraction is optional and never proof of payment.

## Dashboard and exports

Dashboard, transaction, and analytics views support This Month, Last Month,
This Year, All Time, and Custom Range filters. Dashboard cash totals use
transactions dated in the selected period; invoice totals use issue dates in
that period. The outstanding and overdue amounts are grouped by currency.
Income/expense comparisons, monthly cash flow, and spending-by-category charts
use the selected period and one currency at a time.

The transaction page's CSV uses its active search, type, currency, category,
and date filters. Analytics exports use the selected date range; invoice CSV
records are filtered by issue date. Invoice totals are kept separate from cash
received in all summaries.

## Test

The test suite does not contact Ollama or modify the local finance database:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests use temporary SQLite databases and generated in-memory PDFs.

## Known limitations

- No OCR, bank synchronization, currency conversion, recurring transactions,
  tax calculations, multi-user authentication, or cloud backup.
- The app does not independently verify that money reached a bank account.
  Payment confirmation is an explicit record entered by the user.
- Local AI output can omit or misread invoice fields and must be checked.
- Local-only data storage is not a backup strategy. Protect and back up the
  database yourself.
- This MVP has not been validated as production accounting software or with
  real user workflows. Check applicable data-protection and model-license terms
  before using real customer documents.
