---
name: grandmother-workflow-feedback
description: "Review Memoir from a non-technical grandmother user perspective, evaluate real workflows end-to-end, capture usability pain points, and convert them into actionable feature requests. Use when: validating UX for memory capture, timeline browsing, period-event-asset organization, linking assets, and question answering. Produces: updated docs/grandmother-workflow-feedback.md with findings, prioritized requests, and acceptance criteria."
argument-hint: "Optional: workflow to focus on (for example: 'record audio memory and link photos')"
---

# Grandmother Workflow Feedback

## Purpose
Use this skill to run a user-centered product review for Memoir through the lens of a non-tech-savvy grandmother. The goal is to turn workflow friction into concrete, build-ready feature requests.

## When to Use
- Before or after shipping UX changes
- During weekly product review
- After major backend or frontend workflow changes
- When deciding what to build next for usability
- When asked to gather user-style feedback rather than technical code feedback

## Required Output
Always create or update this document in place:
- `docs/grandmother-workflow-feedback.md`

Every run must append a dated review entry with:
- Exactly one scenario (one end-to-end workflow) per run
- Scenario tested
- Friction points and confusion points
- Recommended feature requests
- Priority labels (High/Medium/Low) and acceptance criteria
- Issue-ready request blocks for direct backlog copy

## Review Lens
Assume the user:
- Is not technical
- Needs low-cognitive-load workflows
- Prefers explicit labels over hidden actions
- Needs confidence that actions succeeded
- Benefits from guided, step-by-step progress

Use these product preferences as fixed constraints unless explicitly overridden:
- Hierarchical model: Periods -> Events -> Assets
- Photos and documents default to linked assets (not standalone memories)
- Timeline should support zoomed-out roll-up behavior
- Manual linking comes before AI suggestions

## Procedure
1. Define the review scenario
- Select one real user goal (example: record a story, assign it to an event, and attach old photos).
- Review exactly one scenario per run.
- If no scenario is provided, default to: capture one memory, organize it into Period/Event, and link one asset.

2. Map the current workflow
- Trace the exact user path in UI terms (button labels, sequence, expected result).
- Include all major transitions: capture, save, organize, and verify outcome.

3. Evaluate from grandmother perspective
- At each step, score clarity and confidence:
  - Clarity: Is the next action obvious?
  - Confidence: Does the user know what happened after an action?
  - Recovery: Can mistakes be corrected easily?
  - Cognitive load: Is there too much text, too many choices, or ambiguous wording?

4. Branch on severity
- High severity (blocker): user cannot complete the task without assistance.
- Medium severity: user can complete task but with uncertainty, retries, or confusion.
- Low severity: minor friction that slows but does not block progress.

5. Convert feedback to feature requests
- For each Medium/High issue, create one feature request with:
  - Problem statement in user language
  - Proposed product behavior
  - Priority: High, Medium, or Low
  - Acceptance criteria (testable)
  - Issue-ready block (Title, Problem, Proposed behavior, Acceptance criteria, Priority)
  - Optional notes for implementation constraints

6. Update feedback document
- Append a new dated section to `docs/grandmother-workflow-feedback.md`.
- Do not remove prior review history.
- Normalize wording to user-focused language, not implementation detail.

7. Completion checks
- Confirm at least one real workflow was reviewed end-to-end.
- Confirm every Medium/High issue has a feature request.
- Confirm acceptance criteria are measurable and non-technical.
- Confirm the feedback document was updated this run.

## Feedback Entry Template
Use this structure for each appended review entry.

### Review Date
YYYY-MM-DD

### Scenario
- Goal:
- Starting point:
- End state expected by user:

### Workflow Walkthrough
1. Step:
- User expectation:
- Actual experience:
- Rating (Clear / Unclear):

### Friction Log
- Severity (High/Medium/Low):
- Where it happens:
- Why it is confusing for a non-technical grandmother:
- Evidence:

### Feature Requests
- Title:
- Priority (High/Medium/Low):
- User problem:
- Proposed behavior:
- Acceptance criteria:

### Issue-Ready Blocks
- Issue title:
- Priority (High/Medium/Low):
- Problem:
- Proposed behavior:
- Acceptance criteria:

### Overall Summary
- Task success (Yes/No/Partial):
- Confidence level after completion (High/Medium/Low):
- Top 3 improvements to prioritize next:

## Quality Bar
- Use plain language and avoid jargon
- Prefer observed behavior over assumptions
- Tie each request to a specific workflow step
- Keep requests scoped to one user-visible improvement each
- Ensure acceptance criteria can be validated in UI behavior
