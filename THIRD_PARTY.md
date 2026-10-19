# Third-party components

Kora's original code is under the MIT license. This public source tree and public
online ZIP do not redistribute Python, Tcl/Tk, yt-dlp, FFmpeg or IDM binaries.

- Python / Tcl/Tk: obtained from a user's installation or the official signed
  Windows installer. https://www.python.org/ and https://docs.python.org/3/license.html
- yt-dlp: https://github.com/yt-dlp/yt-dlp . Installed from its published PyPI wheel;
  its metadata, licenses and component notices remain in the installed vendor folder.
- FFmpeg: https://ffmpeg.org/ . Acquired through the imageio-ffmpeg Windows wheel
  (https://github.com/imageio/imageio-ffmpeg). The selected binary may be GPL-licensed;
  the wrapper's BSD license does not replace FFmpeg's license. Installed license
  notices and artifact checksums are retained alongside the tools.
- Rust: https://www.rust-lang.org/ . The launcher is built from the included original source.
- REA: optional, separately installed by developers; no REA package is distributed here.

If you later redistribute a fully bundled installer, review and satisfy the
licenses and source requirements of its exact binaries before publishing it.
The earlier personal development ZIP is not the public release asset.
