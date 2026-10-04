# Milestones

How work is grouped and handed out, from murphy360/template-python. One page.

Where Memoir differs: its five milestones (v0.1 to v0.5) were written before this page existed, so the
demonstration ticket at the end of each also does the close-out, and there is no questions ticket yet. Add a
questions ticket to a milestone the first time a question only the owner can answer comes up. Each
demonstration is judged first by stories recorded per month.

## The parts of a milestone

- **The milestone.** A GitHub milestone with a name and a goal. Its description carries the RUN ORDER.
- **The RUN ORDER.** A numbered list of the tickets in the milestone, in the order to do them. An agent takes the
  first ticket in the list that is still open, is not assigned to the owner and is not an epic.
- **The questions ticket.** One ticket in the milestone, assigned to the owner. Every question only the owner can
  answer goes there, so that the tickets a pull request closes stay clean. Answers are written on it.
- **The demonstration ticket.** A ticket the owner runs alone, from the run sheet, on a build of `main`. It ends in
  a verdict, **Approved** or **Disapproved**. After Disapproved, each issue found is either fixed before the next
  attempt or moved to the next milestone.
- **The close-out ticket.** The last ticket of the milestone. It writes the run sheet from the template, brings the
  docs up to date, and reviews the backlog.
- **The run sheet.** The written script of the demonstration, one per milestone, copied from a template and
  rehearsed once before the demonstration. It is one numbered list from a cold machine to the report. Each step
  has the click path, a **Pass:** line saying what the operator sees, and a screenshot. A step done on the command
  line is a flagged known issue with its own ticket. Keep the template in `docs/DEMO_TEMPLATE.md` once you have one.

## Versions

A version (a tag and a release) is cut only after the milestone's demonstration ends in **Approved**, and only on
the owner's word. An agent never tags or creates a release on its own. It may prepare the version pull request.

## Tickets

Every ticket uses `.github/ISSUE_TEMPLATE/ticket.md`: Problem, What to build, For the implementer, Done. The
implementer section names the files, the tests, the docs and what done means, so that whoever picks it up needs
nothing else.

## Setting up a milestone

1. Create the milestone and write its goal.
2. Create the questions ticket, assigned to the owner.
3. Create the tickets, and write the RUN ORDER in the milestone description.
4. Create the demonstration ticket and the close-out ticket, last in the order.
