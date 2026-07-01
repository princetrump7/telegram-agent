"""Telegram Web App — Mira-like dashboard inside Telegram.

Serves the web app HTML + backend API.
Works as a standalone server (dev mode) or mounted into the webhook server (prod).
"""

import logging
from pathlib import Path

import uvicorn
from fastapi import APIRouter, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from starlette.requests import Request

from config import config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Router — mountable into any FastAPI app
# ---------------------------------------------------------------------------
router = APIRouter()

IMAGE_DIR = Path.home() / ".telegram-agent" / "images"


def _mem():
    from memory import memory
    return memory


def _gallery():
    from image_client import get_gallery, delete_from_gallery
    return get_gallery, delete_from_gallery


# ── Stats ──
@router.get("/api/stats")
async def get_stats(chat_id: int = Query(...)):
    mem = _mem()
    conv = mem.get(chat_id)
    notes = mem.get_notes(chat_id)
    done_notes = mem.get_notes(chat_id, include_done=True)
    gallery_get, _ = _gallery()

    return {
        "messages": conv.message_count if conv else 0,
        "input_tokens": conv.total_input_tokens if conv else 0,
        "output_tokens": conv.total_output_tokens if conv else 0,
        "total_tokens": conv.total_tokens if conv else 0,
        "active_notes": len(notes),
        "completed_notes": len(done_notes) - len(notes),
        "images_generated": len(gallery_get()),
        "days_active": 1,
    }


# ── Notes CRUD ──
@router.get("/api/notes")
async def list_notes(chat_id: int = Query(...), include_done: bool = False):
    notes = _mem().get_notes(chat_id, include_done=include_done)
    return {"notes": notes}


@router.post("/api/notes")
async def create_note(request: Request, chat_id: int = Query(...)):
    body = await request.json()
    content = body.get("content", "")
    title = body.get("title", "") or content[:50]
    if not content:
        raise HTTPException(400, "content is required")
    note_id = _mem().add_note(chat_id, content, title)
    return {"id": note_id, "status": "created"}


@router.put("/api/notes/{note_id}/done")
async def mark_done(note_id: int):
    if _mem().mark_note_done(note_id):
        return {"status": "done"}
    raise HTTPException(404, "Note not found")


@router.delete("/api/notes/{note_id}")
async def delete_note(note_id: int):
    if _mem().mark_note_done(note_id):
        return {"status": "deleted"}
    raise HTTPException(404, "Note not found")


# ── Gallery ──
@router.get("/api/images")
async def list_images():
    gallery_get, _ = _gallery()
    return {"images": gallery_get()}


@router.delete("/api/images/{image_id}")
async def delete_image(image_id: str):
    _, gallery_del = _gallery()
    if gallery_del(image_id):
        return {"status": "deleted"}
    raise HTTPException(404, "Image not found")


@router.get("/images/{filename}")
async def serve_image(filename: str):
    filepath = IMAGE_DIR / filename
    if not filepath.exists():
        raise HTTPException(404, "Image not found")
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "png"
    ctype = {"png": "image/png", "jpg": "image/jpeg",
             "jpeg": "image/jpeg", "webp": "image/webp"}.get(ext, "image/png")
    return Response(content=filepath.read_bytes(), media_type=ctype)


# ---------------------------------------------------------------------------
# The Web App HTML — Mira.tg inspired design
# ---------------------------------------------------------------------------
WEBAPP_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Agent — AI in your messenger</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #07070d;
    --surface: rgba(20,20,35,0.6);
    --surface-hover: rgba(30,30,50,0.8);
    --border: rgba(255,255,255,0.06);
    --border-hover: rgba(255,255,255,0.12);
    --cyan: #00d4ff;
    --cyan-dim: rgba(0,212,255,0.15);
    --violet: #7c3aed;
    --violet-dim: rgba(124,58,237,0.12);
    --text: #f0f0f5;
    --text-dim: #9494a8;
    --text-muted: #5c5c72;
    --success: #34d399;
    --radius: 16px;
    --radius-sm: 10px;
    --radius-full: 9999px;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
  body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    overflow-x: hidden;
    padding-bottom: 90px;
  }

  /* ── Glowing background orbs ── */
  .glow-blue {
    position: fixed; top: -200px; right: -150px;
    width: 500px; height: 500px;
    background: radial-gradient(circle, rgba(0,212,255,0.08) 0%, transparent 70%);
    pointer-events: none; z-index: 0;
  }
  .glow-violet {
    position: fixed; bottom: -200px; left: -150px;
    width: 500px; height: 500px;
    background: radial-gradient(circle, rgba(124,58,237,0.08) 0%, transparent 70%);
    pointer-events: none; z-index: 0;
  }

  /* ── Header ── */
  .header {
    position: relative; z-index: 10;
    padding: 22px 20px 14px;
    background: linear-gradient(180deg, rgba(7,7,13,0.95) 0%, transparent 100%);
  }
  .header-inner {
    display: flex; align-items: center; justify-content: space-between;
    max-width: 500px; margin: 0 auto;
  }
  .header-left { display: flex; align-items: center; gap: 10px; }
  .header-logo {
    width: 36px; height: 36px;
    background: linear-gradient(135deg, var(--cyan), var(--violet));
    border-radius: 10px;
    display: flex; align-items: center; justify-content: center;
    font-size: 18px; font-weight: 800; color: white;
  }
  .header h1 { font-size: 18px; font-weight: 700; letter-spacing: -0.3px; }
  .header-badge {
    font-size: 10px; font-weight: 600; letter-spacing: 0.3px;
    color: var(--cyan); text-transform: uppercase;
    background: var(--cyan-dim); padding: 2px 8px;
    border-radius: var(--radius-full);
  }
  .header-right {
    color: var(--text-muted); font-size: 20px;
    cursor: pointer; transition: color 0.2s;
  }
  .header-right:hover { color: var(--text); }

  /* ── Tab Bar ── */
  .tab-bar {
    position: relative; z-index: 10;
    display: flex; gap: 4px;
    padding: 4px 12px;
    max-width: 500px; margin: 0 auto;
  }
  .tab-btn {
    flex: 1;
    padding: 10px 8px;
    border: none; border-radius: var(--radius-sm);
    background: transparent; color: var(--text-muted);
    font-family: 'Inter', sans-serif;
    font-size: 12px; font-weight: 600;
    cursor: pointer; transition: all 0.25s;
    white-space: nowrap; display: flex;
    align-items: center; justify-content: center; gap: 5px;
  }
  .tab-btn .tab-icon { font-size: 16px; }
  .tab-btn:hover { color: var(--text-dim); background: rgba(255,255,255,0.03); }
  .tab-btn.active {
    color: white;
    background: linear-gradient(135deg, var(--cyan-dim), var(--violet-dim));
    box-shadow: 0 0 20px rgba(0,212,255,0.05);
  }

  /* ── Content ── */
  .content {
    position: relative; z-index: 5;
    padding: 16px;
    max-width: 500px; margin: 0 auto;
  }

  /* ── Cards ── */
  .card {
    background: var(--surface);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border-radius: var(--radius);
    padding: 20px;
    margin-bottom: 14px;
    border: 1px solid var(--border);
    transition: border-color 0.3s;
  }
  .card:hover { border-color: var(--border-hover); }
  .card-header {
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 16px;
  }
  .card-label {
    font-size: 11px; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.8px; color: var(--text-muted);
  }
  .card-more {
    font-size: 11px; color: var(--cyan); font-weight: 500;
    cursor: pointer; text-decoration: none;
  }
  .card-more:hover { text-decoration: underline; }

  /* ── Hero Section ── */
  .hero {
    text-align: center;
    padding: 20px 0 10px;
    position: relative; z-index: 5;
  }
  .hero h2 {
    font-size: 26px; font-weight: 800;
    letter-spacing: -0.5px; line-height: 1.2;
    background: linear-gradient(135deg, #fff 40%, var(--text-dim));
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    background-clip: text;
  }
  .hero p {
    font-size: 14px; color: var(--text-dim);
    margin-top: 8px; line-height: 1.5;
    max-width: 320px; margin-left: auto; margin-right: auto;
  }
  .hero-cta {
    display: inline-flex; align-items: center; gap: 8px;
    margin-top: 18px;
    padding: 12px 28px;
    background: linear-gradient(135deg, var(--cyan), var(--violet));
    color: white; font-weight: 600; font-size: 15px;
    border: none; border-radius: var(--radius-full);
    cursor: pointer; transition: all 0.3s;
    font-family: 'Inter', sans-serif;
    text-decoration: none;
  }
  .hero-cta:hover {
    transform: translateY(-1px);
    box-shadow: 0 8px 30px rgba(0,212,255,0.2);
  }
  .hero-cta .arrow { font-size: 18px; transition: transform 0.3s; }
  .hero-cta:hover .arrow { transform: translateX(3px); }

  /* ── Stats Grid ── */
  .stats-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .stat-item {
    background: rgba(255,255,255,0.03);
    border-radius: var(--radius-sm);
    padding: 16px 12px;
    text-align: center;
    border: 1px solid rgba(255,255,255,0.04);
    transition: all 0.3s;
  }
  .stat-item:hover {
    background: rgba(255,255,255,0.05);
    border-color: rgba(255,255,255,0.08);
  }
  .stat-value {
    font-size: 28px; font-weight: 800;
    background: linear-gradient(135deg, var(--cyan), var(--violet));
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    background-clip: text;
  }
  .stat-label {
    font-size: 10px; color: var(--text-muted);
    margin-top: 4px; text-transform: uppercase;
    letter-spacing: 0.5px; font-weight: 600;
  }
  .stat-icon { font-size: 20px; margin-bottom: 6px; }

  /* ── Feature Grid ── */
  .feature-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .feature-item {
    background: rgba(255,255,255,0.03);
    border-radius: var(--radius-sm);
    padding: 16px;
    border: 1px solid rgba(255,255,255,0.04);
    transition: all 0.3s;
    cursor: default;
  }
  .feature-item:active { transform: scale(0.97); }
  .feature-icon { font-size: 24px; margin-bottom: 8px; }
  .feature-title { font-size: 13px; font-weight: 600; }
  .feature-desc {
    font-size: 11px; color: var(--text-dim);
    margin-top: 4px; line-height: 1.4;
  }

  /* ── Notes ── */
  .note-item {
    display: flex; align-items: flex-start; gap: 12px;
    padding: 14px 0;
    border-bottom: 1px solid rgba(255,255,255,0.05);
    transition: opacity 0.3s;
  }
  .note-item:last-child { border-bottom: none; padding-bottom: 0; }
  .note-content { flex: 1; min-width: 0; }
  .note-title {
    font-size: 14px; font-weight: 600;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .note-text {
    font-size: 12px; color: var(--text-dim);
    margin-top: 4px; line-height: 1.4;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .note-date { font-size: 10px; color: var(--text-muted); margin-top: 6px; }
  .note-done-btn {
    width: 24px; height: 24px; min-width: 24px;
    border-radius: 50%;
    border: 2px solid var(--text-muted);
    background: transparent;
    cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    font-size: 12px; color: transparent;
    transition: all 0.25s; margin-top: 1px;
  }
  .note-done-btn:hover {
    border-color: var(--success); color: transparent;
    background: rgba(52,211,153,0.1);
  }
  .note-done-btn:active { transform: scale(0.9); }
  .note-item.done .note-title,
  .note-item.done .note-text { text-decoration: line-through; color: var(--text-muted); }
  .note-item.done .note-done-btn {
    border-color: var(--success);
    background: var(--success);
    color: var(--bg);
  }

  /* ── Gallery ── */
  .gallery-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .gallery-item {
    position: relative; border-radius: var(--radius-sm);
    overflow: hidden; aspect-ratio: 1;
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.05);
    transition: transform 0.3s, border-color 0.3s;
  }
  .gallery-item:active { transform: scale(0.97); }
  .gallery-item img {
    width: 100%; height: 100%;
    object-fit: cover; display: block;
  }
  .gallery-meta {
    position: absolute; bottom: 0; left: 0; right: 0;
    background: linear-gradient(transparent 0%, rgba(0,0,0,0.85) 100%);
    padding: 28px 10px 10px;
  }
  .gallery-prompt {
    font-size: 11px; color: rgba(255,255,255,0.9);
    line-height: 1.3;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .gallery-date {
    font-size: 9px; color: rgba(255,255,255,0.4);
    margin-top: 4px;
  }

  /* ── Empty State ── */
  .empty-state {
    text-align: center; padding: 50px 20px;
  }
  .empty-icon { font-size: 48px; display: block; margin-bottom: 16px; }
  .empty-title { font-size: 18px; font-weight: 700; }
  .empty-sub {
    font-size: 13px; color: var(--text-dim);
    margin-top: 6px; line-height: 1.5;
  }
  .empty-hint {
    display: inline-block;
    margin-top: 16px;
    padding: 8px 16px;
    background: var(--cyan-dim);
    color: var(--cyan);
    font-size: 12px; font-weight: 500;
    border-radius: var(--radius-full);
    font-family: 'Inter', sans-serif;
  }

  /* ── Loading ── */
  .loading {
    display: flex; align-items: center; justify-content: center;
    gap: 12px; padding: 60px 20px; color: var(--text-dim);
    font-size: 14px;
  }
  .spinner {
    width: 20px; height: 20px;
    border: 2px solid rgba(255,255,255,0.08);
    border-top-color: var(--cyan);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* ── Grow animation ── */
  @keyframes fadeUp {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
  }
  .card, .stat-item, .feature-item { animation: fadeUp 0.4s ease both; }
  .card:nth-child(2) { animation-delay: 0.1s; }
  .card:nth-child(3) { animation-delay: 0.2s; }
</style>
</head>
<body>

<div class="glow-blue"></div>
<div class="glow-violet"></div>

<div class="header">
  <div class="header-inner">
    <div class="header-left">
      <div class="header-logo">✦</div>
      <div>
        <h1>Agent</h1>
        <span class="header-badge">AI in your messenger</span>
      </div>
    </div>
    <div class="header-right" id="refreshBtn" onclick="renderTab(currentTab)">↻</div>
  </div>
</div>

<div class="tab-bar">
  <button class="tab-btn active" data-tab="dashboard"><span class="tab-icon">✦</span> Home</button>
  <button class="tab-btn" data-tab="notes"><span class="tab-icon">📝</span> Notes</button>
  <button class="tab-btn" data-tab="gallery"><span class="tab-icon">🎨</span> Gallery</button>
  <button class="tab-btn" data-tab="stats"><span class="tab-icon">📊</span> Stats</button>
</div>

<div class="content" id="content">
  <div class="loading"><div class="spinner"></div> Loading</div>
</div>

<script>
const API_BASE = '/app/api';
let currentTab = 'dashboard';
const chatId = new URLSearchParams(window.location.search).get('chat_id') || 0;

document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    if (btn.classList.contains('active')) return;
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentTab = btn.dataset.tab;
    renderTab(currentTab);
  });
});

async function api(path, options = {}) {
  const url = `${API_BASE}${path}${path.includes('?') ? '&' : '?'}_=${Date.now()}`;
  try {
    const res = await fetch(url, {
      headers: { 'Content-Type': 'application/json', ...options.headers },
      ...options,
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (e) {
    console.error('API error:', e);
    return null;
  }
}

function renderTab(tab) {
  const el = document.getElementById('content');
  el.innerHTML = '<div class="loading"><div class="spinner"></div> Loading</div>';
  if (tab === 'dashboard') renderDashboard(el);
  else if (tab === 'notes') renderNotes(el);
  else if (tab === 'gallery') renderGallery(el);
  else if (tab === 'stats') renderStats(el);
}

async function renderDashboard(el) {
  const d = await api(`/stats?chat_id=${chatId}`);
  if (!d) {
    el.innerHTML = `<div class="empty-state"><span class="empty-icon">⚠️</span><div class="empty-title">Could not load</div><div class="empty-sub">Make sure you've chatted with the bot first</div></div>`;
    return;
  }
  el.innerHTML = `
    <div class="hero">
      <h2>Your AI agent,<br>inside your messenger</h2>
      <p>Memory, images, notes, search — all inside Telegram. Zero setup.</p>
      <a class="hero-cta" href="https://t.me/Appilandiabot" target="_blank">
        Open in Telegram <span class="arrow">→</span>
      </a>
    </div>
    <div class="card">
      <div class="card-header">
        <span class="card-label">📊 Activity</span>
        <span class="card-more" onclick="goto('stats')">Full stats →</span>
      </div>
      <div class="stats-grid">
        <div class="stat-item"><div class="stat-icon">💬</div><div class="stat-value">${d.messages||0}</div><div class="stat-label">Messages</div></div>
        <div class="stat-item"><div class="stat-icon">📝</div><div class="stat-value">${d.active_notes||0}</div><div class="stat-label">Notes</div></div>
        <div class="stat-item"><div class="stat-icon">🎨</div><div class="stat-value">${d.images_generated||0}</div><div class="stat-label">Images</div></div>
        <div class="stat-item"><div class="stat-icon">✅</div><div class="stat-value">${d.completed_notes||0}</div><div class="stat-label">Done</div></div>
      </div>
    </div>
    <div class="card">
      <div class="card-header"><span class="card-label">⚡ Quick Actions</span></div>
      <div class="feature-grid">
        <div class="feature-item" onclick="goto('notes')">
          <div class="feature-icon">📝</div>
          <div class="feature-title">Notes</div>
          <div class="feature-desc">View & manage saved notes</div>
        </div>
        <div class="feature-item" onclick="goto('gallery')">
          <div class="feature-icon">🎨</div>
          <div class="feature-title">Gallery</div>
          <div class="feature-desc">Browse generated images</div>
        </div>
        <div class="feature-item">
          <div class="feature-icon">🔍</div>
          <div class="feature-title">Search</div>
          <div class="feature-desc">Use /web in the chat</div>
        </div>
        <div class="feature-item">
          <div class="feature-icon">🧠</div>
          <div class="feature-title">Memory</div>
          <div class="feature-desc">I remember everything</div>
        </div>
      </div>
    </div>`;
}

async function renderNotes(el) {
  const d = await api(`/notes?chat_id=${chatId}&include_done=true`);
  if (!d) { el.innerHTML = '<div class="empty-state"><span class="empty-icon">⚠️</span><div class="empty-title">Could not load</div></div>'; return; }
  const notes = d.notes || [];
  if (!notes.length) {
    el.innerHTML = `<div class="empty-state">
      <span class="empty-icon">📝</span>
      <div class="empty-title">No notes yet</div>
      <div class="empty-sub">Use /note in the chat to save reminders</div>
      <span class="empty-hint">💬 /note remember this idea</span>
    </div>`;
    return;
  }
  let html = '<div class="card"><div class="card-header"><span class="card-label">📝 All Notes</span><span class="card-more">' + notes.filter(n=>!n.done).length + ' active</span></div>';
  for (const n of notes) {
    const done = n.done ? 'done' : '';
    const dt = new Date(n.created_at*1000).toLocaleDateString('en-US',{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});
    html += `<div class="note-item ${done}">
      <button class="note-done-btn" data-id="${n.id}" ${n.done?'disabled':''}>${n.done?'✓':''}</button>
      <div class="note-content">
        <div class="note-title">${esc(n.title)}</div>
        <div class="note-text">${esc(n.content)}</div>
        <div class="note-date">${dt}</div>
      </div>
    </div>`;
  }
  html += '</div>';
  el.innerHTML = html;
  el.querySelectorAll('.note-done-btn:not([disabled])').forEach(b => {
    b.addEventListener('click', async () => {
      await api(`/notes/${b.dataset.id}/done`, {method:'PUT'});
      renderNotes(el);
    });
  });
}

async function renderGallery(el) {
  const d = await api(`/images?chat_id=${chatId}`);
  if (!d) { el.innerHTML = '<div class="empty-state"><span class="empty-icon">⚠️</span><div class="empty-title">Could not load</div></div>'; return; }
  const images = d.images || [];
  if (!images.length) {
    el.innerHTML = `<div class="empty-state">
      <span class="empty-icon">🎨</span>
      <div class="empty-title">No images yet</div>
      <div class="empty-sub">Use /draw in the chat to generate images</div>
      <span class="empty-hint">🎨 /draw a futuristic city</span>
    </div>`;
    return;
  }
  let html = '<div class="card"><div class="card-header"><span class="card-label">🎨 Gallery</span><span class="card-more">' + images.length + ' images</span></div><div class="gallery-grid">';
  for (const img of images) {
    const dt = new Date(img.created_at*1000).toLocaleDateString('en-US',{month:'short',day:'numeric'});
    html += `<div class="gallery-item">
      <img src="/app/images/${img.filename}" alt="${esc(img.prompt)}" loading="lazy">
      <div class="gallery-meta">
        <div class="gallery-prompt">${esc(img.prompt)}</div>
        <div class="gallery-date">${dt}</div>
      </div>
    </div>`;
  }
  html += '</div></div>';
  el.innerHTML = html;
}

async function renderStats(el) {
  const d = await api(`/stats?chat_id=${chatId}`);
  if (!d) { el.innerHTML = '<div class="empty-state"><span class="empty-icon">⚠️</span><div class="empty-title">Could not load</div></div>'; return; }
  const total = (d.input_tokens||0)+(d.output_tokens||0);
  el.innerHTML = `
    <div class="card">
      <div class="card-header"><span class="card-label">💬 Conversation</span></div>
      <div class="stats-grid">
        <div class="stat-item"><div class="stat-icon">💬</div><div class="stat-value">${d.messages||0}</div><div class="stat-label">Messages</div></div>
        <div class="stat-item"><div class="stat-icon">∑</div><div class="stat-value">${fmt(total)}</div><div class="stat-label">Total Tokens</div></div>
        <div class="stat-item"><div class="stat-icon">📥</div><div class="stat-value">${fmt(d.input_tokens||0)}</div><div class="stat-label">Input</div></div>
        <div class="stat-item"><div class="stat-icon">📤</div><div class="stat-value">${fmt(d.output_tokens||0)}</div><div class="stat-label">Output</div></div>
      </div>
    </div>
    <div class="card">
      <div class="card-header"><span class="card-label">📦 Activity</span></div>
      <div class="stats-grid">
        <div class="stat-item"><div class="stat-icon">📝</div><div class="stat-value">${d.active_notes||0}</div><div class="stat-label">Active Notes</div></div>
        <div class="stat-item"><div class="stat-icon">✅</div><div class="stat-value">${d.completed_notes||0}</div><div class="stat-label">Completed</div></div>
        <div class="stat-item"><div class="stat-icon">🎨</div><div class="stat-value">${d.images_generated||0}</div><div class="stat-label">Images</div></div>
        <div class="stat-item"><div class="stat-icon">📅</div><div class="stat-value">${d.days_active||1}</div><div class="stat-label">Days Active</div></div>
      </div>
    </div>
    <div class="card">
      <div class="card-header"><span class="card-label">🧠 Model</span></div>
      <p style="color:var(--text-dim);font-size:13px;">DeepSeek V4 Flash</p>
    </div>`;
}

function goto(tab) {
  document.querySelectorAll('.tab-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.tab === tab);
  });
  currentTab = tab;
  renderTab(tab);
}

function esc(t) { const d=document.createElement('div'); d.textContent=t||''; return d.innerHTML; }
function fmt(n) { if(n>=1e6) return (n/1e6).toFixed(1)+'M'; if(n>=1e3) return (n/1e3).toFixed(1)+'K'; return n.toString(); }

renderTab('dashboard');

// Support ?tab= param from inline keyboard links
const tabParam = new URLSearchParams(window.location.search).get('tab');
if (tabParam) {
  const btn = document.querySelector(`.tab-btn[data-tab="${tabParam}"]`);
  if (btn) btn.click();
}
</script>
</body>
</html>"""


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def webapp_page():
    return WEBAPP_HTML


# ---------------------------------------------------------------------------
# Standalone FastAPI app (for dev mode)
# ---------------------------------------------------------------------------
app = FastAPI(title="Telegram Agent Web App", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router, prefix="/app")


def run_webapp() -> None:
    """Run the web app standalone (dev mode)."""
    port = config.WEBAPP_PORT
    host = config.WEBAPP_HOST
    logger.info("Web App starting on http://%s:%s/app", host, port)
    uvicorn.run(app, host=host, port=port, log_level="warning")
