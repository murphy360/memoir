# Accounts

Who can get in, how, and what each person may do. Requirements section 9 is the why.

## Getting in

- **There is no sign-up.** The first account, the owner, is made once on the server:

  ```bash
  docker compose exec memoir-api memoir-cli create-owner --email you@example.org --name "Your name" --archive "The family's name"
  ```

  It asks for the password twice. A second run refuses: after the first owner, people join by invitation.
- **Invitations.** The owner opens *People with access*, enters an email and a role, and gets a link. The link is
  shown once, works once, and expires after 7 days. The owner can revoke it before it is used. Opening it shows who
  invited you and to which archive; you pick your name and a password, and you are signed in.
- **Passwords.** At least 12 characters. No rules about digits or symbols. A few of the passwords everyone guesses
  first are refused, as is your own email. Passwords are stored as argon2id hashes.
- **Forgotten password.** The owner sets a temporary one on *People with access*. That signs the person out
  everywhere; at their next sign-in they must choose their own before anything else works.

## Sessions

- Signing in starts a server-side session. The browser holds a random token in an HttpOnly, Secure, SameSite=Lax
  cookie; the database keeps only its hash.
- A session ends after 30 days without use. Using the app keeps it alive and renews the cookie.
- *Your account* lists where you are signed in, and offers *Sign out everywhere else*, which ends every other
  session at once. Changing your password does the same.
- Sign-in is refused, with the same message as a wrong password, after 5 failures from one address within a
  minute, or 10 failures on one account within 15 minutes.

## Roles

| Role | May |
|---|---|
| Owner | Everything, plus manage people, invitations, settings, export, and deleting the archive |
| Contributor | Record, upload, edit and organise; answer questions; review faces |
| Viewer | Browse and listen; nothing changes. A viewer may still change their own name and password |

**Executor** is not a role but a grant on top of one. The executor opens the sealed queue and carries out a
storyteller's legacy wishes (requirements section 15). Owners can do what the executor can.

The archive always keeps at least one owner: the last owner cannot be demoted or removed.

## Protection against forged requests (CSRF)

Every change (POST, PUT, PATCH, DELETE) must come from one of `MEMOIR_ALLOWED_ORIGINS`, by its Origin header or, if a
browser leaves that out, its Referer. A signed-in change must also send the session's CSRF token in an
`X-CSRF-Token` header. The API sets the token in a `memoir_csrf` cookie the app can read; the web client adds the
header to every change by itself.

## The audit log

Logins (and failed ones), owner creation, invitations made, revoked and accepted, role and executor changes,
temporary passwords, password changes, removals and "sign out everywhere" are recorded with who, whom, when and from
which address. The owner reads it at `GET /api/audit`.

## For developers

- Every router guards its routes with a dependency from `app/accounts/deps.py`: `require_role(Role.CONTRIBUTOR)`
  for changes, `require_role(Role.VIEWER)` for reading, `require_role(Role.OWNER)` for administration,
  `require_executor` for the sealed queue. `tests/test_roles.py` walks every route in the OpenAPI document and
  fails when a new route forgets.
- Tables that people edit use the `Audited` mixin (`app/core/audited.py`): `created_by`, `updated_by`,
  `updated_at` and `deleted_at` are filled from the request's user automatically. Removal sets `deleted_at`.
- Settings: `MEMOIR_PUBLIC_URL` (for invitation links), `MEMOIR_ALLOWED_ORIGINS`, `MEMOIR_COOKIE_SECURE` (off only
  on plain-http localhost), `MEMOIR_SESSION_IDLE_DAYS`, `MEMOIR_INVITATION_DAYS`, the `MEMOIR_LOGIN_*` limits, and
  `MEMOIR_FORWARDED_ALLOW_IPS` (the proxies whose X-Forwarded-For is believed).
