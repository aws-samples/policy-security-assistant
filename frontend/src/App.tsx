import { useState, useRef, useEffect } from "react";
import Markdown from "react-markdown";
import Findings, { type Finding } from "./Findings";

// API calls go through CloudFront as relative paths — no config needed
const API_BASE = "/api";

const SAMPLE_POLICY = JSON.stringify(
  {
    Version: "2012-10-17",
    Statement: [
      {
        Action: "ec2:*",
        Resource: "*",
        Effect: "Allow",
        Condition: { StringEquals: { "ec2:Region": "us-east-2" } },
      },
    ],
  },
  null,
  2
);

type Lang = "en" | "es" | "pt";
type Tab = "analyze" | "generate";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  policy?: string;
  explanation?: string;
  aa_findings?: Finding[];
  isInitialPolicy?: boolean; // marks the first message with the policy textarea
}

export default function App() {
  const [tab, setTab] = useState<Tab>("analyze");
  const [lang, setLang] = useState<Lang>("en");
  const [loading, setLoading] = useState(false);

  // Analyze chat state
  const [analyzePolicy, setAnalyzePolicy] = useState(SAMPLE_POLICY);
  const [analyzeMsgs, setAnalyzeMsgs] = useState<ChatMessage[]>([]);
  const [analyzeInput, setAnalyzeInput] = useState("");
  const [analyzeError, setAnalyzeError] = useState("");
  const [analyzeSubmitted, setAnalyzeSubmitted] = useState(false);
  const analyzeEndRef = useRef<HTMLDivElement>(null);

  // Generate chat state
  const [genMsgs, setGenMsgs] = useState<ChatMessage[]>([]);
  const [genInput, setGenInput] = useState(
    "A Lambda function that reads from a DynamoDB table called 'orders' in us-east-1 and writes logs to CloudWatch"
  );
  const [genError, setGenError] = useState("");
  const genEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    analyzeEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [analyzeMsgs]);

  useEffect(() => {
    genEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [genMsgs]);

  // ── Analyze: initial submission ──
  const handleAnalyzeSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!analyzePolicy.trim()) return;
    setAnalyzeError("");
    setLoading(true);
    setAnalyzeSubmitted(true);

    const userMsg: ChatMessage = {
      role: "user",
      content: analyzePolicy,
      isInitialPolicy: true,
    };
    const updated = [userMsg];
    setAnalyzeMsgs(updated);

    try {
      const res = await fetch(`${API_BASE}/security-assistant`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ policy: analyzePolicy, lang }),
      });
      let data = await res.json();
      if (!res.ok) { setAnalyzeError(data.error || `Request failed (${res.status})`); return; }
      if (typeof data.body === "string") { data = JSON.parse(data.body); }

      const assistantMsg: ChatMessage = {
        role: "assistant",
        content: data.message,
        explanation: data.message,
        aa_findings: data.aa_findings || [],
      };
      setAnalyzeMsgs([...updated, assistantMsg]);
    } catch {
      setAnalyzeError("Failed to connect to the API. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  // ── Analyze: follow-up message ──
  const handleAnalyzeFollowUp = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!analyzeInput.trim()) return;
    setAnalyzeError("");
    setLoading(true);

    const userMsg: ChatMessage = { role: "user", content: analyzeInput };
    const updated = [...analyzeMsgs, userMsg];
    setAnalyzeMsgs(updated);
    setAnalyzeInput("");

    try {
      const apiHistory = updated.slice(0, -1).map((m) => ({
        role: m.role,
        content: m.role === "user" && m.isInitialPolicy
          ? `Analyze the following IAM policy:\n\`\`\`json\n${m.content}\n\`\`\``
          : (m.explanation || m.content),
      }));

      const res = await fetch(`${API_BASE}/security-assistant`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          policy: analyzePolicy,
          message: analyzeInput,
          lang,
          messages: apiHistory,
        }),
      });
      let data = await res.json();
      if (!res.ok) { setAnalyzeError(data.error || `Request failed (${res.status})`); return; }
      if (typeof data.body === "string") { data = JSON.parse(data.body); }

      const assistantMsg: ChatMessage = {
        role: "assistant",
        content: data.message,
        explanation: data.message,
      };
      setAnalyzeMsgs([...updated, assistantMsg]);
    } catch {
      setAnalyzeError("Failed to connect to the API. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleAnalyzeReset = () => {
    setAnalyzeMsgs([]);
    setAnalyzeInput("");
    setAnalyzeError("");
    setAnalyzeSubmitted(false);
  };

  // ── Generate: send message ──
  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!genInput.trim()) return;
    setGenError("");
    setLoading(true);

    const userMsg: ChatMessage = { role: "user", content: genInput };
    const updated = [...genMsgs, userMsg];
    setGenMsgs(updated);
    setGenInput("");

    try {
      const apiHistory = updated.slice(0, -1).map((m) => ({
        role: m.role,
        content: m.content,
      }));

      const res = await fetch(`${API_BASE}/generate-policy`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ description: genInput, lang, messages: apiHistory }),
      });
      let data = await res.json();
      if (!res.ok) { setGenError(data.error || `Request failed (${res.status})`); return; }
      if (typeof data.body === "string") { try { data = JSON.parse(data.body); } catch {/* */} }

      const assistantMsg: ChatMessage = {
        role: "assistant",
        content: data.raw_assistant || JSON.stringify(data),
      };

      if (data.safe === true && data.policy) {
        const policyObj = typeof data.policy === "string" ? JSON.parse(data.policy) : data.policy;
        assistantMsg.policy = JSON.stringify(policyObj, null, 2);
        assistantMsg.explanation = data.explanation || "";
        if (data.aa_findings) assistantMsg.aa_findings = data.aa_findings;
      } else if (data.message) {
        assistantMsg.explanation = data.message;
      }

      setGenMsgs([...updated, assistantMsg]);
    } catch {
      setGenError("Failed to connect to the API. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleGenReset = () => {
    setGenMsgs([]);
    setGenInput("");
    setGenError("");
  };

  // ── Shared chat message renderer ──
  const renderAssistantMsg = (msg: ChatMessage, tabType: Tab) => (
    <>
      {msg.explanation && (
        <div className="chat-explanation">
          <Markdown>{msg.explanation}</Markdown>
        </div>
      )}
      {msg.aa_findings !== undefined && (msg.aa_findings.length > 0 || msg.isInitialPolicy === undefined) && (
        <Findings findings={msg.aa_findings} />
      )}
      {msg.policy && (
        <details className="chat-policy-details">
          <summary>
            <span>View {tabType === "generate" ? "generated" : "updated"} policy</span>
            <button className="btn-copy" type="button"
              onClick={(e) => { e.preventDefault(); navigator.clipboard.writeText(msg.policy!); }}>
              Copy
            </button>
          </summary>
          <pre><code>{msg.policy}</code></pre>
        </details>
      )}
      {!msg.policy && !msg.explanation && (
        <div className="chat-msg-text">{msg.content}</div>
      )}
    </>
  );

  return (
    <div className="container">
      <header className="header">
        <h1>Policy Security Assistant</h1>
        <p className="subtitle">Powered by Amazon Bedrock — Claude Sonnet 4.5</p>
      </header>

      <nav className="tabs" role="tablist">
        <button role="tab" aria-selected={tab === "analyze"}
          className={`tab ${tab === "analyze" ? "tab-active" : ""}`}
          onClick={() => setTab("analyze")}>
          Analyze Policy
        </button>
        <button role="tab" aria-selected={tab === "generate"}
          className={`tab ${tab === "generate" ? "tab-active" : ""}`}
          onClick={() => setTab("generate")}>
          Generate Policy
        </button>
      </nav>

      {/* ── ANALYZE TAB ── */}
      {tab === "analyze" && (
        <>
          {!analyzeSubmitted ? (
            <>
              <p className="instructions">
                Paste an IAM policy below to check if it follows the principle of least
                privilege. After the analysis, you can ask follow-up questions or request fixes.
              </p>
              <form onSubmit={handleAnalyzeSubmit}>
                <div className="form-group">
                  <label htmlFor="policy-input">IAM Policy (JSON)</label>
                  <textarea id="policy-input" rows={16} value={analyzePolicy}
                    onChange={(e) => setAnalyzePolicy(e.target.value)} spellCheck={false} />
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label htmlFor="lang-select">Response language</label>
                    <select id="lang-select" value={lang} onChange={(e) => setLang(e.target.value as Lang)}>
                      <option value="en">English</option>
                      <option value="es">Español</option>
                      <option value="pt">Português</option>
                    </select>
                  </div>
                  <button type="submit" disabled={loading} className="btn-primary">
                    {loading ? "Analyzing…" : "Analyze Policy"}
                  </button>
                </div>
              </form>
            </>
          ) : (
            <>
              <div className="chat-header">
                <p className="instructions">
                  Ask follow-up questions, request fixes, or ask to modify the policy.
                </p>
                <button className="btn-secondary" onClick={handleAnalyzeReset}>New analysis</button>
              </div>

              <div className="chat-container">
                {analyzeMsgs.map((msg, i) => (
                  <div key={i} className={`chat-msg chat-msg-${msg.role}`}>
                    <div className="chat-msg-label">{msg.role === "user" ? "You" : "Assistant"}</div>
                    {msg.role === "user" && msg.isInitialPolicy && (
                      <details className="chat-policy-details">
                        <summary><span>Submitted policy</span></summary>
                        <pre><code>{msg.content}</code></pre>
                      </details>
                    )}
                    {msg.role === "user" && !msg.isInitialPolicy && (
                      <div className="chat-msg-text">{msg.content}</div>
                    )}
                    {msg.role === "assistant" && renderAssistantMsg(msg, "analyze")}
                  </div>
                ))}
                {loading && <div className="chat-loading">Thinking…</div>}
                <div ref={analyzeEndRef} />
              </div>

              {analyzeError && <div className="error" role="alert">{analyzeError}</div>}

              <form onSubmit={handleAnalyzeFollowUp} className="chat-input-form">
                <div className="form-group" style={{ flex: 1 }}>
                  <label htmlFor="analyze-chat" className="sr-only">Message</label>
                  <textarea id="analyze-chat" rows={3} value={analyzeInput}
                    onChange={(e) => setAnalyzeInput(e.target.value)}
                    placeholder="e.g., 'Fix issue #2' or 'Restrict to instances tagged Environment=prod'…"
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleAnalyzeFollowUp(e); }
                    }}
                  />
                </div>
                <div className="chat-input-actions">
                  <select value={lang} onChange={(e) => setLang(e.target.value as Lang)}
                    aria-label="Response language">
                    <option value="en">EN</option>
                    <option value="es">ES</option>
                    <option value="pt">PT</option>
                  </select>
                  <button type="submit" disabled={loading || !analyzeInput.trim()} className="btn-primary">
                    {loading ? "…" : "Send"}
                  </button>
                </div>
              </form>
            </>
          )}
        </>
      )}

      {/* ── GENERATE TAB ── */}
      {tab === "generate" && (
        <>
          <div className="chat-header">
            <p className="instructions">
              Describe what permissions your application needs. You can refine the
              policy through conversation — ask to add conditions, change regions,
              restrict resources, etc.
            </p>
            {genMsgs.length > 0 && (
              <button className="btn-secondary" onClick={handleGenReset}>New conversation</button>
            )}
          </div>

          <div className="chat-container">
            {genMsgs.map((msg, i) => (
              <div key={i} className={`chat-msg chat-msg-${msg.role}`}>
                <div className="chat-msg-label">{msg.role === "user" ? "You" : "Assistant"}</div>
                {msg.role === "user" && <div className="chat-msg-text">{msg.content}</div>}
                {msg.role === "assistant" && renderAssistantMsg(msg, "generate")}
              </div>
            ))}
            {loading && <div className="chat-loading">Thinking…</div>}
            <div ref={genEndRef} />
          </div>

          {genError && <div className="error" role="alert">{genError}</div>}

          <form onSubmit={handleGenerate} className="chat-input-form">
            <div className="form-group" style={{ flex: 1 }}>
              <label htmlFor="gen-chat" className="sr-only">Message</label>
              <textarea id="gen-chat" rows={3} value={genInput}
                onChange={(e) => setGenInput(e.target.value)}
                placeholder={genMsgs.length === 0
                  ? "Describe the permissions you need…"
                  : "Refine the policy — e.g., 'restrict to us-east-1' or 'also allow S3 read'…"}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleGenerate(e); }
                }}
              />
            </div>
            <div className="chat-input-actions">
              <select value={lang} onChange={(e) => setLang(e.target.value as Lang)}
                aria-label="Response language">
                <option value="en">EN</option>
                <option value="es">ES</option>
                <option value="pt">PT</option>
              </select>
              <button type="submit" disabled={loading || !genInput.trim()} className="btn-primary">
                {loading ? "…" : "Send"}
              </button>
            </div>
          </form>
        </>
      )}

      <footer className="disclaimer">
        This solution is a demonstration. Automated policy analysis should be
        considered a suggestion. Validate with a security specialist before
        implementing any policy.
      </footer>
    </div>
  );
}
