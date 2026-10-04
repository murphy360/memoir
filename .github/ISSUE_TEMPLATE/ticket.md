---
name: Ticket
about: A work item with what to build, how to test it, the docs to update and what done means
title: ""
labels: ""
assignees: ""
---

## Problem

State the problem in short sentences. Say what happens now. Say why it matters.

## What to build

1. List the required changes in run order.
2. Name the files, tests, docs and behaviour that define done.

## For the implementer

### Read first

- Read `CLAUDE.md` before you change code.
- Read the whole ticket before you start.
- Ask on the ticket if the owner kept a design choice.

### Build

- Make the smallest change that solves the ticket.
- Keep the code rules and the file-size limit in mind while you edit.

### Tests

- Add or update the unit tests the ticket needs.
- Run the tests in Docker and paste the end of the output in the PR body.

### Docs

- Update the spec for the area.
- Update the user manual, and the training material where the project has it.
- Update any run sheet the change alters.

## Done

- [ ] The change is in, small and readable.
- [ ] Tests for every new behaviour pass in Docker.
- [ ] `python3 code_rules.py` (from murphy360/standards) prints OK.
- [ ] The docs are updated in the same PR.
- [ ] One PR opened with `Closes #N`, with every `Note:` line the deployer needs.
