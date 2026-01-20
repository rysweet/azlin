#!/usr/bin/env node
/**
 * Icon generation script for PWA assets
 * Converts SVG to various PNG sizes required for PWA
 */

import sharp from 'sharp';
import { readFileSync, writeFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const AZURE_BLUE = '#0078d4';

async function generateIcons() {
  console.log('🎨 Generating PWA icons...');

  try {
    // Read the base SVG
    const svgBuffer = readFileSync(join(__dirname, 'icon-base.svg'));

    // Generate 192x192 icon
    console.log('📱 Creating pwa-192x192.png...');
    await sharp(svgBuffer)
      .resize(192, 192)
      .png()
      .toFile(join(__dirname, 'pwa-192x192.png'));

    // Generate 512x512 icon (maskable - with safe area)
    // For maskable icons, the design should be centered within 80% of the canvas
    console.log('📱 Creating pwa-512x512.png...');
    await sharp(svgBuffer)
      .resize(512, 512)
      .png()
      .toFile(join(__dirname, 'pwa-512x512.png'));

    // Generate apple-touch-icon (180x180)
    console.log('🍎 Creating apple-touch-icon.png...');
    await sharp(svgBuffer)
      .resize(180, 180)
      .png()
      .toFile(join(__dirname, 'apple-touch-icon.png'));

    // Generate favicon (32x32 for ico, we'll create a simple PNG)
    console.log('⭐ Creating favicon.png (32x32)...');
    await sharp(svgBuffer)
      .resize(32, 32)
      .png()
      .toFile(join(__dirname, 'favicon-32.png'));

    // Generate 16x16 favicon
    console.log('⭐ Creating favicon.png (16x16)...');
    await sharp(svgBuffer)
      .resize(16, 16)
      .png()
      .toFile(join(__dirname, 'favicon-16.png'));

    console.log('✅ All icons generated successfully!');
    console.log('\n📦 Generated files:');
    console.log('  - pwa-192x192.png');
    console.log('  - pwa-512x512.png');
    console.log('  - apple-touch-icon.png');
    console.log('  - masked-icon.svg (already exists)');
    console.log('  - favicon-16.png & favicon-32.png');
    console.log('\n💡 Note: For favicon.ico, you can use an online converter');
    console.log('   or install imagemagick: convert favicon-32.png favicon.ico');

  } catch (error) {
    console.error('❌ Error generating icons:', error.message);
    process.exit(1);
  }
}

generateIcons();
