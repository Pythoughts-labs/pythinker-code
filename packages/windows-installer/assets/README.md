# Installer assets

- `pythinker.ico` — Windows multi-resolution icon (16/32/48/256). Regenerate
  from `docs/media/logo.png` with ImageMagick:
  `magick docs/media/logo.png -define icon:auto-resize=16,32,48,256 packages/windows-installer/assets/pythinker.ico`.
  Committed as a binary blob; do not hand-edit.

- `LICENSE.rtf` — Apache-2.0 wrapper shown on the wizard's EULA page.

- (Optional) `pythinker-banner.bmp` (164×314, 24-bit) — left wizard image.
- (Optional) `pythinker-header.bmp` (150×57, 24-bit) — top-right wizard image.

If the optional banners are absent, Inno Setup falls back to its default
modern-style wizard chrome, which is acceptable for v1.
