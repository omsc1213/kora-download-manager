# Publish this prepared package

Planned owner: omsc1213
Planned repository: kora-download-manager

1. Create an empty public repository at https://github.com/new . Do not initialize
   it with another README, license or .gitignore; this tree includes them.
2. Upload the CONTENTS of this folder as the repository root. Do not upload this
   folder as one nested directory. The source ZIP can be extracted first.
3. Alternatively, in this folder:

   git init -b main
   git add .
   git commit -m "Prepare Kora 0.4 public preview"
   git remote add origin https://github.com/omsc1213/kora-download-manager.git
   git push -u origin main

4. Draft a GitHub release with tag v0.4.0 and title Kora 0.4.0 Preview.
   Use RELEASE_NOTES.md as its body and mark it as a pre-release.
5. Attach Kora-v0.4.0-Windows-Online.zip and SHA256SUMS.txt from the public output
   folder, not the earlier personal Kora-Download-Manager-v04.zip.
6. Enable Issues and private vulnerability reporting. Add a real screenshot or
   demo recorded from your own app before promoting it widely.
7. Publish the release, check its download/install flow on another Windows PC,
   then use marketing/LAUNCH_COPY.md to announce it.

The prepared source contains no personal queue, downloaded media, REA evidence,
cached runtime, vendored binaries, credentials or previous work records.
This preparation does not mean a GitHub repository or release is already public.
