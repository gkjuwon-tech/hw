const fs = require('fs');
const sharp = require('sharp');
const pngToIco = require('png-to-ico');

const svgCode = `
<svg width="512" height="512" viewBox="0 0 512 512" xmlns="http://www.w3.org/2000/svg">
  <rect width="512" height="512" rx="100" fill="#0B0C0A" />
  
  <g stroke="#3a3c36" stroke-width="12">
    <!-- Vertical lines -->
    <line x1="128" y1="96" x2="128" y2="416" />
    <line x1="256" y1="96" x2="256" y2="416" />
    <line x1="384" y1="96" x2="384" y2="416" />
    
    <!-- Horizontal lines -->
    <line x1="96" y1="128" x2="416" y2="128" />
    <line x1="96" y1="256" x2="416" y2="256" />
    <line x1="96" y1="384" x2="416" y2="384" />
  </g>

  <!-- Normal intersections -->
  <g fill="#4f6d1d">
    <circle cx="128" cy="128" r="16" />
    <circle cx="256" cy="128" r="16" />
    <circle cx="384" cy="128" r="16" />
    <circle cx="128" cy="256" r="16" />
    <circle cx="384" cy="256" r="16" />
    <circle cx="128" cy="384" r="16" />
    <circle cx="256" cy="384" r="16" />
    <circle cx="384" cy="384" r="16" />
  </g>

  <!-- Active "pressure" intersection (center) -->
  <circle cx="256" cy="256" r="48" fill="#b5e853" opacity="0.3" filter="blur(8px)" />
  <circle cx="256" cy="256" r="28" fill="#b5e853" />
</svg>
`;

fs.writeFileSync('build/icon.svg', svgCode);

async function generateIcons() {
  console.log('Generating PNG...');
  await sharp(Buffer.from(svgCode))
    .resize(512, 512)
    .png()
    .toFile('build/icon.png');
    
  console.log('Generating ICO...');
  const buf = await pngToIco('build/icon.png');
  fs.writeFileSync('build/icon.ico', buf);
  console.log('Done!');
}

generateIcons().catch(console.error);
