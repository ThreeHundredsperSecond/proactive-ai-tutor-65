// Render frozen statement images; no network access and no source solutions.
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const sharp = require(process.env.SHARP_MODULE || 'sharp');
const run = path.resolve(process.argv[2]);
const hash = p => crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
(async () => {
  const manifestPath = path.join(run, 'manifest.json');
  const m = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
  for (const task of m.tasks) for (const image of task.images) {
    const source = path.join(run, image.svg_path), target = path.join(run, image.path);
    if (hash(source) !== image.original_sha256) throw Error('Changed source image');
    if (!fs.existsSync(target)) await sharp(source, { density: 192 }).flatten({ background: '#ffffff' }).png().toFile(target);
    if (image.png_sha256 && hash(target) !== image.png_sha256) throw Error('Changed rendered image');
    image.png_sha256 = hash(target);
  }
  m.image_renderer = { tool: 'sharp', version: sharp.versions.sharp, density: 192, background: '#ffffff' };
  fs.writeFileSync(manifestPath, JSON.stringify(m, null, 2) + '\n');
  console.log('Statement images rendered and hashed');
})().catch(e => { console.error(e); process.exitCode = 1; });
