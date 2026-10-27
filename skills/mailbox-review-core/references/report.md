# Report template (your final T3 reply)

T3 renders Markdown, `<details>` accordions and links inline: no HTML page, no file. Subjects come only
from each index row's `link` (escaped, Gmail thread link); any other URL only through
`cockpit.py link --url … [--label …]` (drops query strings and tokens). No raw mail, no quotes.

```markdown
## Mailbox today · <mailbox> · <date>

### Do first
**<row.link>** · <priority> · <new case | carried from <date> | reply waiting, no ReplyPen draft | draft corrected>
<action, 8-14 words>

<details><summary>Why · evidence</summary>

- <owner fact 1-3>

*<evidence title>*
- `<path:line | command | record id>`
  - <point>

`Mail-ref: gmail:<thread id> <mailbox>` · Case thread: `<owner id, if any>`

</details>

… up to seven cards, most urgent first.

<details><summary>N more actions</summary>

- <row.link> · <priority>: <action>

</details>

<details><summary>N old cases: no customer mail for 14+ days</summary>

- <row.link> · customer last wrote <date>: <action>

</details>

### Confirmed product bugs
**<title>** · <row.link>  
Affected: <how many, how counted> · owner: <role>  
Fix: <direction> · <fix thread or PR>

### What limited this review
- <gap> · unblock: <who> · <row.link>

### Lessons for ReplyPen
- <proposed | go | landed> · <row.link> · `<target>`: **<change>** · <why>

<coverage.line from index.json, verbatim>

**Ledger** (≤10): send · decide · discard
```

## Operator level

The wrapper says which operator is at the keyboard. Developer: technical, concise. Product owner:
what the customer sees, what changes, the risk, a one-line reply to approve; paths and commands in a
closed `<details>`.

Every card keeps its `Mail-ref` line: that is how tomorrow's `t3-mail-link index` finds today's
conclusion. Omit empty sections.
