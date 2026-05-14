# SACP Participant Onboarding — Windows

**SACP Phase**: Phase 1 (post-rename; MCP protocol in Phase 2)
**Last Updated**: 2026-05-13
**Tested Against**: Claude Desktop (latest available); mcp-remote (latest npm)

This document covers Windows-specific setup steps; read `participant-onboarding.md` first for the bundle format and general workflow.

## Step 1: Locate the Claude Desktop Config File

The Claude Desktop configuration file lives at:

```
%APPDATA%\Claude\claude_desktop_config.json
```

To open this path in Explorer, press `Win+R`, type `%APPDATA%\Claude`, and press Enter. If the `Claude` directory does not exist, create it. If `claude_desktop_config.json` does not exist inside it, create the file (see the sample config block in Step 3).

## Step 2: Find the 8.3 Short Path for Node.js

**Why this matters:** When Claude Desktop launches `npx` on Windows, it uses `cmd.exe /C` internally to spawn the process. The `cmd.exe /C` invocation has a well-known space-handling bug: a path containing spaces — such as `C:\Program Files\nodejs\npx.cmd` — causes the spawn to fail silently. The config file accepts a path string and there is no error reported to the user; the MCP server simply never starts.

The fix is to use the 8.3 short-path form for any path segment containing spaces.

**How to find your machine's 8.3 name for Program Files:**

Open a cmd.exe window (press `Win+R`, type `cmd`, press Enter) and run:

```cmd
dir /x "C:\"
```

Look for the entry corresponding to `Program Files`. The 8.3 name appears in the column to the left of the long name and typically reads `PROGRA~1`. The exact name on your machine is authoritative — use the value `dir /x` reports, not the example here.

The resulting short path for `npx.cmd` is:

```
C:\PROGRA~1\nodejs\npx.cmd
```

If Node.js is installed to a different drive or directory, apply the same `dir /x` technique to find the 8.3 form of whichever path segment contains spaces.

## Step 3: The env-var Workaround for `--header`

**Why this matters:** On Windows, the `--header` argument value `"Authorization: Bearer mytoken"` fails because of the space after the colon. The `mcp-remote` process receives a malformed header value and the orchestrator sees no `Authorization` header, returning 401.

The working pattern uses **no space after the colon** in the `--header` argument, and places the actual token value in the `env` block as a named environment variable.

**WRONG — do not use this form on Windows:**

```text
"--header", "Authorization: Bearer SACP_DOC_EXAMPLE_A1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6"
```

The space after `Bearer` causes the header to be rejected on Windows.

**CORRECT — use this form:**

```text
"--header", "Authorization:Bearer ${SACP_BEARER_TOKEN}"
```

with the token value placed in the `env` block (see the full sample below). The `${SACP_BEARER_TOKEN}` interpolation is handled by `mcp-remote` at runtime; Claude Desktop passes the env block to the child process.

## Sample `claude_desktop_config.json` for Windows

Replace `000000000000` with the actual session_id from your bundle. Replace the `SACP_BEARER_TOKEN` value with your actual bearer token. If your machine's 8.3 name for `Program Files` differs from `PROGRA~1`, update the `command` path accordingly.

```json
{
  "mcpServers": {
    "sacp": {
      "command": "C:\\PROGRA~1\\nodejs\\npx.cmd",
      "args": [
        "mcp-remote",
        "http://orchestrator.example:8750/sse/000000000000",
        "--header",
        "Authorization:Bearer ${SACP_BEARER_TOKEN}"
      ],
      "env": {
        "SACP_BEARER_TOKEN": "SACP_DOC_EXAMPLE_A1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6"
      }
    }
  }
}
```

If your `claude_desktop_config.json` already contains entries for other MCP servers, the `mcpServers` object is a dictionary — add `"sacp": { ... }` as a new key alongside the existing entries. Do not replace the entire `mcpServers` block.

After editing, save the file with LF line endings (see Step 4 below), then restart Claude Desktop.

## Step 4: CRLF vs LF

**Why this matters:** Claude Desktop reads `claude_desktop_config.json` strictly. On some Windows installs, text editors save files with Windows-style CRLF (`\r\n`) line endings. CRLF inside a JSON file can cause Claude Desktop to silently fail to load the config — the symptom is that the SACP MCP server never appears in Claude Desktop's tool list, with no error message.

**How to check the line ending style:**

Open the file in VS Code. In the bottom-right corner of the status bar, you will see either `CRLF` or `LF`. If it shows `CRLF`, the file needs to be converted.

**Fix in VS Code:** Click the `CRLF` indicator in the bottom-right corner, select `LF` from the dropdown, then save the file.

**Fix in Notepad++:** Edit menu → EOL Conversion → Unix (LF).

**Fix in Notepad (modern Windows 11):** File → Save As → in the Encoding dropdown select `UTF-8` (not `UTF-8 with BOM`). Modern Notepad saves with LF line endings when UTF-8 is selected.

## Step 5: Windows Defender First-Run Stall

On first invocation of `npx mcp-remote`, Windows Defender's real-time scanner may stall the process while it scans the Node.js binaries and the `mcp-remote` npm package. This was the root cause observed in the 2026-05-12 debug session on Windows — the connection appeared to hang for several minutes with no error message before eventually succeeding (or timing out).

**Wait-it-out option:** On first run, wait 2–5 minutes before concluding there is a failure. If the connection eventually succeeds, no further action is needed; Defender will have cached the scan result and subsequent invocations will not stall.

**Exclusion path (if repeated stalls occur):** You can add the Node.js npm cache directory and the Node.js installation directory to Defender's excluded folders:

1. Open Windows Security → Virus & threat protection → Manage settings (under "Virus & threat protection settings") → Exclusions → Add or remove exclusions.
2. Add the following paths as folder exclusions:
   - `C:\Users\<your-username>\AppData\Roaming\npm`
   - `C:\Program Files\nodejs` (or your Node.js install directory)

**Risk note:** Adding a folder exclusion reduces Defender's scanning coverage for files in that directory. Only apply this exclusion if the stall is persistent and you are confident the Node.js installation came from a trusted source (e.g., the official installer from nodejs.org).

## Step 6: PowerShell vs cmd.exe Quoting for Manual Diagnostics

When running `mcp-remote` manually to diagnose a connection issue, the quoting rules differ between PowerShell and cmd.exe.

**PowerShell:**

```powershell
npx mcp-remote "http://orchestrator.example:8750/sse/000000000000" --header "Authorization:Bearer SACP_DOC_EXAMPLE_A1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6"
```

**cmd.exe:**

```cmd
npx mcp-remote http://orchestrator.example:8750/sse/000000000000 --header "Authorization:Bearer SACP_DOC_EXAMPLE_A1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6"
```

Key differences: PowerShell requires double quotes around the URL if you include any special characters; cmd.exe does not require quotes around a plain URL in this case. In both shells, the `--header` argument value must **not** have a space after the colon (`Authorization:Bearer`, not `Authorization: Bearer`).

When diagnostics succeed from the command line but fail from Claude Desktop, the most common cause is a path issue in the config (verify the 8.3 short path) or a CRLF issue in the file (verify line endings per Step 4).

## Reconnect After Sleep

When your laptop wakes from sleep, Windows Defender may re-scan the `mcp-remote` process before allowing it to resume. Symptoms: Claude Desktop shows the SACP tools as disconnected or unavailable after the wake. The fix is the same as the first-run stall — wait 2–5 minutes for Defender to complete the rescan. If this occurs repeatedly, apply the exclusion path from Step 5.

The SACP turn-event stream itself is stateless on reconnect; once Defender clears, the client re-subscribes and receives the next turn. No turns are replayed. See `participant-onboarding.md` for the catch-up path via session transcript export.

---

Following this guide end-to-end should take 15 minutes or less. If you encounter issues not covered here, the troubleshooting matrix in `participant-onboarding.md` is the first stop.
