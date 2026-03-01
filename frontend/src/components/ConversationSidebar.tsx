import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";

interface Conversation {
  id: string;
  title: string | null;
  updated_at: string;
  project_id: string | null;
}

interface Props {
  conversations: Conversation[];
  onNew: () => void;
}

export default function ConversationSidebar({ conversations, onNew }: Props) {
  const { t } = useTranslation();
  const { conversationId } = useParams();

  return (
    <aside className="r-chat-sidebar">
      <p className="r-chat-sidebar-label">{t("chat")}</p>
      <button onClick={onNew} className="r-btn-primary" style={{ width: "100%", justifyContent: "center" }}>
        + {t("new_conversation")}
      </button>
      <div style={{ display: "flex", flexDirection: "column", gap: "2px", marginTop: "var(--space-sm)" }}>
        {conversations.map((c) => (
          <Link
            key={c.id}
            to={`/chat/${c.id}`}
            className={`r-conv-item${c.id === conversationId ? " active" : ""}`}
          >
            {c.project_id && <span style={{ marginRight: "4px", opacity: 0.5 }}>📁</span>}
            {c.title || t("new_conversation")}
          </Link>
        ))}
      </div>
    </aside>
  );
}
