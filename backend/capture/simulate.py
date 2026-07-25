"""Someone to be on the other end of the call.

The check-in loop needs a counterparty to run at all, and the counterparty is
also the experiment. A check-in that only works against a cooperative patient —
one who volunteers everything relevant the moment they are asked how things are
going — does not work, because that patient does not exist and is not who this
is for.

So LlmPatient is given symptoms it is told never to volunteer. If the agent's
open question misses them and its direct question finds them, that is the whole
thesis demonstrated rather than asserted: some things have to be asked about,
and knowing which things is what the disease context is for.

ScriptedPatient replays fixed answers, needs no API key, and is what the tests
and the offline demo run on. Freeze an LlmPatient conversation into one of
these and the demonstration replays forever, for free.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

import anthropic
import openai
from dotenv import load_dotenv

load_dotenv()

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-5")
PROVIDER = os.environ.get("LLM_PROVIDER", "anthropic").strip().lower()
CODEX_MODEL = os.environ.get("CODEX_MODEL", "gpt-5")
CODEX_BASE_URL = os.environ.get("CODEX_BASE_URL", "https://api.openai.com/v1")

PATIENT_PROMPT = """You are role-playing a patient receiving a short check-in \
phone call from a health app, weeks after a doctor's appointment. Answer as \
that person would — not as an assistant, and not as a good interviewee.

Who you are:
{persona}

How you actually are right now:
{state}

Things that are true about you but which you WILL NOT mention unless you are \
asked about them specifically and directly:
{hidden}

These last ones matter. You have not connected them to your appointment or \
your treatment at all — as far as you are concerned they are unrelated, or \
just life. If someone asks an open question like "has anything changed?" or \
"anything new?", you say no, or you mention something else entirely. Only if \
someone asks about one of them by name — or describes it closely enough that \
you realise that is what they mean — do you say yes, and then you talk about \
it naturally, the way someone does when they had not thought it was worth \
mentioning.

How to speak:
- One or two sentences. This is a phone call, not an essay.
- Plain spoken English, with the hesitations and vagueness of speech.
- Do not use clinical words for your symptoms. Describe them the way you would \
to a friend.
- If you are asked something you do not know, say so.
- Never break character and never mention that you are role-playing.

Reply with only what you say out loud. No quotation marks, no narration."""


class SimulateError(RuntimeError):
    """The simulated patient could not respond."""


@dataclass
class ScriptedPatient:
    """A patient whose answers are decided in advance.

    Replies are matched by keyword against what the agent said, so a script
    survives the agent rewording its questions — which it will, since it writes
    them itself. First match wins, so put the specific patterns first.
    """

    replies: list[tuple[str, str]] = field(default_factory=list)
    default: str = "I'm not sure, sorry."
    said: list[str] = field(default_factory=list)

    def respond(self, agent_said: str) -> str:
        self.said.append(agent_said)
        haystack = agent_said.lower()
        for pattern, reply in self.replies:
            if re.search(pattern, haystack, re.IGNORECASE):
                return reply
        return self.default

    @classmethod
    def from_file(cls, path) -> "ScriptedPatient":
        """Load a script: {"replies": [[pattern, reply], ...], "default": str}."""
        body = json.loads(open(path).read())
        return cls(
            replies=[tuple(pair) for pair in body.get("replies", [])],
            default=body.get("default", cls.default),
        )


@dataclass
class StdinPatient:
    """You, at the terminal.

    The best development loop there is, and a viable demo fallback when a live
    voice call will not cooperate.
    """

    said: list[str] = field(default_factory=list)

    def respond(self, agent_said: str) -> str:
        print(f"\n  AGENT: {agent_said}")
        reply = input("  YOU:   ").strip()
        self.said.append(reply)
        return reply or "I don't know."


@dataclass
class LlmPatient:
    """A patient played by a model, with things it will not volunteer.

    `hidden_symptoms` should be phrases from the disease context's watch_for
    vocabulary. Give it the over-replacement cluster and the call becomes the
    experiment: an agent that only asks open questions comes away with nothing,
    and one that reads the context and asks directly comes away with the catch.
    """

    persona: str = (
        "A 52-year-old who had part of their thyroid removed a couple of months "
        "ago and started on thyroid tablets after the last appointment. Busy, "
        "not especially interested in medical detail, a bit vague about dates."
    )
    state: str = (
        "The tiredness is a little better than it was. You have been taking the "
        "tablet most mornings, though you forgot a couple of times. You have not "
        "had the repeat blood test yet — you keep meaning to book it."
    )
    hidden_symptoms: list[str] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)
    said: list[str] = field(default_factory=list)

    def _system(self) -> str:
        hidden = (
            "\n".join(f"- {s}" for s in self.hidden_symptoms)
            if self.hidden_symptoms
            else "- (nothing in particular)"
        )
        return PATIENT_PROMPT.format(
            persona=self.persona, state=self.state, hidden=hidden
        )

    def respond(self, agent_said: str) -> str:
        self.history.append({"role": "user", "content": agent_said})

        if PROVIDER == "codex":
            if not os.environ.get("CODEX_API_KEY"):
                raise SimulateError("CODEX_API_KEY is not set.")
            client = openai.OpenAI(
                api_key=os.environ["CODEX_API_KEY"], base_url=CODEX_BASE_URL
            )
            try:
                response = client.chat.completions.create(
                    model=CODEX_MODEL,
                    messages=[
                        {"role": "system", "content": self._system()},
                        *self.history,
                    ],
                )
            except openai.APIError as exc:
                raise SimulateError(f"Simulated patient failed: {exc}") from exc
            reply = (response.choices[0].message.content or "").strip()
        else:
            if not os.environ.get("ANTHROPIC_API_KEY"):
                raise SimulateError("ANTHROPIC_API_KEY is not set.")
            try:
                response = anthropic.Anthropic().messages.create(
                    model=MODEL,
                    max_tokens=300,
                    system=self._system(),
                    messages=self.history,
                )
            except anthropic.APIError as exc:
                raise SimulateError(f"Simulated patient failed: {exc}") from exc
            reply = "".join(
                b.text for b in response.content if getattr(b, "type", None) == "text"
            ).strip()

        self.history.append({"role": "assistant", "content": reply})
        self.said.append(reply)
        return reply

    def as_script(self) -> dict:
        """Freeze this conversation so it can be replayed without a key."""
        replies = []
        for i in range(0, len(self.history) - 1, 2):
            asked = self.history[i]["content"]
            answered = self.history[i + 1]["content"]
            # A few distinctive words are a better key than the whole question,
            # since the agent rephrases between runs.
            words = [w for w in re.findall(r"[a-z]{5,}", asked.lower())][:3]
            replies.append([r"\b" + r"\b.*\b".join(words) + r"\b", answered])
        return {"replies": replies, "default": "I'm not sure, sorry."}
