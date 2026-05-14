# SACP Participant Onboarding — macOS

**SACP Phase**: Phase 1 (post-rename; MCP protocol in Phase 2)
**Last Updated**: 2026-05-13
**Tested Against**: Claude Desktop (latest available); mcp-remote (latest npm)

This document covers macOS-specific setup steps; read `participant-onboarding.md` first for the bundle format and general workflow.

## Step 1: Locate the Claude Desktop Config File

The Claude Desktop configuration file lives at:

```
~/Library/Application Support/Claude/claude_desktop_config.json
```

The `Library` folder is hidden by default in Finder. To navigate to it:

- In Finder: open the **Go** menu, then hold the **Option** key — the `Library` item appears in the menu. Click it to open `~/Library`.
- In Terminal: run `open ~/Library` to open the folder in Finder.

Once inside `~/Library`, navigate to `Application Support/Claude/`. If the `Claude` directory does not exist, create it. If `claude_desktop_config.json` does not exist inside it, create the file (see the sample config block in Step 2).

## Step 2: Add the SACP MCP Server Entry

macOS does not require the 8.3 short-path workaround or the env-var colon workaround that Windows requires. The standard `npx` command works directly.

**Sample `claude_desktop_config.json` for macOS:**

Replace `000000000000` with the actual session_id from your bundle. Replace the `SACP_BEARER_TOKEN` value with your actual bearer token.

```json
{
  "mcpServers": {
    "sacp": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "http://orchestrator.example:8750/sse/000000000000",
        "--header",
        "Authorization: Bearer ${SACP_BEARER_TOKEN}"
      ],
      "env": {
        "SACP_BEARER_TOKEN": "SACP_DOC_EXAMPLE_A1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6"
      }
    }
  }
}
```

On macOS, the `Authorization: Bearer` value **can** include a space after the colon — this differs from Windows, where the space causes a silent failure. The `${SACP_BEARER_TOKEN}` interpolation is handled by `mcp-remote` at runtime.

If your `claude_desktop_config.json` already contains entries for other MCP servers, the `mcpServers` object is a dictionary — add `"sacp": { ... }` as a new key alongside the existing entries without replacing the full block.

After editing, save the file and restart Claude Desktop.

## Step 3: Gatekeeper Quarantine

macOS applies a quarantine attribute to files downloaded from the internet. If macOS shows a dialog saying "can't be opened because it is from an unidentified developer" when Claude Desktop attempts to invoke `node` or `npx`, remove the quarantine attribute for that binary:

```bash
xattr -d com.apple.quarantine /path/to/node
```

To find the correct path:

```bash
which node
which npx
```

Run the `xattr -d` command for whichever binary is being blocked.

**Risk note:** Removing the quarantine attribute bypasses Gatekeeper's signature check for that specific binary. This is acceptable when the binary comes from the official Node.js installer (nodejs.org) and you have verified the installer's integrity. Do not remove the quarantine attribute from binaries obtained from unknown sources. The quarantine attribute on other files in your system is unaffected by this command.

If you encounter a Gatekeeper prompt that involves a different binary not anticipated in this doc, the general principle is the same (`xattr -d com.apple.quarantine <path>`), but verify the binary's source before proceeding.

## Step 4: First-Run Permission Prompts

Claude Desktop may present one or more permission prompts on first use of the SACP MCP server:

- **Network access prompt**: Allow. The SACP connection requires outbound network access to reach the orchestrator's SSE endpoint.
- **Keychain access prompt**: You may allow or deny. SACP uses the config file for credentials, not the system keychain. Denying keychain access does not affect SACP functionality.
- **Any prompt mentioning "sacp" or "mcp-remote"**: Allow. These prompts correspond to the `mcp-remote` bridge process that Claude Desktop is launching on your behalf.

If a prompt appears that is not listed here and you are unsure, consult your facilitator before allowing.

## Step 5: Apple Silicon Notes

Node.js from the official installer at nodejs.org ships as a **universal binary** that runs natively on both Intel and Apple Silicon (M-series) Macs without Rosetta 2. No special configuration is required for the SACP onboarding flow when using the official Node.js installer.

If you are managing Node.js with `nvm` or `volta`, verify that the active version is the native ARM64 build on Apple Silicon:

```bash
node -p "process.arch"
```

On an M-series Mac, this should return `arm64`. If it returns `x64`, your Node.js installation is running under Rosetta 2, which works but is slower. To switch to the native ARM64 build, use your version manager to install and activate an ARM64-native Node.js version (consult your version manager's documentation for the specific steps).

Rosetta 2 is **not required** for any part of the SACP onboarding flow when using the official Node.js universal installer.

## Reconnect After Sleep

The SACP turn-event stream is stateless on reconnect. When your Mac wakes from sleep and the connection is re-established, the client re-subscribes to the stream and receives the next turn — missed turns are not replayed. No special macOS handling is required beyond restarting Claude Desktop if the connection is not automatically re-established.

For the catch-up path via session transcript export, see `participant-onboarding.md`.

---

Following this guide end-to-end should take 15 minutes or less. If you encounter issues not covered here, the troubleshooting matrix in `participant-onboarding.md` is the first stop.
