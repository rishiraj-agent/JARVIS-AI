from __future__ import annotations

import urllib.parse
import webbrowser


def open_search(query: str) -> str:
    if not query.strip():
        return "Tell me what you would like to search for."
    url = "https://www.google.com/search?" + urllib.parse.urlencode({"q": query.strip()})
    if not webbrowser.open(url, new=2):
        return "I couldn't open your default browser. Check your Windows default-app settings."
    return f"Opened a browser search for: {query.strip()}\nThese live results are from your browser, not verified by JARVIS."


def open_website(address: str) -> str:
    value = address.strip()
    if not value:
        return "Please provide a website address."
    if "://" not in value:
        value = "https://" + value
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or any(
        character.isspace() for character in value
    ):
        return "That address is invalid. Use a public website URL beginning with http:// or https://."
    if not webbrowser.open(value, new=2):
        return "I couldn't open your default browser. Check your Windows default-app settings."
    return f"Opened {value}"
