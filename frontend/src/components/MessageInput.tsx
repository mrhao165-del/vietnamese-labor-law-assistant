import { useEffect, useRef, useState } from 'react';
import { Send, Paperclip } from 'lucide-react';

type Props = {
  onSend: (text: string) => void;
  disabled?: boolean;
};

export function MessageInput({ onSend, disabled }: Props) {
  const [text, setText] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 150) + 'px';
  }, [text]);

  const submit = () => {
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setText('');
  };

  return (
    <div className="w-full bg-gradient-to-t from-surface-bright via-surface-bright to-transparent pt-md pb-md px-container-padding flex-none">
      <div className="max-w-chat-max-width mx-auto">
        <div className="flex items-end bg-surface-container-lowest border border-outline-variant hover:border-primary/40 focus-within:border-secondary focus-within:ring-2 focus-within:ring-secondary/15 rounded-xl p-1.5 transition-all shadow-card-sm">
          <button
            className="p-2 text-on-surface-variant hover:bg-surface-variant hover:text-primary rounded-lg transition-colors shrink-0"
            aria-label="Đính kèm"
          >
            <Paperclip className="w-5 h-5" />
          </button>
          <textarea
            ref={textareaRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            className="flex-1 bg-transparent border-none focus:ring-0 text-body-md font-body-md placeholder:text-outline resize-none max-h-[150px] min-h-[44px] py-2 px-2 outline-none text-on-surface"
            placeholder="Nhập câu hỏi về Bộ luật Lao động…"
            rows={1}
          />
          <button
            onClick={submit}
            disabled={disabled || !text.trim()}
            className="p-2.5 bg-primary text-on-primary hover:bg-primary-container disabled:bg-outline-variant disabled:text-outline rounded-lg transition-all flex items-center justify-center shrink-0 disabled:cursor-not-allowed"
            aria-label="Gửi"
          >
            <Send className="w-[18px] h-[18px]" />
          </button>
        </div>
        <div className="text-center mt-2">
          <span className="text-label-sm font-label-sm text-outline">
            Trợ lý AI có thể mắc sai lầm. Hãy kiểm tra lại các thông tin quan trọng.
          </span>
        </div>
      </div>
    </div>
  );
}
