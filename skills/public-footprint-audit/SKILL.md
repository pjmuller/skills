---
name: public-footprint-audit
description: "Use for \"what can strangers find about me online\", locking down public profiles against phishing, CEO fraud or impersonation, the same audit for a consenting family or team member, or rechecking earlier removals. Not background checks on others without consent."
---

Audit what an outsider can actually discover; recommend the smallest changes that meet the person's preferred audience. Default to research and a private report, not account changes or removal submissions.

## Scope and identity

Seeds: the person's supplied names, aliases, usernames, country and known profiles; ask only for missing identifiers that materially affect matching. **Confirm authorization for another person's audit; relationship alone is not consent.** Don't request passwords, government IDs or full birth dates to start.

Desired audience: public, any signed-in user, approved connections, or nobody. Unspecified → approved connections for personal information, minimal public professional identity. An arbitrary signed-in account is not a trusted connection.

Keep private knowledge separate from public evidence. Require corroborating signals (name + employer + location, or an authoritative cross-link); username/email matches alone can be collisions. Label ambiguous matches; don't fold them into the biography. No separate dossiers on relatives.

## Research

1. Search exact names and spelling variants, usernames, known contact identifiers and organization associations. Add platform/domain and document queries. Inspect different-language/old-domain copies. Keep a query/coverage ledger; don't describe search exhaustion as completeness.
2. Cover social profiles **and individual posts**, public code/commit metadata/gists, personal and company sites, event/interview/video pages, directories/registries, documents and third-party mirrors. For nontechnical people prioritize the sites found, not a fixed developer checklist. Follow actual links, not a huge guessed account list.
3. Open results without the person's session: an owner's browser view, private connector result or local repo doesn't prove public exposure. Public APIs/raw files are fine. Archives: label snapshot date separately from today's check.
4. Normal fetch fails → an available public-page capture/enrichment provider (read its instructions first). Cache privately, honor price caps, no repeated paid calls. Stop on credential failures, explicit access controls or rate limits. **Never bypass login, CAPTCHA or paywalls.** Provider data without visible public provenance is **provider-only**, not proven anonymous exposure.
5. Inspect content, not just HTTP status. Classify each result as **live anonymous**, **search-index only**, **historical archive**, **provider-only**, **blocked/unknown**, **not found in tested searches**, or **excluded identity mismatch**. Log date, URL, method, identity confidence and a short evidence excerpt/category. A 404/403/login wall is not proof of privacy or absence.
6. Prioritize compound exposures: contact/address/birth date, family and recovery clues, signatures, predictable routines, financial claims, recognizable trusted relationships, account/tenant identifiers and invoice channels. Explain the potential harm briefly; do not write phishing scripts or test credentials. Mask secret-looking values, stop validating them, and recommend revocation if genuine. Distinguish a business address/phone from a current home/private number.
7. End after all relevant categories have a recorded outcome and follow-up query rounds stop yielding meaningful new sources; otherwise report the remaining scope explicitly. Parallel researchers should own disjoint categories and return evidence, not unsupported conclusions.

## Recommendations

Verify platform controls against current official docs and cite the exact help page: 2–5 short steps plus a direct settings link when verified. Mark inferred UI labels or unavailable controls; never invent a privacy switch.

Treat separately: profile visibility, old posts, new-post defaults, contact discovery, public comments, tagged content, commits/history, and third-party copies. Hiding a profile need not hide its posts. A private profile need not make repositories private. Unlisted links and noindex are not access control. Git author-email changes affect future commits; history/forks/caches need separate handling.

For company sites recommend removing nonessential family/contact/operational details while preserving intended professional presence. For official records (gazettes, company filings, registers) run the [field-level preflight](official-records.md) before any recommendation: document type, jurisdiction and filing date, the person's role, then mandatory / optional / unknown per field, each with the provision opened. A mandatory field is real exposure but not a removal finding. An optional field is a candidate for an erasure request to the publisher, never a promised outcome. Aggregator copies are a separate route. Recommend professional advice only for actual registration/legal changes.

Source removal, search delisting and stale-cache refresh are separate actions; cite official search-engine removal instructions with eligibility limits. **Don't send requests, upload ID, change audiences, delete posts/repos or rewrite history unless separately authorized**; prepare concrete targets and consequences first.

## Deliver and verify

Fill [report-template.md](report-template.md), length matching findings. **Save report/evidence in a private user-selected directory outside versioned skill sources (restrict permissions); never publish the dossier in a repo, shared Page or public artifact.** Minimize exact sensitive values, especially relatives'. Public skill examples must be fictional.

The template orders it: highest-impact actions, evidence, per-platform steps, research detail collapsed, coverage gaps and whether changes were made. Never claim no exposure for a platform that couldn't be inspected.

For a rerun, compare canonical URLs and exposed fields to the prior report: new, still exposed, removed at source, stale index, or unverifiable. Verify approved changes as an anonymous visitor and, if explicitly authorized and available, an unrelated signed-in account. Record source and index outcomes independently. Keep status pending until observed; propose a recheck interval without scheduling unless requested.
