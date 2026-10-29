/** AI Assistant: a conversational front-end over the grounded, local-first
 * assistant. It answers only from your saved records; every figure comes
 * straight from the API (never fabricated) and every change it wants to make
 * is shown as a proposal you must confirm before anything is written. The
 * optional local language model is offered here but never loaded by itself —
 * you press Load, and you can free it again with Unload. */
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../services/api";
import { formatMinor } from "../lib/money";
import type {
  AssistantCard,
  AssistantMessage,
  AssistantModelStatus,
  ProposedAction,
  SendResponse,
} from "../types/api";

function MetricCard({ card }: { card: Extract<AssistantCard, { kind: "metrics" }> }) {
  return (
    <div className="card metric-card">
      <h3>{card.title}</h3>
      <div className="metric-grid">
        {card.items.map((m) => (
          <div key={m.label} className="metric">
            <span className="metric-label">{m.label}</span>
            <span className="metric-value">
              {m.minor !== null ? formatMinor(m.minor) : m.text ?? "—"}
            </span>
            {m.hint && <span className="metric-hint muted">{m.hint}</span>}
          </div>
        ))}
      </div>
    </div>
  );
}

function ListCard({ card }: { card: Extract<AssistantCard, { kind: "list" }> }) {
  return (
    <div className="card list-card">
      <h3>{card.title}</h3>
      <ul className="result-list">
        {card.rows.map((r, i) => (
          <li key={i} className="result-row">
            <div className="result-row-head">
              <strong>{r.heading}</strong>
              {r.sub && <span className="muted"> · {r.sub}</span>}
              {r.badge && <span className="badge">{r.badge}</span>}
              {r.minor !== null && (
                <span className="result-amount">{formatMinor(r.minor)}</span>
              )}
            </div>
            {r.lines.length > 0 && (
              <div className="result-lines muted">{r.lines.join(" · ")}</div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function ProposalCard({
  proposal,
  onConfirm,
  onDismiss,
  busy,
}: {
  proposal: ProposedAction;
  onConfirm: (id: number) => void;
  onDismiss: (id: number) => void;
  busy: boolean;
}) {
  return (
    <div className="card proposal-card">
      <div className="proposal-head">
        <span className="badge">{proposal.status}</span>
        <strong>{proposal.title}</strong>
      </div>
      <p className="muted">
        Nothing is saved until you confirm. This is a suggestion only.
      </p>
      {proposal.status === "pending" && (
        <div className="btn-row">
          <button
            className="btn primary"
            disabled={busy}
            onClick={() => onConfirm(proposal.id)}
          >
            Confirm &amp; apply
          </button>
          <button className="btn" disabled={busy} onClick={() => onDismiss(proposal.id)}>
            Dismiss
          </button>
        </div>
      )}
      {proposal.status === "confirmed" && (
        <p className="muted">Confirmed — the records above have been written.</p>
      )}
      {proposal.status === "dismissed" && <p className="muted">Dismissed.</p>}
    </div>
  );
}

const STATE_LABEL: Record<AssistantModelStatus["state"], string> = {
  unloaded: "Not loaded",
  loading: "Loading…",
  ready: "Ready",
  failed: "Failed",
};

/** Badge + Load/Unload control for the optional local model. Hidden entirely
 * when the backend doesn't offer the feature, so nothing implies a load. */
function ModelBar({
  status,
  busy,
  onLoad,
  onUnload,
}: {
  status: AssistantModelStatus;
  busy: boolean;
  onLoad: () => void;
  onUnload: () => void;
}) {
  if (!status.enabled) return null;

  const size = status.size_mb !== null ? ` · ${Math.round(status.size_mb)} MB` : "";
  const loading = status.state === "loading";

  return (
    <div className="card model-bar">
      <div className="model-bar-head">
        <span className={`badge ${status.state === "ready" ? "active" : status.state === "failed" ? "expense" : loading ? "transfer" : ""}`}>
          {STATE_LABEL[status.state]}
        </span>
        <strong>Local language model</strong>
        <span className="muted">
          {status.model_file ? (
            <>
              <span className="model-file">{status.model_file}</span>
              {size ? ` ${size}` : ""}
            </>
          ) : (
            "no model file found"
          )}
        </span>
      </div>

      <p className="muted">
        Off until you load it — the app never starts this model by itself. When
        it is loaded it helps the on-device router: it can pick which tool to
        run, reword a summary, and answer questions the router would otherwise
        miss - always grounded on your own saved records and the built-in help.
        Every number still comes from your records, and any reply that
        introduces a new figure is rejected. Unload frees the memory again.
      </p>

      {status.error && <p className="error-banner">{status.error}</p>}

      <div className="btn-row">
        {status.state === "ready" ? (
          <button className="btn" disabled={busy} onClick={onUnload}>
            Unload model
          </button>
        ) : (
          <button
            className="btn primary"
            disabled={busy || loading || !status.available}
            onClick={onLoad}
          >
            {loading ? "Loading…" : "Load model"}
          </button>
        )}
        <span className="muted model-bar-meta">
          {status.threads} threads · {status.ctx} token context
        </span>
      </div>
    </div>
  );
}

export function AssistantPage() {
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [convoId, setConvoId] = useState<number | null>(null);
  const [input, setInput] = useState("");
  const [assetId, setAssetId] = useState("");
  const [busy, setBusy] = useState(false);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [model, setModel] = useState<AssistantModelStatus | null>(null);
  const [modelBusy, setModelBusy] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const refreshModel = useCallback(() => {
    api<AssistantModelStatus>("/api/assistant/model")
      .then(setModel)
      .catch(() => {});
  }, []);

  useEffect(() => {
    api<string[]>("/api/assistant/suggestions").then(setSuggestions).catch(() => {});
    refreshModel();
  }, [refreshModel]);

  // A load runs in the background, so poll until the state settles.
  useEffect(() => {
    if (model?.state !== "loading") return;
    const timer = setInterval(refreshModel, 700);
    return () => clearInterval(timer);
  }, [model?.state, refreshModel]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView?.({ behavior: "smooth" });
  }, [messages]);

  async function newChat() {
    setMessages([]);
    setConvoId(null);
    setInput("");
    setAssetId("");
    setError(null);
  }

  async function changeModel(action: "load" | "unload") {
    setModelBusy(true);
    setError(null);
    try {
      setModel(await api<AssistantModelStatus>(`/api/assistant/model/${action}`, {
        method: "POST",
      }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setModelBusy(false);
    }
  }

  async function send(text: string) {
    const message = text.trim();
    if (!message || busy) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api<SendResponse>("/api/assistant/messages", {
        method: "POST",
        body: {
          message,
          conversation_id: convoId,
          asset_id: assetId.trim() || null,
        },
      });
      setConvoId(res.conversation_id);
      setMessages((prev) => [...prev, res.user_message, res.assistant_message]);
      setInput("");
      setAssetId("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function resolveProposal(id: number, action: "confirm" | "dismiss") {
    setBusy(true);
    setError(null);
    try {
      if (action === "confirm") {
        const res = await api<{ proposal: ProposedAction; assistant_message: AssistantMessage }>(
          `/api/assistant/proposals/${id}/confirm`,
          { method: "POST" },
        );
        setMessages((prev) => {
          const updated = prev.map((m) =>
            m.proposal?.id === id ? { ...m, proposal: res.proposal } : m,
          );
          return [...updated, res.assistant_message];
        });
      } else {
        const proposal = await api<ProposedAction>(`/api/assistant/proposals/${id}/dismiss`, {
          method: "POST",
        });
        setMessages((prev) =>
          prev.map((m) => (m.proposal?.id === id ? { ...m, proposal } : m)),
        );
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  // Re-render the interactive proposal from message state.
  function renderMessage(msg: AssistantMessage) {
    return (
      <div key={msg.id} className={`chat-bubble ${msg.role}`}>
        <p className="chat-text">{msg.content}</p>
        {msg.cards?.map((card, i) =>
          card.kind === "metrics" ? (
            <MetricCard key={i} card={card} />
          ) : (
            <ListCard key={i} card={card} />
          ),
        )}
        {msg.proposal && (
          <ProposalCard
            proposal={msg.proposal}
            busy={busy}
            onConfirm={(pid) => resolveProposal(pid, "confirm")}
            onDismiss={(pid) => resolveProposal(pid, "dismiss")}
          />
        )}
      </div>
    );
  }

  return (
    <div className="assistant-page">
      <div className="page-header">
        <h1>AI Assistant</h1>
        {convoId !== null && (
          <button className="btn" onClick={newChat} disabled={busy}>
            New chat
          </button>
        )}
      </div>

      <p className="muted">
        I answer only from your saved records — I never invent data. A change I
        suggest (a task or inventory item) is saved only after you confirm it.
      </p>

      {model && (
        <ModelBar
          status={model}
          busy={modelBusy}
          onLoad={() => changeModel("load")}
          onUnload={() => changeModel("unload")}
        />
      )}

      <div className="chat-log">
        {messages.length === 0 && (
          <div className="card empty-state">
            <p>Ask me something about your LifeSmart data:</p>
            <div className="chip-row">
              {suggestions.map((s) => (
                <button key={s} className="chip" disabled={busy} onClick={() => send(s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map(renderMessage)}
        <div ref={bottomRef} />
      </div>

      {error && (
        <p className="error-banner" role="alert">
          {error}
        </p>
      )}

      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
      >
        <input
          className="composer-input"
          placeholder="e.g. What am I missing in my wardrobe?"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={busy}
        />
        <input
          className="composer-asset"
          placeholder="Image asset id (optional)"
          value={assetId}
          onChange={(e) => setAssetId(e.target.value)}
          disabled={busy}
        />
        <button className="btn primary" type="submit" disabled={busy || !input.trim()}>
          {busy ? "Thinking…" : "Send"}
        </button>
      </form>
    </div>
  );
}
