import { useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "../api/client";
import { useAuthStore } from "../store/auth";
import LanguageSwitcher from "../components/LanguageSwitcher";
import ConversationSidebar from "../components/ConversationSidebar";
import MessageBubble from "../components/MessageBubble";
import MemoryBadge from "../components/MemoryBadge";

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
  const { user, logout } = useAuthStore();

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
          body: JSON.stringify({ message: text }),
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
    <div className="h-screen flex flex-col bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between shrink-0">
        <button onClick={() => navigate("/")} className="font-bold text-gray-900 text-lg">
          Rastro
        </button>
        <div className="flex items-center gap-3">
          <MemoryBadge />
          <LanguageSwitcher />
          <span className="text-sm text-gray-500">{user?.email}</span>
          <button
            onClick={() => { logout(); navigate("/login"); }}
            className="text-sm text-gray-500 hover:text-gray-900"
          >
            {t("sign_out")}
          </button>
        </div>
      </header>

      <div className="flex flex-1 min-h-0">
        <ConversationSidebar conversations={conversations} onNew={handleNew} />

        <div className="flex-1 flex flex-col min-h-0">
          <div className="flex-1 overflow-y-auto px-6 py-6">
            {messages.length === 0 && !streaming ? (
              <div className="flex flex-col items-center justify-center h-full text-center">
                <p className="text-xl font-semibold text-gray-700 mb-2">{t("conversation_empty")}</p>
                <p className="text-gray-400 text-sm">{t("conversation_hint")}</p>
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

          <div className="shrink-0 bg-white border-t border-gray-200 px-6 py-4">
            <div className="flex items-end gap-3 max-w-3xl mx-auto">
              <textarea
                className="flex-1 border border-gray-300 rounded-xl px-4 py-3 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-gray-900"
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
                className="bg-gray-900 text-white px-4 py-3 rounded-xl text-sm font-medium hover:bg-gray-800 disabled:opacity-40 shrink-0"
              >
                {streaming ? t("thinking") : "↑"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
