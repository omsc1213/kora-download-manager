# Public preview validation

- Clean source regression suite: 42 tests passed.
- Rust launcher: 2 tests passed; release executable rebuilt from the public source.
- Browser URL policy and capture simulations: passed.
- Installer using an existing Python/Tk installation: passed in a temporary folder,
  with shortcut creation, launch and video downloads disabled for that check.
- Public native-messaging protocol using the installed Python path: passed.
- Source and asset archive privacy/allowlist scans and integrity checks: passed.

The original development edition also passed desktop startup/shutdown checks.
The public release's fresh Python download/bootstrap, upstream video-tool download,
live sites, real network speed comparisons, Windows restart recovery and an
installed-browser extension round trip remain unverified in this environment.
The earlier live media checks were blocked by Windows socket permissions.

The GitHub Actions workflow is prepared, not yet run on GitHub. This is a preview,
not a production-readiness or security certification. No IDM speed comparison is claimed.
