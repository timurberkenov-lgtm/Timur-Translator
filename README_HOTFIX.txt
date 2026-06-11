Timur Translator v16.3.3 macOS TLS certificate hotfix

Upload the CONTENTS of this folder to the root of your GitHub repository.
Replace existing files when GitHub asks.

What this fixes:
- macOS packaged app error: SSL: CERTIFICATE_VERIFY_FAILED
- OpenAI Realtime WebSocket TLS handshake in packaged .app builds

Important:
- Rebuild the desktop applications in GitHub Actions after uploading this patch.
- Download the NEW macOS artifact or publish a NEW release tag.
- Do not reuse an old .app: the CA bundle must be embedded during packaging.
