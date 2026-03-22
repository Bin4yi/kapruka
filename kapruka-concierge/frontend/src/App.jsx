import { useReducer, useState, useEffect, useRef, useCallback, createContext, useContext } from "react";
import { a2uiReducer, dispatchJSONL } from "./a2ui/engine";
import kaprukaLogo from "./assets/kapruka.jpg";

const GallerySelectContext = createContext(null);
const OnboardingContext    = createContext(null);

// ── Design tokens ─────────────────────────────────────────────────────────────
const C = {
  bg:      "#F1F3F2",
  bgSub:   "#FFFFFF",
  bd:      "#E5E7EB",
  bd2:     "#D1D5DB",
  side:    "#FFFFFF",
  side2:   "#F9FAFB",
  side3:   "#F3F4F6",
  sideBd:  "#E5E7EB",
  sideTx:  "#0B0B0B",
  sideTx2: "#374151",
  sideTx3: "#6B7280",
  accent:  "#0B0B0B",
  accentL: "#374151",
  gold:    "#0B0B0B",
  goldL:   "#374151",
  tx:      "#0B0B0B",
  tx2:     "#374151",
  tx3:     "#6B7280",
  g:       "#10B981",
  r:       "#EF4444",
  b:       "#0B0B0B",
  y:       "#F59E0B",
  p:       "#0B0B0B",
};

// ── Onboarding chip options ────────────────────────────────────────────────────
const ALLERGY_OPTIONS = [
  "nuts", "shellfish", "gluten", "dairy", "eggs", "soy", "spicy food", "alcohol",
];
const PREF_OPTIONS = [
  "dark chocolate", "flowers", "spa & wellness", "electronics", "books",
  "tea", "fruit baskets", "fashion", "toys", "jewelry", "beauty & skincare",
  "home decor", "cakes", "food hampers",
];
const DISTRICT_OPTIONS = [
  "Colombo", "Gampaha", "Kalutara", "Kandy", "Matale", "Nuwara Eliya",
  "Galle", "Matara", "Hambantota", "Jaffna", "Kilinochchi", "Mannar",
  "Vavuniya", "Mullaitivu", "Batticaloa", "Ampara", "Trincomalee",
  "Kurunegala", "Puttalam", "Anuradhapura", "Polonnaruwa", "Badulla",
  "Monaragala", "Ratnapura", "Kegalle",
];

// Quick-action categories for the empty state
const QUICK_ACTIONS = [
  { icon:"🎂", label:"Birthday Cakes",   color:"#F59E0B", q:"birthday cake" },
  { icon:"🌸", label:"Fresh Flowers",    color:"#F472B6", q:"flowers" },
  { icon:"🍫", label:"Chocolates",       color:"#92400E", q:"chocolate gifts" },
  { icon:"🎁", label:"Gift Hampers",     color:"#10B981", q:"food hampers" },
  { icon:"📱", label:"Electronics",      color:"#3B82F6", q:"electronics" },
  { icon:"💆", label:"Spa & Wellness",   color:"#8B5CF6", q:"spa wellness" },
];

// ── A2UI helpers ───────────────────────────────────────────────────────────────
const mkDM = (sid, data)  => JSON.stringify({ type:"dataModelUpdate", surfaceId:sid, data });
const mkBR = (sid, root)  => JSON.stringify({ type:"beginRendering",  surfaceId:sid, root });
const mkSU = (sid, comps) => JSON.stringify({ type:"surfaceUpdate",   surfaceId:sid, components:comps });
const cc   = (id, type, props={}) => ({ id, type, props });

// ── Surface builders ───────────────────────────────────────────────────────────
function buildSurfaces(profile = {}) {
  const lines = [];

  lines.push(mkSU("agent_surface", [
    cc("root","Column",{ gap:8, children:["ag_pipe","ag_route","ag_refl","ag_delivery","ag_prod"] }),
    cc("ag_pipe",     "PipelinePanel",   {}),
    cc("ag_route",    "RouteChip",       { route:{path:"/route"} }),
    cc("ag_refl",     "ReflectionPanel", {}),
    cc("ag_delivery", "DeliveryBadge",   { feasible:{path:"/delivery_feasible"}, district:{path:"/delivery_district"}, days:{path:"/delivery_days"} }),
    cc("ag_prod",     "MiniProductCard", { name:{path:"/prod_name"}, price:{path:"/prod_price"}, image:{path:"/prod_image"}, tags:{path:"/prod_tags"} }),
  ]));
  lines.push(mkDM("agent_surface", {
    ph_r:"idle", ph_s:"idle", ph_ref:"idle", ph_d:"idle",
    route:"", confidence:0, recipient:"",
    rf1:"idle", rf2:"idle", rf3:"idle", rf1_active:false,
    prod_name:"", prod_price:"", prod_image:"", prod_safe:true, prod_tags:[],
    delivery_feasible:false, delivery_district:"", delivery_days:"",
  }));
  lines.push(mkBR("agent_surface","root"));

  lines.push(mkSU("memory_surface", [
    cc("root","Column",{ gap:6, children:["m_st","m_lt","m_sem","m_found"] }),
    cc("m_st",    "MemoryChip",  { label:{literalString:"Short-Term"},  sublabel:{path:"/st_label"},         active:{path:"/st_active"},  tier:{literalString:"st"}       }),
    cc("m_lt",    "MemoryChip",  { label:{literalString:"LT-RAG"},      sublabel:{literalString:"Qdrant"},   active:{path:"/lt_active"},  tier:{literalString:"ltrag"}    }),
    cc("m_sem",   "MemoryChip",  { label:{literalString:"Semantic"},    sublabel:{literalString:"Profiles"}, active:{path:"/sem_active"}, tier:{literalString:"semantic"} }),
    cc("m_found", "ProfileData", { allergies:{path:"/allergies"}, preferences:{path:"/preferences"}, district:{path:"/district"}, active:{path:"/sem_active"} }),
  ]));
  lines.push(mkDM("memory_surface", {
    st_active:false, st_label:"Idle", lt_active:false, sem_active:false,
    allergies:    profile.allergies    || [],
    preferences:  profile.preferences || [],
    district:     profile.district    || "",
  }));
  lines.push(mkBR("memory_surface","root"));

  lines.push(mkSU("gallery_surface", [
    cc("root","ProductGallery",{ products:{path:"/products"} }),
  ]));
  lines.push(mkDM("gallery_surface", { products:[] }));
  lines.push(mkBR("gallery_surface","root"));

  lines.push(mkDM("chat_surface",         { thinking:false, thinking_label:"Thinking...", response:"" }));
  lines.push(mkDM("notification_surface", { toast_text:"", toast_visible:false }));
  return lines;
}

function buildOnboardingSurface() {
  const lines = [];
  lines.push(mkSU("onboarding_surface", [ cc("root","OnboardingWizard",{}) ]));
  lines.push(mkDM("onboarding_surface", { step:0, recipient:"", allergies:[], preferences:[], district:"", budget:"" }));
  lines.push(mkBR("onboarding_surface","root"));
  return lines;
}

// ── Sidebar widgets ────────────────────────────────────────────────────────────
function SLabel({ children }) {
  return (
    <div style={{ fontSize:10, fontFamily:"var(--mono)", color:C.sideTx3, letterSpacing:3, textTransform:"uppercase", marginBottom:12, display:"flex", alignItems:"center", gap:8 }}>
      <span>{children}</span>
      <span style={{ flex:1, height:"1px", background:C.sideBd }} />
    </div>
  );
}

function PhaseRow({ label, status, icon }) {
  const col = { idle:C.sideTx3, active:C.y, done:C.g, error:C.r }[status] || C.sideTx3;
  const isActive = status === "active";
  const isDone   = status === "done";
  return (
    <div style={{
      display:"flex", alignItems:"center", gap:10, padding:"7px 10px", borderRadius:8,
      background: isActive ? `${col}18` : "transparent",
      transition:"all .3s",
    }}>
      <div style={{
        width:8, height:8, borderRadius:"50%", flexShrink:0,
        background:  isDone || isActive ? col : "transparent",
        border:      isDone || isActive ? "none" : `1.5px solid ${C.sideTx3}`,
        boxShadow:   isActive ? `0 0 10px ${col}` : "none",
        animation:   isActive ? "pulse 1s infinite" : "none",
        transition:  "all .3s",
      }} />
      <span style={{ fontSize:13, fontFamily:"var(--mono)", color:col, fontWeight: isActive ? 600 : 400, flex:1 }}>{label}</span>
      <span style={{ fontSize:11, color: isDone ? col : C.sideTx3 }}>{icon}</span>
    </div>
  );
}

function PipelinePanel({ dm = {} }) {
  return (
    <div>
      <SLabel>Pipeline</SLabel>
      <div style={{ display:"flex", flexDirection:"column", gap:2 }}>
        <PhaseRow label="Route"   status={dm.ph_r   || "idle"} icon="→" />
        <PhaseRow label="Search"  status={dm.ph_s   || "idle"} icon="⊙" />
        <PhaseRow label="Reflect" status={dm.ph_ref || "idle"} icon="◎" />
        <PhaseRow label="Done"    status={dm.ph_d   || "idle"} icon="✓" />
      </div>
    </div>
  );
}

function ReflectionPanel({ dm = {} }) {
  const rf1 = dm.rf1 || "idle";
  if (rf1 === "idle") return null;
  return (
    <div style={{ borderTop:`1px solid ${C.sideBd}`, paddingTop:12, marginTop:4, animation:"fadeIn .3s" }}>
      <SLabel>Reflection</SLabel>
      <div style={{ display:"flex", flexDirection:"column", gap:2 }}>
        {[["Draft", rf1, "①"], ["Verify", dm.rf2||"idle", "②"], ["Revise", dm.rf3||"idle", "③"]].map(([l,s,n]) => (
          <PhaseRow key={l} label={l} status={s} icon={n} />
        ))}
      </div>
    </div>
  );
}

function RouteChip({ dm = {} }) {
  const route = dm.route || "";
  if (!route) return null;
  const map = {
    SEARCH_CATALOG:   { label:"Catalog Search", color:C.accentL },
    CHECK_LOGISTICS:  { label:"Logistics",      color:"#38BDF8"  },
    UPDATE_PREFERENCE:{ label:"Profile Update", color:C.goldL   },
    CHITCHAT:         { label:"Conversation",   color:"#38BDF8"  },
    CLARIFICATION:    { label:"Clarifying",     color:C.y        },
    ORDER_HISTORY:    { label:"Order History",  color:C.sideTx2  },
  };
  const m = map[route];
  if (!m) return null;
  return (
    <div style={{ display:"flex", alignItems:"center", gap:8, padding:"7px 10px", borderRadius:8, background:`${m.color}18`, border:`1px solid ${m.color}30` }}>
      <div style={{ width:7, height:7, borderRadius:"50%", background:m.color, flexShrink:0 }} />
      <span style={{ fontSize:12, color:m.color, fontFamily:"var(--mono)", fontWeight:600, flex:1 }}>{m.label}</span>
      {dm.confidence ? <span style={{ fontSize:11, color:C.sideTx3 }}>{Math.round(dm.confidence*100)}%</span> : null}
    </div>
  );
}

function DeliveryBadge({ dm = {} }) {
  const dist = dm.delivery_district || "";
  if (!dist) return null;
  const ok  = dm.delivery_feasible;
  const col = ok ? C.g : C.r;
  return (
    <div style={{ display:"flex", alignItems:"center", gap:8, padding:"7px 10px", borderRadius:8, background:`${col}18`, border:`1px solid ${col}30` }}>
      <span style={{ fontSize:14, color:col }}>{ok ? "✓" : "✕"}</span>
      <span style={{ fontSize:12, color:col, fontFamily:"var(--mono)", fontWeight:500 }}>{dist}{dm.delivery_days ? ` · ${dm.delivery_days}` : ""}</span>
    </div>
  );
}

function MiniProductCard({ dm = {} }) {
  const nm = dm.prod_name || "";
  if (!nm) return null;
  return (
    <div style={{ display:"flex", gap:10, alignItems:"center", padding:"9px 10px", borderRadius:10, background:C.side3, border:`1px solid ${C.sideBd}`, animation:"slideDown .4s" }}>
      {dm.prod_image
        ? <img src={`/api/image?url=${encodeURIComponent(dm.prod_image)}`} alt="" style={{ width:38, height:38, borderRadius:7, objectFit:"cover", flexShrink:0 }} />
        : <div style={{ width:38, height:38, borderRadius:7, background:`${C.accent}30`, display:"flex", alignItems:"center", justifyContent:"center", fontSize:18, color:C.accentL, flexShrink:0 }}>◈</div>
      }
      <div style={{ minWidth:0 }}>
        <div style={{ fontSize:13, color:C.sideTx, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap", fontWeight:500, lineHeight:1.3 }}>{nm}</div>
        {dm.prod_price && <div style={{ fontSize:12, color:C.goldL, fontFamily:"var(--mono)", marginTop:3, fontWeight:600 }}>Rs.{Number(dm.prod_price).toLocaleString()}</div>}
      </div>
    </div>
  );
}

function MemoryChip({ label, sublabel, active, tier, dm = {} }) {
  const rv  = (bv) => bv?.path ? (dm[bv.path.replace(/^\//,"")] ?? null) : (bv?.literalString ?? bv);
  const lbl = rv(label) ?? "";
  const sub = rv(sublabel) ?? "";
  const act = rv(active) ?? false;
  const tr  = rv(tier) ?? "st";
  const colorMap = { st:"#38BDF8", ltrag:C.accentL, semantic:"#34D399" };
  const col = colorMap[tr] || "#38BDF8";
  return (
    <div style={{
      display:"flex", alignItems:"center", gap:10, padding:"9px 12px", borderRadius:10,
      background: act ? `${col}14` : C.side2,
      border: `1px solid ${act ? col + "40" : C.sideBd}`,
      boxShadow: act ? `0 0 20px ${col}20` : "none",
      transition:"all .4s cubic-bezier(0.32,0.72,0,1)",
    }}>
      <div style={{ width:9, height:9, borderRadius:"50%", background: act ? col : C.sideTx3, flexShrink:0, animation: act ? "pulse 1.2s infinite" : "none", transition:"background .3s" }} />
      <div style={{ flex:1, minWidth:0 }}>
        <div style={{ fontSize:13, color: act ? C.sideTx : C.sideTx2, fontWeight:500 }}>{lbl}</div>
        <div style={{ fontSize:11, color: act ? col : C.sideTx3, fontFamily:"var(--mono)", marginTop:2, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{sub}</div>
      </div>
      {act && <div style={{ width:7, height:7, borderRadius:"50%", background:col, flexShrink:0 }} />}
    </div>
  );
}

function ProfileData({ allergies, preferences, district, active, dm = {} }) {
  const rv  = (bv) => bv?.path ? (dm[bv.path.replace(/^\//,"")] ?? null) : (bv?.literalString ?? bv);
  const alg = rv(allergies) ?? [];
  const prf = rv(preferences) ?? [];
  const dst = rv(district) ?? "";
  const act = rv(active) ?? false;
  if (!alg.length && !prf.length && !dst) return null;
  return (
    <div style={{ overflow:"hidden", maxHeight: act ? 160 : 0, opacity: act ? 1 : 0, transition:"max-height .45s cubic-bezier(0.32,0.72,0,1), opacity .3s" }}>
      <div style={{ padding:"12px", borderRadius:10, border:`1px solid ${C.g}35`, background:`${C.g}0A`, marginTop:6 }}>
        <div style={{ fontSize:10, color:C.g, fontFamily:"var(--mono)", letterSpacing:2, marginBottom:8, fontWeight:600 }}>PROFILE ACTIVE</div>
        <div style={{ display:"flex", flexWrap:"wrap", gap:5 }}>
          {alg.map((a,i) => <span key={i} style={{ padding:"3px 9px", borderRadius:99, fontSize:11, background:`${C.r}18`, color:"#FCA5A5", border:`1px solid ${C.r}35`, fontFamily:"var(--mono)" }}>!{a}</span>)}
          {prf.map((p,i) => <span key={i} style={{ padding:"3px 9px", borderRadius:99, fontSize:11, background:`${C.g}14`, color:"#86EFAC", border:`1px solid ${C.g}28`, fontFamily:"var(--mono)" }}>+{p}</span>)}
        </div>
        {dst && <div style={{ fontSize:11, color:C.sideTx2, fontFamily:"var(--mono)", marginTop:8 }}>📍 {dst}</div>}
      </div>
    </div>
  );
}

// ── Chat widgets ───────────────────────────────────────────────────────────────
function ThinkingDots({ active, label }) {
  if (!active) return null;
  return (
    <div style={{ display:"flex", alignItems:"center", gap:12, padding:"14px 16px" }}>
      <div style={{ display:"flex", gap:5 }}>
        {[0,1,2].map(i => <div key={i} style={{ width:8, height:8, borderRadius:"50%", background:C.accent, animation:`pulse 1.4s ease ${i*0.18}s infinite`, opacity:0.7 }} />)}
      </div>
      <span style={{ fontSize:14, color:C.tx3 }}>{label || "Thinking..."}</span>
    </div>
  );
}

function HeroWelcome({ content }) {
  return (
    <div style={{ display:"flex", justifyContent:"flex-start", marginBottom:24, animation:"fadeUp .3s" }}>
      <div style={{ width:36, height:36, borderRadius:"50%", flexShrink:0, marginRight:12, alignSelf:"flex-end", overflow:"hidden", background:C.accent, display:"flex", alignItems:"center", justifyContent:"center", color:"#fff", fontSize:14, fontWeight:600 }}>
        <img src={kaprukaLogo} alt="Kapruka" style={{width:"100%", height:"100%", objectFit:"cover"}} />
      </div>
      <div style={{
        maxWidth:"75%", padding:"20px 24px",
        borderRadius: "24px 24px 24px 4px",
        background: "#0B0B0B", color: "#FFFFFF",
        fontSize:15, lineHeight:1.6, whiteSpace:"pre-wrap",
        boxShadow: "0 8px 24px rgba(0,0,0,0.08)",
      }}>
        <div style={{ fontSize:12, color:"#9CA3AF", fontFamily:"var(--mono)", letterSpacing:1, marginBottom:8, fontWeight:600 }}>KAPRUKA CONCIERGE</div>
        {content}
      </div>
    </div>
  );
}

// Regular chat bubble
function ChatBubble({ msg }) {
  const isUser = msg.role === "user";
  return (
    <div style={{ display:"flex", justifyContent: isUser ? "flex-end" : "flex-start", marginBottom:24, animation:"fadeUp .3s" }}>
      {!isUser && (
        <div style={{ width:36, height:36, borderRadius:"50%", flexShrink:0, marginRight:12, alignSelf:"flex-end", overflow:"hidden", background:C.accent, display:"flex", alignItems:"center", justifyContent:"center", color:"#fff", fontSize:14, fontWeight:600 }}>
          <img src={kaprukaLogo} alt="Kapruka" style={{width:"100%", height:"100%", objectFit:"cover"}} />
        </div>
      )}
      <div style={{
        maxWidth:"75%", padding:"16px 20px",
        borderRadius: isUser ? "24px 24px 4px 24px" : "24px 24px 24px 4px",
        background: isUser ? "#FFFFFF" : "#0B0B0B",
        color: isUser ? "#000000" : "#FFFFFF",
        border: "none",
        fontSize:15, lineHeight:1.6, whiteSpace:"pre-wrap",
        boxShadow: isUser ? "0 4px 20px rgba(0,0,0,0.04)" : "0 8px 24px rgba(0,0,0,0.08)",
      }}>{msg.content}</div>
      {isUser && (
        <div style={{ width:36, height:36, borderRadius:"50%", flexShrink:0, marginLeft:12, alignSelf:"flex-end", overflow:"hidden", background:"#fff", display:"flex", alignItems:"center", justifyContent:"center", color:C.tx, fontSize:10, fontWeight:700, boxShadow:"0 2px 8px rgba(0,0,0,0.05)", border:`1px solid ${C.bd}` }}>
          ME
        </div>
      )}
    </div>
  );
}

// Empty state grid — shown when only the welcome message exists
function QuickActions({ profile, onSelect }) {
  return (
    <div style={{ marginTop:4, marginBottom:8, animation:"fadeIn .5s .15s both" }}>
      <div style={{ display:"flex", alignItems:"center", gap:10, marginBottom:14 }}>
        <span style={{ flex:1, height:1, background:C.bd }} />
        <span style={{ fontSize:11, color:C.tx3, fontFamily:"var(--mono)", letterSpacing:1 }}>QUICK SEARCHES</span>
        <span style={{ flex:1, height:1, background:C.bd }} />
      </div>
      <div style={{ display:"grid", gridTemplateColumns:"repeat(3,1fr)", gap:8 }}>
        {QUICK_ACTIONS.map(({ icon, label, color, q }) => {
          const query = `${q} for ${profile.recipient}`;
          return (
            <button key={label} onClick={() => onSelect(query)}
              style={{
                display:"flex", flexDirection:"column", alignItems:"flex-start", gap:8,
                padding:"14px 14px", borderRadius:14, cursor:"pointer", textAlign:"left",
                background:"rgba(255,255,255,0.03)", border:`1px solid rgba(255,255,255,0.1)`,
                backdropFilter:"blur(16px)", WebkitBackdropFilter:"blur(16px)",
                boxShadow:"0 4px 12px rgba(0,0,0,0.5)",
                transition:"all .2s cubic-bezier(0.32,0.72,0,1)",
              }}
              onMouseEnter={e => {
                e.currentTarget.style.borderColor = color + "90";
                e.currentTarget.style.background  = "rgba(255,255,255,0.08)";
                e.currentTarget.style.transform   = "translateY(-3px)";
                e.currentTarget.style.boxShadow   = `0 10px 24px ${color}30`;
              }}
              onMouseLeave={e => {
                e.currentTarget.style.borderColor = "rgba(255,255,255,0.1)";
                e.currentTarget.style.background  = "rgba(255,255,255,0.03)";
                e.currentTarget.style.transform   = "translateY(0)";
                e.currentTarget.style.boxShadow   = "0 4px 12px rgba(0,0,0,0.5)";
              }}
            >
              <span style={{ fontSize:22 }}>{icon}</span>
              <span style={{ fontSize:12, color:C.tx2, fontWeight:600, lineHeight:1.3 }}>{label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ── Product widgets ────────────────────────────────────────────────────────────
function ProductCard({ product, onClick }) {
  const [hover, setHov] = useState(false);
  const img  = product.image || product.image_url || (product.image_urls||[])[0] || "";
  const tags = (product.tags||[]).slice(0,2);
  return (
    <div
      onClick={() => onClick?.(product)}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        flexShrink:0, width:170, borderRadius:16, overflow:"hidden", cursor:"pointer",
        background: "#FFFFFF",
        border: hover ? `1px solid #000` : `1px solid #E5E7EB`,
        boxShadow: hover ? "0 12px 32px rgba(0,0,0,0.08)" : "none",
        transform: hover ? "translateY(-2px)" : "translateY(0)",
        transition:"all .2s cubic-bezier(0.32,0.72,0,1)",
        padding:"6px",
      }}
    >
      <div style={{ height:120, borderRadius:12, background:"#F3F4F6", overflow:"hidden", position:"relative" }}>
        {img
          ? <img src={`/api/image?url=${encodeURIComponent(img)}`} alt={product.name||""} style={{ width:"100%", height:"100%", objectFit:"cover" }} />
          : <div style={{ width:"100%", height:"100%", display:"flex", alignItems:"center", justifyContent:"center", fontSize:30, color:C.accent, opacity:0.2 }}>◈</div>
        }
        {tags.length > 0 && (
          <div style={{ position:"absolute", bottom:5, left:5, display:"flex", gap:3 }}>
            {tags.map((t,i) => <span key={i} style={{ padding:"2px 7px", borderRadius:5, fontSize:9, background:"rgba(255,255,255,0.94)", color:C.tx2, fontFamily:"var(--mono)", fontWeight:600 }}>{t}</span>)}
          </div>
        )}
      </div>
      <div style={{ padding:"10px 12px 12px" }}>
        <div style={{ fontSize:12, color:C.tx, fontWeight:600, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap", marginBottom:5, lineHeight:1.35 }}>{product.name||""}</div>
        <div style={{ fontSize:13, color:C.gold, fontFamily:"var(--mono)", fontWeight:700 }}>{product.price ? `Rs.${Number(product.price).toLocaleString()}` : "—"}</div>
        {product.rating && <div style={{ fontSize:10, color:C.y, marginTop:4 }}>{"★".repeat(Math.round(product.rating))}{"☆".repeat(5-Math.round(product.rating))}</div>}
      </div>
    </div>
  );
}

function ProductModal({ product, onClose }) {
  if (!product) return null;
  const img = product.image || product.image_url || (product.image_urls||[])[0] || "";
  return (
    <div onClick={onClose} style={{ position:"fixed", inset:0, zIndex:1000, background:"rgba(0,0,0,0.4)", backdropFilter:"blur(4px)", display:"flex", alignItems:"center", justifyContent:"center", animation:"fadeIn .2s", padding: 24 }}>
      <div onClick={e=>e.stopPropagation()} style={{ width:"100%", maxWidth:400, borderRadius:24, overflow:"hidden", background:"#FFFFFF", boxShadow:"0 24px 64px rgba(0,0,0,0.2)", animation:"slideUp .3s cubic-bezier(0.32,0.72,0,1)" }}>
        <div style={{ padding:6 }}>
          <div style={{ height:240, background:"#F3F4F6", position:"relative", borderRadius:18, overflow:"hidden" }}>
            {img && <img src={`/api/image?url=${encodeURIComponent(img)}`} alt={product.name||""} style={{ width:"100%", height:"100%", objectFit:"cover" }} />}
            <button onClick={onClose} style={{ position:"absolute", top:12, right:12, width:36, height:36, borderRadius:"50%", background:"#FFFFFF", color:"#000", border:"none", fontSize:16, display:"flex", alignItems:"center", justifyContent:"center", cursor:"pointer", boxShadow:"0 4px 12px rgba(0,0,0,0.15)" }}>✕</button>
          </div>
        </div>
        <div style={{ padding:"20px 24px 28px" }}>
          <div style={{ display:"flex", flexWrap:"wrap", gap:5, marginBottom:12 }}>
            {(product.tags||[]).map((t,i) => <span key={i} style={{ padding:"4px 10px", borderRadius:6, fontSize:11, background:`#F3F4F6`, color:`#374151`, border:`1px solid #E5E7EB`, fontFamily:"var(--mono)", fontWeight:500 }}>{t}</span>)}
          </div>
          <div style={{ fontSize:17, fontWeight:700, color:C.tx, marginBottom:8, lineHeight:1.4 }}>{product.name||""}</div>
          <div style={{ fontSize:22, color:C.gold, fontFamily:"var(--mono)", fontWeight:700, marginBottom:18 }}>{product.price ? `Rs.${Number(product.price).toLocaleString()}` : "—"}</div>
          {product.url && (
            <a href={product.url} target="_blank" rel="noopener noreferrer" style={{ display:"flex", alignItems:"center", justifyContent:"center", padding:"13px", borderRadius:40, fontSize:15, fontWeight:600, background:C.accent, color:"#fff", boxShadow:`0 8px 24px rgba(0,0,0,0.15)`, letterSpacing:0.3, textDecoration:"none" }}>
              View on Kapruka →
            </a>
          )}
        </div>
      </div>
    </div>
  );
}

function NotificationToast({ text, visible }) {
  const [show, setShow] = useState(false);
  useEffect(() => {
    if (visible && text) { setShow(true); const t = setTimeout(() => setShow(false), 3500); return () => clearTimeout(t); }
    else setShow(false);
  }, [visible, text]);
  if (!show) return null;
  return (
    <div style={{ position:"fixed", bottom:80, right:20, zIndex:2000, padding:"13px 20px", borderRadius:12, background:C.accent, color:"#fff", fontSize:14, fontWeight:600, boxShadow:"0 8px 32px rgba(99,102,241,0.45)", animation:"slideUp .3s" }}>
      {text}
    </div>
  );
}

// ── A2UI ProductGallery widget ─────────────────────────────────────────────────
function ProductGallery({ products: productsBV, dm = {} }) {
  const rv     = (bv) => bv?.path ? (dm[bv.path.replace(/^\//,"")] ?? null) : (bv?.literalString ?? bv);
  const prods  = rv(productsBV) ?? [];
  const onSelect = useContext(GallerySelectContext);
  if (!Array.isArray(prods) || !prods.length) return null;
  return (
    <div style={{ animation:"slideUp .4s cubic-bezier(0.32,0.72,0,1)" }}>
      <div style={{ fontSize:11, color:C.tx3, fontFamily:"var(--mono)", letterSpacing:1, marginBottom:12, display:"flex", alignItems:"center", gap:8 }}>
        <span style={{ width:7, height:7, borderRadius:"50%", background:C.accent, display:"inline-block" }} />
        <span>{prods.length} recommendations found</span>
        <span style={{ color:C.bd2 }}>· click to expand</span>
      </div>
      <div style={{ display:"flex", gap:10, overflowX:"auto", paddingBottom:6 }}>
        {prods.map((p,i) => <ProductCard key={i} product={p} onClick={onSelect} />)}
      </div>
    </div>
  );
}

// ── A2UI OnboardingWizard widget ───────────────────────────────────────────────
function ChipButton({ label, selected, onClick }) {
  return (
    <button onClick={onClick} style={{
      padding:"7px 16px", borderRadius:99, fontSize:13, fontWeight:500,
      background: selected ? C.accent : C.bgSub,
      color:      selected ? "#fff"   : C.tx2,
      border:    `1.5px solid ${selected ? C.accent : C.bd}`,
      cursor:"pointer", transition:"all .15s",
      boxShadow: selected ? `0 2px 10px ${C.accent}35` : "none",
    }}>{label}</button>
  );
}

function OnboardingWizard({ dm = {} }) {
  const ctx  = useContext(OnboardingContext);
  const step = dm.step ?? 0;
  const push = useCallback((data) => ctx?.mergeDM(data), [ctx]);

  const [nameInput,   setNameInput]   = useState(dm.recipient || "");
  const [budgetInput, setBudgetInput] = useState(dm.budget    || "");

  const STEPS = ["Recipient", "Allergies", "Preferences", "Details"];

  const toggleChip = (field, val) => {
    const curr = dm[field] || [];
    push({ [field]: curr.includes(val) ? curr.filter(x=>x!==val) : [...curr, val] });
  };

  const stepStyle = { display:"flex", flexDirection:"column", gap:22, animation:"fadeUp .35s cubic-bezier(0.32,0.72,0,1)" };

  const nextBtn = (onClick, label="Next →", disabled=false) => (
    <button onClick={onClick} disabled={disabled} style={{
      alignSelf:"flex-end", padding:"12px 30px", borderRadius:11,
      fontSize:14, fontWeight:600, background: disabled ? C.bgSub : C.accent,
      color: disabled ? C.tx3 : "#fff", border:`1.5px solid ${disabled ? C.bd : C.accent}`,
      cursor: disabled ? "not-allowed" : "pointer",
      boxShadow: disabled ? "none" : `0 4px 14px ${C.accent}40`,
      transition:"all .18s",
    }}>{label}</button>
  );

  const backBtn = (onClick) => (
    <button onClick={onClick} style={{ padding:"12px 22px", borderRadius:11, fontSize:14, color:C.tx3, border:`1.5px solid ${C.bd}`, background:"transparent", cursor:"pointer" }}>← Back</button>
  );

  return (
    <div style={{ width:"100%", maxWidth:520, margin:"0 auto" }}>
      {/* Progress bar */}
      <div style={{ display:"flex", gap:6, marginBottom:32 }}>
        {STEPS.map((s, i) => (
          <div key={i} style={{ flex:1, display:"flex", flexDirection:"column", alignItems:"center", gap:7 }}>
            <div style={{
              width:30, height:30, borderRadius:"50%", display:"flex", alignItems:"center", justifyContent:"center",
              fontSize:12, fontWeight:700,
              background: i < step ? C.g : i === step ? C.accent : C.bgSub,
              color:      i <= step ? "#fff" : C.tx3,
              border:    `2px solid ${i < step ? C.g : i === step ? C.accent : C.bd}`,
              transition:"all .3s",
              boxShadow: i === step ? `0 3px 10px ${C.accent}35` : "none",
            }}>{i < step ? "✓" : i+1}</div>
            <span style={{ fontSize:10, color: i === step ? C.accent : C.tx3, fontFamily:"var(--mono)", fontWeight: i === step ? 700 : 400, letterSpacing:0.5 }}>{s}</span>
          </div>
        ))}
      </div>

      {step === 0 && (
        <div style={stepStyle}>
          <div>
            <div style={{ fontSize:22, fontWeight:700, color:C.tx, marginBottom:8 }}>Who are you gifting?</div>
            <div style={{ fontSize:14, color:C.tx3, lineHeight:1.6 }}>Give them a name — we'll remember their preferences.</div>
          </div>
          <input
            value={nameInput}
            onChange={e => setNameInput(e.target.value)}
            onKeyDown={e => { if (e.key==="Enter" && nameInput.trim()) push({ step:1, recipient:nameInput.trim() }); }}
            placeholder="e.g. Wife, Mom, Kasun, Dilini…"
            autoFocus
            style={{ padding:"13px 16px", borderRadius:11, border:`1.5px solid ${C.bd2}`, fontSize:15, color:C.tx, background:C.bg, fontFamily:"var(--sans)", outline:"none", transition:"border-color .2s" }}
            onFocus={e => e.target.style.borderColor = C.accent}
            onBlur={e  => e.target.style.borderColor = C.bd2}
          />
          {nextBtn(() => { if (nameInput.trim()) push({ step:1, recipient:nameInput.trim() }); }, "Next →", !nameInput.trim())}
        </div>
      )}

      {step === 1 && (
        <div style={stepStyle}>
          <div>
            <div style={{ fontSize:22, fontWeight:700, color:C.tx, marginBottom:8 }}>Any allergies for <span style={{ color:C.accent }}>{dm.recipient}</span>?</div>
            <div style={{ fontSize:14, color:C.tx3, lineHeight:1.6 }}>We'll avoid these in all recommendations. Skip if none.</div>
          </div>
          <div style={{ display:"flex", flexWrap:"wrap", gap:8 }}>
            {ALLERGY_OPTIONS.map(a => (
              <ChipButton key={a} label={a} selected={(dm.allergies||[]).includes(a)} onClick={() => toggleChip("allergies", a)} />
            ))}
          </div>
          <div style={{ display:"flex", gap:10, justifyContent:"flex-end" }}>
            {backBtn(() => push({ step:0 }))}
            {nextBtn(() => push({ step:2 }))}
          </div>
        </div>
      )}

      {step === 2 && (
        <div style={stepStyle}>
          <div>
            <div style={{ fontSize:22, fontWeight:700, color:C.tx, marginBottom:8 }}>What does <span style={{ color:C.accent }}>{dm.recipient}</span> enjoy?</div>
            <div style={{ fontSize:14, color:C.tx3, lineHeight:1.6 }}>Pick anything — we'll prioritise these. Skip if unsure.</div>
          </div>
          <div style={{ display:"flex", flexWrap:"wrap", gap:8 }}>
            {PREF_OPTIONS.map(p => (
              <ChipButton key={p} label={p} selected={(dm.preferences||[]).includes(p)} onClick={() => toggleChip("preferences", p)} />
            ))}
          </div>
          <div style={{ display:"flex", gap:10, justifyContent:"flex-end" }}>
            {backBtn(() => push({ step:1 }))}
            {nextBtn(() => push({ step:3 }))}
          </div>
        </div>
      )}

      {step === 3 && (
        <div style={stepStyle}>
          <div>
            <div style={{ fontSize:22, fontWeight:700, color:C.tx, marginBottom:8 }}>Delivery details</div>
            <div style={{ fontSize:14, color:C.tx3, lineHeight:1.6 }}>Helps us check availability and filter by budget.</div>
          </div>
          <div style={{ display:"flex", flexDirection:"column", gap:16 }}>
            <div>
              <label style={{ fontSize:12, fontWeight:600, color:C.tx2, display:"block", marginBottom:7, fontFamily:"var(--mono)", letterSpacing:1 }}>DELIVERY DISTRICT</label>
              <select
                value={dm.district || ""}
                onChange={e => push({ district: e.target.value })}
                style={{ width:"100%", padding:"12px 14px", borderRadius:10, border:`1.5px solid ${C.bd2}`, fontSize:14, color: dm.district ? C.tx : C.tx3, background:C.bg, fontFamily:"var(--sans)", outline:"none", cursor:"pointer" }}
              >
                <option value="">Select district (optional)</option>
                {DISTRICT_OPTIONS.map(d => <option key={d} value={d}>{d}</option>)}
              </select>
            </div>
            <div>
              <label style={{ fontSize:12, fontWeight:600, color:C.tx2, display:"block", marginBottom:7, fontFamily:"var(--mono)", letterSpacing:1 }}>BUDGET (LKR)</label>
              <input
                value={budgetInput}
                onChange={e => setBudgetInput(e.target.value)}
                placeholder="e.g. 5000 (optional)"
                style={{ width:"100%", padding:"12px 14px", borderRadius:10, border:`1.5px solid ${C.bd2}`, fontSize:14, color:C.tx, background:C.bg, fontFamily:"var(--sans)", outline:"none", boxSizing:"border-box", transition:"border-color .2s" }}
                onFocus={e => e.target.style.borderColor = C.accent}
                onBlur={e  => e.target.style.borderColor = C.bd2}
              />
            </div>
          </div>
          <div style={{ display:"flex", gap:10, justifyContent:"flex-end" }}>
            {backBtn(() => push({ step:2 }))}
            <button
              onClick={() => {
                const budgetLkr = budgetInput ? parseFloat(budgetInput.replace(/[^\d.]/g,"")) || null : null;
                ctx?.onComplete({ recipient:dm.recipient, allergies:dm.allergies||[], preferences:dm.preferences||[], district:dm.district||"", budget_lkr:budgetLkr });
              }}
              style={{ padding:"12px 30px", borderRadius:11, fontSize:14, fontWeight:600, background:C.g, color:"#fff", border:`1.5px solid ${C.g}`, cursor:"pointer", boxShadow:`0 4px 14px ${C.g}40`, transition:"all .18s" }}
            >Save & Start →</button>
          </div>
        </div>
      )}
    </div>
  );
}

// ── A2UI renderer ──────────────────────────────────────────────────────────────
const WIDGET_MAP = {
  Column:          ({ children, gap=8 }) => <div style={{ display:"flex", flexDirection:"column", gap }}>{children}</div>,
  PipelinePanel,
  RouteChip:       ({ dm }) => <RouteChip dm={dm} />,
  ReflectionPanel: ({ dm }) => <ReflectionPanel dm={dm} />,
  DeliveryBadge:   ({ dm }) => <DeliveryBadge dm={dm} />,
  MiniProductCard: ({ dm }) => <MiniProductCard dm={dm} />,
  MemoryChip,
  ProfileData,
  ProductGallery,
  OnboardingWizard,
};

function RenderNode({ id, comps, dm }) {
  if (!id || !comps?.[id]) return null;
  const node     = comps[id];
  const type     = node.type || node.widget || Object.keys(node.component||{})[0];
  const rawProps = node.props || node.component?.[type] || {};
  const Widget   = WIDGET_MAP[type];
  if (!Widget) return null;
  const childIds = rawProps.children;
  const children = Array.isArray(childIds)
    ? childIds.map(cid => <RenderNode key={cid} id={cid} comps={comps} dm={dm} />)
    : null;
  return <Widget {...rawProps} gap={typeof rawProps.gap==="number"?rawProps.gap:8} dm={dm}>{children}</Widget>;
}

function SurfaceView({ surface, style }) {
  if (!surface?.ready || !surface.root) return null;
  return <div style={style}><RenderNode id={surface.root} comps={surface.comps} dm={surface.dm} /></div>;
}

// ── Login Screen ───────────────────────────────────────────────────────────────
const PRESET_USERS = ["Binula", "Kasun", "Nimal", "Sanduni"];

function LoginScreen({ onLogin }) {
  const [name, setName] = useState("");
  const [err,  setErr]  = useState("");

  const submit = (n) => {
    const v = (n || name).trim();
    if (!v) { setErr("Please enter your name."); return; }
    onLogin(v);
  };

  return (
    <div style={{ display:"flex", alignItems:"center", justifyContent:"center", height:"100dvh", background:"transparent" }}>
      <div className="glass-panel" style={{ width:380, borderRadius:24, boxShadow:"0 8px 40px rgba(0,0,0,0.10)", padding:"44px 40px", animation:"fadeUp .4s cubic-bezier(0.32,0.72,0,1)" }}>
        <div style={{ display:"flex", alignItems:"center", gap:12, marginBottom:32 }}>
          <div style={{ width:40, height:40, borderRadius:12, background:C.accent, display:"flex", alignItems:"center", justifyContent:"center", fontSize:19, color:"#fff", fontWeight:700, boxShadow:`0 4px 12px ${C.accent}50` }}>K</div>
          <div>
            <div style={{ fontFamily:"var(--serif)", fontSize:18, fontStyle:"italic", color:C.gold }}>Kapruka</div>
            <div style={{ fontSize:9, color:C.tx3, fontFamily:"var(--mono)", letterSpacing:2 }}>GIFT CONCIERGE</div>
          </div>
        </div>
        <div style={{ fontSize:22, fontWeight:700, color:C.tx, marginBottom:7 }}>Welcome back</div>
        <div style={{ fontSize:14, color:C.tx3, marginBottom:28, lineHeight:1.6 }}>Enter your name to start or resume your session.</div>
        <div style={{ display:"flex", gap:6, flexWrap:"wrap", marginBottom:16 }}>
          {PRESET_USERS.map(u => (
            <button key={u} onClick={() => submit(u)}
              style={{ padding:"6px 14px", borderRadius:8, fontSize:13, fontWeight:500, background:C.bgSub, color:C.tx2, border:`1px solid ${C.bd}`, cursor:"pointer", transition:"all .15s" }}
              onMouseEnter={e => { e.target.style.borderColor=C.accent; e.target.style.color=C.accent; e.target.style.background=`${C.accent}08`; }}
              onMouseLeave={e => { e.target.style.borderColor=C.bd; e.target.style.color=C.tx2; e.target.style.background=C.bgSub; }}
            >{u}</button>
          ))}
        </div>
        <div style={{ display:"flex", gap:8 }}>
          <input
            value={name}
            onChange={e => { setName(e.target.value); setErr(""); }}
            onKeyDown={e => e.key === "Enter" && submit()}
            placeholder="Or type your name…"
            style={{ flex:1, padding:"11px 15px", borderRadius:10, border:`1.5px solid ${err ? C.r : C.bd2}`, fontSize:14, color:C.tx, background:C.bg, outline:"none", fontFamily:"var(--sans)", transition:"border-color .2s" }}
            onFocus={e => e.target.style.borderColor = C.accent}
            onBlur={e  => e.target.style.borderColor = err ? C.r : C.bd2}
            autoFocus
          />
          <button onClick={() => submit()}
            style={{ padding:"11px 20px", borderRadius:10, background:C.accent, color:"#fff", fontSize:14, fontWeight:600, border:"none", cursor:"pointer", boxShadow:`0 2px 10px ${C.accent}40`, transition:"opacity .15s" }}
            onMouseEnter={e => e.target.style.opacity=".85"}
            onMouseLeave={e => e.target.style.opacity="1"}
          >Start →</button>
        </div>
        {err && <div style={{ fontSize:13, color:C.r, marginTop:8 }}>{err}</div>}
        <div style={{ marginTop:26, paddingTop:22, borderTop:`1px solid ${C.bd}`, fontSize:12, color:C.tx3, lineHeight:1.65 }}>
          Each name gets its own session — searches, preferences, and history are saved per session.
        </div>
      </div>
    </div>
  );
}

// ── Onboarding Screen ──────────────────────────────────────────────────────────
function OnboardingScreen({ user, onComplete }) {
  const [surfaces, dispatch] = useReducer(a2uiReducer, {});

  useEffect(() => {
    buildOnboardingSurface().forEach(line => dispatchJSONL(line, dispatch));
  }, []);

  const mergeDM = useCallback((data) => {
    dispatch({ type:"MERGE", sid:"onboarding_surface", data });
  }, []);

  const handleComplete = useCallback(async (profile) => {
    localStorage.setItem(`kc_profile_${user.toLowerCase().replace(/\s+/g,"_")}`, JSON.stringify(profile));
    try {
      await fetch("/api/profile", {
        method:"POST", headers:{ "Content-Type":"application/json" }, body:JSON.stringify(profile),
      });
    } catch (_) {}
    onComplete(profile);
  }, [user, onComplete]);

  return (
    <OnboardingContext.Provider value={{ mergeDM, onComplete:handleComplete }}>
      <div style={{ display:"flex", alignItems:"flex-start", justifyContent:"center", minHeight:"100dvh", background:"transparent", padding:"44px 20px" }}>
        <div style={{ width:"100%", maxWidth:600 }}>
          <div style={{ display:"flex", alignItems:"center", gap:12, marginBottom:40 }}>
            <div style={{ width:38, height:38, borderRadius:11, background:C.accent, display:"flex", alignItems:"center", justifyContent:"center", fontSize:18, color:"#fff", fontWeight:700, boxShadow:`0 4px 12px ${C.accent}50` }}>K</div>
            <div>
              <div style={{ fontFamily:"var(--serif)", fontSize:17, fontStyle:"italic", color:C.gold }}>Kapruka</div>
              <div style={{ fontSize:9, color:C.tx3, fontFamily:"var(--mono)", letterSpacing:2 }}>GIFT CONCIERGE</div>
            </div>
            <div style={{ marginLeft:"auto", fontSize:14, color:C.tx3 }}>
              Hi, <span style={{ fontWeight:600, color:C.tx2 }}>{user}</span>
            </div>
          </div>
          <div className="glass-panel" style={{ borderRadius:22, padding:"40px", animation:"fadeUp .4s cubic-bezier(0.32,0.72,0,1)" }}>
            <SurfaceView surface={surfaces["onboarding_surface"]} style={{}} />
          </div>
          <div style={{ textAlign:"center", marginTop:18, fontSize:12, color:C.tx3 }}>
            You can update preferences anytime by telling the concierge.
          </div>
        </div>
      </div>
    </OnboardingContext.Provider>
  );
}

// ── Helpers ────────────────────────────────────────────────────────────────────
function _profileKey(user) { return `kc_profile_${user.toLowerCase().replace(/\s+/g,"_")}`; }
function _loadProfile(user) {
  try { const r = localStorage.getItem(_profileKey(user)); return r ? JSON.parse(r) : null; } catch (_) { return null; }
}
function _generateSuggestions(profile) {
  const items = [];
  if (profile.preferences?.[0]) items.push(`${profile.preferences[0]} for ${profile.recipient}`);
  if (profile.preferences?.[1]) items.push(`${profile.preferences[1]} gift ideas`);
  if (profile.allergies?.[0])   items.push(`No-${profile.allergies[0]} gifts`);
  if (profile.district)         items.push(`Deliver to ${profile.district}?`);
  if (!items.length)            items.push(`Gift ideas for ${profile.recipient}`);
  return items.slice(0, 4);
}

// ── Main App ───────────────────────────────────────────────────────────────────
export default function App() {
  const [user,    setUser]    = useState(() => localStorage.getItem("kc_user") || null);
  const [profile, setProfile] = useState(() => { const u = localStorage.getItem("kc_user"); return u ? _loadProfile(u) : null; });

  const handleLogin = (name) => { localStorage.setItem("kc_user", name); setUser(name); setProfile(_loadProfile(name)); };
  const handleLogout = () => { localStorage.removeItem("kc_user"); setUser(null); setProfile(null); };

  if (!user) return <LoginScreen onLogin={handleLogin} />;
  if (!profile) return <OnboardingScreen user={user} onComplete={(p) => setProfile(p)} />;
  return <ConciergeApp user={user} profile={profile} onLogout={handleLogout} />;
}

function ConciergeApp({ user, profile, onLogout }) {
  const [surfaces,    dispatch]  = useReducer(a2uiReducer, {});
  const [chatHistory, setChat]   = useState([{
    role:"assistant",
    content:`Ayubowan! I'm your Kapruka gift concierge.\n\nI have ${profile.recipient}'s profile ready — I know their allergies and preferences. What's the occasion?`,
  }]);
  const [input,    setInput]   = useState("");
  const [loading,  setLoading] = useState(false);
  const [selected, setSelected]= useState(null);

  const sessionId  = useRef(`session_${user.toLowerCase().replace(/\s+/g,"_")}`);
  const chatEndRef = useRef(null);
  const esRef      = useRef(null);

  const suggestions = _generateSuggestions(profile);
  const hasUserMsg  = chatHistory.some(m => m.role === "user");

  useEffect(() => {
    buildSurfaces(profile).forEach(line => dispatchJSONL(line, dispatch));
  }, []);

  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior:"smooth" }); }, [chatHistory]);

  useEffect(() => {
    const dm = surfaces["chat_surface"]?.dm || {};
    if (dm.response && loading) {
      setChat(prev => [...prev, { role:"assistant", content:dm.response }]);
      dispatch({ type:"MERGE", sid:"chat_surface", data:{ response:"", thinking:false } });
      setLoading(false);
      if (esRef.current) { esRef.current.close(); esRef.current = null; }
    }
  }, [surfaces, loading]);

  const notifDM = surfaces["notification_surface"]?.dm || {};
  const chatDM  = surfaces["chat_surface"]?.dm         || {};

  const sendMessage = useCallback(() => {
    const msg = input.trim();
    if (!msg || loading) return;
    setInput(""); setLoading(true);
    setChat(prev => [...prev, { role:"user", content:msg }]);
    dispatch({ type:"MERGE", sid:"agent_surface",        data:{ ph_r:"idle", ph_s:"idle", ph_ref:"idle", ph_d:"idle", route:"", rf1:"idle", rf2:"idle", rf3:"idle", prod_name:"", delivery_district:"" } });
    dispatch({ type:"MERGE", sid:"gallery_surface",      data:{ products:[] } });
    dispatch({ type:"MERGE", sid:"chat_surface",         data:{ thinking:true, thinking_label:"Thinking...", response:"" } });
    dispatch({ type:"MERGE", sid:"notification_surface", data:{ toast_visible:false } });
    dispatch({ type:"MERGE", sid:"memory_surface",       data:{ st_active:true, st_label:"Writing..." } });

    const url = `/stream?session_id=${sessionId.current}&message=${encodeURIComponent(msg)}&recipient=${encodeURIComponent(profile.recipient)}`;
    const es  = new EventSource(url);
    esRef.current = es;
    es.onmessage = e => {
      const d = e.data || "";
      if (!d || d.trim() === "" || d.trim() === ": done") return;
      dispatchJSONL(d, dispatch);
    };
    es.onerror = () => {
      es.close(); esRef.current = null; setLoading(false);
      dispatch({ type:"MERGE", sid:"chat_surface",  data:{ thinking:false } });
      dispatch({ type:"MERGE", sid:"memory_surface",data:{ st_active:false } });
    };
  }, [input, loading, profile.recipient]);

  const handleKey = e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); } };

  const placeholder = `Gift for ${profile.recipient}${profile.district ? ` in ${profile.district}` : ""}…`;
  const budgetLabel = profile.budget_lkr ? `Rs.${Number(profile.budget_lkr).toLocaleString()}` : null;

  return (
    <GallerySelectContext.Provider value={setSelected}>
    <div style={{ display:"flex", flexDirection:"column", height:"100dvh", background:"transparent", overflow:"hidden" }}>

      <header style={{
        flexShrink:0, height:80,
        display:"flex", alignItems:"center", padding:"0 32px", gap:16, zIndex:10,
        background: "transparent",
      }}>
        <div style={{ position:"relative", display:"flex", flexShrink:0 }}>
          <div style={{ width:48, height:48, borderRadius:"50%", background:C.accent, overflow:"hidden", display:"flex", alignItems:"center", justifyContent:"center", color:"#fff", fontSize:20, fontWeight:700 }}>
             <img src={kaprukaLogo} alt="Kapruka" style={{width:"100%", height:"100%", objectFit:"cover"}} />
          </div>
          <div style={{ position:"absolute", bottom:0, right:0, width:14, height:14, borderRadius:"50%", background:C.g, border:`2.5px solid ${C.bg}` }} />
        </div>
        <div style={{ display:"flex", flexDirection:"column", justifyContent:"center" }}>
          <div style={{ fontSize:19, fontWeight:600, color:C.tx, letterSpacing:"-0.3px", lineHeight:1.2 }}>Kapruka Concierge</div>
          <div style={{ fontSize:14, color:C.tx3, display:"flex", alignItems:"center", gap:6, fontWeight:500 }}>
            <span style={{ width:6, height:6, borderRadius:"50%", background:C.g }} /> Online
          </div>
        </div>
        <div style={{ marginLeft:"auto", flexShrink:0, display:"flex", alignItems:"center", gap:12 }}>
           <div style={{ width:44, height:44, borderRadius:"50%", background:"#fff", display:"flex", alignItems:"center", justifyContent:"center", fontWeight:600, fontSize:15, boxShadow:"0 2px 12px rgba(0,0,0,0.06)", border:`1px solid ${C.bd}` }}>{user[0].toUpperCase()}</div>
        </div>
      </header>

      {/* ── BODY ────────────────────────────────────────────────────────────── */}
      <div style={{ flex:1, display:"flex", overflow:"hidden" }}>

        {/* LEFT: Chat */}
        <main style={{ flex:1, display:"flex", flexDirection:"column", overflow:"hidden", minWidth:0, background:"transparent" }}>

          {/* Messages */}
          <div style={{ flex:1, overflowY:"auto", padding:"28px 28px 16px" }}>
            {chatHistory.map((msg, i) =>
              i === 0 && msg.role === "assistant"
                ? <HeroWelcome key={i} content={msg.content} />
                : <ChatBubble  key={i} msg={msg} />
            )}

            {/* Empty state — quick-action grid */}
            {!hasUserMsg && !loading && (
              <QuickActions profile={profile} onSelect={setInput} />
            )}

            {chatDM.thinking && <ThinkingDots active label={chatDM.thinking_label} />}
            <div ref={chatEndRef} />
          </div>

          {/* Gallery */}
          <SurfaceView
            surface={surfaces["gallery_surface"]}
            style={{ flexShrink:0, padding:"0 28px 14px", background:"transparent" }}
          />

          {/* Suggestion chips */}
          <div style={{ flexShrink:0, padding:"0 28px 12px", display:"flex", gap:7, flexWrap:"nowrap", overflowX:"auto", background:"transparent" }}>
            {suggestions.map((s,i) => (
              <button key={i} onClick={() => setInput(s)}
                style={{
                  flexShrink:0, display:"flex", alignItems:"center", gap:6,
                  padding:"8px 16px", borderRadius:99, fontSize:13, fontWeight:500,
                  background:"#FFFFFF", color:"#374151", border:`1px solid #E5E7EB`,
                  cursor:"pointer", transition:"all .2s", whiteSpace:"nowrap",
                  boxShadow:"0 2px 8px rgba(0,0,0,0.04)",
                }}
                onMouseEnter={e => { e.currentTarget.style.borderColor = "#0B0B0B"; e.currentTarget.style.color = "#0B0B0B"; }}
                onMouseLeave={e => { e.currentTarget.style.borderColor = "#E5E7EB"; e.currentTarget.style.color = "#374151"; }}
              >
                {s}
              </button>
            ))}
          </div>

          {/* Input */}
          <div style={{ flexShrink:0, padding:"0 32px 32px", background:"transparent" }}>
            <div
              style={{ display:"flex", alignItems:"center", gap:16, padding:"12px 12px 12px 24px", borderRadius:40, background:"#FFFFFF", boxShadow:"0 8px 32px rgba(0,0,0,0.06)", border:"1px solid rgba(0,0,0,0.03)", transition:"box-shadow .2s" }}
            >
              <textarea
                rows={1} value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKey}
                placeholder="Write a Message..."
                maxLength={500}
                style={{ flex:1, resize:"none", background:"transparent", border:"none", fontSize:15, color:"#0B0B0B", padding:"4px 0", fontFamily:"var(--sans)" }}
              />
              <button onClick={sendMessage} disabled={loading || !input.trim()} style={{
                width:44, height:44, borderRadius:"50%", flexShrink:0,
                background: (loading || !input.trim()) ? "#F3F4F6" : "#0B0B0B",
                color:      (loading || !input.trim()) ? "#9CA3AF" : "#FFFFFF",
                display:"flex", alignItems:"center", justifyContent:"center",
                transition: "all .2s", cursor: (loading || !input.trim()) ? "not-allowed" : "pointer",
              }}>
                {loading
                  ? <span style={{ width:16, height:16, borderRadius:"50%", border:`2px solid #9CA3AF`, borderTopColor:"transparent", animation:"spin .8s linear infinite", display:"inline-block" }} />
                  : <span style={{ fontSize:18 }}>➤</span>
                }
              </button>
            </div>
          </div>
        </main>

        {/* RIGHT: sidebar */}
        <aside style={{
          width:280, flexShrink:0,
          background:"#FFFFFF",
          borderRadius: 24,
          margin:"0 32px 32px 0",
          boxShadow:"0 8px 32px rgba(0,0,0,0.04)",
          border:`1px solid ${C.bd}`,
          overflowY:"auto", padding:"32px 24px",
          display:"flex", flexDirection:"column", gap:32,
        }}>
          <div>
            <SLabel>Live Agent</SLabel>
            <SurfaceView surface={surfaces["agent_surface"]} />
          </div>
          <div style={{ height:1, background:C.sideBd }} />
          <div>
            <SLabel>Memory</SLabel>
            <SurfaceView surface={surfaces["memory_surface"]} />
          </div>
        </aside>
      </div>

      {selected && <ProductModal product={selected} onClose={() => setSelected(null)} />}
      <NotificationToast text={notifDM.toast_text} visible={notifDM.toast_visible} />
    </div>
    </GallerySelectContext.Provider>
  );
}
