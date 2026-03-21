import { useReducer, useState, useEffect, useRef, useCallback } from "react";
import { a2uiReducer, dispatchJSONL } from "./a2ui/engine";

// ─────────────────────────────────────────────────────────────────────────────
// Design tokens (mirrored from CSS vars for inline styles)
// ─────────────────────────────────────────────────────────────────────────────
const C = {
  bg:    "#050810", bg1:"#080C18", bg2:"#0D1220", bg3:"#141A2E",
  bd:    "rgba(255,255,255,0.06)", bd2:"rgba(255,255,255,0.10)",
  gold:  "#C9953A", goldL:"#F0B84A",
  tx:    "#E8DFD0", tx2:"#8A8FA8",
  g:     "#22C55E", r:"#EF4444", b:"#60A5FA", p:"#A78BFA", y:"#F59E0B",
};

const PROFILES = {
  Wife:   { allergies:["nuts","shellfish"], preferences:["dark chocolate","flowers","spa"],   district:"Colombo", budget:"Rs.5,000"  },
  Mother: { allergies:["gluten"],           preferences:["fruit baskets","tea"],              district:"Kandy",   budget:"Rs.3,000"  },
  Friend: { allergies:[],                   preferences:["electronics","books"],              district:"Galle",   budget:"Rs.15,000" },
};

const SUGGESTIONS = {
  Wife:   ["Dark chocolate gift box under Rs.3000", "Spa & wellness hamper", "Flowers + cake combo"],
  Mother: ["Fruit basket for Kandy delivery", "Premium tea collection", "Birthday cake under Rs.2000"],
  Friend: ["Latest tech gadget under Rs.10000", "Books + coffee hamper", "Do you deliver to Galle?"],
};

// ─────────────────────────────────────────────────────────────────────────────
// A2UI init helpers
// ─────────────────────────────────────────────────────────────────────────────
const mkDM = (sid, data) => JSON.stringify({ type:"dataModelUpdate", surfaceId:sid, data });
const mkBR = (sid, root) => JSON.stringify({ type:"beginRendering",  surfaceId:sid, root });
const mkSU = (sid, comps) => JSON.stringify({ type:"surfaceUpdate",  surfaceId:sid, components:comps });
const c    = (id, type, props={}) => ({ id, type, props });

function buildSurfaces(rec) {
  const p = PROFILES[rec] || PROFILES.Wife;
  const lines = [];

  // agent_surface
  lines.push(mkSU("agent_surface", [
    c("root","Column",{ gap:6, children:["ag_pipe","ag_route","ag_refl","ag_delivery","ag_prod"] }),
    c("ag_pipe","PipelinePanel",{}),
    c("ag_route","RouteChip",{ route:{path:"/route"} }),
    c("ag_refl","ReflectionPanel",{}),
    c("ag_delivery","DeliveryBadge",{ feasible:{path:"/delivery_feasible"}, district:{path:"/delivery_district"}, days:{path:"/delivery_days"} }),
    c("ag_prod","MiniProductCard",{ name:{path:"/prod_name"}, price:{path:"/prod_price"}, image:{path:"/prod_image"}, tags:{path:"/prod_tags"} }),
  ]));
  lines.push(mkDM("agent_surface", {
    ph_r:"idle", ph_s:"idle", ph_ref:"idle", ph_d:"idle",
    route:"", confidence:0, recipient:"",
    rf1:"idle", rf2:"idle", rf3:"idle", rf1_active:false,
    prod_name:"", prod_price:"", prod_image:"", prod_safe:true, prod_tags:[],
    delivery_feasible:false, delivery_district:"", delivery_days:"",
  }));
  lines.push(mkBR("agent_surface","root"));

  // memory_surface
  lines.push(mkSU("memory_surface", [
    c("root","Column",{ gap:5, children:["m_st","m_lt","m_sem","m_found"] }),
    c("m_st","MemoryChip",  { label:{literalString:"Short-Term"},   sublabel:{path:"/st_label"},  active:{path:"/st_active"},  tier:{literalString:"st"}       }),
    c("m_lt","MemoryChip",  { label:{literalString:"LT-RAG"},       sublabel:{literalString:"Qdrant"},  active:{path:"/lt_active"},  tier:{literalString:"ltrag"}    }),
    c("m_sem","MemoryChip", { label:{literalString:"Semantic"},     sublabel:{literalString:"Profiles"},active:{path:"/sem_active"}, tier:{literalString:"semantic"} }),
    c("m_found","ProfileData",{ allergies:{path:"/allergies"}, preferences:{path:"/preferences"}, district:{path:"/district"}, active:{path:"/sem_active"} }),
  ]));
  lines.push(mkDM("memory_surface", {
    st_active:false, st_label:"Idle", lt_active:false, sem_active:false,
    allergies:p.allergies, preferences:p.preferences, district:p.district,
  }));
  lines.push(mkBR("memory_surface","root"));

  // gallery_surface — flat keys for g0..g3
  const galDM = {};
  ["g0","g1","g2","g3"].forEach(k => {
    galDM[`${k}_name`]=""; galDM[`${k}_price`]=""; galDM[`${k}_image`]="";
    galDM[`${k}_rating`]=""; galDM[`${k}_safe`]=true; galDM[`${k}_visible`]=false;
  });
  lines.push(mkDM("gallery_surface", galDM));

  // chat_surface
  lines.push(mkDM("chat_surface", { thinking:false, thinking_label:"Thinking...", response:"" }));

  // notification_surface
  lines.push(mkDM("notification_surface", { toast_text:"", toast_visible:false }));

  return lines;
}

// ─────────────────────────────────────────────────────────────────────────────
// Micro-components
// ─────────────────────────────────────────────────────────────────────────────

function Orb({ style }) {
  return <div style={{ position:"absolute", borderRadius:"50%", filter:"blur(80px)", pointerEvents:"none", ...style }} />;
}

function PhaseRow({ label, status, icon }) {
  const s = { idle: C.tx2, active: C.y, done: C.g, error: C.r }[status] || C.tx2;
  return (
    <div style={{ display:"flex", alignItems:"center", gap:8, padding:"4px 0" }}>
      <div style={{
        width:6, height:6, borderRadius:"50%", flexShrink:0,
        background: status==="idle" ? "transparent" : s,
        border: status==="idle" ? `1px solid ${C.tx2}` : "none",
        boxShadow: status==="active" ? `0 0 10px ${s}` : "none",
        animation: status==="active" ? "pulse 1s infinite" : "none",
        transition: "all .4s cubic-bezier(0.32,0.72,0,1)",
      }} />
      <span style={{ fontSize:11, fontFamily:"var(--mono)", color:s, transition:"color .3s", fontWeight: status==="active" ? 600 : 400 }}>
        {icon} {label}
      </span>
    </div>
  );
}

function PipelinePanel({ dm = {} }) {
  return (
    <div>
      <div style={{ fontSize:9, fontFamily:"var(--mono)", color:C.gold, letterSpacing:3, textTransform:"uppercase", marginBottom:8 }}>Pipeline</div>
      <PhaseRow label="Route"   status={dm.ph_r   || "idle"} icon="◈" />
      <PhaseRow label="Search"  status={dm.ph_s   || "idle"} icon="◎" />
      <PhaseRow label="Reflect" status={dm.ph_ref || "idle"} icon="◉" />
      <PhaseRow label="Done"    status={dm.ph_d   || "idle"} icon="◆" />
    </div>
  );
}

function ReflectionPanel({ dm = {} }) {
  const rf1 = dm.rf1 || "idle";
  const rf2 = dm.rf2 || "idle";
  const rf3 = dm.rf3 || "idle";
  if (rf1 === "idle" && rf2 === "idle" && rf3 === "idle") return null;
  return (
    <div style={{ animation:"fadeIn .3s" }}>
      <div style={{ fontSize:9, fontFamily:"var(--mono)", color:C.p, letterSpacing:3, textTransform:"uppercase", marginBottom:6 }}>Reflection</div>
      {[["Draft",rf1,"①"],[" Verify",rf2,"②"],["Revise",rf3,"③"]].map(([lbl,st,n]) => (
        <PhaseRow key={lbl} label={lbl} status={st} icon={n} />
      ))}
    </div>
  );
}

function RouteChip({ dm = {} }) {
  const route = dm.route || "";
  if (!route) return null;
  const map = {
    SEARCH_CATALOG:   { label:"Catalog Agent",   color:C.p,    icon:"◈" },
    CHECK_LOGISTICS:  { label:"Logistics Agent", color:"#2DD4BF", icon:"⬡" },
    UPDATE_PREFERENCE:{ label:"Profile Update",  color:C.gold,  icon:"◎" },
    CHITCHAT:         { label:"Conversation",    color:C.b,    icon:"◇" },
    CLARIFICATION:    { label:"Clarifying",      color:C.y,    icon:"?" },
    ORDER_HISTORY:    { label:"Order History",   color:C.tx2,  icon:"▣" },
  };
  const m = map[route];
  if (!m) return null;
  return (
    <div style={{
      display:"inline-flex", alignItems:"center", gap:6,
      padding:"4px 10px", borderRadius:6,
      background:`${m.color}12`, border:`1px solid ${m.color}30`,
      fontSize:10, color:m.color, fontFamily:"var(--mono)",
      animation:"fadeIn .3s",
    }}>
      {m.icon} {m.label}
      {dm.confidence ? <span style={{ color:C.tx2, fontSize:9 }}>· {Math.round(dm.confidence * 100)}%</span> : null}
    </div>
  );
}

function DeliveryBadge({ dm = {} }) {
  const dist = dm.delivery_district || "";
  if (!dist) return null;
  const ok = dm.delivery_feasible;
  return (
    <div style={{
      display:"inline-flex", alignItems:"center", gap:5,
      padding:"4px 10px", borderRadius:6,
      background: ok ? `${C.g}10` : `${C.r}10`,
      border:`1px solid ${ok ? C.g+"30" : C.r+"30"}`,
      fontSize:10, color: ok ? C.g : C.r, fontFamily:"var(--mono)",
      animation:"fadeIn .3s",
    }}>
      {ok ? "↑" : "✕"} {dist}{dm.delivery_days ? ` · ${dm.delivery_days}` : ""}
    </div>
  );
}

function MiniProductCard({ dm = {} }) {
  const nm = dm.prod_name || "";
  if (!nm) return null;
  const img = dm.prod_image || "";
  return (
    <div style={{
      display:"flex", gap:8, alignItems:"center",
      padding:"8px 10px", borderRadius:8,
      background:C.bg3, border:`1px solid ${C.bd2}`,
      animation:"slideDown .4s cubic-bezier(0.32,0.72,0,1)",
    }}>
      {img
        ? <img src={`/api/image?url=${encodeURIComponent(img)}`} alt="" style={{ width:36, height:36, borderRadius:5, objectFit:"cover", flexShrink:0 }} />
        : <div style={{ width:36, height:36, borderRadius:5, background:C.bg, display:"flex", alignItems:"center", justifyContent:"center", fontSize:16, flexShrink:0 }}>◈</div>
      }
      <div style={{ minWidth:0 }}>
        <div style={{ fontSize:11, color:C.tx, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap", fontFamily:"var(--sans)" }}>{nm}</div>
        {dm.prod_price && <div style={{ fontSize:10, color:C.gold, fontFamily:"var(--mono)" }}>LKR {Number(dm.prod_price).toLocaleString()}</div>}
      </div>
    </div>
  );
}

function MemoryChip({ label, sublabel, active, tier, dm = {} }) {
  const rv  = (bv) => bv?.path ? (dm[bv.path.replace(/^\//,"")] ?? null) : (bv?.literalString ?? bv);
  const lbl = rv(label) ?? "";
  const sub = rv(sublabel) ?? "";
  const act = rv(active)   ?? false;
  const tr  = rv(tier)     ?? "st";
  const colorMap = { st:C.b, ltrag:C.p, semantic:C.g };
  const iconMap  = { st:"●", ltrag:"■", semantic:"▲" };
  const col = colorMap[tr] || C.b;
  return (
    <div style={{
      display:"flex", alignItems:"center", gap:8, padding:"7px 9px",
      borderRadius:7, border:`1px solid ${act ? col+"44" : C.bd}`,
      background: act ? `${col}09` : C.bg2,
      boxShadow: act ? `0 0 16px ${col}22` : "none",
      transition:"all .4s cubic-bezier(0.32,0.72,0,1)",
    }}>
      <span style={{ fontSize:9, color: act ? col : C.tx2, transition:"color .3s" }}>{iconMap[tr]}</span>
      <div style={{ flex:1, minWidth:0 }}>
        <div style={{ fontSize:10, color: act ? C.tx : C.tx2, fontFamily:"var(--sans)", fontWeight:500, transition:"color .3s" }}>{lbl}</div>
        <div style={{ fontSize:9, color: act ? col : C.tx2, fontFamily:"var(--mono)", overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap", transition:"color .3s" }}>{sub}</div>
      </div>
      {act && <div style={{ width:5, height:5, borderRadius:"50%", background:col, animation:"pulse 1.2s infinite", flexShrink:0 }} />}
    </div>
  );
}

function ProfileData({ allergies, preferences, district, active, dm = {} }) {
  const rv  = (bv) => bv?.path ? (dm[bv.path.replace(/^\//,"")] ?? null) : (bv?.literalString ?? bv);
  const alg = rv(allergies)   ?? [];
  const prf = rv(preferences) ?? [];
  const dst = rv(district)    ?? "";
  const act = rv(active)      ?? false;
  if (!alg.length && !prf.length && !dst) return null;
  return (
    <div style={{
      overflow:"hidden",
      maxHeight: act ? 160 : 0,
      opacity:   act ? 1 : 0,
      transition:"max-height .45s cubic-bezier(0.32,0.72,0,1), opacity .3s",
    }}>
      <div style={{ padding:"9px 10px", borderRadius:7, border:`1px solid ${C.g}25`, background:`${C.g}07`, marginTop:2 }}>
        <div style={{ fontSize:9, color:C.g, fontFamily:"var(--mono)", letterSpacing:2, marginBottom:6 }}>PROFILE ACTIVE</div>
        <div style={{ display:"flex", flexWrap:"wrap", gap:3 }}>
          {alg.map((a,i) => <span key={i} style={{ padding:"2px 7px", borderRadius:99, fontSize:9, background:`${C.r}15`, color:C.r, border:`1px solid ${C.r}25`, fontFamily:"var(--mono)" }}>! {a}</span>)}
          {prf.map((p,i) => <span key={i} style={{ padding:"2px 7px", borderRadius:99, fontSize:9, background:`${C.g}10`, color:C.g, border:`1px solid ${C.g}20`, fontFamily:"var(--mono)" }}>+ {p}</span>)}
        </div>
        {dst && <div style={{ fontSize:9, color:C.tx2, fontFamily:"var(--mono)", marginTop:5 }}>loc: {dst}</div>}
      </div>
    </div>
  );
}

function ThinkingDots({ active, label }) {
  if (!active) return null;
  return (
    <div style={{ display:"flex", alignItems:"center", gap:10, padding:"12px 16px" }}>
      <div style={{ display:"flex", gap:5 }}>
        {[0,1,2].map(i => (
          <div key={i} style={{ width:7, height:7, borderRadius:"50%", background:C.gold, animation:`pulse 1.4s ease ${i*0.18}s infinite` }} />
        ))}
      </div>
      <span style={{ fontSize:11, color:C.tx2, fontFamily:"var(--mono)" }}>{label || "Thinking..."}</span>
    </div>
  );
}

function ProductCard({ product, onClick }) {
  const [hover, setHov] = useState(false);
  const img  = product.image_url || (product.image_urls || [])[0] || "";
  const name = product.name || "";
  const price= product.price;
  const tags = (product.tags || []).slice(0,3);
  const rating = product.rating;

  return (
    <div
      onClick={() => onClick && onClick(product)}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        flexShrink:0, width:160,
        borderRadius:12, overflow:"hidden",
        border:`1px solid ${hover ? C.gold+"55" : C.bd}`,
        background:C.bg2,
        cursor:"pointer",
        transform: hover ? "translateY(-3px) scale(1.02)" : "translateY(0) scale(1)",
        boxShadow: hover ? `0 8px 32px rgba(0,0,0,.5), 0 0 0 1px ${C.gold}22` : `0 2px 8px rgba(0,0,0,.3)`,
        transition:"all .3s cubic-bezier(0.32,0.72,0,1)",
        animation:"fadeUp .4s cubic-bezier(0.32,0.72,0,1)",
      }}
    >
      {/* Image */}
      <div style={{ height:100, background:C.bg3, overflow:"hidden", position:"relative" }}>
        {img
          ? <img src={`/api/image?url=${encodeURIComponent(img)}`} alt={name} style={{ width:"100%", height:"100%", objectFit:"cover" }} />
          : <div style={{ width:"100%", height:"100%", display:"flex", alignItems:"center", justifyContent:"center", fontSize:28, color:C.gold, opacity:0.5 }}>◈</div>
        }
        {tags.length > 0 && (
          <div style={{ position:"absolute", bottom:5, left:5, display:"flex", gap:3, flexWrap:"wrap" }}>
            {tags.map((t,i) => (
              <span key={i} style={{ padding:"1px 5px", borderRadius:3, fontSize:8, background:"rgba(0,0,0,.7)", color:C.gold, fontFamily:"var(--mono)" }}>{t}</span>
            ))}
          </div>
        )}
      </div>
      {/* Info */}
      <div style={{ padding:"8px 9px" }}>
        <div style={{ fontSize:11, color:C.tx, fontWeight:500, marginBottom:4, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{name}</div>
        <div style={{ fontSize:12, color:C.gold, fontFamily:"var(--mono)", fontWeight:600 }}>
          {price ? `Rs. ${Number(price).toLocaleString()}` : "—"}
        </div>
        {rating && (
          <div style={{ fontSize:9, color:C.y, marginTop:3 }}>
            {"★".repeat(Math.round(rating))}{"☆".repeat(5-Math.round(rating))}
          </div>
        )}
      </div>
    </div>
  );
}

function ProductModal({ product, onClose }) {
  if (!product) return null;
  const img  = product.image_url || (product.image_urls || [])[0] || "";
  const name = product.name || "";
  const price= product.price;
  const desc = product.description || "";
  const tags = product.tags || [];
  const rating = product.rating;
  const url  = product.url || "";

  return (
    <div
      onClick={onClose}
      style={{
        position:"fixed", inset:0, zIndex:1000,
        background:"rgba(5,8,16,.85)", backdropFilter:"blur(12px)",
        display:"flex", alignItems:"center", justifyContent:"center",
        animation:"fadeIn .2s",
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          width:340, borderRadius:16, overflow:"hidden",
          background:C.bg2, border:`1px solid ${C.bd2}`,
          boxShadow:"0 32px 64px rgba(0,0,0,.8)",
          animation:"slideUp .35s cubic-bezier(0.32,0.72,0,1)",
        }}
      >
        {/* Image */}
        <div style={{ height:200, background:C.bg3, position:"relative" }}>
          {img
            ? <img src={`/api/image?url=${encodeURIComponent(img)}`} alt={name} style={{ width:"100%", height:"100%", objectFit:"cover" }} />
            : <div style={{ width:"100%", height:"100%", display:"flex", alignItems:"center", justifyContent:"center", fontSize:48, color:C.gold, opacity:0.4 }}>◈</div>
          }
          {/* Close */}
          <button onClick={onClose} style={{
            position:"absolute", top:10, right:10, width:28, height:28, borderRadius:"50%",
            background:"rgba(0,0,0,.6)", color:C.tx, fontSize:14,
            display:"flex", alignItems:"center", justifyContent:"center",
          }}>✕</button>
        </div>
        {/* Details */}
        <div style={{ padding:"16px 18px" }}>
          {/* Tags */}
          <div style={{ display:"flex", flexWrap:"wrap", gap:4, marginBottom:10 }}>
            {tags.map((t,i) => <span key={i} style={{ padding:"2px 7px", borderRadius:4, fontSize:9, background:C.bg3, color:C.gold, border:`1px solid ${C.gold}30`, fontFamily:"var(--mono)" }}>{t}</span>)}
          </div>
          <div style={{ fontSize:15, fontWeight:600, color:C.tx, marginBottom:6, lineHeight:1.4 }}>{name}</div>
          <div style={{ fontSize:18, color:C.gold, fontFamily:"var(--mono)", fontWeight:700, marginBottom:8 }}>
            {price ? `LKR ${Number(price).toLocaleString()}` : "—"}
          </div>
          {rating && (
            <div style={{ fontSize:12, color:C.y, marginBottom:8 }}>
              {"★".repeat(Math.round(rating))}{"☆".repeat(5-Math.round(rating))}
              {product.review_count && <span style={{ color:C.tx2, fontSize:10, marginLeft:5 }}>({product.review_count})</span>}
            </div>
          )}
          {desc && desc.length < 200 && (
            <p style={{ fontSize:11, color:C.tx2, lineHeight:1.6, marginBottom:12 }}>{desc}</p>
          )}
          {url && (
            <a href={url} target="_blank" rel="noopener noreferrer" style={{
              display:"flex", alignItems:"center", justifyContent:"center", gap:6,
              padding:"10px", borderRadius:8, fontSize:12, fontWeight:600,
              background:`linear-gradient(135deg,${C.gold},${C.goldL})`,
              color:C.bg, transition:"opacity .2s",
            }}
            onMouseEnter={e=>e.currentTarget.style.opacity=".85"}
            onMouseLeave={e=>e.currentTarget.style.opacity="1"}
            >
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
    <div style={{
      position:"fixed", bottom:72, right:16, zIndex:2000,
      padding:"10px 16px", borderRadius:10,
      background:`linear-gradient(135deg,${C.gold},${C.goldL})`,
      color:C.bg, fontSize:12, fontWeight:600,
      boxShadow:"0 8px 32px rgba(0,0,0,.6)",
      animation:"slideUp .3s cubic-bezier(0.32,0.72,0,1)",
      maxWidth:260,
    }}>{text}</div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Recursive A2UI renderer — handles both flat (our format) and component format
// ─────────────────────────────────────────────────────────────────────────────
const WIDGET_MAP = {
  Column:          ({ children, gap=8 }) => <div style={{ display:"flex", flexDirection:"column", gap }}>{children}</div>,
  PipelinePanel,
  RouteChip:       ({ dm })  => <RouteChip dm={dm} />,
  ReflectionPanel: ({ dm })  => <ReflectionPanel dm={dm} />,
  DeliveryBadge:   ({ dm })  => <DeliveryBadge dm={dm} />,
  MiniProductCard: ({ dm })  => <MiniProductCard dm={dm} />,
  MemoryChip,
  ProfileData,
};

function RenderNode({ id, comps, dm }) {
  if (!id || !comps?.[id]) return null;
  const node = comps[id];
  const widgetType = node.type || node.widget || Object.keys(node.component || {})[0];
  const rawProps   = node.props || node.component?.[widgetType] || {};
  const Widget     = WIDGET_MAP[widgetType];
  if (!Widget) return null;

  const childIds = rawProps.children;
  let children = null;
  if (Array.isArray(childIds)) {
    children = childIds.map(cid => <RenderNode key={cid} id={cid} comps={comps} dm={dm} />);
  }

  const gapVal = typeof rawProps.gap === "number" ? rawProps.gap : 8;

  return <Widget {...rawProps} gap={gapVal} dm={dm}>{children}</Widget>;
}

function SurfaceView({ surface, style }) {
  if (!surface?.ready || !surface.root) return null;
  return <div style={style}><RenderNode id={surface.root} comps={surface.comps} dm={surface.dm} /></div>;
}

// ─────────────────────────────────────────────────────────────────────────────
// Main App
// ─────────────────────────────────────────────────────────────────────────────
export default function App() {
  const [surfaces,   dispatch]    = useReducer(a2uiReducer, {});
  const [chatHistory, setChat]    = useState([{
    role:"assistant",
    content:"Ayubowan. I'm your Kapruka gift concierge — I know your recipients' allergies and preferences. No dangerous recommendations, ever.\n\nWho are you gifting and what's the occasion?",
  }]);
  const [input,      setInput]    = useState("");
  const [loading,    setLoading]  = useState(false);
  const [recipient,  setRec]      = useState("Wife");
  const [selected,   setSelected] = useState(null);   // product modal

  const sessionId  = useRef("s_" + Date.now());
  const chatEndRef = useRef(null);
  const esRef      = useRef(null);

  // Init surfaces on recipient change
  useEffect(() => {
    buildSurfaces(recipient).forEach(line => dispatchJSONL(line, dispatch));
  }, [recipient]);

  // Auto-scroll
  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior:"smooth" }); }, [chatHistory]);

  // Watch for completed response (the fixed "response" key)
  useEffect(() => {
    const dm = surfaces["chat_surface"]?.dm || {};
    if (dm.response && loading) {
      setChat(prev => [...prev, { role:"assistant", content:dm.response }]);
      dispatch({ type:"MERGE", sid:"chat_surface", data:{ response:"", thinking:false } });
      setLoading(false);
      if (esRef.current) { esRef.current.close(); esRef.current = null; }
    }
  }, [surfaces, loading]);

  // Derive products from gallery_surface
  const galDM = surfaces["gallery_surface"]?.dm || {};
  const products = ["g0","g1","g2","g3"].reduce((acc, k) => {
    if (galDM[`${k}_visible`] && galDM[`${k}_name`]) {
      acc.push({
        name:  galDM[`${k}_name`],
        price: galDM[`${k}_price`],
        image_url: galDM[`${k}_image`],
        rating:galDM[`${k}_rating`],
        safe:  galDM[`${k}_safe`],
        _key:  k,
      });
    }
    return acc;
  }, []);

  const notifDM = surfaces["notification_surface"]?.dm || {};
  const chatDM  = surfaces["chat_surface"]?.dm || {};
  const profile = PROFILES[recipient] || PROFILES.Wife;

  const sendMessage = useCallback(() => {
    const msg = input.trim();
    if (!msg || loading) return;
    setInput(""); setLoading(true);
    setChat(prev => [...prev, { role:"user", content:msg }]);

    // Reset state
    dispatch({ type:"MERGE", sid:"agent_surface",       data:{ ph_r:"idle", ph_s:"idle", ph_ref:"idle", ph_d:"idle", route:"", rf1:"idle", rf2:"idle", rf3:"idle", prod_name:"", delivery_district:"" } });
    dispatch({ type:"MERGE", sid:"gallery_surface",     data:{ g0_visible:false, g1_visible:false, g2_visible:false, g3_visible:false } });
    dispatch({ type:"MERGE", sid:"chat_surface",        data:{ thinking:true, thinking_label:"Thinking...", response:"" } });
    dispatch({ type:"MERGE", sid:"notification_surface",data:{ toast_visible:false } });
    dispatch({ type:"MERGE", sid:"memory_surface",      data:{ st_active:true, st_label:"Writing..." } });

    const url = `/stream?session_id=${sessionId.current}&message=${encodeURIComponent(msg)}&recipient=${encodeURIComponent(recipient)}`;
    const es  = new EventSource(url);
    esRef.current = es;

    es.onmessage = e => {
      const data = e.data || "";
      if (!data || data.trim() === "" || data.trim() === ": done") return;
      dispatchJSONL(data, dispatch);
    };
    es.onerror = () => {
      es.close(); esRef.current = null; setLoading(false);
      dispatch({ type:"MERGE", sid:"chat_surface",  data:{ thinking:false } });
      dispatch({ type:"MERGE", sid:"memory_surface",data:{ st_active:false } });
    };
  }, [input, loading, recipient]);

  const handleKey = e => { if (e.key==="Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); } };

  return (
    <div style={{ display:"flex", flexDirection:"column", height:"100dvh", background:C.bg, overflow:"hidden", position:"relative" }}>

      {/* Ambient orbs */}
      <Orb style={{ width:400, height:400, top:"-10%", left:"20%", background:`radial-gradient(circle,${C.p}18 0%,transparent 70%)`, animation:"orb1 18s ease-in-out infinite" }} />
      <Orb style={{ width:300, height:300, bottom:"15%", right:"5%",  background:`radial-gradient(circle,${C.gold}12 0%,transparent 70%)`, animation:"orb2 22s ease-in-out infinite" }} />

      {/* ── HEADER ─────────────────────────────────────────────────────────── */}
      <header style={{
        flexShrink:0, height:56,
        borderBottom:`1px solid ${C.bd}`,
        background:"rgba(8,12,24,0.8)", backdropFilter:"blur(20px)",
        display:"flex", alignItems:"center", padding:"0 20px", gap:16, position:"relative", zIndex:10,
      }}>
        {/* Logo */}
        <div style={{ display:"flex", alignItems:"center", gap:9, flexShrink:0 }}>
          <div style={{
            width:30, height:30, borderRadius:8,
            background:`linear-gradient(135deg,${C.gold},${C.goldL})`,
            display:"flex", alignItems:"center", justifyContent:"center",
            fontSize:14, color:C.bg, fontWeight:700,
          }}>K</div>
          <div>
            <div style={{
              fontFamily:"var(--serif)", fontSize:16, fontStyle:"italic",
              background:`linear-gradient(90deg,${C.gold},${C.goldL},${C.gold})`,
              backgroundSize:"200% auto", WebkitBackgroundClip:"text",
              WebkitTextFillColor:"transparent", animation:"shimmer 4s linear infinite",
            }}>Kapruka</div>
            <div style={{ fontSize:8, color:C.tx2, fontFamily:"var(--mono)", letterSpacing:2 }}>GIFT CONCIERGE</div>
          </div>
        </div>

        {/* Recipient toggle */}
        <div style={{ flex:1, display:"flex", alignItems:"center", justifyContent:"center", gap:4 }}>
          {Object.keys(PROFILES).map(r => (
            <button key={r} onClick={() => setRec(r)} style={{
              padding:"5px 14px", borderRadius:7, fontSize:12, fontWeight:500,
              background: r===recipient ? `${C.gold}20` : "transparent",
              color:      r===recipient ? C.gold : C.tx2,
              border:`1px solid ${r===recipient ? C.gold+"55" : C.bd}`,
              transition:"all .3s cubic-bezier(0.32,0.72,0,1)",
            }}>{r}</button>
          ))}
          <span style={{ width:1, height:16, background:C.bd, margin:"0 4px" }} />
          {/* Allergy badges */}
          {profile.allergies.map((a,i) => (
            <span key={i} style={{ padding:"2px 7px", borderRadius:4, fontSize:9, background:`${C.r}15`, color:C.r, border:`1px solid ${C.r}25`, fontFamily:"var(--mono)" }}>!{a}</span>
          ))}
          {profile.preferences.slice(0,2).map((p,i) => (
            <span key={i} style={{ padding:"2px 7px", borderRadius:4, fontSize:9, background:`${C.g}10`, color:C.g, border:`1px solid ${C.g}20`, fontFamily:"var(--mono)" }}>+{p}</span>
          ))}
        </div>

        {/* Budget */}
        <span style={{ padding:"4px 12px", borderRadius:6, fontSize:10, border:`1px solid ${C.gold}40`, color:C.gold, fontFamily:"var(--mono)", flexShrink:0 }}>
          {profile.budget}
        </span>
      </header>

      {/* ── BODY ───────────────────────────────────────────────────────────── */}
      <div style={{ flex:1, display:"flex", overflow:"hidden" }}>

        {/* LEFT: Chat + Gallery + Input */}
        <main style={{ flex:1, display:"flex", flexDirection:"column", overflow:"hidden", minWidth:0 }}>

          {/* Chat messages */}
          <div style={{ flex:1, overflowY:"auto", padding:"20px 24px 8px" }}>
            {chatHistory.map((msg, i) => (
              <div key={i} style={{
                display:"flex", justifyContent: msg.role==="user" ? "flex-end" : "flex-start",
                marginBottom:14, animation:"fadeUp .35s cubic-bezier(0.32,0.72,0,1)",
              }}>
                {msg.role === "assistant" && (
                  <div style={{
                    width:24, height:24, borderRadius:6, flexShrink:0, marginRight:8,
                    background:`linear-gradient(135deg,${C.gold},${C.goldL})`,
                    display:"flex", alignItems:"center", justifyContent:"center",
                    fontSize:10, color:C.bg, fontWeight:700, alignSelf:"flex-end",
                  }}>K</div>
                )}
                <div style={{
                  maxWidth:"72%", padding:"11px 15px",
                  borderRadius: msg.role==="user" ? "14px 14px 3px 14px" : "14px 14px 14px 3px",
                  background: msg.role==="user"
                    ? `linear-gradient(135deg,#162340,#0D1830)`
                    : C.bg2,
                  border:`1px solid ${msg.role==="user" ? "#1E3B62" : C.bd}`,
                  fontSize:13, color:C.tx, lineHeight:1.65, whiteSpace:"pre-wrap",
                  boxShadow:`0 2px 12px rgba(0,0,0,.3)`,
                }}>{msg.content}</div>
              </div>
            ))}

            {/* Live thinking indicator */}
            {chatDM.thinking && <ThinkingDots active={true} label={chatDM.thinking_label} />}
            <div ref={chatEndRef} />
          </div>

          {/* Product gallery — appears when products load */}
          {products.length > 0 && (
            <div style={{
              flexShrink:0, padding:"0 24px 12px",
              animation:"slideUp .4s cubic-bezier(0.32,0.72,0,1)",
            }}>
              <div style={{ fontSize:9, color:C.tx2, fontFamily:"var(--mono)", letterSpacing:2, marginBottom:8 }}>
                RECOMMENDATIONS · {products.length} found · click to expand
              </div>
              <div style={{ display:"flex", gap:10, overflowX:"auto", paddingBottom:4 }}>
                {products.map((p,i) => <ProductCard key={p._key||i} product={p} onClick={setSelected} />)}
              </div>
            </div>
          )}

          {/* Suggestion chips */}
          <div style={{ flexShrink:0, padding:"0 24px 8px", display:"flex", gap:6, flexWrap:"wrap" }}>
            {SUGGESTIONS[recipient].map((s,i) => (
              <button key={i} onClick={() => { setInput(s); }}
                style={{
                  padding:"4px 10px", borderRadius:5, fontSize:10,
                  background:C.bg2, color:C.tx2, border:`1px solid ${C.bd}`,
                  fontFamily:"var(--mono)",
                  transition:"all .2s cubic-bezier(0.32,0.72,0,1)",
                }}
                onMouseEnter={e=>{e.target.style.borderColor=C.gold+"55";e.target.style.color=C.gold;}}
                onMouseLeave={e=>{e.target.style.borderColor=C.bd;e.target.style.color=C.tx2;}}
              >{s}</button>
            ))}
          </div>

          {/* Input bar */}
          <div style={{
            flexShrink:0, padding:"10px 24px 14px",
            borderTop:`1px solid ${C.bd}`,
            background:`${C.bg1}CC`, backdropFilter:"blur(12px)",
          }}>
            {/* Double-bezel input */}
            <div style={{ padding:2, borderRadius:12, background:C.bg3, border:`1px solid ${C.bd2}` }}>
              <div style={{ display:"flex", alignItems:"flex-end", gap:8, background:C.bg2, borderRadius:10, padding:"8px 8px 8px 14px", boxShadow:"inset 0 1px 1px rgba(255,255,255,0.04)" }}>
                <textarea
                  rows={1}
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  onKeyDown={handleKey}
                  placeholder={`Gift for ${recipient} in ${profile.district}…`}
                  maxLength={500}
                  style={{
                    flex:1, resize:"none", background:"transparent",
                    border:"none", fontSize:13, color:C.tx, lineHeight:1.5,
                  }}
                />
                <div style={{ display:"flex", alignItems:"center", gap:6, flexShrink:0 }}>
                  <span style={{ fontSize:9, color:C.tx2, fontFamily:"var(--mono)" }}>{input.length}/500</span>
                  {/* Button-in-button pattern */}
                  <button onClick={sendMessage} disabled={loading||!input.trim()}
                    style={{
                      display:"flex", alignItems:"center", gap:6,
                      padding:"7px 14px", borderRadius:8,
                      background: (loading||!input.trim()) ? C.bg3 : `linear-gradient(135deg,${C.gold},${C.goldL})`,
                      color: (loading||!input.trim()) ? C.tx2 : C.bg,
                      fontSize:12, fontWeight:600,
                      transition:"all .25s cubic-bezier(0.32,0.72,0,1)",
                      transform: loading ? "scale(0.97)" : "scale(1)",
                    }}
                  >
                    {loading
                      ? <span style={{ width:12, height:12, borderRadius:"50%", border:`2px solid ${C.tx2}`, borderTopColor:"transparent", animation:"spin .8s linear infinite", display:"inline-block" }} />
                      : <>Send <span style={{ width:18, height:18, borderRadius:"50%", background:"rgba(0,0,0,.18)", display:"inline-flex", alignItems:"center", justifyContent:"center", fontSize:10 }}>→</span></>
                    }
                  </button>
                </div>
              </div>
            </div>
          </div>
        </main>

        {/* RIGHT: Agent + Memory panel */}
        <aside style={{
          width:220, flexShrink:0,
          borderLeft:`1px solid ${C.bd}`,
          overflowY:"auto", padding:"16px 14px",
          background:`${C.bg1}99`, backdropFilter:"blur(8px)",
          display:"flex", flexDirection:"column", gap:16,
        }}>
          {/* Agent panel */}
          <div>
            <div style={{ fontSize:9, color:C.gold, fontFamily:"var(--mono)", letterSpacing:3, textTransform:"uppercase", marginBottom:10 }}>Live Agent</div>
            <SurfaceView surface={surfaces["agent_surface"]} />
          </div>

          <div style={{ height:1, background:C.bd }} />

          {/* Memory panel */}
          <div>
            <div style={{ fontSize:9, color:C.tx2, fontFamily:"var(--mono)", letterSpacing:3, textTransform:"uppercase", marginBottom:10 }}>Memory Stack</div>
            <SurfaceView surface={surfaces["memory_surface"]} />
          </div>
        </aside>
      </div>

      {/* Product detail modal */}
      {selected && <ProductModal product={selected} onClose={() => setSelected(null)} />}

      {/* Toast notification */}
      <NotificationToast text={notifDM.toast_text} visible={notifDM.toast_visible} />
    </div>
  );
}
