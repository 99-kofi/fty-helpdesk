"""Website channel (Phase 2): guest sessions + embeddable chat widget. No auth — public."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.websocket import broadcast as ws_broadcast
from app.core.database import get_db
from app.models.conversation import Conversation, Message
from app.models.customer import Customer, CustomerIdentity
from app.services.ai_autoreply import maybe_auto_reply
from app.services.assignment import maybe_auto_assign
from app.services.automation import evaluate_event_rules

router = APIRouter(prefix="/web", tags=["webchat"])


class SessionIn(BaseModel):
    name: str | None = None
    email: str | None = None


class GuestMessageIn(BaseModel):
    content: str


@router.post("/sessions")
def create_session(data: SessionIn, db: Session = Depends(get_db)):
    customer = Customer(name=data.name, email=data.email)
    db.add(customer)
    db.flush()
    guest_id = f"web-{uuid.uuid4().hex[:12]}"
    db.add(CustomerIdentity(customer_id=customer.id, channel="web", external_user_id=guest_id))
    conv = Conversation(customer_id=customer.id, channel="web", status="open")
    db.add(conv)
    db.commit()
    return {"guest_id": guest_id, "customer_id": customer.id, "conversation_id": conv.id}


def _conv_for_guest(db: Session, guest_id: str) -> Conversation:
    ident = db.query(CustomerIdentity).filter_by(channel="web", external_user_id=guest_id).first()
    if not ident:
        raise HTTPException(404, "Unknown session")
    conv = (
        db.query(Conversation)
        .filter_by(customer_id=ident.customer_id, channel="web")
        .order_by(Conversation.id.desc())
        .first()
    )
    if not conv:
        raise HTTPException(404, "No conversation")
    return conv


@router.get("/sessions/{guest_id}/messages")
def guest_messages(guest_id: str, after: int = 0, db: Session = Depends(get_db)):
    conv = _conv_for_guest(db, guest_id)
    msgs = (
        db.query(Message)
        .filter(Message.conversation_id == conv.id, Message.id > after)
        .order_by(Message.id)
        .all()
    )
    if conv.status == "closed":
        conv.status = "reopened"
        db.commit()
    return {
        "conversation_id": conv.id,
        "status": conv.status,
        "messages": [{"id": m.id, "from": m.sender_type, "text": m.content} for m in msgs],
    }


@router.post("/sessions/{guest_id}/messages")
async def guest_send(guest_id: str, data: GuestMessageIn, background: BackgroundTasks, db: Session = Depends(get_db)):
    if not data.content.strip():
        raise HTTPException(422, "Empty message")
    conv = _conv_for_guest(db, guest_id)
    if conv.status in ("new", "closed", "resolved"):
        conv.status = "open"
    text = data.content.strip()[:2000]
    m = Message(
        conversation_id=conv.id,
        sender_type="customer",
        sender_id=guest_id,
        content=text,
    )
    db.add(m)
    conv.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(m)

    # same pipeline as every other channel: classify -> team/worker -> rules -> auto-reply -> realtime
    cls = maybe_auto_assign(db, conv, text)
    evaluate_event_rules(db, "message_created", {
        "channel": "web", "text": text,
        "intent": cls.intent, "confidence": cls.confidence,
        "team": conv.assigned_team, "priority": conv.priority,
        "conversation": conv,
    })
    # FAQ auto-reply: answer instantly from KB without waiting for human
    try:
        if db.query(Message).filter_by(conversation_id=conv.id).order_by(Message.id.desc()).first().sender_type == "customer":
            maybe_auto_reply(db, conv, text)
    except Exception:
        import logging

        logging.getLogger("fty.ai").exception("web auto-reply failed")
    conv.updated_at = datetime.now(timezone.utc)
    db.commit()

    background.add_task(ws_broadcast, {"type": "message", "channel": "web", "conversation_id": conv.id, "sender": "customer"})
    return {"ok": True, "id": m.id, "conversation_id": conv.id}


@router.get("/logo.png")
def serve_logo():
    """Serve the FTY logo from the project root directory."""
    import pathlib

    here = pathlib.Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "fty-logo.png"
        if candidate.exists():
            return Response(candidate.read_bytes(), media_type="image/png")
    return Response(b"", media_type="image/png", status_code=404)


# ---------------------------------------------------------------------------
# Chat widget JS
# ---------------------------------------------------------------------------
WIDGET_JS = r"""/* FTY webchat widget */
(function () {
  var s = document.currentScript;
  var base = (s && s.dataset.base) || location.origin;
  var guest = localStorage.getItem('fty_guest') || null;
  var lastId = 0, isOpen = false, timer = null;

  /* ---- launcher ---- */
  var btn = document.createElement('button');
  btn.id = 'fty-launcher';
  btn.innerHTML = '\u{1F4AC} Chat with us';
  btn.style.cssText = [
    'position:fixed;bottom:24px;right:24px;z-index:9999',
    'background:linear-gradient(135deg,#1a1a2e,#16213e)',
    'color:#fff;border:2px solid rgba(255,255,255,.15)',
    'border-radius:999px;padding:14px 22px',
    'font-size:15px;font-weight:600;cursor:pointer',
    'box-shadow:0 8px 32px rgba(0,0,0,.55)',
    'font-family:system-ui;letter-spacing:.3px',
    'transition:transform .2s,box-shadow .2s',
    'display:flex;align-items:center;gap:8px',
  ].join(';');
  btn.onmouseenter = function () {
    btn.style.transform = 'translateY(-2px)';
    btn.style.boxShadow = '0 12px 40px rgba(0,0,0,.65)';
  };
  btn.onmouseleave = function () {
    btn.style.transform = '';
    btn.style.boxShadow = '0 8px 32px rgba(0,0,0,.55)';
  };

  /* ---- chat box ---- */
  var box = document.createElement('div');
  box.id = 'fty-chatbox';
  var isMobile = window.innerWidth <= 480;
  box.style.cssText = [
    'position:fixed;z-index:9999',
    isMobile ? 'top:0;left:0;right:0;bottom:0;width:100%;max-height:100%;border-radius:0' : 'bottom:88px;right:24px;width:360px;max-height:520px;border-radius:16px',
    'display:none;flex-direction:column',
    'background:#0d0d1a;overflow:hidden',
    'box-shadow:0 24px 64px rgba(0,0,0,.75)',
    'border:1px solid rgba(255,255,255,.08)',
    'font-family:system-ui',
  ].join(';');
  // Responsive on resize
  window.addEventListener('resize', function() {
    var m = window.innerWidth <= 480;
    if (m) {
      box.style.top='0'; box.style.left='0'; box.style.right='0'; box.style.bottom='0';
      box.style.width='100%'; box.style.maxHeight='100%'; box.style.borderRadius='0';
      box.style.bottom=''; box.style.right='';
    } else {
      box.style.top=''; box.style.left=''; box.style.right='24px'; box.style.bottom='88px';
      box.style.width='360px'; box.style.maxHeight='520px'; box.style.borderRadius='16px';
    }
  });

  box.innerHTML = [
    '<div style="background:linear-gradient(135deg,#1a1a2e,#16213e);padding:16px 18px;',
    'display:flex;align-items:center;gap:12px;border-bottom:1px solid rgba(255,255,255,.08)">',
    '<img src="' + base + '/api/v1/web/logo.png" alt="FTY" ',
    'style="width:36px;height:36px;object-fit:contain;background:#fff;border-radius:50%;padding:3px;flex-shrink:0" ',
    'onerror="this.style.display=\'none\'"/>',
    '<div style="flex:1;min-width:0">',
    '<div style="font-weight:700;font-size:15px;color:#fff">Free The Youth</div>',
    '<div style="font-size:12px;color:#a5b4fc;margin-top:1px;display:flex;align-items:center;gap:5px">',
    '<span style="display:inline-block;width:7px;height:7px;background:#34d399;border-radius:50%"></span>',
    'Support is online</div></div>',
    '<button id="fty-close" style="background:none;border:none;color:#8b90b3;cursor:pointer;font-size:22px;line-height:1;padding:2px">&times;</button>',
    '</div>',
    '<div id="fty-msgs" style="flex:1;overflow-y:auto;padding:16px 14px;display:flex;flex-direction:column;',
    'gap:10px;min-height:240px;max-height:340px;background:#0d0d1a;',
    'scrollbar-width:thin;scrollbar-color:rgba(129,140,248,.2) transparent"></div>',
    '<div style="border-top:1px solid rgba(255,255,255,.07);padding:12px;background:#111128">',
    '<div style="display:flex;gap:8px;align-items:center">',
    '<input id="fty-in" placeholder="Type your message\u2026" autocomplete="off" ',
    'style="flex:1;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.12);',
    'color:#eef0ff;border-radius:999px;padding:10px 16px;font-size:14px;outline:none;font-family:inherit"/>',
    '<button id="fty-send" style="background:linear-gradient(135deg,#6366f1,#7c3aed);border:none;',
    'border-radius:50%;width:40px;height:40px;color:#fff;cursor:pointer;font-size:18px;',
    'display:flex;align-items:center;justify-content:center;flex-shrink:0">\u27A4</button>',
    '</div>',
    '<div style="text-align:center;font-size:11px;color:#4a4a72;margin-top:8px">',
    'Powered by <b style="color:#6366f1">FTY HelpDesk</b></div>',
    '</div>',
  ].join('');

  document.body.appendChild(btn);
  document.body.appendChild(box);

  /* ---- helpers ---- */
  function addMsg(from, text, animate) {
    var d = document.createElement('div');
    d.style.cssText = 'padding:10px 14px;border-radius:14px;font-size:14px;max-width:82%;line-height:1.5;word-break:break-word;' +
      (from === 'customer'
        ? 'align-self:flex-end;background:linear-gradient(135deg,#4f46e5,#7c3aed);color:#fff;border-bottom-right-radius:4px'
        : 'align-self:flex-start;background:rgba(255,255,255,.07);color:#eef0ff;border-bottom-left-radius:4px');
    if (animate) {
      d.style.opacity = '0'; d.style.transform = 'translateY(8px)';
      d.style.transition = 'opacity .25s,transform .25s';
    }
    d.textContent = text;
    box.querySelector('#fty-msgs').appendChild(d);
    if (animate) requestAnimationFrame(function () { d.style.opacity = '1'; d.style.transform = ''; });
    var el = box.querySelector('#fty-msgs'); el.scrollTop = el.scrollHeight;
  }

  function addTyping() {
    var t = document.createElement('div');
    t.id = 'fty-typing';
    t.style.cssText = 'align-self:flex-start;background:rgba(255,255,255,.07);color:#8b90b3;padding:10px 14px;border-radius:14px;border-bottom-left-radius:4px;font-size:13px';
    t.textContent = 'Support is typing\u2026';
    box.querySelector('#fty-msgs').appendChild(t);
    var el = box.querySelector('#fty-msgs'); el.scrollTop = el.scrollHeight;
  }

  function removeTyping() {
    var t = box.querySelector('#fty-typing');
    if (t) t.remove();
  }

  async function ensure() {
    if (guest) return;
    var r = await fetch(base + '/api/v1/web/sessions', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}',
    });
    guest = (await r.json()).guest_id;
    localStorage.setItem('fty_guest', guest);
  }

  async function poll() {
    if (!guest) return;
    var r = await fetch(base + '/api/v1/web/sessions/' + guest + '/messages?after=' + lastId);
    if (!r.ok) return;
    var j = await r.json();
    removeTyping();
    j.messages.forEach(function (m) {
      if (m.id > lastId) { addMsg(m.from, m.text, true); lastId = m.id; }
    });
  }

  function openChat() {
    isOpen = true;
    box.style.display = 'flex';
    btn.innerHTML = '\u2715 Close';
    btn.style.background = 'linear-gradient(135deg,#374151,#1f2937)';
    ensure().then(function () { poll(); timer = setInterval(poll, 3500); });
    setTimeout(function () { var i = box.querySelector('#fty-in'); if (i) i.focus(); }, 100);
    var msgs = box.querySelector('#fty-msgs');
    if (msgs && msgs.children.length === 0) {
      addMsg('agent', '\uD83D\uDC4B Hey! Welcome to Free The Youth support. How can we help you today?', true);
    }
  }

  function closeChat() {
    isOpen = false;
    box.style.display = 'none';
    btn.innerHTML = '\uD83D\uDCAC Chat with us';
    btn.style.background = 'linear-gradient(135deg,#1a1a2e,#16213e)';
    if (timer) clearInterval(timer);
  }

  btn.onclick = function () { isOpen ? closeChat() : openChat(); };
  box.querySelector('#fty-close').onclick = closeChat;

  async function sendMsg() {
    var inp = box.querySelector('#fty-in');
    if (!inp.value.trim()) return;
    var text = inp.value.trim();
    inp.value = '';
    addMsg('customer', text, true);
    await ensure();
    addTyping();
    await fetch(base + '/api/v1/web/sessions/' + guest + '/messages', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: text }),
    });
    setTimeout(poll, 800);
  }

  box.querySelector('#fty-send').onclick = sendMsg;
  box.querySelector('#fty-in').addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMsg(); }
  });
})();
"""


# ---------------------------------------------------------------------------
# Demo page HTML
# ---------------------------------------------------------------------------
DEMO_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>Free The Youth &mdash; Customer Support Demo</title>
  <meta name="description" content="Test the FTY HelpDesk customer support widget. Send a message and see it arrive in the agent inbox in real time."/>
  <link rel="preconnect" href="https://fonts.googleapis.com"/>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap"/>
  <style>
    *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
    :root{
      --bg:#07070f;--surface:rgba(20,20,38,.72);--border:rgba(199,210,254,.14);
      --text:#eef0ff;--muted:#8b90b3;--primary:#6366f1;--primary-dark:#4f46e5;
      --green:#34d399;--radius:16px;
    }
    html,body{height:100%}
    body{
      font-family:'Inter',system-ui,-apple-system,sans-serif;
      background:
        radial-gradient(1200px 600px at 80% -10%,rgba(79,70,229,.18),transparent 60%),
        radial-gradient(900px 600px at 5% 110%,rgba(124,58,237,.12),transparent 60%),
        #07070f;
      color:var(--text);min-height:100vh;
    }
    body::after{
      content:'';position:fixed;inset:0;pointer-events:none;opacity:.04;z-index:999;
      background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='160' height='160'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2'/></filter><rect width='160' height='160' filter='url(%23n)' opacity='0.6'/></svg>");
    }
    /* NAV */
    nav{
      position:sticky;top:0;z-index:100;
      background:rgba(7,7,15,.85);
      backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);
      border-bottom:1px solid var(--border);
      padding:0 40px;display:flex;align-items:center;gap:16px;height:64px;
    }
    .nav-logo{display:flex;align-items:center;gap:12px;text-decoration:none}
    .nav-logo img{width:40px;height:40px;object-fit:contain;background:#fff;border-radius:50%;padding:4px}
    .nav-logo span{font-weight:800;font-size:18px;letter-spacing:.4px;color:#fff}
    nav .spacer{flex:1}
    .nav-badge{
      background:rgba(99,102,241,.18);border:1px solid rgba(99,102,241,.4);
      color:#a5b4fc;font-size:12px;font-weight:600;
      padding:5px 12px;border-radius:999px;letter-spacing:.5px;
    }
    .nav-cta{
      background:linear-gradient(135deg,#6366f1,#7c3aed);
      color:#fff;border:none;border-radius:999px;
      padding:9px 20px;font-size:14px;font-weight:600;
      cursor:pointer;font-family:inherit;
      box-shadow:0 4px 16px rgba(99,102,241,.4);
      transition:opacity .2s,transform .2s;
    }
    .nav-cta:hover{opacity:.88;transform:translateY(-1px)}
    /* HERO */
    .hero{max-width:960px;margin:0 auto;padding:90px 40px 60px;text-align:center}
    .hero-eyebrow{
      display:inline-flex;align-items:center;gap:8px;
      background:rgba(99,102,241,.12);border:1px solid rgba(99,102,241,.35);
      color:#a5b4fc;font-size:13px;font-weight:600;
      padding:6px 16px;border-radius:999px;letter-spacing:.8px;text-transform:uppercase;
      margin-bottom:28px;
    }
    .hero-eyebrow .dot{width:7px;height:7px;background:var(--green);border-radius:50%;animation:pulse 2s infinite}
    @keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
    h1.hero-title{
      font-size:clamp(36px,6vw,68px);font-weight:900;line-height:1.08;
      letter-spacing:-1.5px;margin-bottom:22px;
      background:linear-gradient(120deg,#fff 30%,#a5b4fc 100%);
      -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;
    }
    .hero-sub{
      font-size:clamp(15px,2vw,20px);color:var(--muted);line-height:1.65;
      max-width:640px;margin:0 auto 40px;font-weight:400;
    }
    .hero-actions{display:flex;gap:14px;justify-content:center;flex-wrap:wrap}
    .btn-primary{
      background:linear-gradient(135deg,#6366f1,#7c3aed);
      color:#fff;border:none;border-radius:999px;padding:14px 32px;
      font-size:16px;font-weight:700;cursor:pointer;font-family:inherit;
      box-shadow:0 8px 28px rgba(99,102,241,.45);
      transition:transform .2s,box-shadow .2s;
    }
    .btn-primary:hover{transform:translateY(-2px);box-shadow:0 12px 36px rgba(99,102,241,.55)}
    .btn-ghost{
      background:rgba(255,255,255,.06);color:#d0d5ff;
      border:1px solid var(--border);border-radius:999px;
      padding:14px 32px;font-size:16px;font-weight:600;
      cursor:pointer;font-family:inherit;transition:background .2s;
    }
    .btn-ghost:hover{background:rgba(255,255,255,.1)}
    /* LOGO CARD */
    .logo-feature{display:flex;justify-content:center;padding:0 40px 60px}
    .logo-card{
      display:flex;align-items:center;gap:24px;
      background:rgba(20,20,38,.6);border:1px solid var(--border);
      border-radius:20px;padding:28px 36px;
      backdrop-filter:blur(16px);max-width:480px;width:100%;
    }
    .logo-card img{width:80px;height:80px;object-fit:contain;background:#fff;border-radius:50%;padding:6px;flex-shrink:0}
    .logo-card h2{font-size:22px;font-weight:800;margin-bottom:4px}
    .logo-card p{color:var(--muted);font-size:14px;line-height:1.55}
    /* FEATURES */
    .features{max-width:1100px;margin:0 auto;padding:20px 40px 80px}
    .section-label{text-align:center;margin-bottom:48px}
    .section-label h2{font-size:clamp(24px,4vw,38px);font-weight:800;margin-bottom:10px;letter-spacing:-.5px}
    .section-label p{color:var(--muted);font-size:16px}
    .feature-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:20px}
    .feature-card{
      background:rgba(255,255,255,.03);border:1px solid var(--border);
      border-radius:var(--radius);padding:28px 24px;
      transition:background .2s,border-color .2s,transform .2s;
      position:relative;overflow:hidden;
    }
    .feature-card:hover{background:rgba(99,102,241,.06);border-color:rgba(99,102,241,.35);transform:translateY(-2px)}
    .feature-card::before{
      content:'';position:absolute;top:0;left:0;right:0;height:1px;
      background:linear-gradient(90deg,transparent,rgba(99,102,241,.6),transparent);
      opacity:0;transition:opacity .3s;
    }
    .feature-card:hover::before{opacity:1}
    .feat-icon{font-size:32px;margin-bottom:16px}
    .feature-card h3{font-size:17px;font-weight:700;margin-bottom:8px}
    .feature-card p{font-size:14px;color:var(--muted);line-height:1.6}
    /* STEPS */
    .how{max-width:900px;margin:0 auto;padding:20px 40px 80px;text-align:center}
    .steps{display:flex;gap:16px;flex-wrap:wrap;justify-content:center;margin-top:44px}
    .step{
      flex:1;min-width:180px;max-width:220px;
      background:rgba(255,255,255,.03);border:1px solid var(--border);
      border-radius:var(--radius);padding:28px 20px;
    }
    .step-num{
      width:36px;height:36px;border-radius:50%;
      background:linear-gradient(135deg,#6366f1,#7c3aed);
      color:#fff;font-size:16px;font-weight:800;
      display:flex;align-items:center;justify-content:center;margin:0 auto 14px;
    }
    .step h4{font-size:15px;font-weight:700;margin-bottom:6px}
    .step p{font-size:13px;color:var(--muted);line-height:1.55}
    /* DEMO SECTION */
    .demo-section{max-width:900px;margin:0 auto;padding:20px 40px 80px;text-align:center}
    .demo-box{
      background:rgba(20,20,38,.7);border:1px solid var(--border);
      border-radius:24px;padding:48px 40px;
      backdrop-filter:blur(20px);position:relative;overflow:hidden;
    }
    .demo-box::before{
      content:'';position:absolute;top:-1px;left:10%;right:10%;height:1px;
      background:linear-gradient(90deg,transparent,rgba(99,102,241,.8),transparent);
    }
    .demo-box h2{font-size:clamp(22px,3vw,32px);font-weight:800;margin-bottom:12px}
    .demo-box>p{color:var(--muted);font-size:16px;line-height:1.65;max-width:560px;margin:0 auto 32px}
    .demo-tip{
      display:inline-flex;align-items:center;gap:8px;
      background:rgba(52,211,153,.1);border:1px solid rgba(52,211,153,.3);
      color:#34d399;border-radius:999px;padding:8px 18px;
      font-size:13px;font-weight:600;margin-bottom:32px;
    }
    .inline-form{display:flex;gap:12px;justify-content:center;flex-wrap:wrap;margin-bottom:24px}
    .inline-form input{
      background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.14);
      color:var(--text);border-radius:999px;padding:12px 20px;font-size:15px;
      font-family:inherit;outline:none;width:280px;transition:border-color .2s;
    }
    .inline-form input:focus{border-color:rgba(99,102,241,.6)}
    .inline-form input::placeholder{color:var(--muted)}
    .send-arrow{
      background:linear-gradient(135deg,#6366f1,#7c3aed);
      color:#fff;border:none;border-radius:999px;
      padding:12px 28px;font-size:15px;font-weight:700;
      cursor:pointer;font-family:inherit;
      box-shadow:0 4px 20px rgba(99,102,241,.4);
      transition:transform .2s,box-shadow .2s;
    }
    .send-arrow:hover{transform:translateY(-2px);box-shadow:0 8px 28px rgba(99,102,241,.55)}
    #send-feedback{
      font-size:14px;color:#34d399;font-weight:600;
      min-height:20px;opacity:0;transition:opacity .4s;
    }
    #send-feedback.show{opacity:1}
    /* FOOTER */
    footer{
      border-top:1px solid var(--border);
      text-align:center;padding:28px 40px;
      color:var(--muted);font-size:13px;
    }
    footer a{color:#6366f1;text-decoration:none}
    footer a:hover{text-decoration:underline}
    /* RESPONSIVE */
    @media(max-width:768px){
      nav{padding:0 16px;height:56px}
      .nav-logo img{width:32px;height:32px}
      .nav-logo span{font-size:16px}
      .nav-badge{display:none}
      .nav-cta{padding:7px 14px;font-size:13px}
      .hero{padding:48px 20px 32px}
      .hero-eyebrow{font-size:11px;padding:5px 12px}
      h1.hero-title{font-size:clamp(28px,8vw,36px)}
      .hero-sub{font-size:15px;padding:0 8px}
      .btn-primary,.btn-ghost{padding:12px 20px;font-size:14px;width:100%;max-width:280px}
      .hero-actions{flex-direction:column;align-items:center}
      .logo-feature{padding:0 20px 32px}
      .logo-card{flex-direction:column;text-align:center;padding:20px}
      .logo-card img{width:64px;height:64px}
      .features,.how,.demo-section{padding-left:16px;padding-right:16px}
      .section-label h2{font-size:24px}
      .feature-grid{grid-template-columns:1fr;gap:14px}
      .feature-card{padding:20px 16px}
      .steps{flex-direction:column;align-items:center}
      .step{max-width:100%;width:100%}
      .demo-box{padding:24px 16px;border-radius:16px}
      .inline-form{flex-direction:column;align-items:stretch}
      .inline-form input{width:100%}
      .send-arrow{width:100%}
    }
    @media(max-width:480px){
      .hero{padding:32px 16px 24px}
      h1.hero-title{font-size:26px;letter-spacing:-0.8px}
      .demo-box{padding:20px 14px}
      .inline-form input{font-size:16px} /* prevents iOS zoom */
    }
  </style>
</head>
<body>

<!-- NAV -->
<nav>
  <a class="nav-logo" href="#">
    <img src="/api/v1/web/logo.png" alt="Free The Youth logo" onerror="this.style.display='none'"/>
    <span>Free The Youth</span>
  </a>
  <div class="spacer"></div>
  <span class="nav-badge">&#x1F9EA; Tester Demo</span>
  <button class="nav-cta" onclick="document.getElementById('demo-anchor').scrollIntoView({behavior:'smooth'})">Try the chat &rarr;</button>
</nav>

<!-- HERO -->
<section class="hero">
  <div class="hero-eyebrow">
    <span class="dot"></span>
    Customer Support Live Demo
  </div>
  <h1 class="hero-title">Support That Moves<br/>at the Speed of Youth</h1>
  <p class="hero-sub">
    This page lets you test-drive the FTY HelpDesk widget. Send a message below
    &mdash; it lands in the agent dashboard instantly, ready for a real reply.
  </p>
  <div class="hero-actions">
    <button class="btn-primary" onclick="document.getElementById('demo-anchor').scrollIntoView({behavior:'smooth'})">&#x1F4AC; Start a conversation</button>
    <button class="btn-ghost" onclick="document.getElementById('how-anchor').scrollIntoView({behavior:'smooth'})">How it works &darr;</button>
  </div>
</section>

<!-- LOGO CARD -->
<div class="logo-feature">
  <div class="logo-card">
    <img src="/api/v1/web/logo.png" alt="FTY" onerror="this.style.display='none'"/>
    <div>
      <h2>Free The Youth</h2>
      <p>A brand built on community. Our helpdesk keeps every customer conversation human, fast, and fully organized.</p>
    </div>
  </div>
</div>

<!-- FEATURES -->
<section class="features">
  <div class="section-label">
    <h2>Platform Capabilities</h2>
    <p>Everything the FTY team needs to deliver world-class support</p>
  </div>
  <div class="feature-grid">
    <div class="feature-card"><div class="feat-icon">&#x1F4E5;</div><h3>Unified Inbox</h3><p>Instagram, WhatsApp, Facebook, Email, and Web &mdash; all channels in one organized queue.</p></div>
    <div class="feature-card"><div class="feat-icon">&#x1F534;</div><h3>Priority Routing</h3><p>Urgent conversations bubble to the top automatically. Workers tackle the most critical queries first.</p></div>
    <div class="feature-card"><div class="feat-icon">&#x26A1;</div><h3>Status Workflow</h3><p>In Progress &rarr; Waiting for Customer &rarr; Resolved. Clear stages prevent conversations falling through cracks.</p></div>
    <div class="feature-card"><div class="feat-icon">&#x1F916;</div><h3>AI Reply Suggestions</h3><p>Smart knowledge-base suggestions help agents reply faster and more consistently.</p></div>
    <div class="feature-card"><div class="feat-icon">&#x1F7E2;</div><h3>Availability Control</h3><p>Workers set Available, Away, or Offline. New conversations only route to active agents.</p></div>
    <div class="feature-card"><div class="feat-icon">&#x1F4CA;</div><h3>Analytics &amp; SLA</h3><p>Track response times, resolution rates, and team performance to continuously improve the experience.</p></div>
  </div>
</section>

<!-- HOW IT WORKS -->
<section class="how" id="how-anchor">
  <div class="section-label">
    <h2>How the Demo Works</h2>
    <p>Three simple steps to test the full support flow</p>
  </div>
  <div class="steps">
    <div class="step"><div class="step-num">1</div><h4>Open the widget</h4><p>Click the purple chat button in the bottom-right corner of this page.</p></div>
    <div class="step"><div class="step-num">2</div><h4>Send a message</h4><p>Type anything &mdash; a question, an order issue, or just &ldquo;Hello!&rdquo; &mdash; and press Enter.</p></div>
    <div class="step"><div class="step-num">3</div><h4>Watch it arrive</h4><p>Your message appears live in the agent&rsquo;s inbox, ready for the team to reply in-thread.</p></div>
  </div>
</section>

<!-- DEMO SECTION -->
<section class="demo-section" id="demo-anchor">
  <div class="demo-box">
    <div class="demo-tip">&#x1F4AC; Live &mdash; messages go directly to the agent inbox</div>
    <h2>Send a Test Message</h2>
    <p>
      Use the quick-send form below, or click the chat bubble (bottom-right) to open the full widget experience.
      Either way your message reaches a real agent queue instantly.
    </p>
    <div class="inline-form">
      <input id="quick-msg" type="text" placeholder="e.g. I have a question about my order&hellip;" maxlength="500"
        onkeydown="if(event.key==='Enter'){quickSend();}"/>
      <button class="send-arrow" onclick="quickSend()">Send &rarr;</button>
    </div>
    <div id="send-feedback">&#x2705; Message sent! Check the agent inbox.</div>
    <p style="font-size:13px;color:var(--muted);margin-top:16px">
      Or open the <strong style="color:#a5b4fc">&#x1F4AC; Chat with us</strong> button in the bottom-right for the full widget experience.
    </p>
  </div>
</section>

<!-- FOOTER -->
<footer>
  <p>&copy; 2026 Free The Youth &middot; Powered by <a href="#">FTY HelpDesk</a> &middot; Built by <a href="#">WAIT Technologies</a></p>
</footer>

<script src="/api/v1/web/widget.js" data-base=""></script>
<script>
  var _quickGuest = localStorage.getItem('fty_guest') || null;
  async function ensureQuick() {
    if (_quickGuest) return;
    var r = await fetch('/api/v1/web/sessions', {method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    _quickGuest = (await r.json()).guest_id;
    localStorage.setItem('fty_guest', _quickGuest);
  }
  async function quickSend() {
    var inp = document.getElementById('quick-msg');
    var text = inp.value.trim();
    if (!text) return;
    inp.disabled = true;
    try {
      await ensureQuick();
      await fetch('/api/v1/web/sessions/' + _quickGuest + '/messages', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({content: text})
      });
      inp.value = '';
      var fb = document.getElementById('send-feedback');
      fb.classList.add('show');
      setTimeout(function(){fb.classList.remove('show');}, 4000);
    } catch(e) {
      alert('Could not send \\u2014 is the backend running?');
    } finally {
      inp.disabled = false;
      inp.focus();
    }
  }
</script>
</body>
</html>
"""


@router.get("/widget.js")
def widget_js():
    return Response(WIDGET_JS.replace("{base}", ""), media_type="application/javascript")


@router.get("/widget-demo", response_class=HTMLResponse)
def widget_demo():
    return DEMO_HTML
