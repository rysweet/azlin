#!/usr/bin/env node
/**
 * Create favicon.ico from PNG files
 */

import pngToIco from 'png-to-ico';
import { writeFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

async function createFavicon() {
  console.log('⭐ Creating favicon.ico...');

  try {
    // Create ICO with multiple sizes (16x16 and 32x32)
    const buf = await pngToIco([
      join(__dirname, 'favicon-16.png'),
      join(__dirname, 'favicon-32.png')
    ]);

    writeFileSync(join(__dirname, 'favicon.ico'), buf);
    console.log('✅ favicon.ico created successfully!');
  } catch (error) {
    console.error('❌ Error creating favicon:', error.message);
    process.exit(1);
  }
}

createFavicon();
