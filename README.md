# Minecraft Bedrock Realms for Home Assistant

**Status: early development (Phase 3 — proof of concept).** Not yet installable via HACS.

An unofficial Home Assistant custom integration for monitoring Minecraft Bedrock Realms /
Realms Plus, via Microsoft/Xbox authentication. Not affiliated with Mojang or Microsoft.

- [Research notes](docs/research.md) — confirmed API/auth mechanism, sourced from reading the
  actual code of prismarine-realms, prismarine-auth, elytra-ms, and RealmsPlayerlistBot.
- [Architecture](docs/architecture.md) — the chosen design and why.

## Current state

The authentication and Realms API client live under
`custom_components/minecraft_bedrock_realms/` and are exercised by a standalone CLI at
`poc/realm_cli.py`. The full Home Assistant integration (config flow, sensors, coordinator) is
not implemented yet — that's Phase 4, gated on the PoC successfully reading real Realm data.

### Running the proof-of-concept

```bash
pip install -r requirements-dev.txt
python -m poc.realm_cli
```

This will print a Microsoft device-code login URL and code. Open it in any browser, sign in with
the Microsoft account that owns or has joined the Realm you want to monitor, and the CLI will
print that account's Realms, their open/closed state, and who's currently online.

## License

MIT — see [LICENSE](LICENSE).
