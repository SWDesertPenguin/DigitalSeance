# Implementation Plan: AI Security Pipeline

**Branch**: `007-ai-security-pipeline` | **Date**: 2026-04-12 | **Spec**: [spec.md](spec.md)

## Summary

Defense-in-depth security layer for AI-to-AI conversation: context sanitization (injection pattern stripping), inter-agent spotlighting (datamarking), output validation (pattern + semantic), exfiltration filtering, jailbreak detection, prompt extraction defense, and log scrubbing. Integrates into existing turn loop and context assembly.

## Technical Context

**Language/Version**: Python 3.11+ (existing)
**Primary Dependencies**: N/A
**Storage**: N/A
No new dependencies. Pure Python regex, hashlib, and string processing.

## Constitution Check

All gates pass. This feature directly addresses V10 (AI security pipeline) — previously partial, now fully enforced.

## Project Structure

### New Files

```text
src/security/
├── __init__.py
├── sanitizer.py           # Injection pattern stripping
├── spotlighting.py        # Datamarking for inter-agent messages
├── output_validator.py    # Pattern + semantic validation
├── exfiltration.py        # URL, markdown, credential filtering
├── jailbreak.py           # Behavioral drift heuristics
├── prompt_protector.py    # Canary tokens, fragment scanning
├── scrubber.py            # Log credential redaction

tests/
├── test_sanitizer.py
├── test_spotlighting.py
├── test_output_validator.py
├── test_exfiltration.py
├── test_jailbreak.py
├── test_prompt_protector.py
├── test_scrubber.py
```

### Existing Code to Modify

- `src/orchestrator/context.py` — apply sanitizer + spotlighting in _add_messages
- `src/orchestrator/loop.py` — run output validation after dispatch, before persist
