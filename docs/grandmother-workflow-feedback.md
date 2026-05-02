# Grandmother Workflow Feedback Log

Purpose: track non-technical user-perspective workflow reviews and convert findings into feature requests for Memoir.

## How to Use This Log
- Append a new dated section for each review run.
- Keep each run to exactly one scenario.
- Keep prior entries as historical context.
- Focus on user-visible workflow behavior.
- For every Medium or High friction point, add a feature request with acceptance criteria.
- Include issue-ready blocks for direct copy into backlog tickets.

---

## 2026-05-01 Initial Template Entry

### Scenario
- Goal: Capture one memory, place it in the right Period/Event, and link one photo.
- Starting point: Home page with no context of data model.
- End state expected by user: Memory is saved, organized, and visible where expected.

### Workflow Walkthrough
1. Step: Start recording memory
- User expectation: A clear start/stop path and confirmation that recording saved.
- Actual experience: Not yet reviewed.
- Rating (Clear / Unclear): Unclear

2. Step: Assign memory to Period/Event
- User expectation: Simple guidance about where this memory belongs.
- Actual experience: Not yet reviewed.
- Rating (Clear / Unclear): Unclear

3. Step: Link a photo asset
- User expectation: Upload is obvious and linkage result is visible.
- Actual experience: Not yet reviewed.
- Rating (Clear / Unclear): Unclear

### Friction Log
- Severity (High/Medium/Low): Medium
- Where it happens: End-to-end organization flow
- Why it is confusing for a non-technical grandmother: Multiple concepts without guided help can feel abstract.
- Evidence: Placeholder until first full walkthrough.

### Feature Requests
- Title: Guided organize flow after capture
- Priority (High/Medium/Low): High
- User problem: After recording, user may not know what to do next.
- Proposed behavior: Show a simple step-by-step organizer (Choose Period -> Choose Event -> Link assets).
- Acceptance criteria: After saving a memory, user sees a guided 3-step flow and can complete all steps without leaving context.

### Issue-Ready Blocks
- Issue title: Guided post-capture organizer for non-technical users
- Priority (High/Medium/Low): High
- Problem: Users can save a memory but may not know how to organize it into Period/Event and linked assets.
- Proposed behavior: Immediately after save, show a guided 3-step flow with clear labels and success confirmations.
- Acceptance criteria: User can complete Choose Period -> Choose Event -> Link asset in one flow, with clear confirmation at each step.

### Overall Summary
- Task success (Yes/No/Partial): Partial
- Confidence level after completion (High/Medium/Low): Low
- Top 3 improvements to prioritize next:
  - Add post-capture guidance
  - Reduce ambiguous labels in organization actions
  - Improve success confirmations after save/link actions

---

## 2026-05-01 Grandma remembered a story from the 1960s

### Scenario
- Goal: Quickly note down a newly remembered event from the 1960s before details are forgotten.
- Starting point: Home screen with Life Periods visible and no explicit "quick note" path.
- End state expected by user: Story is captured, clearly placed in the 1960s period, and easy to find again.

### Workflow Walkthrough
1. Step: Tap + New Memory and begin capture
- User expectation: One obvious "start talking" button and reassurance the note is saved.
- Actual experience: The flow opens a capture drawer with recording controls and device options. The technical option "Input device" appears before capture action, which adds decision friction for a non-technical user.
- Rating (Clear / Unclear): Unclear

2. Step: Stop recording and process
- User expectation: Immediate confirmation that the memory was saved and where it went.
- Actual experience: Recording uses "Stop & Process" and can show statuses like "Processing..." and "Saved ✓" in event capture contexts, but overall location (which period/event now contains the memory) is not made explicit in plain language.
- Rating (Clear / Unclear): Unclear

3. Step: Place memory into the right 1960s context
- User expectation: A simple prompt like "Was this in your 1960s years?" and one-click placement.
- Actual experience: Organization depends on navigating Life Periods, opening a period, and creating or selecting events. Controls like "Open", "Create Event", and date text fields exist, but there is no guided "place this memory" step after capture.
- Rating (Clear / Unclear): Unclear

4. Step: Confirm retrieval later
- User expectation: Easy way to find this memory again under a clearly named decade period.
- Actual experience: Period sorting options exist (for example timeline oldest/newest), but no post-save summary confirms the exact final location in plain terms.
- Rating (Clear / Unclear): Unclear

### Friction Log
- Severity (High/Medium/Low): High
- Where it happens: Capture start (first interaction)
- Why it is confusing for a non-technical grandmother: Technical setup wording appears too early, before the core action of speaking the memory.
- Evidence: Capture flow exposes "Input device" selection in recording panels prior to user confidence that "record now" is the primary task.

- Severity (High/Medium/Low): High
- Where it happens: Immediately after save/process
- Why it is confusing for a non-technical grandmother: User cannot confidently tell where the new memory lives in the Period -> Event structure.
- Evidence: No plain-language confirmation like "Saved to: 1960s -> Summer Job" appears after processing.

- Severity (High/Medium/Low): Medium
- Where it happens: Period/Event organization step
- Why it is confusing for a non-technical grandmother: Requires understanding two-level hierarchy and manually choosing where to put the memory without guidance.
- Evidence: User must operate Life Period cards and event creation forms, but there is no guided organizer that starts from the fresh memory.

### Feature Requests
- Title: One-tap "Quick Memory" capture mode
- Priority (High/Medium/Low): High
- User problem: When a memory suddenly comes back, setup choices delay capture and risk losing details.
- Proposed behavior: Add a simplified entry point that starts recording immediately and hides advanced options unless requested.
- Acceptance criteria: From home screen, user can start recording in one tap and complete save without interacting with device settings.

- Title: Plain-language save destination confirmation
- Priority (High/Medium/Low): High
- User problem: After processing, user does not know where the memory was placed.
- Proposed behavior: Show a clear confirmation banner with final location and one-tap "Change location" action.
- Acceptance criteria: After save, UI displays "Saved to [Period] -> [Event]" and user can correct placement in one action.

- Title: Guided "Place this memory" organizer for decade-era stories
- Priority (High/Medium/Low): Medium
- User problem: Choosing Period and Event is mentally heavy for non-technical users.
- Proposed behavior: After capture, present a 3-step wizard: choose/create period (with decade suggestions), choose/create event, confirm.
- Acceptance criteria: User can place a new memory into a period/event through a single guided flow without navigating multiple cards manually.

### Issue-Ready Blocks
- Issue title: Add one-tap Quick Memory capture path
- Priority (High/Medium/Low): High
- Problem: Grandmother users recalling old stories need immediate capture, but technical input setup appears before recording and adds hesitation.
- Proposed behavior: Provide a "Quick Memory" button that starts recording immediately; move device settings behind an optional "Advanced" control.
- Acceptance criteria: User can open app, tap one button, record, and save in under 15 seconds without touching device settings.

- Issue title: Show explicit save location after processing
- Priority (High/Medium/Low): High
- Problem: Users cannot confidently tell where a memory was stored in the hierarchy after processing.
- Proposed behavior: Display a success message with exact placement (Period and Event) and a visible "Change location" action.
- Acceptance criteria: Every successful save shows a destination summary and supports immediate reassignment from the same message.

- Issue title: Add guided placement wizard with decade suggestions
- Priority (High/Medium/Low): Medium
- Problem: Manual period/event organization is too abstract for non-technical users, especially for decade-based memories.
- Proposed behavior: Launch a guided organizer after save with suggested periods (for example "1960s") and simple next/back actions.
- Acceptance criteria: User completes Period -> Event assignment through a single guided flow and sees final confirmation at the end.

### Overall Summary
- Task success (Yes/No/Partial): Partial
- Confidence level after completion (High/Medium/Low): Low
- Top 3 improvements to prioritize next:
  - Add immediate quick-capture path with minimal decisions
  - Add explicit post-save destination confirmation
  - Add guided organizer with decade-aware suggestions

---

## 2026-05-01 Grandma uploads an old photo and wants to tell a story about it later

### Scenario
- Goal: Upload an old photo, put it somewhere it belongs, and come back later to record a spoken story about what is in the picture.
- Starting point: Home screen. Grandma has a photo on her phone or computer she wants to save.
- End state expected by user: Photo is visible in the app, has a clear label, and has a "tell me about this" recording tied to it when she is ready.

### Workflow Walkthrough
1. Step: Find where to upload a photo
- User expectation: An obvious "Add a photo" button on the home screen.
- Actual experience: The main action button is "+ New Memory" which implies audio. Photo upload is inside the CaptureSidebar as "Upload a Document" — labeled with technical filetype hints (.pdf, .jpg, etc.), not "Upload a Photo." No dedicated photo entry point is visible on the home screen.
- Rating (Clear / Unclear): Unclear

2. Step: Photo is processed and lands in Unlinked Assets Inbox
- User expectation: The photo appears where it belongs, labeled and ready to link to her story.
- Actual experience: Photo appears in the "Unlinked Assets Inbox" section near the bottom of the page — a section with a technical-sounding name. The inbox shows asset rows with "Expand / Collapse" toggles and a dropdown to select an event, but there is no explanation of what "unlinked" means or what to do next.
- Rating (Clear / Unclear): Unclear

3. Step: Link the photo to a life period or event
- User expectation: Simple question like "Which part of your life is this from?" with clear period options.
- Actual experience: User sees a dropdown of life events (not periods) and a "Link to Event" button. If no events exist yet for the right period, the user must first exit this area, navigate to Life Periods, expand a period, create an event, then return to the inbox. No way to link directly to a period without creating an event first.
- Rating (Clear / Unclear): Unclear

4. Step: Come back later and record a spoken story about the photo
- User expectation: See the photo with a clear "Tell your story" or "Add a recording" prompt next to it.
- Actual experience: The photo is now an asset inside an event. To add a narration, user must: find the event, click "Open," scroll to the EventCapturePanel, and start recording under "Record Audio." The photo and the recording interface are in the same event, but no visual connection between the photo and the record button communicates "record about this photo." The photo is under a separate expand/collapse in the asset list.
- Rating (Clear / Unclear): Unclear

### Friction Log
- Severity (High/Medium/Low): High
- Where it happens: Initial photo upload entry point
- Why it is confusing for a non-technical grandmother: "Upload a Document" does not sound like "add a photo." The photo-specific path is hidden inside a sidebar designed around audio.
- Evidence: CaptureSidebar uses document-upload language; no dedicated "Add Photo" button exists on the home screen.

- Severity (High/Medium/Low): High
- Where it happens: Unlinked Assets Inbox labeling and instructions
- Why it is confusing for a non-technical grandmother: "Unlinked" is a technical word. There are no instructions explaining what to do next.
- Evidence: The inbox section heading is "Unlinked Assets Inbox" with no plain-language prompt; linking requires selecting from an event dropdown with no period-level option and no fallback if no events exist.

- Severity (High/Medium/Low): Medium
- Where it happens: Returning later to add a story/recording about the photo
- Why it is confusing for a non-technical grandmother: No visual connection exists between the uploaded photo and the place to record a story about it.
- Evidence: Photo asset and "Record Audio" panel are siblings inside an event, but the record button does not reference or display the photo, and the photo does not have a "Tell your story" affordance.

### Feature Requests
- Title: Dedicated "Add a Photo" entry point on the home screen
- Priority (High/Medium/Low): High
- User problem: There is no obvious way to add a photo — the primary button says "New Memory" and implies speaking.
- Proposed behavior: Add a clearly labeled "Add a Photo" button or icon on the home screen that goes directly to photo upload, separate from audio capture.
- Acceptance criteria: User can upload a photo from the home screen without opening the audio capture drawer or reading any technical file-type labels.

- Title: Rename "Unlinked Assets Inbox" to plain-language equivalent and add instructions
- Priority (High/Medium/Low): High
- User problem: "Unlinked Assets Inbox" is technical vocabulary a non-technical user cannot act on.
- Proposed behavior: Rename the section to something like "Photos & Files Waiting to Be Placed" and add a one-line instruction: "These photos and files are saved. Choose a memory below to attach each one."
- Acceptance criteria: A non-technical user reading the section heading and subtitle understands what the items are and what to do next, without additional explanation.

- Title: Allow linking a photo directly to a Period (not just an Event)
- Priority (High/Medium/Low): Medium
- User problem: If no event exists for the right period yet, the user hits a dead end while trying to place the photo.
- Proposed behavior: The link dropdown shows periods as top-level options alongside events, and selecting a period places the photo under that period without requiring an event.
- Acceptance criteria: User can link a photo to a period from the inbox even when no events exist under that period.

- Title: Show a "Tell your story" prompt on assets that have no linked narration
- Priority (High/Medium/Low): Medium
- User problem: After placing a photo in an event, there is no invitation to record a story about it.
- Proposed behavior: Assets with no linked audio narration show a subtle "Add your story" button that opens the record panel scrolled to the audio capture section, with the photo visible above.
- Acceptance criteria: User sees the photo and an "Add your story" button in the same view, and tapping it starts recording in context without requiring separate navigation.

### Issue-Ready Blocks
- Issue title: Add dedicated "Add a Photo" button to home screen
- Priority (High/Medium/Low): High
- Problem: Grandmothers with old photos have no clear starting point — the main button implies audio, and photo upload is buried inside document upload language in the sidebar.
- Proposed behavior: Add a photo-specific upload action on the home screen, clearly labeled, that bypasses audio capture entirely.
- Acceptance criteria: User taps "Add a Photo" from the home screen, uploads a photo, and sees it saved — no interaction with audio or document upload flows required.

- Issue title: Replace "Unlinked Assets Inbox" with plain-language name and instructions
- Priority (High/Medium/Low): High
- Problem: "Unlinked Assets Inbox" is incomprehensible to non-technical users and provides no guidance on what to do.
- Proposed behavior: Rename to "Photos & Files Waiting to Be Placed" and add a one-sentence instruction above the list.
- Acceptance criteria: A first-time non-technical user reads the section and can describe what to do next without asking for help.

- Issue title: Enable period-level photo linking from the inbox
- Priority (High/Medium/Low): Medium
- Problem: If no events exist for a period, users cannot link a photo without first navigating away to create an event.
- Proposed behavior: Inbox link dropdown includes periods as top-level choices; linking to a period saves the asset without requiring a child event.
- Acceptance criteria: User can link any inbox photo to a period with zero events and see the photo appear under that period.

- Issue title: Add "Tell your story" prompt on unnarrated photo assets
- Priority (High/Medium/Low): Medium
- Problem: Once a photo is placed in an event, nothing invites the user to record a story about it. The record button and the photo have no visible relationship.
- Proposed behavior: Display an "Add your story" action on photo assets that have no linked audio, opening the audio record panel in context.
- Acceptance criteria: User sees photo and "Add your story" in one view and can begin recording without leaving the photo context.

### Overall Summary
- Task success (Yes/No/Partial): Partial
- Confidence level after completion (High/Medium/Low): Low
- Top 3 improvements to prioritize next:
  - Add a clear "Add a Photo" path on the home screen
  - Rewrite the inbox with plain-language name and one-line instructions
  - Add a "Tell your story" prompt on placed photos with no narration
