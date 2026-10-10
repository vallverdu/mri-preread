# Hospital and imaging-center outreach

Owner: Jordi Vallverdú Alcover. Plan prepared 10 October 2026. No outreach has been sent.

The objective is to recruit two or three institutions for a defined brain MRI viewer pilot,
learn from their imaging and IT teams, and agree a supported deployment scope. Production
adoption follows institutional verification and operational ownership. Optional model research
is a separate workstream; the current MedGemma configuration must not influence diagnosis or
clinical queue priority.

## Offer and audience

Lead with what the institution can evaluate today: linked multiplanar images and volume rendering
in a browser, measurements, location-linked notes, manually drawn voxel masks and portable exports.
Recipients need a supported browser, rather than an installed viewer. The institution installs
the preparation tools and, if wanted, a separate model runtime. MIT applies to application code;
hosting, integration, maintenance and model terms remain separate.

| Audience | Useful starting proposal | People to include |
|---|---|---|
| Independent imaging center or imaging network | Evaluate browser delivery of checked brain studies through its existing portal | Imaging operations, neuroradiology, PACS/RIS and portal engineers |
| Hospital innovation or research team | Co-design a controlled viewer and workflow pilot | Clinical champion, innovation lead, imaging IT, information security |
| Academic neuroradiology group | Evaluate image preparation, geometry and optional model outputs against expert references | Neuroradiology investigator, imaging scientist, research governance |

These are proposed use cases, not measured efficiency or outcome claims. Do not promise a PACS
replacement, validated AI triage, universal DICOM compatibility, a shared clinical annotation
record or high-volume service capacity. Those require implementation and evidence described in
the [integration guide](hospital-integration.md) and [task list](../TODO.md).

MCP exposes study tools to a compatible vision- and tool-capable model client. It does not make
every language model an imaging model. Institution-approved local or hosted endpoints are possible
integration choices. The bundled MedGemma runner currently uses MLX on macOS/Metal; a CUDA adapter
and a reproducible alternative client remain planned work. Brain masking and hemispheric asymmetry
are brain-specific. See [model and hardware boundaries](hardware-and-model.md).

## Prepare a private contact register

Keep prospect details, contact evidence, personalized drafts, replies and opt-out records in
ignored `data/outreach/`, or in an approved private CRM. The public repository contains the plan
and milestones. User-supplied email templates keep their own licensing; adapting a licensed
template for email does not authorize publishing its source under MIT.

For each organization record:

- Stable ID, organization and parent group, country, region, institution type and language.
- Exact published email or contact-form URL, department, official source URL, verification date
  and whether evidence was a live page, an indexed page or an older official document.
- Why it fits this pilot, a factual personalization sentence and the proposed contact route.
- Permission status and evidence, review status, selected sender, approved message version,
  last contact, next action, response, meeting and pilot status.
- Suppression status and reason: opt-out, wrong recipient, hard bounce or no further contact.

Publicly listed does not mean verified delivery or marketing consent. Never guess email patterns,
substitute a privacy/press/appointments inbox for a partnership address, or describe a target as
a partner before agreement. Prefer official innovation and collaboration channels. Where only
patient routes are published, hold the lead until a relevant institutional route is confirmed.

One record per organization can retain alternate routes, but use one route at a time. Coordinate
contacts within the same hospital group. Recheck a selected source shortly before outreach;
reconfirm older PDF and indexed-only addresses before treating them as usable.

## Four-week sequence

Weeks start when the sender, contact route and message are ready; these are planning targets,
not booked meetings or delivery commitments.

| Stage | Work | Exit evidence |
|---|---|---|
| Preparation | Verify an initial worldwide shortlist, prepare HTML/text drafts, finish sender identity and email-client checks | Private register, reviewed drafts, monitored replies and opt-out handling |
| Week 1 | Approach five relevant organizations through their invited collaboration routes or another documented permissible route | Actual contact logged separately from draft creation; two useful conversations is a target |
| Week 2 | Speak with imaging and IT leads; send the detailed proposal where requested; select up to three potential pilots | Named clinical and technical owners, problem statement, samples and agreed scope |
| Week 3 | Run a retrospective viewer evaluation using approved de-identified studies inside each institution | Geometry, measurement, browser, privacy and preparation checks with recorded issues |
| Week 4 | Review results and operational gaps together; agree whether a limited delivery deployment is appropriate | Written acceptance or reasons to stop; support, access, capacity and rollback owners |
| Expansion | Add a new small cohort after reviewing the previous one | Message and onboarding updated using actual findings |

Seek coverage across Europe, North America, Latin America, Africa, Asia and Oceania, rather than
emailing a large list at once. A hospital consortium can help with evaluation; an imaging network
can help with delivery workflows. Geographic coverage is a research goal, not permission to send.

Use a private world map to review country coverage and filter the contact register by country,
region and stage. Distinguish a researched lead from an institution actually contacted or engaged.
Keep a country-level language plan and a recipient-level preferred language. Translate both the
short introduction and the detailed proposal, including subjects, buttons, image descriptions,
model limits and stop-contact instructions. Localize the institutional opening using its actual
published collaboration process; do not only substitute a country name.

For multilingual countries, follow the intended team's published correspondence language and
confirm its preference. Catalan and Spanish can both be appropriate in Spain; Toronto's English
route does not define the language for every Canadian institution. English is used by many of
the selected clinical and international research offices in India, Singapore, Sri Lanka, Kenya
and South Africa. Provide local-language alternatives where useful, rather than assuming one
language from nationality. Use right-to-left email layout where required. Translation drafts
need native-speaking clinical/technical review before sending; language coverage is not evidence
that a translated medical or legal claim has been validated.

For local progress tracking, browser changes must be exportable, opt-outs must survive import,
and imported text must remain text. Store detailed permission evidence and actual provider send
IDs in the private register or CRM; a manually changed dashboard stage is not proof of sending.

For an initial contact, personalize two sentences and use a short message with one clear request:
identify the imaging/IT owner or discuss a 20-minute introduction. Keep the detailed HTML proposal
for a team requesting more information, or a channel explicitly inviting a full proposal.
For a form, paste the corresponding text; do not upload an HTML file as if it were a study.

For a permissible contact, consider one relevant follow-up after 7–10 business days. Silence
does not grant consent. Do not follow up after rejection, opt-out or a hard bounce. If a route is
limited to a stated inquiry or request, stay within that scope. Do not use open-tracking pixels,
bulk BCC, purchased lists or send-time automation for this first cohort.

## Detailed proposal contents

The proposal should identify the maintainer and project, give a reason for contacting this team,
and describe:

1. Browser access and concrete review tools, with a link to the real public MRI demonstration.
2. The preparation path: classic DICOM export or NIfTI → verified sequence roles → analysis → HTML.
3. Controlled delivery through the institution's portal and the current browser-local annotation
   storage behavior; shared clinical records need a separate integration.
4. MCP tool access and optional MedGemma research, including backend requirements, exact input
   and response traces, sampling limits and the failed initial discrimination pilot.
5. A suggested small, retrospective pilot, institutional responsibilities and acceptance criteria.
6. MIT code terms, separate model terms, and a request for an imaging/IT introduction.

Use the [public demo](https://vallverdu.github.io/mri-preread/demo/) and CC0 screenshots, never a
private clinical report or scan attachment. The site's owner-approved header is a website display
asset with separate permission, not an outreach dataset. Example marks in the public demonstration
are interface examples, not validated lesions or predictions.

## Pilot acceptance and production decision

Agree a pilot protocol with each institution. A proposed starting cohort is 10–20 retrospective,
de-identified brain studies across its actual scanners and acquisition protocols; that is a
workflow/compatibility sample, not a clinical model validation sample size.

Verify orientation, reference geometry, sequence assignments, alignment and measurements against
the institution's trusted viewer and original images. Exercise browser access, 2D/3D navigation,
measurement export, note/mask persistence, recovery and JSON round trips. Record preparation and
viewer-load time, study size, browser failures, errors and clinician feedback; do not invent
performance thresholds before agreeing them with the team.

Before a limited delivery deployment, the institution must own authentication and authorization
for both the viewer and stored data, retention, records, monitoring, support, rollback and measured
capacity. Pin the source/dependency versions and retain the original clinical PACS/RIS workflow.
Patient-ready sharing requires institutional approval and a supported intended use.

Optional AI evaluation requires its own expert references, held-out positives and negatives,
coverage record and detection/localization/error metrics. The existing six-case pilot flagged
all 91 sampled planes. It demonstrates traceable execution, not useful detection; it cannot
support a sensitivity/specificity or urgency claim. Keep any AI pilot in shadow mode until a
separate evaluation and governance decision supports a different use.

## Sender choice

Prefer the maintainer's existing Gmail account for a small, individually reviewed correspondence
workflow once it is connected and tested. HTML is supported: keep matching plain-text and HTML
parts in a MIME message; an HTML file attached to an email is not its formatted body.
Google documents [MIME message preparation](https://developers.google.com/workspace/gmail/api/guides/sending)
and [draft creation](https://developers.google.com/workspace/gmail/api/guides/drafts).
OAuth credentials and tokens stay outside Git. Draft creation, authorization and actual sending
are separate steps. Sender limits and account status must be checked at setup, not assumed.

Alternatively, use `info@` on the maintainer's domain through Amazon SES after validating account,
region, identity and reply handling. Verify the domain, enable DKIM, review aligned SPF/DMARC and
custom MAIL FROM where appropriate, and preserve existing MX/TXT records. Check production access:
the [SES sandbox](https://docs.aws.amazon.com/ses/latest/dg/request-production-access.html) restricts
recipients to verified identities or simulator addresses. Verification and sandbox status are
regional; an S3 website does not establish SES readiness.

SES sends mail but is not an IMAP/POP mailbox; its receiving feature routes mail to AWS processing
destinations. Configure a monitored `Reply-To` such as the existing Gmail address, or establish a
real mailbox/forwarder before displaying the new address as a reply channel. See
[SES receiving](https://docs.aws.amazon.com/ses/latest/dg/receiving-email.html) and
[verified identities](https://docs.aws.amazon.com/ses/latest/dg/verify-addresses-and-domains.html).
Connect bounce/complaint events to an operational suppression register and check account-level
suppression before using SES. Keep recipient permission evidence with each send. SES is not a way
around consent or Gmail policy restrictions.

## Contact eligibility

Assess the proposed message and recipient under applicable sender and recipient rules. A free
open-source project is not automatically exempt from promotional-email rules. An invitation to
submit a relevant collaboration inquiry has a limited scope and is not consent to a newsletter.
Where eligibility is uncertain, use an appropriate published proposal process or obtain permission
through a permissible route before promotional email; an unsolicited email asking for consent can
itself be regulated. A form is not a general exemption either.

Examples to resolve before an international batch:

- Spain: [LSSI articles 20–22](https://www.boe.es/buscar/act.php?id=BOE-A-2002-13758#a21) restrict
  unsolicited promotional electronic messages and require clear sender identity and opt-out.
- Canada: [CRTC CASL guidance](https://crtc.gc.ca/eng/com500/faq500.htm) addresses consent,
  identification and unsubscribe requirements, including messages arriving from abroad.
- Australia: [ACMA guidance](https://www.acma.gov.au/dealing-with-spam) explains consent,
  sender details and stopping messages. Check the specific basis rather than assuming B2B consent.
- United States: [FTC CAN-SPAM guidance](https://www.ftc.gov/business-guidance/resources/can-spam-act-compliance-guide-business)
  covers commercial B2B messages, sender identity, advertising disclosure, postal address and opt-out.

These examples are not a worldwide legal clearance. Check the other relevant jurisdictions and
provider policies before using their leads. Maintain an immediate manual opt-out process for the
small cohort; future campaign-scale use needs suitable unsubscribe infrastructure. A monitored
reply address and an explicit instruction to reply to stop contact must appear in both MIME parts.

## Tracking and review

Use stages `researched → route_review → permissible_contact → contacted → replied → meeting →
pilot_scoping → pilot_active → accepted/closed`. `hold`, `opted_out` and `bounced` stop further sends.
Keep stage, permission and suppression as separate fields. Update sent time and provider message ID
only after a confirmed send; opening a draft is not contact.

Track relevant responses, routed introductions, meetings, scoped pilots, accepted deployments,
technical blockers and explicit rejections. Delivered messages and booked meetings are distinct
from goals. Do not use opens as evidence of interest. Review the shortlist weekly and remove stale
personal details that are no longer needed, retaining minimal suppression information.

Commit generic milestones to [TODO.md](../TODO.md) for project-manager. Keep addresses, correspondence,
account details and institutional study data out of public commits. Before the first send, review
the exact recipients, permitted route, final subject/body/footer, selected sender and small batch.
