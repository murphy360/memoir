# Frontend

The web app (`web/`): Vite, React and TypeScript, served as static files under `/memoir/`. Requirements section 11
is the spec; this page is how it is built.

## Two postures

One application, two layouts, chosen by the screen's width (`src/app/usePosture.ts`, 768 px):

| Posture | For | Chrome |
|---|---|---|
| **Phone** (below 768 px) | Capturing | The page, then a tab bar fixed to the bottom: Home, Timeline, People, Questions, Account. Home is a big Record button and the questions waiting |
| **Wide** (768 px and up) | Reviewing | A header with Record and your name, the whole navigation on the left, a workspace. Home is the review workspace |

The breakpoint is a layout choice, not a feature switch. Every route exists in both postures; `src/app/router.tsx`
lists them once (`shellRoutes`) and `src/app/Layouts.tsx` wraps them in the posture's chrome. The navigation is
one list (`src/app/nav.ts`): the phone shows the five items marked `tab`, the wide screen shows all of them, and
items with a `role` show only to that role and above.

## Where state lives

| State | Where | Why |
|---|---|---|
| What the server knows | TanStack Query's cache, one query per entity (`["person", 7]`, `["people", q]`) | Fetch what a screen shows, not the whole archive; refetch what a change touched |
| What a link should reproduce (search, sort, filters, which panel is open) | The URL, with `useUrlState` (`src/lib/urlState.ts`) | A reload or a shared link lands on the same view. Writes replace history, so typing does not fill the back button |
| What belongs to this device (microphone, collapsed panels) | Local storage, with `useStoredState` (`src/lib/storedState.ts`), keys prefixed `memoir:` | Survives a reload; never sent anywhere |
| A form being filled | The component | Nothing else needs it |

No global "loading" flag: a running request disables only its own controls.

## Changes and feedback

- **Optimistic changes** use `useOptimisticMutation` (`src/lib/optimistic.ts`): the cache shows the change at once;
  if the server refuses, the change is undone and a toast shows the server's own message; either way the query is
  refetched. The profile name is the first user of it.
- **Toasts** (`src/components/Toast.tsx`, `useToast()`): success and information are announced politely, errors as
  alerts. Feedback appears where the user is looking, never in a closed panel (requirements 11.6).
- **Errors** read as the server's sentence: `messageOf(error)` (`src/lib/errors.ts`) and `<ErrorText>` turn an
  `ApiError` into its message and a network failure into "Memoir could not reach the server".
- **Confirmations** (`useConfirm`, `src/components/Confirm.tsx`) say in plain words what will happen
  ("Its 3 epics move to Childhood").

## Components

`src/components/`: `Button` (a real button; `busy` disables it), `Field` and `ErrorText` (`Form.tsx`), `DateField`
(shows how a date reads), `EmptyState` (why a list is empty and the way to fill it), `Toast`, `Confirm`. The
**gallery** at `/gallery` shows them together, to check by eye and by keyboard.

Rules, so the app never grows another 3,940-line page:

- A component file stays under 300 lines; a component takes at most a dozen props. Split before adding.
- A screen lives in `src/pages/` or `src/features/<area>/`; shared pieces in `src/components/`.
- Every interactive thing is a real `button`, `a` or form control with a visible label. No clickable headings, no
  icon-only buttons without an `aria-label`.
- Pages inside the shell render a `section`; the layout owns the one `main` landmark.

## Accessibility

16 px text, contrast to WCAG AA (the colours are in `src/styles.css`), a 3 px focus ring on everything, buttons at
least 44 px tall, a "Skip to content" link, and the tab bar clear of the phone's home indicator. Lighthouse scores
the shell pages 100 for accessibility on mobile and desktop.

## Installing

The app is a PWA: `public/manifest.webmanifest` with 192 and 512 px icons (and a maskable one), an Apple touch icon
for iOS, and a service worker (`public/sw.js`) that passes every request to the network. Chrome reports no
installability errors. There is no offline mode yet: nothing is cached, so nothing can be stale.

## Testing

- `make test` runs Vitest in the web image: components, both postures (the test setup answers `matchMedia` for a
  width the test sets: `renderApp(path, WIDE)`), every shell page in both, URL and stored state, optimistic
  rollback, toasts and confirmations. Tests stub `fetch` with `test/fakeApi.ts`.
- `make smoke` drives a real Chromium through a running stack: sign in, every page in both postures with a reload,
  one `main` landmark each, and the keyboard reaching every navigation link (`e2e/`).
