import { FilePlus } from "@phosphor-icons/react";
import type { AgentConversation, AgentProviderId } from "../types";

type Option = { value: string; label: string; disabled?: boolean };
type ConversationControlsProps = {
  conversations: AgentConversation[];
  activeConversationId?: string;
  provider: AgentProviderId;
  model: string;
  providers: Option[];
  models: Option[];
  onSelectConversation: (id: string) => void;
  onCreateConversation: () => void;
  onSelectProvider: (id: AgentProviderId) => void;
  onSelectModel: (model: string) => void;
};

/** @brief Manage independent project conversations and unified AI provider/model selection. */
export function ConversationControls({
  conversations,
  activeConversationId,
  provider,
  model,
  providers,
  models,
  onSelectConversation,
  onCreateConversation,
  onSelectProvider,
  onSelectModel,
}: ConversationControlsProps) {
  return (
    <div className="agent-conversation-controls">
      <select aria-label="Değiştir AI Konuşma" value={activeConversationId ?? ""} onChange={(event) => onSelectConversation(event.target.value)}>
        {conversations.length === 0 ? <option value="">Bu projede henüz konuşma yok</option> : null}
        {conversations.map((conversation) => <option value={conversation.id} key={conversation.id}>{conversation.title}</option>)}
      </select>
      <button type="button" aria-label="Yeni AI Konuşma" title="Yeni AI Konuşma" onClick={onCreateConversation}>
        <FilePlus size={15} weight="bold" />
      </button>
      <select aria-label="Seç AI Sağlayıcı" value={provider} onChange={(event) => onSelectProvider(event.target.value as AgentProviderId)}>
        {providers.map((option) => <option value={option.value} disabled={option.disabled} key={option.value}>{option.label}</option>)}
      </select>
      <select aria-label="Konuşma modelini seç" value={model} onChange={(event) => onSelectModel(event.target.value)}>
        {models.map((option) => <option value={option.value} key={option.value}>{option.label}</option>)}
      </select>
    </div>
  );
}
