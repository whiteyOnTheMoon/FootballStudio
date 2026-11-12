# FS-015a / #34: Provider-neutral guarded title generation seam

**Scope:** An offline-testable internal service boundary, **not an integrated
LLM provider** or completed title-selection experience. Existing #34 and #35
remain open. No endpoint, web button, worker queue, provider SDK, service URL,
secret or external network code is added.

The trusted caller explicitly provides an owner, existing job ID and dossier
version, operator-approved LLM tariff key, pessimistic maximum billing units,
fresh UUIDv4 and a trusted backend object. The service re-checks owner access
and loads a versioned dossier via `load_fact_dossier`. It uses the existing
`build_title_brief` fail-closed reviewed-fact contract.

**Two independent gates** must be open before any backend invocation:
`TITLE_LLM_ENABLED` (hardcoded `False` for this release) and the existing
`PAID_API_CALLS_ENABLED` (also off in production). An approved LLM-only
rate card with available credential, correctly configured shared monthly cap,
database budget lock, conservative maximum units and fresh UUIDv4 are required.
The exact request is reserved against the shared UTC monthly USD cap (10 USD
approved ceiling) before dispatch. The dispatch marker is written immediately
before calling the trusted backend. If dispatch is uncertain, the reservation
remains committed; known trusted costs are settled before title validation,
including when the title output is rejected. A new retry requires a new UUID
and a new budget check. No raw requests/responses or credentials are stored in
this service. All backend errors are converted into safe codes.

A backend must return exactly a `TitleBackendResult`: structured candidate
titles plus a trusted billed USD amount and a positive billing confirmation.
Failure to provide reliable accounting **does not** silently settle as zero:
it keeps the reservation uncertain and does not accept the output. Successful
results require exactly three structurally validated unique candidates and
still require **human editorial selection**; there is no automatic update of
the ProductionJob title. Review of semantic truth and potential unnumbered
hallucinations remains mandatory.

## Test / rollout

`python manage.py test app.production.test_title_llm_adapter`

Fake-only tests cover default-off, paid gate, owner isolation, missing dossiers,
no reviewed facts, cost exhaustion, wrong tariff purpose, successful settlement,
unsafe titles after billing, unknown cost, provider exception and replay.
No genuine provider is contacted; production must remain disabled.

Before real integration: #8 provider/model/privacy/cost approval; verified
supplier upper-bound pricing and usage response; separate reviewed adapter;
a secure explicit user/request queue with idempotency; a controlled artifact
and audit model for full #34 completion; UI title choice #35. Never toggle
either setting merely to demonstrate a fake-provider test in production.
