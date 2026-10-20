"""Claude calls for the AI-assisted steps. Streams text back to the UI."""
from __future__ import annotations

import base64
from collections.abc import Iterator

import anthropic

MODEL = "claude-opus-5-5"


def document_blocks(docs: list[dict]) -> list[dict]:
    """docs: [{id, name, kind: 'pdf'|'text', data: bytes|str}] -> content blocks."""
    blocks = []
    for d in docs:
        title = f"{d['id']} — {d['name']}"
        if d["kind"] == "pdf":
            blocks.append(
                {
                    "type": "document",
                    "title": title,
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": base64.standard_b64encode(d["data"]).decode(),
                    },
                }
            )
        else:
            blocks.append(
                {
                    "type": "document",
                    "title": title,
                    "source": {"type": "text", "media_type": "text/plain", "data": d["data"]},
                }
            )
    return blocks


def stream_step(
    api_key: str | None,
    system: str,
    user: str,
    docs: list[dict] | None = None,
    effort: str = "high",
) -> Iterator[str]:
    """Yield response text as it streams. Raises RuntimeError with a readable message."""
    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
    content = document_blocks(docs or []) + [{"type": "text", "text": user}]
    try:
        with client.beta.messages.stream(
            model=MODEL,
            max_tokens=64000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            thinking={"type": "adaptive"},
            output_config={"effort": effort},
            system=system,
            messages=[{"role": "user", "content": content}],
        ) as stream:
            for event in stream:
                if event.type == "content_block_delta" and event.delta.type == "text_delta":
                    yield event.delta.text
            final = stream.get_final_message()
    except anthropic.AuthenticationError as e:
        raise RuntimeError("Claude rejected the API key.") from e
    except anthropic.RateLimitError as e:
        raise RuntimeError("Rate limited by the Claude API — try again shortly.") from e
    except anthropic.BadRequestError as e:
        raise RuntimeError(f"Claude API rejected the request: {e.message}") from e
    except anthropic.APIStatusError as e:
        raise RuntimeError(f"Claude API error {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise RuntimeError("Could not reach the Claude API.") from e
    except TypeError as e:
        # raised by the client when no API key or other credential is configured
        if "authentication" not in str(e):
            raise
        raise RuntimeError("No Claude API key configured.") from e

    if final.stop_reason == "refusal":
        yield "\n\n> Claude declined this request."
    elif final.stop_reason == "max_tokens":
        yield "\n\n> Output truncated at the token limit."
