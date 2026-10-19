# Hacktoberfest Open-Source AI Challenge: Week 2 — Side Hustle Draft

> Draft for review. Confirm the challenge prompt, dates, submission format, and
> eligibility before submitting. This project has not been tested with a user
> cohort; do not present the current implementation as validated market demand.

**Challenge:** Week 2, event ID 80; theme: Side Hustle  
**Window:** October 12–18, 2026; submission deadline October 19, 2026 at 06:59
UTC (11:59 PM PDT on October 18)  
**Required tag:** `hf26challenge`  
**Challenge hub and rules:** <https://dev.to/challenges/hf26>

**Eligibility check before submission:** the challenge requires a new project
and repository started and completed during its challenge window. The existing
prototype's start date has not been verified here. Confirm that it qualifies
before submitting; do not imply that recent polish means the project began
within the challenge period.

## Project

**PocketCFO AI** is a local-first invoice review and cash-flow tracker for
freelancers and small creative businesses.

## The problem

Independent workers often have to move between invoice files and separate
spreadsheets or bookkeeping tools to understand what they billed, what has
actually been paid, and which expenses affect their cash flow. A missed due
date or an unpaid invoice mistaken for received income can make a small
business's financial picture less clear. PocketCFO focuses on making invoice
review, payment recording, and basic income/expense tracking one understandable
workflow.

This problem statement is the product hypothesis behind the prototype, not a
claim based on interviews or customer usage.

## Why open innovation matters

Small businesses should be able to inspect how their financial data is
processed and choose a local workflow rather than depending on a hosted AI
service. Keeping the app's extraction adapter small and its validation,
accounting calculations, and storage visible makes it easier for the community
to inspect, test, and improve the parts that affect trust. Contributors can
also run the app with manual invoice entry and no model.

## Where local AI helps

The optional local Qwen2.5 3B model drafts invoice fields from selectable PDF
text. It can reduce repetitive typing, but it is not authoritative: the user
reviews each field, fixes missing or uncertain values, and confirms before
saving. Invoice content is sent to the user's local Ollama service rather than
a hosted AI API. The configured 3B model is under the Qwen license; users must
review those terms for their intended use.

## Product walkthrough

1. Upload a selectable-text PDF and request a local extraction, or enter an
   invoice manually.
2. Review and edit the suggested invoice data before confirming it.
3. Track an invoice as unpaid, overdue, or paid. Overdue means its due date is
   before today and payment has not been confirmed.
4. Explicitly confirm payment to create or reconcile one linked income
   transaction. The invoice amount is never counted as cash received before
   that action.
5. Filter transactions and date-bounded cash-flow reports, then export CSV.

## Current validation status

The project includes automated unit tests for validation, PDF extraction,
mocked local-model responses, duplicate prevention, per-currency calculations,
CSV preparation, invoice payment linking, and migration from the earlier
invoice schema. Tests use temporary databases and synthetic PDFs. Passing unit
tests do not establish usability, accounting suitability, model accuracy, or
production readiness.

Before presenting this as validated for real freelancers, conduct usability
sessions using consented, redacted or synthetic invoices; test the workflow on
supported hardware; measure extraction quality on a representative,
permission-cleared document set; and review privacy, security, and licensing
requirements. Do not upload real financial documents to a shared demo.

## Demo assets to add before publishing

- Dashboard screenshot (synthetic records only)
- Invoice review and payment-confirmation screenshot (synthetic invoice only)
- Short local run recording or demo link; none is included yet
- Public repository URL; none is included in this draft

## Known limitations

No OCR, bank verification, currency conversion, tax calculations, cloud backup,
or multi-user authentication is included. The app is a portfolio MVP and is not
production accounting software.
