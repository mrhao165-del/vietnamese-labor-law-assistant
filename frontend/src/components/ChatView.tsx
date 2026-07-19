import { useEffect } from 'react';
import { Bot } from 'lucide-react';
import type { Message as MessageType } from '../lib/supabase';
import { MessageBubble } from './MessageBubble';
import { TypingIndicator } from './TypingIndicator';

type Props = {
  messages: MessageType[];
  isThinking: boolean;
  onFeedback: (id: string, feedback: 'up' | 'down') => void;
  onViewCitation: () => void;
  endRef: React.RefObject<HTMLDivElement>;
};

export function ChatView({ messages, isThinking, onFeedback, onViewCitation, endRef }: Props) {
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isThinking, endRef]);

  return (
    <div className="flex-1 w-full overflow-y-auto px-container-padding py-xl">
      <div className="max-w-chat-max-width w-full mx-auto flex flex-col gap-xl pb-10">
        {messages.map((m) => (
          <MessageBubble
            key={m.id}
            message={m}
            onFeedback={onFeedback}
            onViewCitation={onViewCitation}
          />
        ))}
        {isThinking && (
          <div className="flex justify-start w-full gap-md animate-fade-in-up">
            <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center shrink-0 mt-1 shadow-sm">
              <Bot className="w-4 h-4 text-on-primary" />
            </div>
            <div className="bg-surface-container-low border border-outline-variant rounded-2xl rounded-tl-sm p-md shadow-card-sm">
              <TypingIndicator />
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>
    </div>
  );
}
