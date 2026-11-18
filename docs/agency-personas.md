# Agency and its three personas (what the Server already gives each)

Written 2026-11-18 from the Server's web app and routes (app 0.10.21). The Server repository is private, so this describes behaviour, not code. Companion to `agency-spec.md`
(requirements) and `agency-design.md` (shape). Status: for review.

## The personas, by job

| | Does | Works in |
|---|---|---|
| **End-user** | Asks questions of governed data, reads answers, brings a file, starts or approves a workflow, says when an answer is wrong | the front-end: Ask today, Agency alongside it |
| **Business analyst** | Decides what the data means and which answers to trust: terms, metrics, trusted questions, reviews what people flagged, curates dashboards | the Server's admin console, areas *Business Catalog* and *Answer Quality* |
| **IT-admin** | Connects sources, decides who can reach what, picks models, keeps it healthy and auditable | the admin console, areas *Data Sources*, *Operations* and *Settings* |

The admin console is one product with six areas, in the order an administrator's work flows: Data Sources, Business Catalog, Answer Quality, Automation, Operations, Settings.
Its sign-in is separate from the end-user's (admin roles `ADMIN` and `READER`; `READER` sees the same console read-only). The same person is often both: a business login to use the
front-end and an admin login to run the back end.

## What the Server already gives each persona

**End-user** (the `/app/*` surface; one business login, session cookie):
ask with streamed progress; conversations; starter questions (from the trusted-question bank); Workspaces (`/app/namespaces`, the session's chosen scope); the list of data sources the session can reach;
the glossary (`/app/knowledge`); a thumbs up/down with a note (`/app/feedback`); **ask an admin for help** (`/app/help-request`); **save an answer as a reusable question** (`/app/questions/save-as-reusable`,
held until an admin approves it); add an answer to a dashboard; **export an answer as PDF or Word** (`/app/ask/report`); **deep analysis** (propose, revise, approve, list); and
**temporary file uploads** (`/app/uploads`: a CSV or Excel file the person can ask about, kept for that conversation only, never a registered source, visible to no one else).
Deny-by-default grants per user: see SQL, see sources, upload files, and (0.10.19) start workflows and approve. `/app/whoami` also reports the edition and whether workflows exist (0.10.20).

**Business analyst** (admin console):
*Business Catalog*: terms and ontology (and a propose-review-approve path for ontology changes), the context glossary every prompt is built with, the governed metric catalog, mechanically verified data rules, column search.
*Answer Quality*: Review (what people flagged as wrong and what they asked for help with, side-by-side answer review with a draft correction), Activity (every question and how it was answered), the
Quality loop board, **Trusted questions** (the curated question-to-SQL pairs served first, and the source of the front-end's starters), Signals (which tables get asked about), Explore (the semantic trace), Dashboards.

**IT-admin** (admin console):
*Data Sources*: sources, uploads, SaaS connectors, MCP servers, documents. *Settings*: models, **Groups (which are the Workspaces)**, security (column tags and the access policy), **Users and access (accounts, roles, the grants above)**,
API and MCP. *Operations*: health, infrastructure (version, licence, certificate, connectivity), system pressure, cost and usage, the audit log.

## The loop that joins them, and why it matters for Agency

```
end-user asks  --thumbs / note / help request-->  Review (analyst)  --approves a fix or a trusted question-->  trusted-question bank  --> starters and fast answers for every end-user
end-user saves a reusable question  ----------->  held until an analyst approves it  ------------------------>  trusted-question bank
IT-admin sets Groups and grants  -------------->  decides which Workspaces and which actions each end-user sees
```

Everything the analyst and the IT-admin do lands in the same Server, so **any front-end that talks to the same `/app/*` routes inherits it for free**: Agency's starter tiles are the analyst's trusted
questions, its Workspaces are the IT-admin's Groups, its grants are the IT-admin's switches, and everything an Agency user asks is audited under their own name (the layer signs in as the user, not as a service).

## What Agency relies on today, and what is missing for the end-user

Relies on: ask, conversations, starters, Workspaces, `whoami` (grants, edition), the workflow routes, the decision-record route.

Ask's end-user features that Agency does **not** have yet, ranked by what they give the other two personas:
1. **Feedback (thumbs and a note) and "ask an admin for help"**: without them an Agency user has no way to tell the analyst an answer is wrong, so the quality loop is blind to Agency.
2. **Save as a reusable question**: how an end-user nominates a trusted question for the analyst.
3. **Temporary file uploads through the Server** (`/app/uploads`): Agency's table adapter describes a CSV but cannot make it askable; the Server route does exactly that (conversation-scoped, same upload grant). Using it closes the largest gap noted in the adapter work.
4. Export an answer, add to a dashboard, the glossary, the sources list, deep analysis: useful, lower priority.

## What Agency adds that has no home for the analyst or IT-admin

Adapters and their licence flags, upload sharing, the pack catalogue and Workspace generation, the workflow definitions manifest, the Temporal gateway and the cloud add-on, the chart rules. Today these are environment
variables, files and READMEs. The admin console shows none of them.

## Identity

- **One session, the user's own.** The layer keeps the Server session cookie and the browser gets only the layer's. That is right for audit and grants.
- **Gap: single sign-on.** The Ask login offers "Continue with <provider>" (a redirect to `/app/oidc/login`). Agency's sign-in is a username and password form, so an organisation that uses SSO cannot sign in to Agency.
- **Admin sign-in is separate** (`/admin/login`). Agency has no way to know a user is also an admin.

## Recommendation

1. **Keep the admin console as the one back end for analyst and IT-admin, with Ask's look and feel.** Agency is the end-user front-end only; it does not rebuild admin pages.
2. **Add a quiet "Manage" link** in Agency's header that opens the admin console (its own sign-in decides who gets in), configured by `AGENCY_ADMIN_URL`.
3. **Close the feedback loop first**: thumbs and a note, "ask an admin", save as a reusable question, all posting to the existing routes, so Agency users feed the analyst's Review and Trusted-questions queues.
4. **Move the table adapter onto `/app/uploads`** so an uploaded CSV can be asked about (the layer would use the user's own session and grant).
5. **SSO sign-in** through the Server's OIDC redirect before any customer who uses it sees Agency.
6. Later, and with Kumar: a place in the admin console for Agency's own settings (adapters, sharing, workflow definitions), so the IT-admin does not edit environment variables.

## Decisions for you

- Is Agency strictly the end-user front-end, with analysts and IT-admins sent to the admin console? (Recommended.)
- Order of the parity items: feedback and help first, then reusable questions, then `/app/uploads`, then SSO?
- Does the analyst need anything in Agency itself beyond the Manage link, for example a "needs review" badge on an answer they flagged?
