---
name: public-footprint-audit
description: Audit a consenting person's public web footprint for social-engineering exposure, produce an evidence-backed Markdown lockdown checklist, and recheck removals. Use for self-audits or authorized family/member audits, not background checks or account intrusion.
---

Audit what an outsider can actually discover; recommend the smallest changes that meet the person's preferred audience. Default to research and a private report, not account changes or removal submissions.

## Scope and identity

Use the person's supplied names, aliases, usernames, country and known profiles as search seeds. Ask only for missing identifiers that materially affect matching. Confirm authorization for another person's audit; relationship alone is not consent. Do not request passwords, government IDs or complete birth dates to start.

Establish the desired audience: public, any signed-in user, approved connections, or nobody. If unspecified, recommend approved connections for personal information and minimal public professional identity. Explain that an arbitrary signed-in account is not a trusted connection.

Keep local/private knowledge separate from public evidence. Require corroborating signals (e.g. name + employer + location, or an authoritative cross-link); username/email matches alone can be collisions. Label ambiguous matches and do not fold them into the person's biography. Do not expand into relatives' separate dossiers.

## Research

1. Search exact names and spelling variants, usernames, known contact identifiers and organization associations. Add platform/domain and document queries. Inspect different-language/old-domain copies. Keep a query/coverage ledger; don't describe search exhaustion as completeness.
2. Cover social profiles **and individual posts**, public code/commit metadata/gists, personal and company sites, event/interview/video pages, directories/registries, documents and third-party mirrors. For nontechnical people prioritize the sites found, not a fixed developer checklist. Follow actual links, not a huge guessed account list.
3. Open likely results without the person's authenticated session. An owner's browser view, private connector result, or local repository is not proof of public exposure. Use public APIs/raw files when appropriate. For archives label snapshot date separately from today's check.
4. If a normal fetch fails, use an available public-page capture/enrichment provider after reading its instructions. Cache responses privately; honor price caps and avoid repeated paid calls. Stop on credential failures, explicit access controls or rate limits. Never bypass login, CAPTCHA or paywalls. Provider-returned data without visible public provenance is **provider-only**, not proven anonymous web exposure.
5. Inspect content, not just HTTP status. Classify each result as **live anonymous**, **search-index only**, **historical archive**, **provider-only**, **blocked/unknown**, **not found in tested searches**, or **excluded identity mismatch**. Log date, URL, method, identity confidence and a short evidence excerpt/category. A 404/403/login wall is not proof of privacy or absence.
6. Prioritize compound exposures: contact/address/birth date, family and recovery clues, signatures, predictable routines, financial claims, recognizable trusted relationships, account/tenant identifiers and invoice channels. Explain the potential harm briefly; do not write phishing scripts or test credentials. Mask secret-looking values, stop validating them, and recommend revocation if genuine. Distinguish a business address/phone from a current home/private number.
7. End after all relevant categories have a recorded outcome and follow-up query rounds stop yielding meaningful new sources; otherwise report the remaining scope explicitly. Parallel researchers should own disjoint categories and return evidence, not unsupported conclusions.

## Recommendations

Verify platform controls against current official documentation and cite the exact help page. Give 2–5 short steps plus a direct settings link when verified. Mark inferred UI labels or unavailable controls; do not invent a privacy switch.

Treat separately: profile visibility, old posts, new-post defaults, contact discovery, public comments, tagged content, commits/history, and third-party copies. Hiding a profile need not hide its posts. A private profile need not make repositories private. Unlisted links and noindex are not access control. Git author-email changes affect future commits; history/forks/caches need separate handling.

For company sites recommend removing nonessential family/contact/operational details while preserving intended professional presence. For official registers, distinguish optional aggregator copies from legally published records: verify current jurisdiction-specific correction/removal routes, never promise erasure. Recommend professional advice only for actual registration/legal changes.

Source removal, search delisting and stale-cache refresh are separate actions. Cite official search-engine removal instructions; state eligibility and availability limits. Do not send requests, upload ID, change audiences, delete posts/repos or rewrite history unless separately authorized. Prepare concrete targets and consequences first.

## Deliver and verify

Use [report-template.md](report-template.md), adapting length to findings. Save the report/evidence in a private user-selected directory outside public/versioned skill sources; restrict local permissions where supported. Minimize exact sensitive values, especially relatives' details. Do not publish the resulting dossier in a repo, shared Page or public artifact. Public skill examples must be fictional.

Lead with the highest-impact actions, then evidence and concise per-platform instructions; put research detail behind collapsible sections. Include coverage gaps, identity exclusions, sources, verification method, and whether any changes were actually made. Avoid claiming no exposure when a platform could not be inspected.

For a rerun, compare canonical URLs and exposed fields to the prior report: new, still exposed, removed at source, stale index, or unverifiable. Verify approved changes as an anonymous visitor and, if explicitly authorized and available, an unrelated signed-in account. Record source and index outcomes independently. Keep status pending until observed; propose a recheck interval without scheduling unless requested.
