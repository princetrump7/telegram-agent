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
# The Web App HTML
# ---------------------------------------------------------------------------
WEBAPP_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Agent Dashboard</title>
<style>
  :root {
    --bg: #0a0a0f;
    --surface: #14141f;
    --surface-2: #1e1e2e;
    --accent: #7c6af0;
    --accent-dim: #5a4ac0;
    --text: #ededef;
    --text-dim: #8b8b9e;
    --text-muted: #5e5e72;
    --success: #4ade80;
    --danger: #f87171;
    --radius: 12px;
    --radius-sm: 8px;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    padding: 0 0 80px 0;
    min-height: 100vh;
    width: 100%;
  }
  .header {
    background: linear-gradient(135deg, var(--surface) 0%, var(--surface-2) 100%);
    padding: 20px 16px 16px;
    border-bottom: 1px solid rgba(255,255,255,0.06);
    position: sticky; top: 0; z-index: 10;
  }
  .header h1 { font-size: 20px; font-weight: 700; letter-spacing: -0.3px; }
  .header p { font-size: 13px; color: var(--text-dim); margin-top: 2px; }

  .tab-bar {
    display: flex; gap: 4px;
    padding: 8px 12px;
    background: var(--surface);
    border-bottom: 1px solid rgba(255,255,255,0.05);
    position: sticky; top: 68px; z-index: 10;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }
  .tab-bar::-webkit-scrollbar { display: none; }
  .tab-btn {
    flex: 1; min-width: 70px;
    padding: 8px 12px;
    border: none; border-radius: var(--radius-sm);
    background: transparent; color: var(--text-dim);
    font-size: 13px; font-weight: 500;
    cursor: pointer; transition: all 0.2s;
    white-space: nowrap;
  }
  .tab-btn.active { background: var(--accent); color: white; }
  .tab-btn:active { transform: scale(0.96); }

  .content { padding: 12px 16px; }
  .card {
    background: var(--surface);
    border-radius: var(--radius);
    padding: 16px;
    margin-bottom: 12px;
    border: 1px solid rgba(255,255,255,0.05);
  }
  .card-title {
    font-size: 13px; font-weight: 600;
    color: var(--text-dim);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 12px;
  }

  .stats-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
  }
  .stat-item {
    background: var(--surface-2);
    border-radius: var(--radius-sm);
    padding: 14px;
    text-align: center;
  }
  .stat-value { font-size: 24px; font-weight: 700; color: var(--accent); }
  .stat-label {
    font-size: 11px; color: var(--text-muted);
    margin-top: 4px;
    text-transform: uppercase;
    letter-spacing: 0.3px;
  }

  .note-item {
    display: flex; align-items: flex-start; gap: 10px;
    padding: 12px 0;
    border-bottom: 1px solid rgba(255,255,255,0.04);
  }
  .note-item:last-child { border-bottom: none; }
  .note-content { flex: 1; }
  .note-title { font-size: 14px; font-weight: 600; }
  .note-text { font-size: 13px; color: var(--text-dim); margin-top: 4px; }
  .note-date { font-size: 11px; color: var(--text-muted); margin-top: 4px; }
  .note-done-btn {
    background: none; border: 2px solid var(--text-muted);
    border-radius: 50%; width: 22px; height: 22px; min-width: 22px;
    cursor: pointer; display: flex; align-items: center; justify-content: center;
    font-size: 11px; color: var(--text-muted);
    transition: all 0.2s; margin-top: 2px;
  }
  .note-done-btn:hover { border-color: var(--success); color: var(--success); }
  .note-item.done .note-title,
  .note-item.done .note-text { text-decoration: line-through; color: var(--text-muted); }

  .gallery-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .gallery-item {
    position: relative; border-radius: var(--radius-sm);
    overflow: hidden; aspect-ratio: 1;
    background: var(--surface-2);
  }
  .gallery-item img {
    width: 100%; height: 100%;
    object-fit: cover; display: block;
  }
  .gallery-prompt {
    position: absolute; bottom: 0; left: 0; right: 0;
    background: linear-gradient(transparent, rgba(0,0,0,0.8));
    padding: 24px 8px 8px;
    font-size: 11px; color: rgba(255,255,255,0.9);
    line-height: 1.3;
  }
  .gallery-empty {
    text-align: center; padding: 40px 20px;
    color: var(--text-muted);
  }
  .gallery-empty span { font-size: 48px; display: block; margin-bottom: 12px; }
  .empty-state {
    text-align: center; padding: 40px 20px;
    color: var(--text-muted);
  }
  .empty-state span { font-size: 48px; display: block; margin-bottom: 12px; }
  .loading { text-align: center; padding: 40px; color: var(--text-dim); }
  .loading::after {
    content: ''; display: inline-block;
    width: 20px; height: 20px;
    border: 2px solid var(--text-muted);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    margin-left: 8px; vertical-align: middle;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>

<div class="header">
  <h1>✦ Agent</h1>
  <p>Your personal AI dashboard</p>
</div>

<div class="tab-bar">
  <button class="tab-btn active" data-tab="dashboard">📊 Home</button>
  <button class="tab-btn" data-tab="notes">📝 Notes</button>
  <button class="tab-btn" data-tab="gallery">🎨 Gallery</button>
  <button class="tab-btn" data-tab="stats">📈 Stats</button>
</div>

<div class="content" id="content">
  <div class="loading">Loading</div>
</div>

<script>
const API_BASE = '/app/api';
let currentTab = 'dashboard';
const chatId = new URLSearchParams(window.location.search).get('chat_id') || 0;

document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
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
  el.innerHTML = '<div class="loading">Loading</div>';
  if (tab === 'dashboard') renderDashboard(el);
  else if (tab === 'notes') renderNotes(el);
  else if (tab === 'gallery') renderGallery(el);
  else if (tab === 'stats') renderStats(el);
}

async function renderDashboard(el) {
  const d = await api(`/stats?chat_id=${chatId}`);
  if (!d) { el.innerHTML = '<div class="empty-state"><span>⚠️</span>Could not load</div>'; return; }
  el.innerHTML = `
    <div class="card">
      <div class="stats-grid">
        <div class="stat-item"><div class="stat-value">${d.messages||0}</div><div class="stat-label">Messages</div></div>
        <div class="stat-item"><div class="stat-value">${d.active_notes||0}</div><div class="stat-label">Notes</div></div>
        <div class="stat-item"><div class="stat-value">${d.images_generated||0}</div><div class="stat-label">Images</div></div>
        <div class="stat-item"><div class="stat-value">${d.completed_notes||0}</div><div class="stat-label">Done ✅</div></div>
      </div>
    </div>
    <div class="card">
      <div class="card-title">✨ Quick Actions</div>
      <p style="color:var(--text-dim);font-size:14px;line-height:1.6;">
        • Use <b>/draw</b> in the chat to generate images<br>
        • Use <b>/note</b> to save reminders<br>
        • Use <b>/web</b> to search the web<br>
        • Open the <b>Notes</b> or <b>Gallery</b> tabs above
      </p>
    </div>`;
}

async function renderNotes(el) {
  const d = await api(`/notes?chat_id=${chatId}&include_done=true`);
  if (!d) { el.innerHTML = '<div class="empty-state"><span>⚠️</span>Could not load</div>'; return; }
  const notes = d.notes || [];
  if (!notes.length) {
    el.innerHTML = '<div class="empty-state"><span>📝</span>No notes yet<br><span style="font-size:14px;">Use /note in the chat</span></div>';
    return;
  }
  let html = '<div class="card"><div class="card-title">All Notes</div>';
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
  if (!d) { el.innerHTML = '<div class="empty-state"><span>⚠️</span>Could not load</div>'; return; }
  const images = d.images || [];
  if (!images.length) {
    el.innerHTML = '<div class="empty-state"><span>🎨</span>No images yet<br><span style="font-size:14px;">Use /draw in the chat</span></div>';
    return;
  }
  let html = '<div class="gallery-grid">';
  for (const img of images) {
    html += `<div class="gallery-item">
      <img src="/app/images/${img.filename}" alt="${esc(img.prompt)}" loading="lazy">
      <div class="gallery-prompt">${esc(img.prompt)}</div>
    </div>`;
  }
  html += '</div>';
  el.innerHTML = html;
}

async function renderStats(el) {
  const d = await api(`/stats?chat_id=${chatId}`);
  if (!d) { el.innerHTML = '<div class="empty-state"><span>⚠️</span>Could not load</div>'; return; }
  const total = (d.input_tokens||0)+(d.output_tokens||0);
  el.innerHTML = `
    <div class="card">
      <div class="card-title">💬 Conversation</div>
      <div class="stats-grid">
        <div class="stat-item"><div class="stat-value">${d.messages||0}</div><div class="stat-label">Messages</div></div>
        <div class="stat-item"><div class="stat-value">${fmt(total)}</div><div class="stat-label">Total Tokens</div></div>
        <div class="stat-item"><div class="stat-value">${fmt(d.input_tokens||0)}</div><div class="stat-label">Input</div></div>
        <div class="stat-item"><div class="stat-value">${fmt(d.output_tokens||0)}</div><div class="stat-label">Output</div></div>
      </div>
    </div>
    <div class="card">
      <div class="card-title">📦 Activity</div>
      <div class="stats-grid">
        <div class="stat-item"><div class="stat-value">${d.active_notes||0}</div><div class="stat-label">Active Notes</div></div>
        <div class="stat-item"><div class="stat-value">${d.completed_notes||0}</div><div class="stat-label">Completed</div></div>
        <div class="stat-item"><div class="stat-value">${d.images_generated||0}</div><div class="stat-label">Images</div></div>
        <div class="stat-item"><div class="stat-value">${d.days_active||1}</div><div class="stat-label">Days Active</div></div>
      </div>
    </div>`;
}

function esc(t) { const d=document.createElement('div'); d.textContent=t||''; return d.innerHTML; }
function fmt(n) { if(n>=1e6) return (n/1e6).toFixed(1)+'M'; if(n>=1e3) return (n/1e3).toFixed(1)+'K'; return n.toString(); }

renderTab('dashboard');
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
