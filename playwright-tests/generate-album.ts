#!/usr/bin/env node
/**
 * Screenshot Album Generator
 * 
 * Generates a beautiful HTML album/gallery from Playwright screenshots.
 * Groups screenshots by category, shows thumbnails, and allows filtering.
 * 
 * Usage:
 *   npx tsx generate-album.ts [screenshots-dir]
 * 
 * Or via Makefile:
 *   make screenshots-album
 */

import * as fs from 'fs';
import * as path from 'path';

interface ScreenshotGroup {
  name: string;
  title: string;
  screenshots: Screenshot[];
}

interface Screenshot {
  name: string;
  filename: string;
  timestamp: string;
  isLatest: boolean;
  fullPath: string;
}

function parseScreenshotFilename(filename: string): { name: string; timestamp: string; isLatest: boolean } | null {
  // Match patterns like: survey-list-2024-03-15.png or survey-list-latest.png
  // Format: {category}-{name}-{YYYY-MM-DD}.png or {category}-{name}-latest.png
  const timestampMatch = filename.match(/^(.+)-(\d{4}-\d{2}-\d{2})\.png$/);
  const latestMatch = filename.match(/^(.+)-latest\.png$/);
  
  if (timestampMatch) {
    return {
      name: timestampMatch[1],
      timestamp: timestampMatch[2],
      isLatest: false,
    };
  } else if (latestMatch) {
    return {
      name: latestMatch[1],
      timestamp: 'latest',
      isLatest: true,
    };
  }
  return null;
}

function formatTimestamp(timestamp: string): string {
  if (timestamp === 'latest') return 'Latest';
  
  // Parse YYYY-MM-DD format
  return timestamp;
}

function getPrefix(name: string): string {
  // Extract the first part before the first dash
  // e.g., "controlpanel-main-chromium-2024-03-05" -> "controlpanel"
  const firstDash = name.indexOf('-');
  if (firstDash === -1) return name;
  return name.substring(0, firstDash);
}

function groupScreenshots(screenshots: Screenshot[]): ScreenshotGroup[] {
  const groups = new Map<string, Screenshot[]>();
  
  for (const screenshot of screenshots) {
    // Group by prefix (first part of filename)
    const groupName = getPrefix(screenshot.name);
    
    if (!groups.has(groupName)) {
      groups.set(groupName, []);
    }
    groups.get(groupName)!.push(screenshot);
  }
  
  // Convert to array and sort
  const groupTitles: Record<string, string> = {
    'controlpanel': '⚙️ Control Panels',
    'psf': '🎨 Privacy Forms Studio',
    'survey': '📋 Survey',
    'metadata': '📊 Metadata Fieldsets',
    'general': '📁 General',
    'other': '📁 Other',
  };
  
  return Array.from(groups.entries())
    .map(([name, items]) => ({
      name,
      title: groupTitles[name] || `${name.charAt(0).toUpperCase()}${name.slice(1)}`,
      screenshots: items.sort((a, b) => b.timestamp.localeCompare(a.timestamp)),
    }))
    .sort((a, b) => a.title.localeCompare(b.title));
}

function generateHTML(groups: ScreenshotGroup[], outputDir: string): string {
  const totalScreenshots = groups.reduce((sum, g) => sum + g.screenshots.length, 0);
  const latestScreenshots = groups.flatMap(g => g.screenshots).filter(s => s.isLatest).length;
  
  const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>📸 SurveyJS Screenshot Album</title>
  <style>
    :root {
      --bg-primary: #0f172a;
      --bg-secondary: #1e293b;
      --bg-card: #334155;
      --text-primary: #f8fafc;
      --text-secondary: #94a3b8;
      --accent: #3b82f6;
      --accent-hover: #2563eb;
      --border: #475569;
      --shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
    }
    
    * {
      margin: 0;
      padding: 0;
      box-sizing: border-box;
    }
    
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
      background: var(--bg-primary);
      color: var(--text-primary);
      line-height: 1.6;
      min-height: 100vh;
    }
    
    header {
      background: linear-gradient(135deg, var(--bg-secondary) 0%, var(--bg-card) 100%);
      padding: 2rem;
      border-bottom: 1px solid var(--border);
      position: sticky;
      top: 0;
      z-index: 100;
      backdrop-filter: blur(10px);
    }
    
    .header-content {
      max-width: 1600px;
      margin: 0 auto;
    }
    
    h1 {
      font-size: 2rem;
      margin-bottom: 0.5rem;
      display: flex;
      align-items: center;
      gap: 0.75rem;
    }
    
    .subtitle {
      color: var(--text-secondary);
      font-size: 0.95rem;
    }
    
    .stats {
      display: flex;
      gap: 2rem;
      margin-top: 1rem;
      flex-wrap: wrap;
    }
    
    .stat {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      font-size: 0.9rem;
    }
    
    .stat-value {
      font-size: 1.5rem;
      font-weight: 700;
      color: var(--accent);
    }
    
    .controls {
      max-width: 1600px;
      margin: 1.5rem auto;
      padding: 0 2rem;
      display: flex;
      gap: 1rem;
      flex-wrap: wrap;
      align-items: center;
    }
    
    .search-box {
      flex: 1;
      min-width: 250px;
      max-width: 400px;
      position: relative;
    }
    
    .search-box input {
      width: 100%;
      padding: 0.75rem 1rem 0.75rem 2.5rem;
      background: var(--bg-secondary);
      border: 1px solid var(--border);
      border-radius: 0.5rem;
      color: var(--text-primary);
      font-size: 0.95rem;
      transition: border-color 0.2s;
    }
    
    .search-box input:focus {
      outline: none;
      border-color: var(--accent);
    }
    
    .search-box::before {
      content: "🔍";
      position: absolute;
      left: 0.75rem;
      top: 50%;
      transform: translateY(-50%);
    }
    
    .filter-buttons {
      display: flex;
      gap: 0.5rem;
      flex-wrap: wrap;
    }
    
    .filter-btn {
      padding: 0.5rem 1rem;
      background: var(--bg-secondary);
      border: 1px solid var(--border);
      border-radius: 0.5rem;
      color: var(--text-secondary);
      cursor: pointer;
      font-size: 0.85rem;
      transition: all 0.2s;
    }
    
    .filter-btn:hover,
    .filter-btn.active {
      background: var(--accent);
      border-color: var(--accent);
      color: white;
    }
    
    main {
      max-width: 1600px;
      margin: 0 auto;
      padding: 0 2rem 3rem;
    }
    
    .group {
      margin-bottom: 3rem;
    }
    
    .group-header {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      margin-bottom: 1.5rem;
      padding-bottom: 0.75rem;
      border-bottom: 2px solid var(--border);
    }
    
    .group-title {
      font-size: 1.5rem;
      font-weight: 600;
    }
    
    .group-count {
      background: var(--bg-card);
      padding: 0.25rem 0.75rem;
      border-radius: 1rem;
      font-size: 0.85rem;
      color: var(--text-secondary);
    }
    
    .screenshot-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
      gap: 1.5rem;
    }
    
    .screenshot-card {
      background: var(--bg-secondary);
      border-radius: 0.75rem;
      overflow: hidden;
      border: 1px solid var(--border);
      transition: transform 0.2s, box-shadow 0.2s;
      cursor: pointer;
    }
    
    .screenshot-card:hover {
      transform: translateY(-4px);
      box-shadow: var(--shadow);
    }
    
    .screenshot-card.hidden {
      display: none;
    }
    
    .screenshot-thumbnail {
      width: 100%;
      aspect-ratio: 16/10;
      object-fit: cover;
      background: var(--bg-primary);
      border-bottom: 1px solid var(--border);
    }
    
    .screenshot-info {
      padding: 1rem;
    }
    
    .screenshot-name {
      font-weight: 600;
      margin-bottom: 0.25rem;
      word-break: break-word;
    }
    
    .screenshot-meta {
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 0.85rem;
      color: var(--text-secondary);
    }
    
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 0.25rem;
      padding: 0.25rem 0.5rem;
      border-radius: 0.25rem;
      font-size: 0.75rem;
      font-weight: 500;
    }
    
    .badge-latest {
      background: #10b981;
      color: white;
    }
    
    .badge-timestamp {
      background: var(--bg-card);
      color: var(--text-secondary);
    }
    
    /* Lightbox */
    .lightbox {
      display: none;
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: rgba(0, 0, 0, 0.95);
      z-index: 1000;
      padding: 2rem;
    }
    
    .lightbox.active {
      display: flex;
      flex-direction: column;
    }
    
    .lightbox-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 1rem;
    }
    
    .lightbox-title {
      font-size: 1.25rem;
    }
    
    .lightbox-close {
      background: none;
      border: none;
      color: var(--text-primary);
      font-size: 2rem;
      cursor: pointer;
      padding: 0.5rem;
      line-height: 1;
    }
    
    .lightbox-content {
      flex: 1;
      display: flex;
      justify-content: center;
      align-items: center;
      overflow: hidden;
    }
    
    .lightbox-image {
      max-width: 100%;
      max-height: 100%;
      object-fit: contain;
      border-radius: 0.5rem;
    }
    
    .lightbox-nav {
      display: flex;
      justify-content: center;
      gap: 1rem;
      margin-top: 1rem;
    }
    
    .lightbox-btn {
      padding: 0.75rem 1.5rem;
      background: var(--bg-card);
      border: none;
      border-radius: 0.5rem;
      color: var(--text-primary);
      cursor: pointer;
      font-size: 0.9rem;
      transition: background 0.2s;
    }
    
    .lightbox-btn:hover {
      background: var(--accent);
    }
    
    .empty-state {
      text-align: center;
      padding: 4rem 2rem;
      color: var(--text-secondary);
    }
    
    .empty-state-icon {
      font-size: 4rem;
      margin-bottom: 1rem;
    }
    
    @media (max-width: 768px) {
      header {
        padding: 1rem;
      }
      
      h1 {
        font-size: 1.5rem;
      }
      
      .controls {
        padding: 0 1rem;
      }
      
      main {
        padding: 0 1rem 2rem;
      }
      
      .screenshot-grid {
        grid-template-columns: 1fr;
      }
    }
  </style>
</head>
<body>
  <header>
    <div class="header-content">
      <h1>📸 SurveyJS Screenshot Album</h1>
      <p class="subtitle">Visual documentation of the SurveyJS Plone integration</p>
      <div class="stats">
        <div class="stat">
          <span class="stat-value">${totalScreenshots}</span>
          <span>Total Screenshots</span>
        </div>
        <div class="stat">
          <span class="stat-value">${latestScreenshots}</span>
          <span>Latest Versions</span>
        </div>
        <div class="stat">
          <span class="stat-value">${groups.length}</span>
          <span>Categories</span>
        </div>
      </div>
    </div>
  </header>
  
  <div class="controls">
    <div class="search-box">
      <input type="text" id="searchInput" placeholder="Search screenshots...">
    </div>
    <div class="filter-buttons">
      <button class="filter-btn active" data-filter="all">All</button>
      <button class="filter-btn" data-filter="latest">Latest Only</button>
      ${groups.map(g => `<button class="filter-btn" data-group="${g.name}">${g.title.split(' ')[0]}</button>`).join('')}
    </div>
  </div>
  
  <main>
    ${groups.length === 0 ? `
      <div class="empty-state">
        <div class="empty-state-icon">📂</div>
        <h2>No screenshots found</h2>
        <p>Run <code>make screenshots</code> to generate screenshots</p>
      </div>
    ` : groups.map(group => `
      <section class="group" data-group="${group.name}">
        <div class="group-header">
          <h2 class="group-title">${group.title}</h2>
          <span class="group-count">${group.screenshots.length}</span>
        </div>
        <div class="screenshot-grid">
          ${group.screenshots.map((screenshot, index) => `
            <article class="screenshot-card" 
                     data-name="${screenshot.name}"
                     data-latest="${screenshot.isLatest}"
                     data-group="${group.name}"
                     onclick="openLightbox('${group.name}', ${index})">
              <img class="screenshot-thumbnail" 
                   src="${screenshot.filename}" 
                   alt="${screenshot.name}"
                   loading="lazy">
              <div class="screenshot-info">
                <div class="screenshot-name">${screenshot.name}</div>
                <div class="screenshot-meta">
                  <span class="badge ${screenshot.isLatest ? 'badge-latest' : 'badge-timestamp'}">
                    ${screenshot.isLatest ? '✨ Latest' : '📅 ' + formatTimestamp(screenshot.timestamp)}
                  </span>
                </div>
              </div>
            </article>
          `).join('')}
        </div>
      </section>
    `).join('')}
  </main>
  
  <div class="lightbox" id="lightbox">
    <div class="lightbox-header">
      <h3 class="lightbox-title" id="lightboxTitle"></h3>
      <button class="lightbox-close" onclick="closeLightbox()">&times;</button>
    </div>
    <div class="lightbox-content">
      <img class="lightbox-image" id="lightboxImage" src="" alt="">
    </div>
    <div class="lightbox-nav">
      <button class="lightbox-btn" onclick="navigateLightbox(-1)">← Previous</button>
      <button class="lightbox-btn" onclick="downloadCurrent()">⬇ Download</button>
      <button class="lightbox-btn" onclick="navigateLightbox(1)">Next →</button>
    </div>
  </div>
  
  <script>
    const groups = ${JSON.stringify(groups)};
    let currentGroup = null;
    let currentIndex = 0;
    
    // Search functionality
    const searchInput = document.getElementById('searchInput');
    searchInput.addEventListener('input', (e) => {
      const term = e.target.value.toLowerCase();
      document.querySelectorAll('.screenshot-card').forEach(card => {
        const name = card.dataset.name.toLowerCase();
        card.classList.toggle('hidden', !name.includes(term));
      });
    });
    
    // Filter buttons
    document.querySelectorAll('.filter-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        
        const filter = btn.dataset.filter;
        const groupFilter = btn.dataset.group;
        
        document.querySelectorAll('.screenshot-card').forEach(card => {
          let show = true;
          if (filter === 'latest') {
            show = card.dataset.latest === 'true';
          } else if (groupFilter) {
            show = card.dataset.group === groupFilter;
          }
          card.classList.toggle('hidden', !show);
        });
        
        // Show/hide group headers
        document.querySelectorAll('.group').forEach(group => {
          const visibleCards = group.querySelectorAll('.screenshot-card:not(.hidden)');
          group.style.display = visibleCards.length > 0 ? 'block' : 'none';
        });
      });
    });
    
    // Lightbox
    function openLightbox(groupName, index) {
      currentGroup = groups.find(g => g.name === groupName);
      currentIndex = index;
      updateLightbox();
      document.getElementById('lightbox').classList.add('active');
      document.body.style.overflow = 'hidden';
    }
    
    function closeLightbox() {
      document.getElementById('lightbox').classList.remove('active');
      document.body.style.overflow = '';
    }
    
    function updateLightbox() {
      const screenshot = currentGroup.screenshots[currentIndex];
      document.getElementById('lightboxImage').src = screenshot.filename;
      document.getElementById('lightboxTitle').textContent = 
        \`\${screenshot.name} (\${currentIndex + 1}/\${currentGroup.screenshots.length})\`;
    }
    
    function navigateLightbox(direction) {
      currentIndex += direction;
      if (currentIndex < 0) currentIndex = currentGroup.screenshots.length - 1;
      if (currentIndex >= currentGroup.screenshots.length) currentIndex = 0;
      updateLightbox();
    }
    
    function downloadCurrent() {
      const screenshot = currentGroup.screenshots[currentIndex];
      const link = document.createElement('a');
      link.href = screenshot.filename;
      link.download = screenshot.filename;
      link.click();
    }
    
    // Keyboard navigation
    document.addEventListener('keydown', (e) => {
      if (!document.getElementById('lightbox').classList.contains('active')) return;
      
      if (e.key === 'Escape') closeLightbox();
      if (e.key === 'ArrowLeft') navigateLightbox(-1);
      if (e.key === 'ArrowRight') navigateLightbox(1);
    });
    
    // Close on background click
    document.getElementById('lightbox').addEventListener('click', (e) => {
      if (e.target.id === 'lightbox') closeLightbox();
    });
  </script>
</body>
</html>`;
  
  return html;
}

function main() {
  const screenshotsDir = process.argv[2] || './screenshots/output';
  const resolvedDir = path.resolve(screenshotsDir);
  
  if (!fs.existsSync(resolvedDir)) {
    console.error(`❌ Screenshots directory not found: ${resolvedDir}`);
    console.log('💡 Run screenshots first: make screenshots');
    process.exit(1);
  }
  
  console.log(`📁 Scanning: ${resolvedDir}`);
  
  // Find all PNG files
  const files = fs.readdirSync(resolvedDir)
    .filter(f => f.endsWith('.png'))
    .map(f => ({
      filename: f,
      parsed: parseScreenshotFilename(f),
    }))
    .filter(item => item.parsed !== null);
  
  if (files.length === 0) {
    console.error('❌ No screenshots found');
    process.exit(1);
  }
  
  // Create screenshot objects
  const screenshots: Screenshot[] = files.map(f => ({
    name: f.parsed!.name,
    filename: f.filename,
    timestamp: f.parsed!.timestamp,
    isLatest: f.parsed!.isLatest,
    fullPath: path.join(resolvedDir, f.filename),
  }));
  
  console.log(`📸 Found ${screenshots.length} screenshots`);
  
  // Group screenshots
  const groups = groupScreenshots(screenshots);
  console.log(`📂 Organized into ${groups.length} groups`);
  
  // Generate HTML
  const html = generateHTML(groups, resolvedDir);
  const outputPath = path.join(resolvedDir, 'index.html');
  fs.writeFileSync(outputPath, html);
  
  console.log(`✅ Album generated: ${outputPath}`);
  console.log(`🌐 Open with: npx serve "${resolvedDir}"`);
  console.log('');
  console.log('Groups:');
  groups.forEach(g => {
    const latestCount = g.screenshots.filter(s => s.isLatest).length;
    console.log(`  • ${g.title}: ${g.screenshots.length} screenshots (${latestCount} latest)`);
  });
}

main();
