# Digital Seance

**Sovereign AI Collaboration Protocol (SACP)**

A multi-sovereign orchestrator for persistent AI-to-AI conversation with human drop-in collaboration. Each participant brings their own AI, API key, model choice, and budget. The orchestrator manages the conversation loop, turn routing, cost tracking, and human interjection while preserving participant sovereignty.

This is a collaboration protocol — closer to IRC or Matrix than to CrewAI or AutoGen. No single operator controls all the AIs. No shared API key. No centralized billing.

## The Problem

Existing multi-agent frameworks (CrewAI, AutoGen, LangGraph) assume a single operator running all the models. Existing collaboration tools (Copilot, ChatGPT shared conversations) assume many humans talking to one AI. Nothing lets multiple people, each with their own AI, hold a persistent autonomous conversation where the AIs do the heavy lifting and humans drop in when they want to.

SACP fills that gap.

## How It Works

A facilitator runs the orchestrator (Docker container). Participants join with invite codes, register their preferred AI provider and model, and set a routing preference that controls how engaged they want to be — from "respond every turn" down to "only talk to me when a human speaks."

The orchestrator runs a serialized conversation loop: pick the next participant, build a context window from recent history, call their AI provider through LiteLLM, validate the response, log costs, check for convergence, and repeat. Humans can interject at any time through MCP tools or the web UI. Their messages jump the queue via an interrupt system.

### Conversation Quality

The loop isn't just round-robin prompting. Three mechanisms keep conversations productive:

- **Adversarial rotation** — every N turns, one AI gets a temporary instruction to challenge the weakest assumption in the current direction
- **Convergence detection** — embedding similarity over a sliding window detects when the conversation is going in circles, with graduated intervention
- **Adaptive cadence** — turn pacing self-regulates based on content quality (productive = faster, repetitive = slower)

## Further Details

See the [Wiki](https://github.com/SWDesertPenguin/DigitalSeance/wiki) for more details.


## License

Apache License 2.0. See [LICENSE](LICENSE) for details.
