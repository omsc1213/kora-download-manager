# Kora 0.4.2 Preview

- Unify desktop, command-file and native GUI launches through a checked Python launcher.
- Keep startup errors in data/startup.log and show an actionable error message.
- Add Check-Kora.cmd and the doctor command for local desktop/data/video-tool readiness checks.
- Reuse the saved Python path during upgrades and tolerate a broken system Python launcher.
- Route installed shortcuts through the same launcher.
- Preserve Twitter/X fallback support and existing download behavior.

Extract the complete Windows Online ZIP and run Setup.cmd. Close Kora before upgrading. Run Setup-Video-Tools.cmd to obtain current video dependencies. Existing data stays in place.

Validation: 55 Python regression tests, install/upgrade checks with paths containing spaces, preservation of existing data, missing-Python error logging and desktop readiness. The release workflow also runs browser checks and Rust tests/build. Fresh Python bootstrap and live Twitter downloads remain unverified locally. This is a preview; private and DRM-protected media are unsupported. YouTube remains excluded.
