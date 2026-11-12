# FS-015a — title generation integration boundary

Status: **preparatory offline contract only**. Issue #34 remains OPEN.

`app.production.title_contract.build_title_brief` accepts only a previously
owner-scoped `load_fact_dossier(...)` snapshot and runs the existing fail-closed
`prepare_script_preview` guard. If no usable, reviewed, source-supported fact
exists, the contract refuses to generate a title brief. It includes at most 12
safe template sentences and their supporting URL/source IDs, never source
articles, reviewer notes or arbitrary assertions.

`validate_title_candidates` requires exactly three unique plain-text English
title strings, the literal selected club name and no numerals that were not in
the reviewed sentences. This is only a **mechanical check**: even an accepted
title may contain a false unnumbered claim and **requires human editorial
review**. No title is stored or exposed to the browser by this change.

Follow-up before completing #34:

1. Product Owner selects and approves a model/provider and acceptable privacy,
   rights and pricing; #8 is still open. Configure the existing shared budget
   gate (#90) with the approved <= 10 USD/month cap. Paid requests remain OFF.
2. Implement an explicitly invoked provider adapter with conservative
   reservation, second pre-dispatch check, trustworthy settlement or uncertainty
   retention, no leaked payloads/secrets and no silent retry.
3. Record per-request model, provider, price revision, cost, safe response
   metadata, dossier version and job owner; store no untrusted provider output as
   verified facts.
4. Owner-only UI and explicit title choice belong to #35, and must not silently
   run a paid model on a GET request.
5. Prove a fake-provider end-to-end flow and all four CI jobs before merging
   production integration. No production paid request without separate approval.

Offline tests: `python manage.py test app.production.test_title_contract`.
