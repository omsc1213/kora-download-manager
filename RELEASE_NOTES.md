# Kora 0.4.1 Preview

Fixes for public Twitter/X video links:

- Recognize official X, Twitter and mobile post URLs, remove tracking parameters, and preserve selected video numbers.
- Retry with Twitter's public syndication endpoint when the default extractor fails. Use the successful method for the actual download.
- Prefer Kora's installed video extractor over an older copy found on the system PATH.
- Add regression coverage for fallback downloads, cancellation, URL boundaries and extractor precedence.

Install: extract the Windows Online ZIP and run Setup.cmd. Existing users should close Kora before replacing their application files and run Setup-Video-Tools.cmd to refresh the extractor. Keep your existing data folder.

This is a preview. Private, deleted, login-required and DRM-protected videos are unsupported. Twitter/X can change its endpoints. Automated regression tests use simulated extractor responses; live site compatibility is not guaranteed. YouTube remains excluded.

