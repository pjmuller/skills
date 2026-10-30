# Lens: how to judge the packets

Read each thread as **intent → execution → claim → what the user did next**. Note the *first*
thing that went wrong in each thread before you name categories ([error analysis](https://hamel.dev/blog/posts/evals-faq/why-is-error-analysis-so-important-in-llm-evals-and-how-is-it-performed.html)):
later trouble usually follows from it.

## Six questions per thread

1. **Goal.** Did the first message say the outcome and when it counts as done? Or did the agent
   have to guess scope, and the user correct it later? ([precision of direction](https://www.anthropic.com/research/claude-code-expertise))
2. **Proof.** Did "done" come with evidence (test output, a screenshot, a live check, a table of
   items with their status)? "Yes, all built" without a list is a claim, not proof.
3. **Who corrected whom.** User corrections after a done-claim = the agent lacked a check or a
   fact. The agent correcting the user = good. A retyped instruction = a rule that is missing from
   a file, or is in one and being ignored (check the instruction files before proposing a line).
4. **Hidden friction.** A failure the final answer never mentions; a fallback ("instead",
   "skipped", "manually") followed by "done"; the same error in many threads (sandbox, missing
   binary, auth, a service that isn't running). Each is a setup fix the user can't see otherwise.
5. **Unasked work.** "I also added/fixed…": useful initiative, or scope growth the user then had
   to review? Say which.
6. **Loop.** North star: the agent closes its own loop (act → observe → fix → verify), so a few
   iterations reach the goal without the user. Find where the loop ran through a human instead
   (lead `broken-loop`), in coding and non-coding work alike:
   - The user looked for the agent: a screenshot of a page the agent could open, pasted logs, "still
     broken", facts an API returns (an email, company data, search volumes), a check on their phone
     where a simulator, browser device emulation or a connected phone would do.
   - The user acted for the agent: logged in, clicked a confirm link, forwarded a mail, exported a
     file, typed a password a password manager holds.
   - The agent was blind: the local app wouldn't start, so the change shipped unseen; a dead token or
     missing access hid the data; "please refresh and tell me what you see".

   Not a break: a judgment only the user can make (scope, taste, money, sending in their name),
   a permission they grant, a truly physical step (eID, phone 2FA, a microphone). The same physical
   step every week is still a candidate for a stored session. A tool existing is no proof it
   worked then: check whether the agent tried it and what failed before blaming the agent.

## Every finding ends in one fix type ([Claude Code best practices](https://code.claude.com/docs/en/best-practices))

| Shape | Fix type | Typical change |
| --- | --- | --- |
| Built something different, rediscovers a fact every time | **context** | one line in AGENTS.md / the global prompt / a skill |
| Said done, wasn't | **check** | a test, seed data, a done-checklist the agent fills in, a Stop hook |
| Did a never-do, skipped an always-do | **enforce** | a hook or permission rule (a prompt line can't guarantee it) |
| Right, but too slow, costly or interrupt-heavy | **default** | model/effort default, install a missing tool, a sandbox allowance |
| The user looked, clicked or pasted for the agent | **default** or **check** | give it eyes and hands: a browser tool, a stored login, a data API, a simulator, seed data, a dev server that starts |

## Rules

- Pick the change with the highest cost × frequency that the user can make in **under 10 minutes**.
  No builds, no new processes, no "be more specific".
- Evidence missing means "not observed", not "not done". A thread the retro didn't read proves nothing.
- A recurring error with an obvious owner outside the user's machine (a provider outage) is not
  this week's change.
- Quote at most a few words; refer to threads by their short id.
- Praise one real pattern; it is the cheapest way to keep a good habit.
