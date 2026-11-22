# Agents: Memoir through your own assistant

A storyteller who talks to Claude, ChatGPT or Gemini every day can tell that assistant a story, and it lands in
Memoir. A family member can ask their assistant "what did Mom say about the farm?". Memoir is an MCP server
(Model Context Protocol) at **https://dontpanic.ddns.net/memoir/mcp**, and the assistant signs in as you.

## What an agent can do

The agent acts as the person who connected it, with that person's role. It sees exactly what that person sees in
the web app, and nothing else.

| Tool | Who | What |
|---|---|---|
| `whoami` | Everyone | Your name, role and archive, and the tools your role allows |
| `search_memories` | Everyone | Stories by their words (title, summary or what was said), a person (told by or mentioning), or dates (`date_from`, `date_to`, read like any Memoir date: `1968`, `summer 1972`, `the 1960s`). 20 at a time, with `next_cursor` for more |
| `get_memory` | Everyone | One story: its words, dates, people, places, where it is filed, the question it answers, and a link to it in the app |
| `timeline` | Everyone | A person's periods in order, each with its events, and the events not yet placed. Your own when no person is given |
| `list_people` | Everyone | The people in the archive, by name, with what else they are called |
| `next_question` | Everyone | The interviewer's next question for you (`INTERVIEWER.md`) |
| `tell_story` | Contributors and owners | Saves a story in your own words, with an optional title, date and the question it answers |

A viewer's agent is not shown `tell_story`, and is refused it if it calls it anyway. Editing or deleting memories,
audio and photos are not offered to agents.

### Telling a story

`tell_story` makes a memory as a quick recording would (`CAPTURE.md`), except that the words are typed:

- The storyteller is you. The words are kept as the agent sent them, and no job ever replaces them.
- With a `question_id` (from `next_question`), it answers that question and goes where the question points.
- It is filed by placement, once, like a quick memory (`TIMELINE.md`). With a date, or an answer to a question
  about a period, it is filed at once and the tool says where. Without a date, it is filed once extraction has read
  one from the words. With AI off, and no date, it waits under **Waiting to be placed**.
- Extraction then finds the people and places, and the interviewer asks its follow-up questions, as for any story.
- The memory shows **Told through Claude** (the agent's name) in the app, under its date.

## Connecting an agent

In claude.ai: **Settings**, **Connectors**, **Add custom connector**, and give it
`https://dontpanic.ddns.net/memoir/mcp`. Claude opens Memoir's sign-in page: type your own Memoir email and password
and press **Sign in and connect**. The tools appear in Claude. Other assistants that take a remote MCP server with
OAuth connect the same way.

**Your account** lists your **Connected agents**: each one's name, when you connected it and when it was last used.
**Disconnect** ends it at once: its next call is refused, and it would have to be connected again. The stories it
told stay.

An agent is also disconnected when you change your password, when an owner sets you a temporary password, and when
an owner removes you.

## The security model

- **Memoir is its own OAuth 2.1 authorisation server.** Agents register themselves (RFC 7591 dynamic client
  registration), and get a code through the person's sign-in with PKCE (S256 only), then tokens for it.
- **The consent page is the web app's sign-in.** It takes the person's Memoir email and password, under the same
  rate limits as signing in to the app (5 failures from one address a minute, 10 on one account in 15 minutes), with
  the same answer for every refusal. A person who must choose a new password is refused until they do. The page
  posts only from Memoir's own origin (the CSRF origin check), and cannot be framed.
- **Where a person is sent back.** An agent may register only redirect addresses in `MEMOIR_AGENT_REDIRECT_URIS`
  (claude.ai's two by default) or on this computer (`http://localhost`, `127.0.0.1`), for desktop assistants. The
  consent page names the agent and the site it returns to.
- **Tokens.** An access token lasts an hour (`MEMOIR_AGENT_ACCESS_MINUTES`); a refresh token 90 days
  (`MEMOIR_AGENT_REFRESH_DAYS`) and is replaced each time it is used. A code lasts five minutes and works once; a
  code used twice ends its connection. The database keeps only SHA-256 hashes of codes, tokens and client secrets.
- **Every call is checked again:** the token, its connection, and the person (removed, or waiting for a new
  password, means refused). Tools go through the same services, role checks and `memories.visible_to` as the web
  app.
- **No cookies.** The token, registration and revocation endpoints and `/mcp` are called by the agent's own
  servers, which send no Origin header. They read no cookie, so the origin check does not apply to them; each
  checks its own credential instead.
- **Logs** carry the client id and the tool name, never what was asked or told. The audit log records
  `agent.connected` (with the agent's name) and `agent.disconnected`.
- **No AI inside a tool.** Placement is a pure function; extraction and questions run as jobs, as for a recording.

## The endpoints

| Path (under `https://dontpanic.ddns.net`) | What |
|---|---|
| `/memoir/mcp` | The MCP server: Streamable HTTP, stateless, JSON responses. Bearer token required; without one, a 401 whose `WWW-Authenticate` names the metadata below |
| `/.well-known/oauth-protected-resource/memoir/mcp` | RFC 9728 protected resource metadata |
| `/.well-known/oauth-authorization-server/memoir` | RFC 8414 authorisation server metadata. The issuer is `https://dontpanic.ddns.net/memoir` |
| `/memoir/.well-known/...` | The same two documents, for clients that look under the issuer's path |
| `/memoir/api/oauth/register` | Dynamic client registration |
| `/memoir/api/oauth/authorize` | The consent page (GET) and its form (POST) |
| `/memoir/api/oauth/token` | Codes and refresh tokens for access tokens |
| `/memoir/api/oauth/revoke` | RFC 7009 revocation. Revoking a refresh token ends the whole connection |

`RUNBOOK.md` has the Caddy routes these need.

## For developers

`api/app/agents/`: `models.py` (clients, grants, codes, tokens), `grants.py` (what OAuth issues, and who a token
speaks for), `oauth.py` and `consent.py` (the endpoints and the consent page), `server.py` (the MCP server, its
tools and the bearer check, on the official `mcp` SDK, pinned), `tools.py` (each tool as a function of the session
and the person), `router.py` (the profile page's list and Disconnect). A new tool goes in `tools.py`, registered in
`server.py`, and is listed in `tools.READ` or `tools.WRITE`. `tests/test_agents_oauth.py` and
`tests/test_agents_mcp.py` cover the flow and every tool as each role.
