Use the internship-agent skill.

This is the scheduled morning run for {name}. The scanners have already run and the
report is written after you finish, so what you add is the judgement:

1. `python3 {agent}/intern_agent.py notes --apply` — act on anything they wrote.
2. `python3 {agent}/intern_agent.py queue --limit 10 --check-forms` — the ranked list
   with anything disqualified by its own application form already removed.
3. Take the **two or three best** that are not already `ready`. Prefer strong
   over real chance, anything closing within ten days over anything that
   isn't, and the places first in their profile over the rest.
4. For each: `python3 {agent}/resume_tailor.py <id>` first - it writes a tailored
   one-page resume.pdf, the notes saying what it cut, and a cover letter
   assembled from their own paragraphs. Then `python3 {agent}/intern_tailor.py brief
   <id>`, read the posting at its link with WebFetch, fill the one slot the
   letter leaves, and `intern_tailor.py save` with `--ask` for every gap you
   could not fill honestly.
5. Stop. Do not submit anything, and do not mark anything submitted.

Two or three properly beats ten generically — they have to read every one.
If nothing clears "real chance", prepare nothing and say so; a morning with
no good postings is a real answer.

Keep your closing summary to a few lines. The report carries the numbers.
