import { useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "../api/client";
import Header from "../components/Header";
import ConversationSidebar from "../components/ConversationSidebar";
import MessageBubble from "../components/MessageBubble";

interface Conversation {
  id: string;
  title: string | null;
  updated_at: string;
  project_id: string | null;
}

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources: any[];
}

interface Source {
  document_id: string;
  title: string;
  source: string;
  source_url: string | null;
  score: number;
  excerpt: string;
}

export default function Chat() {
  const { conversationId } = useParams<{ conversationId?: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation();

  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const [streamingSources, setStreamingSources] = useState<Source[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.get("/chat").then(({ data }) => setConversations(data.items)).catch(() => {});
  }, []);

  useEffect(() => {
    if (!conversationId) {
      setMessages([]);
      return;
    }
    api.get(`/chat/${conversationId}`)
      .then(({ data }) => setMessages(data.messages))
      .catch(() => navigate("/chat"));
  }, [conversationId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingContent]);

  const handleNew = async () => {
    setMessages([]);
    navigate("/chat");
  };

  const handleSend = async () => {
    if (!input.trim() || streaming) return;
    const text = input.trim();
    setInput("");

    let activeConversationId = conversationId;

    if (!activeConversationId) {
      const { data } = await api.post("/chat", { first_message: text });
      activeConversationId = data.id;
      setConversations((prev) => [data, ...prev]);
      navigate(`/chat/${activeConversationId}`, { replace: true });
    }

    const tempUserMsg: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: text,
      sources: [],
    };
    setMessages((prev) => [...prev, tempUserMsg]);
    setStreaming(true);
    setStreamingContent("");
    setStreamingSources([]);

    try {
      const resp = await fetch(
        `${import.meta.env.VITE_API_URL}/chat/${activeConversationId}/messages`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${localStorage.getItem("rastro_token")}`,
          },
          body: JSON.stringify({ message: text, language: localStorage.getItem("rastro_lang") || "es" }),
        }
      );

      const reader = resp.body!.getReader();
      const decoder = new TextDecoder();
      let fullContent = "";
      let finalSources: Source[] = [];

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const lines = decoder.decode(value).split("\n");
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const event = JSON.parse(line.slice(6));
          if (event.type === "token") {
            fullContent += event.content;
            setStreamingContent(fullContent);
          }
          if (event.type === "sources") {
            finalSources = event.sources;
            setStreamingSources(finalSources);
          }
          if (event.type === "done") {
            setMessages((prev) => [
              ...prev,
              { id: crypto.randomUUID(), role: "assistant", content: fullContent, sources: finalSources },
            ]);
            setStreamingContent("");
            setStreamingSources([]);
            setStreaming(false);
          }
        }
      }
    } catch {
      setStreaming(false);
    }
  };

  return (
    <div className="r-chat-page">
      <Header />

      <div className="r-chat-body">
        <ConversationSidebar conversations={conversations} onNew={handleNew} />

        <div className="r-chat-area">
          <div className="r-chat-messages">
            {messages.length === 0 && !streaming ? (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", textAlign: "center" }}>
                <p className="r-page-title" style={{ fontSize: "18px", marginBottom: "var(--space-sm)" }}>{t("conversation_empty")}</p>
                <p style={{ fontSize: "13px", color: "var(--ink-muted)" }}>{t("conversation_hint")}</p>
              </div>
            ) : (
              <>
                {messages.map((m) => (
                  <MessageBubble key={m.id} role={m.role} content={m.content} sources={m.sources} />
                ))}
                {streaming && (
                  <MessageBubble
                    role="assistant"
                    content={streamingContent || ""}
                    sources={streamingSources}
                    streaming={!streamingContent}
                  />
                )}
                <div ref={bottomRef} />
              </>
            )}
          </div>

          <div className="r-chat-input-wrap">
            <div className="r-chat-input-inner">
              <textarea
                className="r-chat-textarea"
                rows={1}
                placeholder={t("type_message")}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleSend();
                  }
                }}
                disabled={streaming}
              />
              <button
                onClick={handleSend}
                disabled={!input.trim() || streaming}
                className="r-chat-send-btn"
              >
                {streaming ? "…" : "↑"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
