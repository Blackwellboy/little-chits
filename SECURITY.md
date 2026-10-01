# Security

Please report security problems privately through GitHub's **Report a vulnerability** button on the Security tab,
not in a public issue.

## Scope

Little Chits is meant to run on your own machine. Things worth reporting:

- the game server reachable from the network without its access token (`--host 0.0.0.0 --token ...` should guard
  every read and write except the minimal health probe);
- a way for a model's reply to run code, write files or reach the network beyond the configured model servers;
- secrets (API keys in `brains.json`) leaking into logs, saves, recordings, exports or the browser.

Model servers you connect (llama.cpp, vLLM, Ollama, cloud APIs) are outside this project's scope.
