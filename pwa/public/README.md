# PWA Icon Assets

This directory contains all icon assets required for the Azlin PWA installation.

## Generated Assets

All icons are generated from `icon-base.svg` using the generation scripts:

### PNG Icons
- `pwa-192x192.png` - Standard PWA icon (192×192)
- `pwa-512x512.png` - Large PWA icon with maskable support (512×512)
- `apple-touch-icon.png` - iOS home screen icon (180×180)
- `favicon.ico` - Browser favicon (multi-size: 16×16, 32×32)

### SVG Icons
- `icon-base.svg` - Source SVG with Azure branding (#0078d4)
- `masked-icon.svg` - Monochrome icon for Safari pinned tabs

## Design

The icons feature:
- **Azure Blue background** (#0078d4) - Microsoft Azure brand color
- **White 'A' letter** - Represents "Azlin"
- **Subtle cloud symbol** - References Azure cloud platform
- **Rounded corners** - Modern, friendly appearance
- **Gradient overlay** - Adds depth and polish

## Regenerating Icons

If you need to regenerate the icons (e.g., after modifying `icon-base.svg`):

```bash
cd pwa/public
npm install
npm run generate
node create-favicon.js
```

This will regenerate all PNG assets and the favicon.ico file.

## Maskable Icon Guidelines

The 512×512 icon is used as a maskable icon (Android adaptive icons). The design ensures all important content stays within the safe area (80% of canvas, centered).

## Browser Support

These assets provide comprehensive PWA installation support for:
- ✅ Chrome/Edge (Android & Desktop)
- ✅ Safari (iOS & macOS)
- ✅ Firefox
- ✅ Samsung Internet
- ✅ Opera

## References

- [PWA Icon Requirements](https://web.dev/articles/add-manifest)
- [Maskable Icons](https://web.dev/articles/maskable-icon)
- [Apple Touch Icons](https://developer.apple.com/design/human-interface-guidelines/app-icons)
