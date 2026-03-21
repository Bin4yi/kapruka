export function parseJSONL(line) {
  try { return JSON.parse(line.trim()); } catch { return null; }
}

export function resolveBoundValue(bv, dm) {
  if (!bv || typeof bv !== "object") return bv;
  if ("literalString"  in bv) return bv.literalString;
  if ("literalBoolean" in bv) return bv.literalBoolean;
  if ("literalNumber"  in bv) return bv.literalNumber;
  if ("literalArray"   in bv) return bv.literalArray;
  if ("path" in bv) {
    const parts = bv.path.replace(/^\//, "").split("/").filter(Boolean);
    return parts.reduce((obj, k) => obj?.[k], dm) ?? null;
  }
  return null;
}

export function applyContents(target, contents = []) {
  contents.forEach(e => {
    if      ("valueString"  in e) target[e.key] = e.valueString;
    else if ("valueBoolean" in e) target[e.key] = e.valueBoolean;
    else if ("valueNumber"  in e) target[e.key] = e.valueNumber;
    else if ("valueArray"   in e) target[e.key] = e.valueArray;
    else if ("valueMap"     in e) { target[e.key] = {}; applyContents(target[e.key], e.valueMap); }
  });
}

export function a2uiReducer(state, action) {
  const sid  = action.sid;
  const prev = state[sid] || { comps:{}, dm:{}, root:null, ready:false };
  switch (action.type) {
    case "SU": {
      const comps = { ...prev.comps };
      (action.components||[]).forEach(c => { comps[c.id] = c; });
      return { ...state, [sid]: { ...prev, comps } };
    }
    case "DM": {
      const dm    = JSON.parse(JSON.stringify(prev.dm));
      const parts = (action.path||"").replace(/^\//, "").split("/").filter(Boolean);
      let t = dm;
      for (const k of parts.slice(0,-1)) { t[k]=t[k]||{}; t=t[k]; }
      if (parts.length > 0) {
        const last = parts.at(-1); t[last]=t[last]||{}; applyContents(t[last], action.contents);
      } else { applyContents(dm, action.contents); }
      return { ...state, [sid]: { ...prev, dm } };
    }
    case "BR": return { ...state, [sid]: { ...prev, root:action.root, ready:true } };
    case "DS": { const s={...state}; delete s[sid]; return s; }
    // Direct data merge (used by App.jsx for fast inline updates)
    case "MERGE": {
      const dm = { ...prev.dm, ...action.data };
      return { ...state, [sid]: { ...prev, dm } };
    }
    default: return state;
  }
}

export function dispatchJSONL(line, dispatch) {
  const msg = parseJSONL(line);
  if (!msg) return;

  // Support both the original A2UI envelope format AND our flat orchestrator format
  const type = msg.type;

  if (type === "surfaceUpdate" || msg.surfaceUpdate) {
    const su = type === "surfaceUpdate" ? msg : msg.surfaceUpdate;
    dispatch({ type:"SU", sid: su.surfaceId || "main", components: su.components });
  }
  if (type === "dataModelUpdate" || msg.dataModelUpdate) {
    const dm = type === "dataModelUpdate" ? msg : msg.dataModelUpdate;
    // Our orchestrator emits {type, surfaceId, data} — merge data directly
    if (dm.data) {
      dispatch({ type:"MERGE", sid: dm.surfaceId || "main", data: dm.data });
    } else {
      dispatch({ type:"DM", sid: dm.surfaceId || "main", path: dm.path, contents: dm.contents });
    }
  }
  if (type === "beginRendering" || msg.beginRendering) {
    const br = type === "beginRendering" ? msg : msg.beginRendering;
    dispatch({ type:"BR", sid: br.surfaceId || "main", root: br.root });
  }
  if (type === "deleteSurface" || msg.deleteSurface) {
    const ds = type === "deleteSurface" ? msg : msg.deleteSurface;
    dispatch({ type:"DS", sid: ds.surfaceId });
  }
}
