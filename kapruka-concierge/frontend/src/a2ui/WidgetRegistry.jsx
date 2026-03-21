import React, { useEffect, useState } from "react";
import { resolveBoundValue } from "./engine";

// ── Design tokens ────────────────────────────────────────────────────────────
const T = {
  bg0:"#07090F", bg1:"#0A0D14", bg2:"#111827", bg3:"#1F2937",
  bd:"#1E2535",  gold:"#C9953A", goldL:"#F5C842",
  tx:"#E2D9C8",  dim:"#6B7280", muted:"#374151",
  g:"#10B981",   r:"#EF4444",   b:"#60A5FA",
  p:"#A78BFA",   y:"#F59E0B",
};

const rv  = (bv, dm) => resolveBoundValue(bv, dm);
const phColor = s => ({ idle:T.dim, active:T.y, done:T.g, error:T.r }[s] || T.dim);

// ── Shared micro-styles ───────────────────────────────────────────────────────
const pill = (bg, color, border) => ({
  display:"inline-block", padding:"2px 7px", borderRadius:99,
  fontSize:9, fontFamily:"'JetBrains Mono',monospace", letterSpacing:1,
  backgroundColor: bg, color, border:`1px solid ${border||"transparent"}`,
});

// ═══════════════════════════════════════════════════════
// STANDARD WIDGETS
// ═══════════════════════════════════════════════════════

function Column({ children, gap=8 }) {
  return <div style={{ display:"flex", flexDirection:"column", gap }}>{children}</div>;
}

function Row({ children, gap=8, align="center" }) {
  return <div style={{ display:"flex", flexDirection:"row", alignItems:align, gap }}>{children}</div>;
}

function Card({ children, variant="default" }) {
  const varMap = {
    default: { bg:T.bg2, border:T.bd },
    success: { bg:"#0D1F14", border:"#10B98133" },
    warning: { bg:"#1A1400", border:"#F59E0B33" },
    error:   { bg:"#1A0808", border:"#EF444433" },
  };
  const v = varMap[variant] || varMap.default;
  return (
    <div style={{
      background:v.bg, border:`1px solid ${v.border}`,
      borderRadius:8, padding:"10px 12px",
    }}>
      {children}
    </div>
  );
}

function Text({ text, style: styleProp, dm }) {
  const val = rv(text, dm) ?? "";
  const styles = {
    h1: {
      fontFamily:"'Cormorant Garamond',serif", fontSize:22, fontWeight:700,
      background:`linear-gradient(90deg,${T.gold},${T.goldL},${T.gold})`,
      backgroundSize:"200% auto",
      WebkitBackgroundClip:"text", WebkitTextFillColor:"transparent",
      animation:"shimmer 3s linear infinite",
    },
    h2: { fontSize:15, fontWeight:600, color:T.tx },
    h3: { fontSize:13, fontWeight:600, color:T.tx },
    body: { fontSize:13, color:T.tx, lineHeight:1.7 },
    caption: { fontSize:11, color:T.dim },
    mono: { fontSize:10, fontFamily:"'JetBrains Mono',monospace", color:T.dim, letterSpacing:1 },
    label: { fontSize:9, fontFamily:"'JetBrains Mono',monospace", color:T.gold, textTransform:"uppercase", letterSpacing:3 },
  };
  const s = rv(styleProp, dm) || "body";
  return <span style={styles[s] || styles.body}>{val}</span>;
}

function Divider() {
  return <div style={{ height:1, background:T.bd, margin:"4px 0" }} />;
}

function Button({ label, action, dm }) {
  const lbl = rv(label, dm) ?? "Click";
  const act = rv(action, dm);
  const handleClick = () => {
    if (!act?.name) return;
    fetch("/action", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body: JSON.stringify({ userAction: { name:act.name, surfaceId:"", sourceComponentId:"", timestamp:new Date().toISOString(), context:act.context||{} } })
    }).catch(()=>{});
  };
  return (
    <button onClick={handleClick} style={{
      background:`linear-gradient(135deg,${T.gold},${T.goldL})`,
      color:T.bg0, border:"none", borderRadius:6, padding:"7px 14px",
      fontSize:12, fontWeight:600, cursor:"pointer", fontFamily:"'Outfit',sans-serif",
    }}>
      {lbl}
    </button>
  );
}

// ═══════════════════════════════════════════════════════
// KAPRUKA CUSTOM WIDGETS
// ═══════════════════════════════════════════════════════

function ChatMessage({ text, role, dm }) {
  const txt  = rv(text, dm) ?? "";
  const rl   = rv(role, dm) ?? "assistant";
  const [vis, setVis] = useState(false);
  useEffect(() => { if (txt) setVis(true); }, [txt]);
  if (!txt) return null;
  const isUser = rl === "user";
  return (
    <div style={{
      display:"flex", justifyContent: isUser ? "flex-end" : "flex-start",
      animation:"fadeUp .35s ease", opacity: vis ? 1 : 0,
      marginBottom:8,
    }}>
      <div style={{
        maxWidth:"82%", padding:"10px 14px", borderRadius: isUser ? "18px 18px 4px 18px" : "18px 18px 18px 4px",
        background: isUser
          ? "linear-gradient(135deg,#1E3A5F,#0F2744)"
          : T.bg2,
        border: `1px solid ${isUser ? "#2A4F7A" : T.bd}`,
        fontSize:14, color:T.tx, lineHeight:1.65,
        fontFamily:"'Outfit',sans-serif",
        whiteSpace:"pre-wrap",
      }}>
        {txt}
      </div>
    </div>
  );
}

function ThinkingDots({ active, label, dm }) {
  const isActive = rv(active, dm) ?? false;
  const lbl      = rv(label,  dm) ?? "Thinking...";
  if (!isActive) return null;
  return (
    <div style={{ display:"flex", flexDirection:"column", alignItems:"flex-start", gap:6, padding:"8px 0" }}>
      <Row gap={5}>
        {[0,1,2].map(i => (
          <div key={i} style={{
            width:8, height:8, borderRadius:"50%",
            background:T.gold,
            animation:`pulse 1.4s ease ${i*0.2}s infinite`,
          }} />
        ))}
      </Row>
      <span style={{ fontSize:11, color:T.dim, fontFamily:"'JetBrains Mono',monospace" }}>{lbl}</span>
    </div>
  );
}

function AgentPhase({ label, status, dm }) {
  const lbl = rv(label,  dm) ?? "";
  const st  = rv(status, dm) ?? "idle";
  const iconMap = { Routing:"🔀", Searching:"🔍", Reflecting:"🔄", Done:"✅" };
  const icon = iconMap[lbl] || "◆";
  const isActive = st === "active";
  const isDone   = st === "done";
  return (
    <div style={{
      display:"flex", alignItems:"center", justifyContent:"space-between",
      padding:"5px 8px", borderRadius:6,
      background: isActive ? "#F59E0B11" : "transparent",
      transition:"background .3s",
    }}>
      <Row gap={7}>
        <span style={{ fontSize:13 }}>{icon}</span>
        <span style={{
          fontSize:12, color: isActive ? T.y : isDone ? T.g : T.dim,
          fontWeight: isActive ? 600 : 400,
          fontFamily:"'Outfit',sans-serif",
        }}>{lbl}</span>
      </Row>
      {(isActive || isDone) && (
        <div style={{
          width:7, height:7, borderRadius:"50%",
          background:phColor(st),
          animation: isActive ? "pulse 1s infinite" : "none",
        }} />
      )}
    </div>
  );
}

function MemoryChip({ label, sublabel, active, tier, dm }) {
  const lbl  = rv(label,    dm) ?? "";
  const sub  = rv(sublabel, dm) ?? "";
  const act  = rv(active,   dm) ?? false;
  const tr   = rv(tier,     dm) ?? "st";
  const colorMap = { st:T.b, ltrag:T.p, semantic:T.g };
  const iconMap  = { st:"💬", ltrag:"🗄️", semantic:"🧠" };
  const c = colorMap[tr] || T.b;
  return (
    <div style={{
      display:"flex", alignItems:"center", gap:8, padding:"7px 10px",
      borderRadius:8, border:`1px solid ${act ? c+"66" : T.bd}`,
      background: act ? c+"0D" : T.bg1,
      boxShadow: act ? `0 0 10px ${c}33` : "none",
      transition:"all .3s",
    }}>
      <span style={{ fontSize:16 }}>{iconMap[tr]}</span>
      <div style={{ flex:1, minWidth:0 }}>
        <div style={{ fontSize:11, color:T.tx, fontWeight:500, fontFamily:"'Outfit',sans-serif" }}>{lbl}</div>
        <div style={{
          fontSize:10, color: act ? c : T.dim,
          fontFamily:"'JetBrains Mono',monospace",
          transition:"color .3s", overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap",
        }}>{sub}</div>
      </div>
      {act && <div style={{ width:6, height:6, borderRadius:"50%", background:c, animation:"pulse 1s infinite", flexShrink:0 }} />}
    </div>
  );
}

function MemoryFound({ active, allergies, preferences, district, dm }) {
  const act   = rv(active,      dm) ?? false;
  const alrgs = rv(allergies,   dm) ?? [];
  const prefs = rv(preferences, dm) ?? [];
  const dist  = rv(district,    dm) ?? "";
  return (
    <div style={{
      overflow:"hidden",
      maxHeight: act ? 200 : 0,
      opacity:   act ? 1 : 0,
      transition:"max-height .4s ease, opacity .3s ease",
    }}>
      <div style={{ padding:"10px", borderRadius:8, border:`1px solid ${T.g}33`, background:`${T.g}0A`, marginTop:4 }}>
        <div style={{ fontSize:11, color:T.g, fontWeight:600, marginBottom:6, fontFamily:"'Outfit',sans-serif" }}>✓ Memory Found</div>
        <div style={{ display:"flex", flexWrap:"wrap", gap:4 }}>
          {alrgs.map((a,i) => <span key={i} style={pill(`${T.r}22`, T.r, T.r+"55")}>⚠ {a}</span>)}
          {prefs.map((p,i) => <span key={i} style={pill(`${T.g}11`, T.g, T.g+"44")}>♥ {p}</span>)}
        </div>
        {dist && <div style={{ fontSize:10, color:T.dim, marginTop:6 }}>📍 {dist}</div>}
      </div>
    </div>
  );
}

function ReflectStep({ label, status, dm }) {
  const lbl = rv(label,  dm) ?? "";
  const st  = rv(status, dm) ?? "idle";
  const isActive = st === "active";
  const isDone   = st === "done";
  const c = isDone ? T.g : isActive ? T.y : T.muted;
  return (
    <Row gap={8}>
      <div style={{
        width:7, height:7, borderRadius:"50%",
        background:c, flexShrink:0,
        boxShadow: isActive ? `0 0 8px ${T.y}88` : "none",
        animation: isActive ? "pulse 1s infinite" : "none",
        transition:"background .3s, box-shadow .3s",
      }} />
      <span style={{
        fontSize:11, color: isActive ? T.y : isDone ? T.g : T.dim,
        fontWeight: isActive ? 600 : 400,
        fontFamily:"'Outfit',sans-serif",
      }}>{lbl}</span>
    </Row>
  );
}

function DraftPreview({ name, price, image, visible, dm }) {
  const nm  = rv(name,    dm) ?? "";
  const pr  = rv(price,   dm) ?? "";
  const img = rv(image,   dm) ?? "";
  const vis = rv(visible, dm) ?? false;
  if (!vis || !nm) return null;
  const imgSrc = img ? `/api/image?url=${encodeURIComponent(img)}` : null;
  return (
    <div style={{
      display:"flex", alignItems:"center", gap:8, padding:"8px",
      borderRadius:7, border:`1px solid ${T.gold}66`,
      background:`${T.gold}0A`,
      animation:"glowPulse 2s infinite",
    }}>
      {imgSrc
        ? <img src={imgSrc} alt="" style={{ width:40, height:40, borderRadius:5, objectFit:"cover", flexShrink:0 }} />
        : <div style={{ width:40, height:40, borderRadius:5, background:T.bg3, flexShrink:0, display:"flex", alignItems:"center", justifyContent:"center", fontSize:18 }}>🎁</div>
      }
      <div style={{ minWidth:0 }}>
        <div style={{ fontSize:11, color:T.tx, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap", fontFamily:"'Outfit',sans-serif" }}>{nm}</div>
        {pr && <div style={{ fontSize:10, color:T.gold, fontFamily:"'JetBrains Mono',monospace" }}>{pr}</div>}
      </div>
    </div>
  );
}

function RouteDecision({ route, dm }) {
  const rt = rv(route, dm) ?? "";
  if (!rt) return null;
  const map = {
    catalog:          { icon:"📦", label:"Catalog Agent",   bg:"#1A0D2E", bd:"#A78BFA44" },
    logistics:        { icon:"🚚", label:"Logistics Agent", bg:"#0D1A1A", bd:"#2DD4BF44" },
    update_preference:{ icon:"📝", label:"Profile Update",  bg:"#1A1400", bd:`${T.gold}44` },
    SEARCH_CATALOG:   { icon:"📦", label:"Catalog Agent",   bg:"#1A0D2E", bd:"#A78BFA44" },
    CHECK_LOGISTICS:  { icon:"🚚", label:"Logistics Agent", bg:"#0D1A1A", bd:"#2DD4BF44" },
    UPDATE_PREFERENCE:{ icon:"📝", label:"Profile Update",  bg:"#1A1400", bd:`${T.gold}44` },
  };
  const m = map[rt];
  if (!m) return null;
  return (
    <div style={{ padding:"7px 10px", borderRadius:7, border:`1px solid ${m.bd}`, background:m.bg, display:"flex", alignItems:"center", gap:7 }}>
      <span style={{ fontSize:14 }}>{m.icon}</span>
      <span style={{ fontSize:11, color:T.tx, fontFamily:"'Outfit',sans-serif" }}>{m.label}</span>
    </div>
  );
}

function SafetyAlert({ product, allergy, dm }) {
  const prod = rv(product, dm) ?? "";
  const alrg = rv(allergy, dm) ?? "";
  if (!prod) return null;
  return (
    <div style={{
      padding:"8px 10px", borderRadius:7,
      border:`1px solid ${T.r}44`, background:`${T.r}11`,
      animation:"fadeUp .3s ease",
    }}>
      <div style={{ fontSize:12, color:T.r, fontWeight:600, fontFamily:"'Outfit',sans-serif" }}>⛔ Rejected: {prod}</div>
      {alrg && <div style={{ fontSize:10, color:T.dim, marginTop:2 }}>Contains {alrg}</div>}
    </div>
  );
}

function DeliveryBadge({ feasible, district, days, dm }) {
  const ok   = rv(feasible, dm) ?? false;
  const dist = rv(district, dm) ?? "";
  const dys  = rv(days,     dm) ?? "";
  if (!dist) return null;
  return (
    <div style={{
      display:"inline-flex", alignItems:"center", gap:5,
      padding:"5px 10px", borderRadius:99,
      background: ok ? `${T.g}11` : `${T.r}11`,
      border:`1px solid ${ok ? T.g+"44" : T.r+"44"}`,
      fontSize:11, color: ok ? T.g : T.r,
      fontFamily:"'Outfit',sans-serif",
    }}>
      {ok ? `🚚 ${dist}${dys ? ` · ${dys}` : ""}` : `⚠ No delivery to ${dist}`}
    </div>
  );
}

// ── Gift box SVG placeholder ──────────────────────────────────────────────────
function GiftBoxSVG() {
  return (
    <svg viewBox="0 0 80 80" width="80" height="80" style={{ opacity:0.5 }}>
      <rect x="10" y="30" width="60" height="40" rx="4" fill={T.bg3} stroke={T.gold} strokeWidth="1.5"/>
      <rect x="8"  y="22" width="64" height="12" rx="4" fill={T.muted} stroke={T.gold} strokeWidth="1.5"/>
      <line x1="40" y1="22" x2="40" y2="70" stroke={T.gold} strokeWidth="2"/>
      <line x1="10" y1="28" x2="70" y2="28" stroke={T.gold} strokeWidth="2"/>
      <ellipse cx="40" cy="20" rx="8" ry="6" fill="none" stroke={T.gold} strokeWidth="1.5"/>
      <ellipse cx="40" cy="20" rx="6" ry="4" fill="none" stroke={T.gold} strokeWidth="1"/>
    </svg>
  );
}

// ── StarRating ────────────────────────────────────────────────────────────────
function StarRating({ rating, size="sm" }) {
  const num = parseFloat(rating) || 0;
  const fs  = size === "md" ? 14 : 11;
  return (
    <span style={{ fontSize:fs, color:T.gold, letterSpacing:1 }}>
      {[1,2,3,4,5].map(i => <span key={i}>{i <= Math.round(num) ? "★" : "☆"}</span>)}
    </span>
  );
}

// ── ProductCard ───────────────────────────────────────────────────────────────
function ProductCard({ name, price, image, safe, reason, rating, reviews, discount, delivery, tags, dm }) {
  const nm   = rv(name,     dm) ?? "";
  const pr   = rv(price,    dm) ?? "";
  const img  = rv(image,    dm) ?? "";
  const sf   = rv(safe,     dm) ?? true;
  const rsn  = rv(reason,   dm) ?? "";
  const rat  = rv(rating,   dm) ?? "";
  const rev  = rv(reviews,  dm) ?? "";
  const disc = rv(discount, dm) ?? "";
  const del  = rv(delivery, dm) ?? "";
  const tgs  = rv(tags,     dm) ?? [];

  if (!nm) return null;
  const imgSrc = img ? `/api/image?url=${encodeURIComponent(img)}` : null;

  return (
    <div style={{
      borderRadius:10, overflow:"hidden",
      border:`1px solid ${sf ? T.bd : T.r+"44"}`,
      background:T.bg2,
      animation:"fadeUp .4s ease",
    }}>
      {/* Image */}
      <div style={{ height:180, overflow:"hidden", position:"relative", background:T.bg3 }}>
        {imgSrc
          ? <img src={imgSrc} alt={nm} style={{ width:"100%", height:"100%", objectFit:"cover" }} />
          : <div style={{ width:"100%", height:"100%", display:"flex", alignItems:"center", justifyContent:"center" }}><GiftBoxSVG /></div>
        }
      </div>

      <div style={{ padding:"10px 12px" }}>
        {/* Tags + discount */}
        {(tgs.length > 0 || disc) && (
          <div style={{ display:"flex", flexWrap:"wrap", gap:4, marginBottom:7 }}>
            {tgs.slice(0,4).map((t,i) => (
              <span key={i} style={pill("transparent", T.gold, T.gold+"55")}>{t}</span>
            ))}
            {disc && <span style={pill(T.r, "#fff", T.r)}>{disc}</span>}
          </div>
        )}

        {/* Name */}
        <div style={{
          fontSize:14, fontWeight:600, color:T.tx, marginBottom:4,
          fontFamily:"'Outfit',sans-serif",
          display:"-webkit-box", WebkitLineClamp:2, WebkitBoxOrient:"vertical", overflow:"hidden",
        }}>{nm}</div>

        {/* Price */}
        <div style={{ fontSize:16, fontWeight:700, color:T.gold, marginBottom:6, fontFamily:"'Outfit',sans-serif" }}>
          {pr ? `LKR ${Number(pr).toLocaleString()}` : pr}
        </div>

        {/* Rating */}
        {rat && (
          <Row gap={5} style={{ marginBottom:6 }}>
            <StarRating rating={rat} size="sm" />
            {rev && <span style={{ fontSize:10, color:T.dim }}>({rev} reviews)</span>}
          </Row>
        )}

        {/* Reason */}
        {rsn && <div style={{ fontSize:11, color: sf ? T.g : T.r, marginBottom:4, lineHeight:1.5 }}>{rsn}</div>}

        {/* Delivery */}
        {del && <div style={{ fontSize:10, color:T.dim, fontStyle:"italic", marginBottom:8 }}>{del}</div>}

        {/* CTA */}
        <a
          href="#"
          style={{
            display:"block", textAlign:"center", padding:"7px",
            border:`1px solid ${T.gold}`, borderRadius:6,
            fontSize:11, color:T.gold, textDecoration:"none",
            fontFamily:"'Outfit',sans-serif",
            transition:"background .2s",
          }}
          onMouseEnter={e => e.target.style.background=`${T.gold}1A`}
          onMouseLeave={e => e.target.style.background="transparent"}
        >
          View on Kapruka →
        </a>
      </div>
    </div>
  );
}

// ── ProductGalleryCard ────────────────────────────────────────────────────────
function ProductGalleryCard({ name, price, image, rating, safe, visible, dm }) {
  const nm  = rv(name,    dm) ?? "";
  const pr  = rv(price,   dm) ?? "";
  const img = rv(image,   dm) ?? "";
  const rat = rv(rating,  dm) ?? "";
  const sf  = rv(safe,    dm) ?? true;
  const vis = rv(visible, dm) ?? false;
  const [hover, setHover] = useState(false);

  if (!vis || !nm) return null;
  const imgSrc = img ? `/api/image?url=${encodeURIComponent(img)}` : null;

  return (
    <div
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        borderRadius:8, overflow:"hidden",
        border:`1px solid ${hover ? T.gold+"66" : T.bd}`,
        background:T.bg2, cursor:"pointer",
        transform: hover ? "scale(1.02)" : "scale(1)",
        boxShadow: hover ? `0 0 12px ${T.gold}22` : "none",
        transition:"all .2s",
        animation:"fadeUp .4s ease",
      }}
    >
      <div style={{ height:100, overflow:"hidden", background:T.bg3 }}>
        {imgSrc
          ? <img src={imgSrc} alt={nm} style={{ width:"100%", height:"100%", objectFit:"cover" }} />
          : <div style={{ width:"100%", height:"100%", display:"flex", alignItems:"center", justifyContent:"center", fontSize:22 }}>🎁</div>
        }
      </div>
      <div style={{ padding:"7px 8px" }}>
        <div style={{
          fontSize:11, color:T.tx, fontFamily:"'Outfit',sans-serif",
          overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap", marginBottom:3,
        }}>{nm}</div>
        <Row gap={4}>
          <span style={{ fontSize:12, fontWeight:700, color:T.gold, fontFamily:"'Outfit',sans-serif" }}>
            {pr ? `LKR ${Number(pr).toLocaleString()}` : pr}
          </span>
          {sf && <span style={{ fontSize:9, color:T.g }}>✓</span>}
        </Row>
        {rat && <StarRating rating={rat} size="sm" />}
      </div>
    </div>
  );
}

// ── NotificationToast ─────────────────────────────────────────────────────────
function NotificationToast({ text, visible, dm }) {
  const txt  = rv(text,    dm) ?? "";
  const vis  = rv(visible, dm) ?? false;
  const [show, setShow] = useState(false);

  useEffect(() => {
    if (vis && txt) {
      setShow(true);
      const t = setTimeout(() => setShow(false), 3000);
      return () => clearTimeout(t);
    } else {
      setShow(false);
    }
  }, [vis, txt]);

  return (
    <div style={{
      position:"fixed", bottom:80, right:16, zIndex:9999,
      transform: show ? "translateY(0)" : "translateY(30px)",
      opacity:   show ? 1 : 0,
      transition:"transform .3s ease, opacity .3s ease",
      pointerEvents: show ? "auto" : "none",
    }}>
      <div style={{
        background:`linear-gradient(135deg,${T.gold},${T.goldL})`,
        color:T.bg0, padding:"10px 16px", borderRadius:10,
        fontSize:13, fontWeight:600, fontFamily:"'Outfit',sans-serif",
        boxShadow:"0 8px 24px rgba(0,0,0,.6)",
        maxWidth:260,
      }}>
        {txt}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════
// WIDGET REGISTRY
// ═══════════════════════════════════════════════════════

const REGISTRY = {
  Column, Row, Card, Text, Divider, Button,
  ChatMessage, ThinkingDots, AgentPhase,
  MemoryChip, MemoryFound,
  ReflectStep, DraftPreview,
  RouteDecision, SafetyAlert, DeliveryBadge,
  ProductCard, ProductGalleryCard, StarRating,
  NotificationToast,
};

// ── Recursive renderer ────────────────────────────────────────────────────────
export function renderNode(id, comps, dm, depth = 0) {
  if (!id || !comps[id]) return null;
  const node = comps[id];

  // Find the widget type and props
  let widgetType = null;
  let widgetProps = {};

  if (node.component) {
    // Standard A2UI format: { id, component: { WidgetName: { ...props } } }
    const keys = Object.keys(node.component);
    if (keys.length > 0) {
      widgetType = keys[0];
      widgetProps = node.component[widgetType] || {};
    }
  } else {
    // Flat format used by initSurfaces: { id, type: "WidgetName", ...props }
    widgetType = node.type || node.widget;
    widgetProps = node.props || node;
  }

  if (!widgetType) return null;

  const Widget = REGISTRY[widgetType];
  if (!Widget) {
    console.warn(`Unknown widget: ${widgetType}`);
    return null;
  }

  // Resolve children — children prop may be an array of IDs or BoundValues
  const rawChildren = widgetProps.children;
  let resolvedChildren = null;
  if (rawChildren) {
    const childIds = Array.isArray(rawChildren)
      ? rawChildren
      : resolveBoundValue(rawChildren, dm);
    if (Array.isArray(childIds)) {
      resolvedChildren = childIds
        .map((cid, i) => <React.Fragment key={cid || i}>{renderNode(cid, comps, dm, depth + 1)}</React.Fragment>)
        .filter(Boolean);
    }
  }

  // Resolve gap for layout widgets
  const gapVal = widgetProps.gap != null ? resolveBoundValue(widgetProps.gap, dm) : undefined;

  return (
    <Widget
      key={id}
      {...widgetProps}
      gap={gapVal !== undefined ? gapVal : widgetProps.gap}
      dm={dm}
    >
      {resolvedChildren}
    </Widget>
  );
}

// ── SurfaceView ───────────────────────────────────────────────────────────────
export function SurfaceView({ surface, style }) {
  if (!surface?.ready || !surface.root) return null;
  return (
    <div style={style}>
      {renderNode(surface.root, surface.comps, surface.dm)}
    </div>
  );
}
