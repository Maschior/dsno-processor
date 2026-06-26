import React, { useEffect, useRef, useState } from "react";
import { api } from "./api.js";

// Ordered to mirror the real workflow: prepare → download → process → upload.
const TABS = [
  { id: "pendencias", label: "1 · Pendências" },
  { id: "download", label: "2 · Download" },
  { id: "processor", label: "3 · Processar" },
  { id: "upload", label: "4 · Upload" },
  { id: "registros", label: "Registros" },
];

const EMPTY_DASH = { phase: "", total: 0, rows: [], running: false, cancelled: false };

// Skeleton matching webui/api.py get_config() shape, so the Settings screen
// always has the full nested structure even before a config.toml exists.
const DEFAULT_CFG = {
  general: { language: "pt", data_source: "spreadsheet" },
  paths: { dsno_directory: "", control_sheet: "", customer_sheet: "", customer_sheet_pre_path: "", database_dir: "" },
  processor: { bypass_file_size_check: false, keep_original: false },
  customer_sheet: { cols: { invoice: "Invoice", booking: "Booking/HAWB", container: "Container" }, config: { sheet_name: "" } },
  control_sheet: { cols: { invoice: "INVOICE", dsno: "ARGUMENT2", date: "CREATION_DATE", status: "STATUS", freight_oracle: "FREIGHT_ORACLE", freight_softway: "FREIGHT_SOFTWAY", description: "Obs" } },
  ebs: { download_url: "", upload_url: "", download_dir: "", upload_dir: "", headless: false, folders: { download_indices: [92, 95, 101], upload_index: 92 } },
  credentials: { email: "", password: "" },
  oracle: { user: "", password: "", dsn: "", customer_id: "", lookback_months: 2, jdbc_jar: "", jvm_path: "" },
};

const NAV_SETTINGS = "settings";

function buildForms(cfg) {
  const p = cfg.paths, ebs = cfg.ebs, folders = ebs.folders, cols = cfg.control_sheet.cols;
  const todayHtml = new Date().toISOString().slice(0, 10); // YYYY-MM-DD for <input type="date">
  return {
    processor: {
      start: todayHtml, end: todayHtml, freight_mode: "SEA", status_filter: "",
      customer_sheet: p.customer_sheet, control_sheet: p.control_sheet, dsno_dir: p.dsno_directory,
    },
    download: {
      // url/sheet/cols/folders kept in state (passed to backend) but not shown in UI
      url: ebs.download_url, sheet: p.control_sheet, dir: ebs.download_dir,
      dsno_col: cols.dsno, date_col: cols.date, status_col: cols.status,
      date_start: "", date_end: "", status_filter: "",
      folders: (folders.download_indices || [92, 95, 101]).join(","),
    },
    upload: { url: ebs.upload_url, dir: ebs.upload_dir, folder: String(folders.upload_index ?? 92) },
  };
}

// Deep-merge a loaded config onto the skeleton so missing keys keep defaults.
function mergeCfg(base, over) {
  const out = Array.isArray(base) ? [...base] : { ...base };
  for (const k in over) {
    if (over[k] && typeof over[k] === "object" && !Array.isArray(over[k]))
      out[k] = mergeCfg(base[k] || {}, over[k]);
    else out[k] = over[k];
  }
  return out;
}

export default function App() {
  const [theme, setTheme] = useState(
    () => localStorage.getItem("dsno-theme") || "light"
  );
  const [tab, setTab] = useState("download"); // first actionable step
  const [forms, setForms] = useState(null); // null until config loads
  const [cfg, setCfg] = useState(null); // raw config dict for the Settings screen
  // One dashboard per operation so running one tab never clobbers another and
  // the state survives tab switches (tab components unmount on navigation).
  const [dashes, setDashes] = useState({ process: EMPTY_DASH, download: EMPTY_DASH, upload: EMPTY_DASH });
  // Pendências (step 1) state, lifted here so it persists across tab switches
  // and the async result lands even after navigating away.
  const [pend, setPend] = useState({ busy: false, result: null, data: null, selected: new Set() });
  const anchorRef = useRef(null); // last-clicked row index for shift-range selection
  const [showLog, setShowLog] = useState(false); // debug log panel
  const [logs, setLogs] = useState([]);

  // Apply + persist theme
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("dsno-theme", theme);
  }, [theme]);

  // Wire the progress bridge that webui/api.py calls via evaluate_js. Each event
  // carries its op (process|download|upload) so it updates only that dashboard.
  useEffect(() => {
    window.__onProgress = ({ op, event, data }) => {
      setDashes((all) => {
        const d = all[op] || EMPTY_DASH;
        const next = { ...d };
        if (event === "phase") next.phase = data.text;
        else if (event === "total") { next.total = data.count; next.rows = []; }
        else if (event === "success") next.rows = [...d.rows, { kind: "success", ...data }];
        else if (event === "error") next.rows = [...d.rows, { kind: "error", ...data }];
        else if (event === "skipped") next.rows = [...d.rows, { kind: "skipped", ...data }];
        else if (event === "cancelled") { next.cancelled = true; }
        else if (event === "finished") { next.running = false; }
        return { ...all, [op]: next };
      });
    };
    return () => { delete window.__onProgress; };
  }, []);

  // Debug panel: stream Python logging lines (bounded to the last 1000).
  useEffect(() => {
    window.__onLog = (line) =>
      setLogs((l) => (l.length > 1000 ? [...l.slice(-1000), line] : [...l, line]));
    return () => { delete window.__onLog; };
  }, []);

  // Load config once, prefill forms + keep the raw dict for Settings
  useEffect(() => {
    api().then(async (a) => {
      let loaded = {};
      try { loaded = await a.get_config(); } catch { /* no config.toml yet */ }
      const merged = mergeCfg(DEFAULT_CFG, loaded);
      setCfg(merged);
      setForms(buildForms(merged));
    });
  }, []);

  function setField(formId, key, value) {
    setForms((f) => ({ ...f, [formId]: { ...f[formId], [key]: value } }));
  }

  // Immutable nested set by dot-path, e.g. setCfgIn("ebs.folders.upload_index", 92)
  function setCfgIn(path, value) {
    setCfg((c) => {
      const next = structuredClone(c);
      const keys = path.split(".");
      let node = next;
      for (let i = 0; i < keys.length - 1; i++) node = node[keys[i]];
      node[keys[keys.length - 1]] = value;
      return next;
    });
  }

  async function browse(formId, key, kind) {
    const a = await api();
    const path = kind === "dir" ? await a.browse_dir() : await a.browse_file(true);
    if (path) setField(formId, key, path);
  }

  async function browseCfg(path, kind) {
    const a = await api();
    const picked = kind === "dir" ? await a.browse_dir() : await a.browse_file(kind === "file");
    if (picked) setCfgIn(path, picked);
  }

  async function saveSettings() {
    const a = await api();
    await a.save_config(cfg);
    setForms(buildForms(cfg)); // refresh operation defaults from saved config
  }

  // ── Pendências (step 1) — lifted so it survives tab switches ──
  async function runPendencias() {
    anchorRef.current = null;
    setPend({ busy: true, result: null, data: null, selected: new Set() });
    try {
      const r = await (await api()).sync_oracle_pending();
      setPend({
        busy: false,
        result: { ok: true, text: `Importados ${r.imported} novos · ${r.skipped} já existentes (status preservado)` },
        data: { columns: r.columns || [], rows: r.rows || [] },
        selected: new Set(),
      });
    } catch (e) {
      setPend((p) => ({ ...p, busy: false, result: { ok: false, text: String(e) } }));
    }
  }
  function togglePend(i, shift) {
    setPend((p) => {
      const next = new Set(p.selected);
      if (shift && anchorRef.current != null) {
        // Shift-click: select the contiguous range from the last clicked row.
        const [lo, hi] = [anchorRef.current, i].sort((a, b) => a - b);
        for (let k = lo; k <= hi; k++) next.add(k);
      } else {
        next.has(i) ? next.delete(i) : next.add(i);
        anchorRef.current = i;
      }
      return { ...p, selected: next };
    });
  }
  function toggleAllPend() {
    setPend((p) => {
      const n = p.data?.rows?.length || 0;
      const allOn = n > 0 && p.selected.size === n;
      return { ...p, selected: allOn ? new Set() : new Set(Array.from({ length: n }, (_, i) => i)) };
    });
  }

  async function start(op) {
    setDashes((all) => ({ ...all, [op]: { ...EMPTY_DASH, running: true } }));
    const a = await api();
    const form = forms[op === "process" ? "processor" : op];
    if (op === "process") {
      a.start_processing({
        ...form,
        start: fromHtmlDate(form.start),
        end: fromHtmlDate(form.end),
        status_filter: splitList(form.status_filter),
      });
    } else if (op === "download") {
      a.start_download({
        ...form,
        date_start: fromHtmlDatetime(form.date_start),
        date_end: fromHtmlDatetime(form.date_end),
      });
    } else {
      a.start_upload(form);
    }
  }

  async function cancel(op) {
    (await api()).cancel(op);
  }

  if (!forms) return null;

  return (
    <div className="app">
      <Topbar
        theme={theme}
        setTheme={setTheme}
        tab={tab}
        setTab={setTab}
        debugOn={showLog}
        onDebug={() => setShowLog((s) => !s)}
      />
      <main className="main">
        <div className="page">
          {tab === "pendencias" && (
            <PendenciasTab pend={pend} onRun={runPendencias} onToggle={togglePend} onToggleAll={toggleAllPend} />
          )}
          {tab === "processor" && (
            <ProcessorTab
              form={forms.processor}
              setField={setField}
              browse={browse}
              dataSource={getIn(cfg, "general.data_source")}
            />
          )}
          {tab === "download" && (
            <DownloadTab
              form={forms.download} setField={setField} browse={browse}
              dataSource={getIn(cfg, "general.data_source")}
            />
          )}
          {tab === "upload" && (
            <UploadTab form={forms.upload} setField={setField} browse={browse} />
          )}
          {tab === "registros" && <RecordsTab />}
          {tab === NAV_SETTINGS && (
            <Settings cfg={cfg} setCfgIn={setCfgIn} browseCfg={browseCfg} onSave={saveSettings} />
          )}
          {(tab === "processor" || tab === "download" || tab === "upload") && (
            <Dashboard
              dash={dashes[tab === "processor" ? "process" : tab]}
              op={tab === "processor" ? "process" : tab}
              onStart={start}
              onCancel={cancel}
            />
          )}
        </div>
      </main>
      {showLog && (
        <LogPanel logs={logs} onClear={() => setLogs([])} onClose={() => setShowLog(false)} />
      )}
    </div>
  );
}

const splitList = (s) => s.split(",").map((x) => x.trim()).filter(Boolean);
const getIn = (obj, path) => path.split(".").reduce((o, k) => (o == null ? o : o[k]), obj);

// DD/MM/YYYY ↔ YYYY-MM-DD (HTML date input)
const toHtmlDate = (s) => {
  if (!s) return "";
  const [d, m, y] = s.split("/");
  return y && m && d ? `${y}-${m.padStart(2, "0")}-${d.padStart(2, "0")}` : "";
};
const fromHtmlDate = (s) => {
  if (!s) return "";
  const [y, m, d] = s.split("-");
  return `${d}/${m}/${y}`;
};
// YYYY-MM-DDTHH:MM (HTML datetime-local) → DD/MM/YYYY HH:MM:SS (backend)
const fromHtmlDatetime = (s) => {
  if (!s) return "";
  const [date, time = "00:00"] = s.split("T");
  const [y, m, d] = date.split("-");
  return `${d}/${m}/${y} ${time}:00`;
};

/* ───────────── Top bar ───────────── */
function Topbar({ theme, setTheme, tab, setTab, debugOn, onDebug }) {
  const items = [...TABS, { id: NAV_SETTINGS, label: "Configurações" }];
  return (
    <header className="topbar">
      <div className="brand">
        <div className="brand-mark">D</div>
        <div className="brand-name">DSNO Processor</div>
      </div>

      <nav className="topnav">
        {items.map((t) => (
          <button
            key={t.id}
            className={"tab" + (tab === t.id ? " on" : "")}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </nav>

      <div className="topbar-right">
        <button
          className={"btn btn-sm " + (debugOn ? "btn-primary" : "btn-secondary")}
          onClick={onDebug}
          title="Mostrar o processo do programa (log)"
        >
          <Icon name="bug" /> Debug
        </button>
        <div className="seg">
          <button className={theme === "light" ? "on" : ""} onClick={() => setTheme("light")}>
            <Icon name="sun" /> Claro
          </button>
          <button className={theme === "dark" ? "on" : ""} onClick={() => setTheme("dark")}>
            <Icon name="moon" /> Escuro
          </button>
        </div>
      </div>
    </header>
  );
}

/* ───────────── Field helpers ───────────── */
function Field({ label, help, span, children }) {
  return (
    <div className={"field" + (span ? " col-span" : "")}>
      <label>{label}</label>
      {children}
      {help && <div className="help">{help}</div>}
    </div>
  );
}

function Text({ form, k, set, mono }) {
  return (
    <input
      className={"input" + (mono ? " mono" : "")}
      value={form[k]}
      onChange={(e) => set(k, e.target.value)}
    />
  );
}

function PathField({ label, help, form, k, set, browse, kind, formId, span }) {
  return (
    <Field label={label} help={help} span={span}>
      <div className="input-with-btn">
        <input className="input mono" value={form[k]} onChange={(e) => set(k, e.target.value)} />
        <button className="btn btn-secondary" onClick={() => browse(formId, k, kind)}>…</button>
      </div>
    </Field>
  );
}

/* ───────────── Tabs ───────────── */
function TabHead({ eyebrow, title, lead }) {
  return (
    <section>
      <div className="page-eyebrow">{eyebrow}</div>
      <h1 className="title">{title}</h1>
      <p className="lead">{lead}</p>
    </section>
  );
}

// A post-step data action (import to DB / sync status). `onRun` returns a
// summary string to show, or null when cancelled; throwing shows an error pill.
function StepAction({ label, help, disabled, onRun }) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null); // { ok, text }
  async function run() {
    setBusy(true);
    setResult(null);
    try {
      const text = await onRun();
      if (text != null) setResult({ ok: true, text });
    } catch (e) {
      setResult({ ok: false, text: String(e) });
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="field col-span">
      <div className="input-with-btn" style={{ alignItems: "center" }}>
        <button className="btn btn-secondary" disabled={disabled || busy} onClick={run}>
          {busy ? "…" : label}
        </button>
        {result && (
          <span className={"pill " + (result.ok ? "success" : "danger")}>
            <span className="dot" /> {result.text}
          </span>
        )}
      </div>
      {help && <div className="help">{help}</div>}
    </div>
  );
}

// Copy rows (with header) to the clipboard as TSV — pastes straight into Excel.
async function copyTsv(columns, rows) {
  const tsv = [columns, ...rows].map((r) => r.join("\t")).join("\n");
  try {
    await navigator.clipboard.writeText(tsv);
  } catch {
    // ponytail: WebView2 can reject the async clipboard API; fall back to execCommand.
    const ta = document.createElement("textarea");
    ta.value = tsv;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
  }
}

// Step 1 — pull pending DSNOs from Oracle (config.oracle) into the internal DB,
// then show the full query result as a selectable, copyable table. State lives
// in App (props) so it survives tab switches and the running animation persists.
function PendenciasTab({ pend, onRun, onToggle, onToggleAll }) {
  const { busy, result, data, selected } = pend;
  const [full, setFull] = useState(false);
  const [copied, setCopied] = useState(false);
  const rows = data?.rows || [];

  async function doCopy() {
    await copyTsv(data.columns, rows.filter((_, i) => selected.has(i)));
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }
  const copyBtn = data && (
    <button className={"btn " + (copied ? "btn-success" : "btn-secondary")}
      disabled={selected.size === 0} onClick={doCopy}>
      {copied ? "Copiado!" : `Copiar selecionadas (${selected.size})`}
    </button>
  );
  const table = data && (
    <PreviewTable columns={data.columns} rows={rows} selected={selected}
      onToggle={onToggle} onToggleAll={onToggleAll} fill={full} />
  );

  return (
    <>
      <TabHead
        eyebrow="Passo 1 — Preparar"
        title="Pendências"
        lead="Busca no Oracle os últimos 2 meses de DSNOs pendentes e adiciona os novos ao banco interno. Registros já existentes são preservados com seu status atual."
      />
      <div className="card">
        <div className="card-body">
          <div className="grid">
            <div className="field col-span">
              <div className="input-with-btn" style={{ alignItems: "center", flexWrap: "wrap" }}>
                <button className="btn btn-secondary" disabled={busy} onClick={onRun}>
                  {busy ? (<><span className="spinner" /> Buscando…</>) : "Buscar pendências no Oracle"}
                </button>
                {copyBtn}
                {data && (
                  <button className="btn btn-secondary" onClick={() => setFull(true)}>
                    <Icon name="expand" /> Tela cheia
                  </button>
                )}
                {result && (
                  <span className={"pill " + (result.ok ? "success" : "danger")}>
                    <span className="dot" /> {result.text}
                  </span>
                )}
              </div>
              <div className="help">
                Usa as credenciais em Configurações → Oracle. Só insere DSNOs novos.
                Clique para marcar uma linha, Shift+clique para selecionar um intervalo.
              </div>
            </div>
          </div>

          {!full && table}
        </div>
      </div>

      {full && (
        <div className="modal-overlay" onClick={() => setFull(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <span className="modal-title">Pendências — {rows.length} registros</span>
              <div style={{ display: "flex", gap: 8 }}>
                {copyBtn}
                <button className="btn btn-secondary btn-sm" onClick={() => setFull(false)}>Fechar</button>
              </div>
            </div>
            <div className="modal-body">{table}</div>
          </div>
        </div>
      )}
    </>
  );
}

// Selectable result table — reused inline and inside the fullscreen modal.
function PreviewTable({ columns, rows, selected, onToggle, onToggleAll, fill }) {
  const allOn = rows.length > 0 && selected.size === rows.length;
  return (
    <div className={"preview-table" + (fill ? " fill" : "")}>
      <table>
        <thead>
          <tr>
            <th>
              <input type="checkbox" checked={allOn} onChange={onToggleAll} disabled={rows.length === 0} />
            </th>
            {columns.map((c) => <th key={c}>{c}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr><td colSpan={columns.length + 1} className="help">Nenhuma pendência no período.</td></tr>
          ) : (
            rows.map((row, i) => (
              <tr key={i} className={selected.has(i) ? "on" : ""} onClick={(e) => onToggle(i, e.shiftKey)}>
                <td><input type="checkbox" checked={selected.has(i)} readOnly /></td>
                {row.map((cell, j) => <td key={j}>{cell}</td>)}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

// Read-only viewer over the internal SQLite tables (control + customer/shipment).
function RecordsTab() {
  const [kind, setKind] = useState("control");
  const [data, setData] = useState({ columns: [], rows: [] });
  const [loading, setLoading] = useState(false);

  async function load(k) {
    setLoading(true);
    try {
      const a = await api();
      setData(await a.get_records(k));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(kind); }, [kind]);

  return (
    <>
      <TabHead
        eyebrow="Banco interno"
        title="Registros"
        lead="Consulta somente-leitura das tabelas internas (SQLite). Mostra os 1000 registros mais recentes."
      />
      <div className="row" style={{ gap: 8, marginBottom: 12 }}>
        <button className={"btn" + (kind === "control" ? "" : " btn-secondary")} onClick={() => setKind("control")}>Controle</button>
        <button className={"btn" + (kind === "shipment" ? "" : " btn-secondary")} onClick={() => setKind("shipment")}>Cliente</button>
        <button className="btn btn-secondary" onClick={() => load(kind)} disabled={loading}>↻ Atualizar</button>
        <span className="help" style={{ alignSelf: "center" }}>{loading ? "Carregando…" : `${data.rows.length} registros`}</span>
      </div>
      <div className="preview-table fill">
        <table>
          <thead>
            <tr>{data.columns.map((c) => <th key={c}>{c}</th>)}</tr>
          </thead>
          <tbody>
            {data.rows.length === 0 ? (
              <tr><td colSpan={Math.max(1, data.columns.length)} className="help">Nenhum registro.</td></tr>
            ) : (
              data.rows.map((row, i) => (
                <tr key={i}>{row.map((cell, j) => <td key={j}>{cell}</td>)}</tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}

function ProcessorTab({ form, setField, browse, dataSource }) {
  const set = (k, v) => setField("processor", k, v);
  const isDb = dataSource === "database";
  const periodSet = !!(form.start && form.end);

  const [availableStatuses, setAvailableStatuses] = useState([]);
  const [checkedStatuses, setCheckedStatuses] = useState(() => splitList(form.status_filter));

  useEffect(() => {
    if (!isDb || !periodSet) { setAvailableStatuses([]); return; }
    // date inputs are YYYY-MM-DD; append time so BETWEEN covers the full day
    api().then((a) => a.get_control_statuses(form.start + "T00:00", form.end + "T23:59"))
      .then(setAvailableStatuses).catch(() => setAvailableStatuses([]));
  }, [isDb, form.start, form.end]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    set("status_filter", checkedStatuses.join(","));
  }, [checkedStatuses]); // eslint-disable-line react-hooks/exhaustive-deps

  function toggleStatus(s) {
    setCheckedStatuses((c) => c.includes(s) ? c.filter((x) => x !== s) : [...c, s]);
  }

  async function importToDb(method) {
    const a = await api();
    const path = await a.browse_file(true);
    if (!path) return null;
    const r = await a[method](path);
    return r.updated != null
      ? `Importados ${r.imported}, atualizados ${r.updated}, ignorados ${r.skipped}`
      : `Importados ${r.imported}, ignorados ${r.skipped}`;
  }

  return (
    <>
      <TabHead
        eyebrow="Passo 4–6 — Processar"
        title="Processador de DSNO"
        lead="Edita os arquivos DSNO em lote a partir da planilha de controle, por intervalo de datas."
      />

      {isDb && (
        <div className="card">
          <div className="card-body">
            <div className="page-eyebrow" style={{ marginBottom: 16 }}>Fonte de dados — banco</div>
            <div className="grid">
              <StepAction
                label="Importar planilha do cliente → BD"
                help="Alimenta o banco interno com as informações a inserir nos arquivos (passos 4–5)."
                onRun={() => importToDb("import_customer_to_db")}
              />
              <StepAction
                label="Importar planilha de controle → BD"
                help="Atualiza o banco com os DSNOs e status da planilha de controle."
                onRun={() => importToDb("import_control_to_db")}
              />
            </div>
          </div>
        </div>
      )}

      <div className="card">
        <div className="card-body">
          <div className="grid">
            <Field label="Data inicial">
              <input type="date" className="input mono" value={form.start}
                onChange={(e) => set("start", e.target.value)} />
            </Field>
            <Field label="Data final">
              <input type="date" className="input mono" value={form.end}
                onChange={(e) => set("end", e.target.value)} />
            </Field>
            <Field label="Modo de frete">
              <select className="select" value={form.freight_mode} onChange={(e) => set("freight_mode", e.target.value)}>
                <option value="SEA">SEA</option>
                <option value="AIR">AIR</option>
              </select>
            </Field>

            <Field label="Filtrar por status" help={!periodSet ? "Selecione um período para habilitar." : "Vazio = todos."} span>
              {isDb ? (
                !periodSet ? (
                  <div className="input" style={{ opacity: 0.4, cursor: "not-allowed" }}>Aguardando período…</div>
                ) : availableStatuses.length === 0 ? (
                  <div className="help">Nenhum registro encontrado para o período.</div>
                ) : (
                  <div style={{ display: "flex", gap: 16, flexWrap: "wrap", paddingTop: 4 }}>
                    {availableStatuses.map((s) => (
                      <label key={s} style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer", fontSize: 14 }}>
                        <input type="checkbox" checked={checkedStatuses.includes(s)} onChange={() => toggleStatus(s)} />
                        {s}
                      </label>
                    ))}
                  </div>
                )
              ) : (
                <input className="input" value={form.status_filter}
                  disabled={!periodSet}
                  onChange={(e) => set("status_filter", e.target.value)}
                  placeholder="Separe por vírgula…" />
              )}
            </Field>

            {!isDb && (
              <PathField label="Planilha do cliente" form={form} k="customer_sheet" set={set} browse={browse} kind="file" formId="processor" span />
            )}
            {!isDb && (
              <PathField label="Planilha de controle" form={form} k="control_sheet" set={set} browse={browse} kind="file" formId="processor" span />
            )}
            <PathField label="Diretório DSNO" form={form} k="dsno_dir" set={set} browse={browse} kind="dir" formId="processor" span />
          </div>
        </div>
      </div>
    </>
  );
}

function DownloadTab({ form, setField, browse, dataSource }) {
  const set = (k, v) => setField("download", k, v);
  const isDb = dataSource === "database";
  const periodSet = !!(form.date_start && form.date_end);

  const [availableStatuses, setAvailableStatuses] = useState([]);
  const [checkedStatuses, setCheckedStatuses] = useState(() =>
    splitList(form.status_filter)
  );

  // Fetch available statuses from DB when period is complete and in db mode
  useEffect(() => {
    if (!isDb || !periodSet) { setAvailableStatuses([]); return; }
    api().then((a) => a.get_control_statuses(form.date_start, form.date_end))
      .then(setAvailableStatuses).catch(() => setAvailableStatuses([]));
  }, [isDb, form.date_start, form.date_end]);

  // Sync checkbox selection → form.status_filter
  useEffect(() => {
    set("status_filter", checkedStatuses.join(","));
  }, [checkedStatuses]); // eslint-disable-line react-hooks/exhaustive-deps

  function toggleStatus(s) {
    setCheckedStatuses((c) => c.includes(s) ? c.filter((x) => x !== s) : [...c, s]);
  }

  async function syncDownloaded() {
    const a = await api();
    const r = await a.sync_status(form.sheet, form.dir);
    return `Status atualizado — processados ${r.processed}, baixados ${r.downloaded}`;
  }

  return (
    <>
      <TabHead
        eyebrow="Passo 2–3 — Baixar"
        title="EBS Download"
        lead="Baixa os arquivos DSNO do Oracle EBS conforme o período selecionado."
      />
      <div className="card">
        <div className="card-body">
          <div className="grid">
            <Field label="Início do período">
              <input type="datetime-local" className="input mono"
                value={form.date_start} onChange={(e) => set("date_start", e.target.value)} />
            </Field>
            <Field label="Fim do período">
              <input type="datetime-local" className="input mono"
                value={form.date_end} onChange={(e) => set("date_end", e.target.value)} />
            </Field>

            <Field label="Filtrar por status" help={!periodSet ? "Selecione um período para habilitar." : "Vazio = todos."} span>
              {isDb ? (
                !periodSet ? (
                  <div className="input" style={{ opacity: 0.4, cursor: "not-allowed" }}>Aguardando período…</div>
                ) : availableStatuses.length === 0 ? (
                  <div className="help">Nenhum registro encontrado para o período.</div>
                ) : (
                  <div style={{ display: "flex", gap: 16, flexWrap: "wrap", paddingTop: 4 }}>
                    {availableStatuses.map((s) => (
                      <label key={s} style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer", fontSize: 14 }}>
                        <input type="checkbox" checked={checkedStatuses.includes(s)} onChange={() => toggleStatus(s)} />
                        {s}
                      </label>
                    ))}
                  </div>
                )
              ) : (
                <input className="input" value={form.status_filter}
                  disabled={!periodSet}
                  onChange={(e) => set("status_filter", e.target.value)}
                  placeholder="Separe por vírgula…" />
              )}
            </Field>

            <PathField label="Diretório de download" form={form} k="dir" set={set} browse={browse} kind="dir" formId="download" span />
            {!isDb && (
              <PathField label="Planilha de controle" form={form} k="sheet" set={set} browse={browse} kind="file" formId="download" span />
            )}
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-body">
          <div className="page-eyebrow" style={{ marginBottom: 16 }}>Passo 3 — Após baixar</div>
          <div className="grid">
            <StepAction
              label="Marcar como Downloaded e recarregar"
              help="Atualiza o status na planilha de controle e no banco para os arquivos já baixados."
              onRun={syncDownloaded}
            />
          </div>
        </div>
      </div>
    </>
  );
}

function UploadTab({ form, setField, browse }) {
  const set = (k, v) => setField("upload", k, v);
  return (
    <>
      <TabHead
        eyebrow="Passo 7–8 — Enviar"
        title="EBS Upload"
        lead="Envia os arquivos DSNO locais para o Oracle EBS na pasta de destino configurada."
      />
      <div className="card">
        <div className="card-body">
          <div className="grid">
            <Field label="URL do EBS (upload)" span><Text form={form} k="url" set={set} mono /></Field>
            <PathField label="Diretório de upload" form={form} k="dir" set={set} browse={browse} kind="dir" formId="upload" span />
            <Field label="Pasta (índice)"><Text form={form} k="folder" set={set} mono /></Field>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-body">
          <div className="page-eyebrow" style={{ marginBottom: 16 }}>Passo 8 — Após enviar</div>
          <div className="grid">
            <StepAction
              label="Marcar como Sent (em breve)"
              help="Reservado: o domínio ainda não tem suporte ao status “Sent”."
              disabled
              onRun={() => null}
            />
          </div>
        </div>
      </div>
    </>
  );
}

/* ───────────── Dashboard ───────────── */
function Dashboard({ dash, op, onStart, onCancel }) {
  const { total, rows, running, cancelled, phase } = dash;
  const counts = rows.reduce(
    (acc, r) => ({ ...acc, [r.kind]: (acc[r.kind] || 0) + 1 }),
    {}
  );
  const pct = total ? Math.min(100, Math.round((rows.length / total) * 100)) : 0;

  return (
    <div className="card">
      <div className="card-body">
        <div className="dash">
          <div className="dash-phase">{cancelled ? "Cancelado pelo usuário." : phase || "Pronto."}</div>
          <div className="progress"><div style={{ width: `${pct}%` }} /></div>
          <div className="counts">
            <div><div className="n" style={{ color: "var(--success-fg)" }}>{counts.success || 0}</div><div className="lbl">sucesso</div></div>
            <div><div className="n" style={{ color: "var(--danger-fg)" }}>{counts.error || 0}</div><div className="lbl">erro</div></div>
            <div><div className="n">{counts.skipped || 0}</div><div className="lbl">ignorado</div></div>
            <div><div className="n">{total}</div><div className="lbl">total</div></div>
          </div>
          {rows.length > 0 && (
            <div className="rows">
              {rows.map((r, i) => (
                <div className="row" key={i}>
                  <span className="name">{r.name}</span>
                  <span className={"pill " + pillKind(r.kind)}>
                    <span className="dot" />
                    {r.detail || labelFor(r.kind)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
      <div className="card-foot">
        <button className="btn btn-secondary" disabled={!running} onClick={() => onCancel(op)}>
          Cancelar
        </button>
        <button className="btn btn-primary" disabled={running} onClick={() => onStart(op)}>
          <Icon name="check" /> Iniciar
        </button>
      </div>
    </div>
  );
}

const pillKind = (k) => (k === "success" ? "success" : k === "error" ? "danger" : "neutral");
const labelFor = (k) => (k === "success" ? "OK" : k === "error" ? "Falha" : "Ignorado");

/* ───────────── Settings ───────────── */
function SettingsCard({ title, children }) {
  return (
    <div className="card">
      <div className="card-body">
        <div className="page-eyebrow" style={{ marginBottom: 16 }}>{title}</div>
        <div className="grid">{children}</div>
      </div>
    </div>
  );
}

function Settings({ cfg, setCfgIn, browseCfg, onSave }) {
  const [saved, setSaved] = useState(false);
  const [err, setErr] = useState("");
  const set = setCfgIn;
  const g = (p) => getIn(cfg, p) ?? "";

  async function save() {
    setErr("");
    try {
      await onSave();
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (e) {
      setErr(String(e));
    }
  }

  const [exported, setExported] = useState(false);
  async function exportCfg() {
    setErr("");
    try {
      const path = await (await api()).export_config();
      if (path) {
        setExported(true);
        setTimeout(() => setExported(false), 2500);
      }
    } catch (e) {
      setErr(String(e));
    }
  }

  const text = (path, mono, type) => (
    <input
      className={"input" + (mono ? " mono" : "")}
      type={type || "text"}
      value={g(path)}
      onChange={(e) => set(path, e.target.value)}
    />
  );
  const pathRow = (label, path, kind, help) => (
    <Field label={label} help={help} span>
      <div className="input-with-btn">
        <input className="input mono" value={g(path)} onChange={(e) => set(path, e.target.value)} />
        <button className="btn btn-secondary" onClick={() => browseCfg(path, kind)}>…</button>
      </div>
    </Field>
  );
  const toggle = (label, path, help) => (
    <Field label={label} help={help} span>
      <label className="switch-row">
        <input type="checkbox" checked={!!getIn(cfg, path)} onChange={(e) => set(path, e.target.checked)} />
        <span>{getIn(cfg, path) ? "Ativado" : "Desativado"}</span>
      </label>
    </Field>
  );

  return (
    <>
      <TabHead
        eyebrow="Sistema"
        title="Configurações"
        lead="Lê e grava o config.toml — os mesmos valores usados pela interface CustomTkinter."
      />

      <SettingsCard title="Geral">
        <Field label="Idioma">
          <select className="select" value={g("general.language")} onChange={(e) => set("general.language", e.target.value)}>
            <option value="en">English</option>
            <option value="pt">Português (BR)</option>
          </select>
        </Field>
        <Field label="Fonte de dados">
          <select className="select" value={g("general.data_source")} onChange={(e) => set("general.data_source", e.target.value)}>
            <option value="spreadsheet">Planilha</option>
            <option value="database">Banco de dados</option>
          </select>
        </Field>
      </SettingsCard>

      <SettingsCard title="Caminhos">
        {pathRow("Diretório DSNO", "paths.dsno_directory", "dir")}
        {pathRow("Planilha de controle", "paths.control_sheet", "file")}
        {pathRow("Planilha do cliente", "paths.customer_sheet", "file")}
        {pathRow("Pasta pré-planilha do cliente", "paths.customer_sheet_pre_path", "dir")}
        {pathRow("Local do banco (SQLite)", "paths.database_dir", "dir", "Pasta do dsno_processor.db — aceita caminho de rede. Vazio = junto ao config.toml.")}
      </SettingsCard>

      <SettingsCard title="Processador">
        {toggle("Ignorar verificação de tamanho", "processor.bypass_file_size_check", "Pula a checagem de tamanho do arquivo após a edição.")}
        {toggle("Manter original", "processor.keep_original", "Copia antes de editar e move o original para Processed/original_files/.")}
      </SettingsCard>

      <SettingsCard title="EBS">
        <Field label="URL de download" span>{text("ebs.download_url", true)}</Field>
        <Field label="URL de upload" span>{text("ebs.upload_url", true)}</Field>
        {pathRow("Diretório de download", "ebs.download_dir", "dir")}
        {pathRow("Diretório de upload", "ebs.upload_dir", "dir")}
        {toggle("Navegador headless", "ebs.headless", "Executa o Chrome em segundo plano.")}
      </SettingsCard>

      <SettingsCard title="Colunas — planilha de controle">
        <Field label="Invoice">{text("control_sheet.cols.invoice", true)}</Field>
        <Field label="DSNO">{text("control_sheet.cols.dsno", true)}</Field>
        <Field label="Data">{text("control_sheet.cols.date", true)}</Field>
        <Field label="Status">{text("control_sheet.cols.status", true)}</Field>
        <Field label="Frete Oracle">{text("control_sheet.cols.freight_oracle", true)}</Field>
        <Field label="Frete Softway">{text("control_sheet.cols.freight_softway", true)}</Field>
        <Field label="Descrição">{text("control_sheet.cols.description", true)}</Field>
      </SettingsCard>

      <SettingsCard title="Colunas — planilha do cliente">
        <Field label="Invoice">{text("customer_sheet.cols.invoice", true)}</Field>
        <Field label="Booking/HAWB">{text("customer_sheet.cols.booking", true)}</Field>
        <Field label="Container">{text("customer_sheet.cols.container", true)}</Field>
        <Field label="Nome da aba" help="Vazio = primeira aba">{text("customer_sheet.config.sheet_name")}</Field>
      </SettingsCard>

      <SettingsCard title="Pastas EBS">
        <Field label="Índices de download" help="Separados por vírgula">
          <input
            className="input mono"
            value={(getIn(cfg, "ebs.folders.download_indices") || []).join(",")}
            onChange={(e) =>
              set(
                "ebs.folders.download_indices",
                e.target.value.split(",").map((x) => parseInt(x.trim(), 10)).filter((n) => !isNaN(n))
              )
            }
          />
        </Field>
        <Field label="Índice de upload">
          <input
            className="input mono"
            value={g("ebs.folders.upload_index")}
            onChange={(e) => set("ebs.folders.upload_index", parseInt(e.target.value, 10) || 0)}
          />
        </Field>
      </SettingsCard>

      <SettingsCard title="Credenciais">
        <Field label="E-mail" span>{text("credentials.email")}</Field>
        <Field label="Senha" span>{text("credentials.password", false, "password")}</Field>
      </SettingsCard>

      <SettingsCard title="Oracle (banco de origem)">
        <Field label="Usuário">{text("oracle.user")}</Field>
        <Field label="Senha">{text("oracle.password", false, "password")}</Field>
        <Field label="Customer ID" help="WND.CUSTOMER_ID">{text("oracle.customer_id", true)}</Field>
        <Field label="Meses retroativos" help="Janela buscada a cada sync">
          <input className="input mono" type="number" value={g("oracle.lookback_months")}
            onChange={(e) => set("oracle.lookback_months", parseInt(e.target.value, 10) || 0)} />
        </Field>
        <Field label="DSN" help="host:porta/service_name ou alias TNS" span>{text("oracle.dsn", true)}</Field>

        <div className="field col-span" style={{ borderTop: "1px solid var(--border)", paddingTop: 16, marginTop: 4 }}>
          <div className="page-eyebrow" style={{ marginBottom: 12 }}>Conexão via JDBC (Java) — não precisa de Oracle Client</div>
        </div>
        {pathRow("JDBC jar", "oracle.jdbc_jar", "any", "ojdbc8.jar ou ojdbc11.jar — conexão via JDBC (jaydebeapi), funciona com verifiers antigos (ex: 10g).")}
        {pathRow("JVM path", "oracle.jvm_path", "dir", "JDK home ou pasta bin (ex: C:/Users/.../.jdks/openjdk-25/bin). Vazio = detectar pelo JAVA_HOME/PATH.")}
      </SettingsCard>

      {err && (
        <div className="alert">
          <div>
            <div className="title">Erro ao salvar</div>
            <div className="msg">{err}</div>
          </div>
        </div>
      )}

      <div className="card">
        <div className="card-foot">
          {saved && (
            <span className="pill success" style={{ marginRight: "auto" }}>
              <span className="dot" /> Salvo
            </span>
          )}
          {exported && (
            <span className="pill success" style={{ marginRight: saved ? 0 : "auto" }}>
              <span className="dot" /> Exportado
            </span>
          )}
          <button className="btn btn-secondary" onClick={exportCfg}>
            Exportar configurações
          </button>
          <button className="btn btn-primary" onClick={save}>
            <Icon name="check" /> Salvar configurações
          </button>
        </div>
      </div>
    </>
  );
}

/* ───────────── Debug log panel ───────────── */
function LogPanel({ logs, onClear, onClose }) {
  const bodyRef = useRef(null);
  useEffect(() => {
    const el = bodyRef.current;
    if (el) {
      // Only auto-scroll when already at the bottom so selection isn't interrupted.
      const atBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 40;
      if (atBottom) el.scrollTop = el.scrollHeight;
    }
  }, [logs]);

  return (
    <div className="logpanel">
      <div className="logpanel-head">
        <span className="logpanel-title"><Icon name="bug" /> Debug · processo do programa</span>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn btn-ghost btn-sm" onClick={onClear}>Limpar</button>
          <button className="btn btn-secondary btn-sm" onClick={onClose}>Fechar</button>
        </div>
      </div>
      <div className="logpanel-body" ref={bodyRef}>
        {logs.length === 0 ? (
          <div className="logpanel-empty">Sem registros ainda. Inicie uma operação.</div>
        ) : (
          logs.map((line, i) => (
            <div key={i} className={"logline" + lineLevel(line)}>{line}</div>
          ))
        )}
      </div>
    </div>
  );
}

// Color hint from the "LEVELNAME: ..." prefix the Python handler emits.
const lineLevel = (l) =>
  l.startsWith("ERROR") || l.startsWith("CRITICAL") ? " err"
    : l.startsWith("WARNING") ? " warn" : "";

/* ───────────── Icons (line, 1.5px, currentColor) ───────────── */
function Icon({ name }) {
  const paths = {
    check: <path d="M5 12l4 4 10-11" />,
    sun: <><circle cx="12" cy="12" r="4" /><path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M18.4 5.6L17 7M7 17l-1.4 1.4" /></>,
    moon: <path d="M20 14a8 8 0 1 1-9.5-9.8A6.5 6.5 0 0 0 20 14z" />,
    bug: <><path d="M9 9V7a3 3 0 0 1 6 0v2" /><rect x="7" y="9" width="10" height="9" rx="5" /><path d="M3 13h4M17 13h4M4 8l3 2M20 8l-3 2M4 18l3-2M20 18l-3-2" /></>,
    expand: <path d="M8 3H5a2 2 0 0 0-2 2v3M16 3h3a2 2 0 0 1 2 2v3M8 21H5a2 2 0 0 1-2-2v-3M16 21h3a2 2 0 0 0 2-2v-3" />,
  };
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      style={{ strokeWidth: 1.8, strokeLinecap: "round", strokeLinejoin: "round" }}>
      {paths[name]}
    </svg>
  );
}
