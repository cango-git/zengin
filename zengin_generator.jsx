import { useState, useCallback } from "react";
import * as XLSX from "xlsx";

// ── 全銀固定長フォーマット生成ロジック ──────────────────────────────────

const pad = (str, len, padChar = " ", right = false) => {
  const s = String(str ?? "");
  if (right) return s.padStart(len, padChar).slice(-len);
  return s.padEnd(len, padChar).slice(0, len);
};
const padNum = (n, len) => String(n ?? 0).padStart(len, "0").slice(-len);
const padStr = (s, len) => pad(s, len, " ", false);

function buildHeader(h) {
  let rec = "";
  rec += "1";                                // データ区分
  rec += "21";                               // 種別コード(総合振込)
  rec += "0";                                // コード区分
  rec += padNum(h.clientCode, 10);           // 依頼人コード
  rec += padStr(h.clientName, 40);           // 依頼人名
  rec += h.transferDate.replace(/-/g, "").slice(4, 8); // 取組日 MMDD
  rec += padNum(h.bankCode, 4);              // 仕向銀行番号
  rec += padStr(h.bankName, 15);             // 仕向銀行名
  rec += padNum(h.branchCode, 3);            // 仕向支店番号
  rec += padStr(h.branchName, 15);           // 仕向支店名
  rec += h.accountType;                      // 預金種目
  rec += padNum(h.accountNumber, 7);         // 口座番号
  rec += " ".repeat(17);                     // ダミー
  return rec;
}

function buildData(row) {
  let rec = "";
  rec += "2";                                       // データ区分
  rec += padNum(row.bankCode, 4);                   // 銀行番号
  rec += padStr(row.bankName, 15);                  // 銀行名
  rec += padNum(row.branchCode, 3);                 // 支店番号
  rec += padStr(row.branchName, 15);                // 支店名
  rec += " ".repeat(4);                             // 手形交換所番号
  rec += String(row.accountType || "1");            // 預金種目
  rec += padNum(row.accountNumber, 7);              // 口座番号
  rec += padStr(row.recipientName, 30);             // 受取人名
  rec += padNum(row.amount, 10);                    // 振込金額
  rec += "0";                                       // 新規コード
  rec += " ".repeat(20);                            // EDI情報
  rec += "7";                                       // 振込指定区分(電信)
  rec += " ";                                       // 識別表示
  rec += " ".repeat(7);                             // ダミー
  return rec;
}

function buildTrailer(rows) {
  const count = rows.length;
  const total = rows.reduce((s, r) => s + Number(r.amount || 0), 0);
  let rec = "";
  rec += "8";
  rec += padNum(count, 6);
  rec += padNum(total, 12);
  rec += " ".repeat(101);
  return rec;
}

function buildEnd() {
  return "9" + " ".repeat(119);
}

// ── カラムマッピング設定 ───────────────────────────────────────────────

const DATA_FIELDS = [
  { key: "bankCode",      label: "銀行番号",   required: true },
  { key: "bankName",      label: "銀行名",     required: false },
  { key: "branchCode",    label: "支店番号",   required: true },
  { key: "branchName",    label: "支店名",     required: false },
  { key: "accountType",   label: "預金種目",   required: true, hint:"1=普通 2=当座 4=貯蓄" },
  { key: "accountNumber", label: "口座番号",   required: true },
  { key: "recipientName", label: "受取人名",   required: true },
  { key: "amount",        label: "振込金額",   required: true },
];

// ── コンポーネント ─────────────────────────────────────────────────────

const inputCls = "w-full bg-zinc-900 border border-zinc-700 rounded px-3 py-2 text-sm text-white placeholder-zinc-500 focus:outline-none focus:border-amber-400 transition-colors";
const labelCls = "block text-xs text-zinc-400 mb-1 font-medium tracking-wide";

export default function ZenginGenerator() {
  const [step, setStep] = useState(1);
  const [header, setHeader] = useState({
    clientCode: "", clientName: "", transferDate: "",
    bankCode: "", bankName: "", branchCode: "", branchName: "",
    accountType: "1", accountNumber: "",
  });
  const [csvHeaders, setCsvHeaders] = useState([]);
  const [csvRows, setCsvRows] = useState([]);
  const [mapping, setMapping] = useState({});
  const [output, setOutput] = useState("");
  const [preview, setPreview] = useState([]);
  const [error, setError] = useState("");

  const today = new Date().toISOString().slice(0, 10);

  // ── Step1: ヘッダー入力 ──
  const updateHeader = (k, v) => setHeader(p => ({ ...p, [k]: v }));

  const step1Valid = header.clientCode && header.clientName && header.transferDate
    && header.bankCode && header.bankName && header.branchCode && header.branchName
    && header.accountNumber;

  // ── Step2: ファイルアップロード ──
  const handleFile = useCallback((file) => {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const data = new Uint8Array(e.target.result);
        const wb = XLSX.read(data, { type: "array" });
        const ws = wb.Sheets[wb.SheetNames[0]];
        const json = XLSX.utils.sheet_to_json(ws, { header: 1 });
        if (!json.length) { setError("ファイルにデータがありません"); return; }
        const headers = json[0].map(String);
        const rows = json.slice(1).filter(r => r.some(c => c !== "" && c != null));
        setCsvHeaders(headers);
        setCsvRows(rows);
        // 自動マッピング
        const autoMap = {};
        DATA_FIELDS.forEach(f => {
          const match = headers.find(h =>
            h.includes(f.label) || h.toLowerCase().includes(f.key.toLowerCase())
          );
          if (match) autoMap[f.key] = match;
        });
        setMapping(autoMap);
        setError("");
      } catch {
        setError("ファイルの読み込みに失敗しました");
      }
    };
    reader.readAsArrayBuffer(file);
  }, []);

  const onDrop = (e) => {
    e.preventDefault();
    handleFile(e.dataTransfer.files[0]);
  };

  const step2Valid = csvRows.length > 0 &&
    DATA_FIELDS.filter(f => f.required).every(f => mapping[f.key]);

  // ── Step3: 生成 ──
  const generate = () => {
    try {
      const dataRows = csvRows.map(row => {
        const obj = {};
        DATA_FIELDS.forEach(f => {
          const col = mapping[f.key];
          if (col) {
            const idx = csvHeaders.indexOf(col);
            obj[f.key] = idx >= 0 ? row[idx] : "";
          } else {
            obj[f.key] = "";
          }
        });
        return obj;
      });

      const lines = [
        buildHeader(header),
        ...dataRows.map(buildData),
        buildTrailer(dataRows),
        buildEnd(),
      ];
      const text = lines.join("\r\n");
      setOutput(text);
      setPreview(lines);
      setStep(3);
    } catch (err) {
      setError("生成エラー: " + err.message);
    }
  };

  const download = () => {
    // Shift-JIS encoding would be ideal; here we use UTF-8 with BOM note
    const blob = new Blob([output], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `zengin_${header.transferDate.replace(/-/g, "")}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // ── UI ──────────────────────────────────────────────────────────────

  const steps = ["依頼人情報", "データ読込", "生成・確認"];

  return (
    <div style={{ fontFamily: "'Noto Sans JP', sans-serif", background: "#0f0f0f", minHeight: "100vh", color: "#e4e4e4" }}>
      <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@300;400;500;700&family=IBM+Plex+Mono:wght@400;600&display=swap" rel="stylesheet" />

      {/* Header */}
      <div style={{ borderBottom: "1px solid #2a2a2a", padding: "20px 32px", display: "flex", alignItems: "center", gap: 16 }}>
        <div style={{ width: 8, height: 8, borderRadius: "50%", background: "#f59e0b" }} />
        <span style={{ fontFamily: "'IBM Plex Mono'", fontSize: 13, color: "#f59e0b", letterSpacing: 2 }}>全銀協フォーマット</span>
        <span style={{ fontSize: 13, color: "#666" }}>総合振込ファイル生成</span>
      </div>

      <div style={{ maxWidth: 780, margin: "0 auto", padding: "32px 24px" }}>

        {/* Step indicator */}
        <div style={{ display: "flex", gap: 0, marginBottom: 40 }}>
          {steps.map((s, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", flex: 1 }}>
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6, flex: 1 }}>
                <div style={{
                  width: 32, height: 32, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 12, fontWeight: 600, fontFamily: "'IBM Plex Mono'",
                  background: step === i + 1 ? "#f59e0b" : step > i + 1 ? "#166534" : "#1a1a1a",
                  color: step === i + 1 ? "#000" : step > i + 1 ? "#4ade80" : "#666",
                  border: step > i + 1 ? "1px solid #166534" : "1px solid #333",
                  transition: "all .3s"
                }}>
                  {step > i + 1 ? "✓" : i + 1}
                </div>
                <span style={{ fontSize: 11, color: step === i + 1 ? "#f59e0b" : "#555" }}>{s}</span>
              </div>
              {i < 2 && <div style={{ height: 1, flex: 0.5, background: step > i + 1 ? "#166534" : "#2a2a2a", marginBottom: 20 }} />}
            </div>
          ))}
        </div>

        {error && (
          <div style={{ background: "#3f1515", border: "1px solid #7f1d1d", borderRadius: 8, padding: "12px 16px", marginBottom: 20, fontSize: 13, color: "#fca5a5" }}>
            ⚠ {error}
          </div>
        )}

        {/* ─── STEP 1 ─── */}
        {step === 1 && (
          <div>
            <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 24, color: "#fff" }}>依頼人情報の入力</h2>

            <SectionCard title="依頼人">
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                <Field label="依頼人コード *" hint="10桁以内の数字">
                  <input className={inputCls} style={iStyle} maxLength={10} placeholder="0000000001"
                    value={header.clientCode} onChange={e => updateHeader("clientCode", e.target.value)} />
                </Field>
                <Field label="依頼人名 *" hint="全角カタカナ・40文字以内">
                  <input className={inputCls} style={iStyle} maxLength={40} placeholder="カブシキガイシャサンプル"
                    value={header.clientName} onChange={e => updateHeader("clientName", e.target.value)} />
                </Field>
                <Field label="取組日 *" hint="振込指定日">
                  <input className={inputCls} style={iStyle} type="date" min={today}
                    value={header.transferDate} onChange={e => updateHeader("transferDate", e.target.value)} />
                </Field>
              </div>
            </SectionCard>

            <SectionCard title="仕向銀行（依頼人口座）">
              <div style={{ display: "grid", gridTemplateColumns: "120px 1fr 100px 1fr", gap: 16, alignItems: "start" }}>
                <Field label="銀行番号 *">
                  <input className={inputCls} style={iStyle} maxLength={4} placeholder="0001"
                    value={header.bankCode} onChange={e => updateHeader("bankCode", e.target.value)} />
                </Field>
                <Field label="銀行名 *">
                  <input className={inputCls} style={iStyle} maxLength={15} placeholder="ニホンギンコウ"
                    value={header.bankName} onChange={e => updateHeader("bankName", e.target.value)} />
                </Field>
                <Field label="支店番号 *">
                  <input className={inputCls} style={iStyle} maxLength={3} placeholder="001"
                    value={header.branchCode} onChange={e => updateHeader("branchCode", e.target.value)} />
                </Field>
                <Field label="支店名 *">
                  <input className={inputCls} style={iStyle} maxLength={15} placeholder="ホンテン"
                    value={header.branchName} onChange={e => updateHeader("branchName", e.target.value)} />
                </Field>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "140px 160px", gap: 16, marginTop: 16 }}>
                <Field label="預金種目 *">
                  <select value={header.accountType} onChange={e => updateHeader("accountType", e.target.value)}
                    style={{ ...iStyle, background: "#0f0f0f", border: "1px solid #3f3f3f", borderRadius: 6, padding: "8px 12px", fontSize: 13, color: "#e4e4e4", width: "100%" }}>
                    <option value="1">1 : 普通</option>
                    <option value="2">2 : 当座</option>
                  </select>
                </Field>
                <Field label="口座番号 *" hint="7桁">
                  <input className={inputCls} style={iStyle} maxLength={7} placeholder="1234567"
                    value={header.accountNumber} onChange={e => updateHeader("accountNumber", e.target.value)} />
                </Field>
              </div>
            </SectionCard>

            <div style={{ display: "flex", justifyContent: "flex-end" }}>
              <Btn disabled={!step1Valid} onClick={() => setStep(2)} primary>
                次へ → データ読込
              </Btn>
            </div>
          </div>
        )}

        {/* ─── STEP 2 ─── */}
        {step === 2 && (
          <div>
            <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 24, color: "#fff" }}>ファイルアップロード・列マッピング</h2>

            {/* Drop zone */}
            <div
              onDrop={onDrop}
              onDragOver={e => e.preventDefault()}
              style={{
                border: "2px dashed #3a3a3a", borderRadius: 12, padding: "40px 24px",
                textAlign: "center", cursor: "pointer", marginBottom: 24,
                background: "#141414", transition: "border-color .2s"
              }}
              onMouseEnter={e => e.currentTarget.style.borderColor = "#f59e0b"}
              onMouseLeave={e => e.currentTarget.style.borderColor = "#3a3a3a"}
              onClick={() => document.getElementById("fileInput").click()}
            >
              <div style={{ fontSize: 32, marginBottom: 12 }}>📂</div>
              <div style={{ fontSize: 14, color: "#aaa" }}>
                {csvRows.length > 0
                  ? <><span style={{ color: "#4ade80" }}>✓ {csvRows.length}件読込済</span> — クリックで再選択</>
                  : <>Excel / CSV をドロップ、またはクリックして選択</>}
              </div>
              <input id="fileInput" type="file" accept=".xlsx,.xls,.csv" style={{ display: "none" }}
                onChange={e => handleFile(e.target.files[0])} />
            </div>

            {csvHeaders.length > 0 && (
              <SectionCard title="列マッピング設定">
                <p style={{ fontSize: 12, color: "#666", marginBottom: 16 }}>アップロードしたファイルの列を全銀フィールドに対応付けてください</p>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 24px 1fr", gap: "12px 8px", alignItems: "center" }}>
                  {DATA_FIELDS.map(f => (
                    <>
                      <div key={f.key + "l"}>
                        <div style={{ fontSize: 12, fontWeight: 600, color: f.required ? "#f59e0b" : "#aaa" }}>
                          {f.label}{f.required && " *"}
                        </div>
                        {f.hint && <div style={{ fontSize: 10, color: "#555" }}>{f.hint}</div>}
                      </div>
                      <div key={f.key + "a"} style={{ textAlign: "center", color: "#444", fontSize: 12 }}>→</div>
                      <select key={f.key + "s"}
                        value={mapping[f.key] || ""}
                        onChange={e => setMapping(p => ({ ...p, [f.key]: e.target.value }))}
                        style={{ background: "#0f0f0f", border: `1px solid ${mapping[f.key] ? "#4ade80" : "#3a3a3a"}`, borderRadius: 6, padding: "7px 10px", fontSize: 12, color: "#e4e4e4", width: "100%" }}>
                        <option value="">-- 列を選択 --</option>
                        {csvHeaders.map(h => <option key={h} value={h}>{h}</option>)}
                      </select>
                    </>
                  ))}
                </div>

                {/* Preview */}
                {csvRows.length > 0 && (
                  <div style={{ marginTop: 20 }}>
                    <div style={{ fontSize: 12, color: "#666", marginBottom: 8 }}>プレビュー（先頭3件）</div>
                    <div style={{ overflowX: "auto" }}>
                      <table style={{ width: "100%", fontSize: 11, borderCollapse: "collapse" }}>
                        <thead>
                          <tr>
                            {csvHeaders.map(h => (
                              <th key={h} style={{ padding: "6px 10px", borderBottom: "1px solid #2a2a2a", color: "#888", textAlign: "left", whiteSpace: "nowrap" }}>{h}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {csvRows.slice(0, 3).map((row, i) => (
                            <tr key={i}>
                              {csvHeaders.map((_, j) => (
                                <td key={j} style={{ padding: "6px 10px", borderBottom: "1px solid #1a1a1a", color: "#ccc", whiteSpace: "nowrap" }}>
                                  {row[j] ?? ""}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </SectionCard>
            )}

            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <Btn onClick={() => setStep(1)}>← 戻る</Btn>
              <Btn disabled={!step2Valid} onClick={generate} primary>
                固定長ファイルを生成
              </Btn>
            </div>
          </div>
        )}

        {/* ─── STEP 3 ─── */}
        {step === 3 && (
          <div>
            <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 8, color: "#fff" }}>生成完了</h2>
            <p style={{ fontSize: 13, color: "#666", marginBottom: 24 }}>
              {csvRows.length}件のデータレコードを含む全銀固定長ファイルを生成しました
            </p>

            {/* Stats */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 12, marginBottom: 24 }}>
              {[
                ["総レコード数", `${preview.length}件`],
                ["データ件数", `${csvRows.length}件`],
                ["合計金額", `¥${csvRows.reduce((s,r)=>{
                  const colIdx = mapping.amount ? csvHeaders.indexOf(mapping.amount) : -1;
                  return s + Number(colIdx>=0?r[colIdx]:0||0);
                },0).toLocaleString()}`],
              ].map(([k,v]) => (
                <div key={k} style={{ background: "#141414", border: "1px solid #2a2a2a", borderRadius: 8, padding: "16px 20px" }}>
                  <div style={{ fontSize: 11, color: "#666", marginBottom: 6 }}>{k}</div>
                  <div style={{ fontSize: 20, fontWeight: 700, fontFamily: "'IBM Plex Mono'", color: "#f59e0b" }}>{v}</div>
                </div>
              ))}
            </div>

            {/* Preview */}
            <SectionCard title="レコードプレビュー">
              <div style={{ overflowX: "auto" }}>
                {preview.map((line, i) => {
                  const type = line[0];
                  const label = type === "1" ? "ヘッダー" : type === "2" ? `データ #${i}` : type === "8" ? "トレーラー" : "エンド";
                  const color = type === "1" ? "#f59e0b" : type === "2" ? "#60a5fa" : type === "8" ? "#a78bfa" : "#666";
                  if (i > 5 && type === "2") return i === 6 ? (
                    <div key="ellipsis" style={{ textAlign: "center", color: "#444", padding: "4px 0", fontSize: 12 }}>…他{csvRows.length - 3}件省略…</div>
                  ) : null;
                  if (i > 3 && type === "2" && i < preview.length - 2) return null;
                  return (
                    <div key={i} style={{ display: "flex", gap: 12, alignItems: "baseline", marginBottom: 6 }}>
                      <span style={{ fontSize: 10, color, minWidth: 70, fontFamily: "'IBM Plex Mono'" }}>{label}</span>
                      <code style={{ fontSize: 10, color: "#888", fontFamily: "'IBM Plex Mono'", wordBreak: "break-all", background: "#0a0a0a", padding: "4px 8px", borderRadius: 4, flex: 1 }}>
                        {line.slice(0, 60)}<span style={{ color: "#444" }}>{line.length > 60 ? "…" : ""}</span>
                      </code>
                      <span style={{ fontSize: 10, color: "#444" }}>{line.length}文字</span>
                    </div>
                  );
                })}
              </div>
            </SectionCard>

            <div style={{ background: "#1a1500", border: "1px solid #854d0e", borderRadius: 8, padding: "12px 16px", marginBottom: 24, fontSize: 12, color: "#fbbf24" }}>
              ⚠ ダウンロードファイルはUTF-8です。ご利用の銀行システムがShift-JISを要求する場合は、テキストエディタ等で文字コードを変換してください。
            </div>

            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <Btn onClick={() => setStep(2)}>← 戻る</Btn>
              <Btn primary onClick={download}>⬇ ファイルをダウンロード (.txt)</Btn>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── 小コンポーネント ──────────────────────────────────────────────────

const iStyle = { background: "#0f0f0f", border: "1px solid #3f3f3f", borderRadius: 6, padding: "8px 12px", fontSize: 13, color: "#e4e4e4", width: "100%", outline: "none" };

function SectionCard({ title, children }) {
  return (
    <div style={{ background: "#141414", border: "1px solid #262626", borderRadius: 10, padding: 24, marginBottom: 20 }}>
      <div style={{ fontSize: 12, fontWeight: 600, color: "#666", letterSpacing: 1, textTransform: "uppercase", marginBottom: 16 }}>{title}</div>
      {children}
    </div>
  );
}

function Field({ label, hint, children }) {
  return (
    <div>
      <label style={{ display: "block", fontSize: 11, color: "#888", marginBottom: 6, fontWeight: 500 }}>{label}</label>
      {children}
      {hint && <div style={{ fontSize: 10, color: "#555", marginTop: 4 }}>{hint}</div>}
    </div>
  );
}

function Btn({ children, onClick, disabled, primary }) {
  return (
    <button onClick={onClick} disabled={disabled} style={{
      padding: "10px 24px", borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: disabled ? "not-allowed" : "pointer",
      background: primary ? (disabled ? "#3a2d00" : "#f59e0b") : "#1a1a1a",
      color: primary ? (disabled ? "#665500" : "#000") : "#aaa",
      border: primary ? "none" : "1px solid #333",
      transition: "all .2s", opacity: disabled ? 0.5 : 1,
    }}>
      {children}
    </button>
  );
}
