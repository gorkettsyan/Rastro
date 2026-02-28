import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";

interface Conversation {
  id: string;
  title: string | null;
  updated_at: string;
}

interface Props {
  conversations: Conversation[];
  onNew: () => void;
}

export default function ConversationSidebar({ conversations, onNew }: Props) {
  const { t } = useTranslation();
  const { conversationId } = useParams();

  return (
    <aside className="w-64 shrink-0 bg-white border-r border-gray-200 flex flex-col h-full">
      <div className="p-4 border-b border-gray-100">
        <button
          onClick={onNew}
          className="w-full bg-gray-900 text-white text-sm font-medium px-4 py-2 rounded-lg hover:bg-gray-800"
        >
          + {t("new_conversation")}
        </button>
      </div>
      <div className="flex-1 overflow-y-auto py-2">
        {conversations.map((c) => (
          <Link
            key={c.id}
            to={`/chat/${c.id}`}
            className={`block px-4 py-3 text-sm hover:bg-gray-50 ${
              c.id === conversationId ? "bg-gray-50 font-medium text-gray-900" : "text-gray-600"
            }`}
          >
            <p className="truncate">{c.title || t("new_conversation")}</p>
            <p className="text-xs text-gray-400 mt-0.5">
              {new Date(c.updated_at).toLocaleDateString()}
            </p>
          </Link>
        ))}
      </div>
    </aside>
  );
}
