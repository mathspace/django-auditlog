# django-auditlog threat model

## Overview

A Django extension records registered model lifecycle changes through signals, optionally attributes them to request users with middleware, and exposes historical rows through ORM helpers and Django admin. This fork writes auditlog_logentry_historical and routes new entries to the changed instance database when supplied (src/auditlog/registry.py:41; src/auditlog/models.py:58; src/auditlog/models.py:189). It runs inside the caller process rather than as a standalone authentication or audit service.

The normal integration installs the package into a Django application, registers selected models and optionally installs its middleware and admin. The caller still owns authentication, model access, database credentials, transaction boundaries and the audience for history. Logging a mutation does not authorize it. This model concerns the public library and generic integration duties; no particular production application, tenant layout or edge configuration is assumed.

| Component | Source |
| --- | --- |
| Registry, lifecycle and M2M capture | src/auditlog/registry.py:41; src/auditlog/receivers.py:10 |
| Historical persistence and querying | src/auditlog/models.py:25; src/auditlog/models.py:63 |
| Request attribution and admin rendering | src/auditlog/middleware.py:29; src/auditlog/mixins.py:65 |
| Operator purge and package | src/auditlog/management/commands/auditlogflush.py:9; setup.py:3 |

| Deployment or workflow | Resource or capability | Configuration and precedence | Safe effective value or location | Readers, writers, or recipients | Enforcing control | Evidence or unknowns |
| --- | --- | --- | --- | --- | --- | --- |
| Library embedded in Django | Audit row creation | Registered model signal → LogEntry manager → instance._state.db when nonempty; otherwise manager routing | auditlog_logentry_historical on instance._state.db; unspecified/empty instance DB uses manager routing | Database readers, backups, Django admin/history consumers | Django DB routing/access; registry include/exclude selection at src/auditlog/diff.py:129 | src/auditlog/models.py:58; src/auditlog/models.py:189 |
| Operator management command | History deletion | Operator command → LogEntry.objects.all() → host manager routing | All LogEntry rows selected by command manager | Host database | Local command authority plus explicit y prompt | src/auditlog/management/commands/auditlogflush.py:15 |
| Registered model CREATE capture | Reused-primary-key history cleanup | CREATE action + content type/object ID → LogEntry manager filter/delete before insertion | Prior matching historical rows on current LogEntry manager routing; not explicitly rebound to instance._state.db | Host audit database | Application CREATE semantics and host manager/database permissions | src/auditlog/models.py:51; src/auditlog/models.py:58 |

## Threat Model, Trust Boundaries, and Assumptions

**Protected assets.** Old/new field values, object representations, additional_data, actor IDs and remote addresses stored in audit rows (src/auditlog/models.py:175). Audit provenance and retention; model/database authority remains that of the caller connection (src/auditlog/models.py:58).

**Actors and starting authority.** A host user may influence editable model fields and request headers, but is not thereby entitled to register models, control Django settings or read audit storage. An operator with management-command/database access can purge history; that is existing operator authority, not an end-user capability (src/auditlog/management/commands/auditlogflush.py:9).

**Trust boundaries and owned controls.**

- Application model save/delete signals cross into historical persistence; register chooses classes, include/exclude fields and custom handlers. Update comparison reads sender.objects by primary key; logging is not authorization of the original mutation (src/auditlog/registry.py:53; src/auditlog/receivers.py:36).
- Middleware consumes an authenticated request.user from caller authentication; first X-Forwarded-For value overrides REMOTE_ADDR. Thread-local dispatch identity gates actor attachment and response/exception hooks disconnect signals. Trusted proxy header normalization belongs to the host (src/auditlog/middleware.py:29; src/auditlog/middleware.py:49; src/auditlog/middleware.py:73).
- JSON text is generated from diffs and parsed for display. Admin uses format_html for cells; password masking in msg is presentation-only, whereas diff persistence retains included values (src/auditlog/receivers.py:24; src/auditlog/diff.py:150; src/auditlog/mixins.py:65).
- Django admin registration inherits host site permissions; related-object query helpers filter identity, not user/tenant entitlement. Library users must authorize history readers separately (src/auditlog/admin.py:7; src/auditlog/models.py:63).
- CREATE capture removes prior audit rows for a reused content type/primary key using the current LogEntry manager before insertion. Cleanup routing is therefore separate from the explicit instance-database insertion; host multi-database and retention expectations must cover both (src/auditlog/models.py:51; src/auditlog/models.py:58).

**Security objectives.** Keep log readers authorized for the full historical values, including data omitted from current records. Preserve actor isolation and treat forwarded addresses as provenance metadata rather than authenticated identity. Choose capture exclusions before persistence and define retention independently from admin presentation.

**Assumptions and unresolved controls.**

- Signal coverage depends on host mutation paths and registry flags; do not infer complete coverage of bulk SQL or independent writers (src/auditlog/registry.py:134).
- Packaging names django-auditlog 0.4.5; no release workflow appears in the supplied tree, so publisher access is unknown (setup.py:3).
- Host DB routers, historical-data retention, permitted audit readers and required mutation coverage remain unresolved. No append-only database control or automatic protection of backups is established by this library.

## Attack Surface, Mitigations, and Attacker Stories

These are prioritized hypotheses, not validated vulnerabilities. Each requires its stated caller, data and exposure prerequisites; ordinary use of authority already granted is not a new capability.

| Priority | Scenario and capability gain | Prerequisites | Impact | Existing controls | Mitigation | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | An ordinary user obtains historical values beyond their current-object access through a host history endpoint or broadly exposed audit admin. | A host exposes log queries to readers who lack equivalent history entitlement. | Disclosure of deleted or prior personal/secret values. | Object identity filters and Django admin permissions; include/exclude fields control capture. | Authorize history readers and minimize stored fields before insertion. | src/auditlog/models.py:63; src/auditlog/admin.py:7; src/auditlog/diff.py:129 |
| 2 | User-controlled forwarded-address data is mistaken for authenticated provenance, or host context integration attributes a mutation to another request. | Unnormalized proxy headers or a demonstrated context-lifecycle failure; header control alone cannot select actor. | Misleading incident attribution or accountability. | Authenticated request.user, thread-local dispatch identity and disconnect hooks. | Normalize proxy headers; preserve middleware ordering and request cleanup; do not authorize by remote_addr. | src/auditlog/middleware.py:29; src/auditlog/middleware.py:49; src/auditlog/middleware.py:73 |
| 2 | A captured secret becomes available to a log reader because presentation masking is assumed to redact storage. | Sensitive fields remain included; a reader can access persisted JSON or another representation. | Disclosure despite a masked admin cell. | Field exclusion; format_html escaping; password masking in msg. | Exclude secrets during diff construction and govern backups/exports as historical data. | src/auditlog/diff.py:150; src/auditlog/mixins.py:65 |
| 3 | A host treats signal history as a complete immutable ledger despite alternate writes, capture suppression or operator purge. | A real requirement covers paths outside registered signals, or a lower-trust actor can invoke privileged controls. | Missing evidence or unauthorized history deletion. | Registry selection and flags; purge requires management authority and y confirmation. | Enumerate required mutation paths and narrowly grant purge/database authority. | src/auditlog/registry.py:134; src/auditlog/management/commands/auditlogflush.py:15 |

## Severity Calibration (Critical, High, Medium, Low)

| Level | Repository-specific example | Counterexample or limiting prerequisite |
| --- | --- | --- |
| Critical | A demonstrated history-access failure exposes a large, highly sensitive dataset or reusable privileged credentials. | Requires actual captured contents, reader reachability and broad impact; a logging package alone does not establish it. |
| High | A lower-privilege reader gains another user’s sensitive historical records or a meaningful secret. | Authorized administrators reading their intended audit data are expected recipients. |
| Medium | A reachable attribution or capture failure materially defeats a defined accountability requirement. | A spoofed address with correctly bound actor and no downstream reliance may have much less impact. |
| Low | Limited metadata disclosure or a localized display/diagnostic defect without confidential values or authority gain. | Intentional operator purge and configured exclusions are not vulnerabilities by themselves. |

This model uses an independent source-backed architecture pass. Repository citations were checked against the supplied inventory and source lines; application code and external services were not executed. Source-established behavior is distinct from unverified deployment exposure. Revisit the model when the described input, storage, authorization or publication boundaries change.

Repository: github.com/mathspace/django-auditlog
Version: d2477be143347c3f5d280fe6e701c0d3bda1ca0d
