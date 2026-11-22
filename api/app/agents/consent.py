"""The consent page: a small form, served by the API, where a person signs in with their
own Memoir email and password to connect an agent. No script, no outside resources.
"""

from html import escape
from urllib.parse import urlsplit

from fastapi.responses import HTMLResponse

# Hidden fields that carry the authorization request through the form, checked again
# when it comes back.
CARRIED = ("client_id", "redirect_uri", "code_challenge", "state", "resource", "scope")
HEADERS = {
    "Cache-Control": "no-store",
    # No form-action: browsers apply it to the redirect back to the agent too.
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; "
    "frame-ancestors 'none'",
    "X-Frame-Options": "DENY",
    # Not no-referrer: then the form would post Origin: null, which the origin check
    # refuses.
    "Referrer-Policy": "same-origin",
}
STYLE = (
    "body{font-family:system-ui,sans-serif;font-size:16px;max-width:28rem;"
    "margin:3rem auto;padding:0 1rem;color:#1b1b1b;line-height:1.5}"
    "label{display:block;margin-top:1rem;font-weight:600}"
    "input,button{font-size:1rem;width:100%;box-sizing:border-box;padding:.7rem;"
    "margin:.3rem 0;min-height:44px}"
    "button{border:0;border-radius:.4rem;cursor:pointer;margin-top:1rem}"
    ".allow{background:#1d4f91;color:#fff}.deny{background:#e8e8e8;color:#1b1b1b}"
    ".err{color:#a40000;font-weight:600}.hint{color:#555}"
    ":focus{outline:3px solid #f2a900;outline-offset:2px}"
)


def page(title: str, body: str, status: int = 200) -> HTMLResponse:
    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{escape(title)}</title><style>{STYLE}</style></head>"
        f"<body><main>{body}</main></body></html>"
    )
    return HTMLResponse(html, status, headers=HEADERS)


def problem(message: str, status: int = 400) -> HTMLResponse:
    """A request that cannot be sent back to the agent: say so here."""
    return page(
        "Memoir cannot connect this agent",
        f"<h1>Memoir cannot connect this agent</h1><p>{escape(message)}</p>"
        "<p class='hint'>Start again from the app you were connecting.</p>",
        status,
    )


def form(
    action: str,
    client_name: str,
    fields: dict,
    email: str = "",
    error: str | None = None,
    status: int = 200,
) -> HTMLResponse:
    app = escape(client_name)
    back_to = escape(urlsplit(fields["redirect_uri"]).netloc or "the app")
    hidden = "".join(
        f'<input type="hidden" name="{k}" value="{escape(fields.get(k) or "")}">'
        for k in CARRIED
    )
    alert = f'<p class="err" role="alert">{escape(error)}</p>' if error else ""
    body = (
        f"<h1>Connect {app} to Memoir</h1>"
        f"<p><strong>{app}</strong> will act as you in Memoir: it can read what you "
        "can read and, if your role allows, tell stories as you. It will return to "
        f"<strong>{back_to}</strong>.</p>"
        "<p class='hint'>You can disconnect it at any time from Your account.</p>"
        f"{alert}"
        f'<form method="post" action="{escape(action)}">{hidden}'
        '<label for="email">Your Memoir email</label>'
        f'<input id="email" name="email" type="email" value="{escape(email)}" '
        'autocomplete="username" required autofocus>'
        '<label for="password">Your Memoir password</label>'
        '<input id="password" name="password" type="password" '
        'autocomplete="current-password" required>'
        '<button class="allow" type="submit" name="decision" value="allow">'
        f"Sign in and connect {app}</button>"
        '<button class="deny" type="submit" name="decision" value="deny" '
        "formnovalidate>Cancel</button></form>"
    )
    return page(f"Connect {client_name} to Memoir", body, status)
