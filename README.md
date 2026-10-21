# Kora Download Manager

**A free, open-source alternative to IDM for Windows.**

Download files and supported videos, choose quality, and pick up paused transfers.
No payment or activation key is required by Kora. No built-in advertising.

**Preview release: v0.4.1.** Kora is an independent project, not affiliated with or
endorsed by Internet Download Manager (IDM). Feature parity and faster speeds
than IDM are not claimed.

## Get Kora

For Windows 10/11 x64. Internet access is required during setup.

Open [Releases](https://github.com/omsc1213/kora-download-manager/releases) and
download **Kora-v0.4.1-Windows-Online.zip**. Extract the complete folder and run
**Setup.cmd**. This is an online installer: internet access is required for
Python (when missing) and the video tools. Third-party binaries are obtained
from upstream sources, rather than included in this public ZIP.

The setup script reuses a compatible Python 3.10+ installation with Tcl/Tk when
available. Otherwise it offers the standard Python installer from python.org,
checks its Windows signature and publisher, and installs it for the current user.
Video-tool downloads are checked against published SHA-256 hashes.

If building from source, install Python 3.10+ with Tcl/Tk and run
`powershell -NoProfile -File .\Launch-Kora.ps1`. Run **Setup-Video-Tools.cmd**
before downloading video-page links. Rust is only needed to build the optional
native launcher and register the browser native host.

## What you can do

- Download direct HTTP/HTTPS files, with parallel transfers where supported.
- Pause and resume eligible downloads; retain the queue after restarting.
- Find formats on supported video pages and select a quality.
- Download accessible direct media, embedded players and unprotected HLS/DASH.
- Generate default names and save videos in a dedicated folder.
- Queue batches, inspect video details and view thumbnails when available.
- Save folder, quality and connection preferences.
- Update video tools, restore the previous tool set, and configure the browser extension.

**YouTube is intentionally excluded**, including embedded YouTube players.
Private or inaccessible media and DRM-protected streams are unsupported.
Some websites will fail or change. This is not an all-sites downloader.

## First use

1. Install with Setup.cmd. Keep Kora closed during an upgrade.
2. Open Video links, paste an individual video URL and select Find video.
3. Choose quality, review the name and folder, then add it to the queue.
4. Use Resume / Retry after a paused or failed transfer.
5. Use Settings & tools for folders, quality, updates and browser setup.

Browser installation is manual: enable Developer mode, load the `browser` folder
unpacked in Chrome or Edge, then register its extension ID inside Kora. Detection
monitors only the tab you explicitly select, for a limited period. The current
native host queues links; open Kora to process them.

## Status and verification

The development build passed 42 focused Python checks, 2 Rust tests, installer,
desktop and native-message protocol checks. Browser policy/capture simulations
also passed. See [VALIDATION.md](VALIDATION.md) for the public package's checks.
Live-site reliability, an installed-browser round trip and a real internet speed
advantage remain unverified. Speeds depend on your connection and the server.

Kora currently uses a Rust launcher and a Python/Tk desktop and download backend.
yt-dlp handles video extraction; FFmpeg handles media conversion/merging.
Optional REA investigation is separate from ordinary downloading and does not
need IDM installed. No IDM executable, extension or proprietary assets are included.

## Development

Create `test-work` before running tests. On Windows with Python/Tk installed:

```powershell
python -m unittest discover -s tests -p test_product_features.py -v
python -m unittest discover -s tests -p test_save_defaults.py -v
```

For all transport/media checks, install the video tools and run the full test
suite in an environment that permits local HTTP sockets. Build the launcher
with `cargo test --offline` and `cargo build --release --offline`, then copy
`target/release/kora.exe` beside `kora.py`. Test app preferences and the queue
use local files; never commit real browsing links or download history.

See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md) and
[THIRD_PARTY.md](THIRD_PARTY.md).

## License

Kora's original code is MIT-licensed. Dependencies retain their own licenses.
Download only content you are authorized to save and follow applicable site rules.

