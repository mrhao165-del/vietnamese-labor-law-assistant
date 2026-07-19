import { useState } from 'react';
import { Bot, ThumbsUp, ThumbsDown, Copy, Check, Search, Calculator, ShieldCheck, FileText, AlertTriangle, Info, ChevronRight } from 'lucide-react';
import type { Message as MessageType } from '../lib/supabase';

type Props = {
  message: MessageType;
  onFeedback: (id: string, feedback: 'up' | 'down') => void;
  onViewCitation: () => void;
};

const CAPABILITY_LABELS: Record<string, { label: string; icon: React.ComponentType<{ className?: string }> }> = {
  search: { label: 'Tra cứu', icon: Search },
  calculate: { label: 'Tính toán', icon: Calculator },
};

const STATUS_STYLES = {
  verified: {
    chip: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    icon: ShieldCheck,
    text: 'ĐƯỢC NGUỒN HỖ TRỢ',
  },
  unverified: {
    chip: 'bg-amber-50 text-amber-700 border-amber-200',
    icon: AlertTriangle,
    text: 'CHƯA ĐỦ CĂN CỨ',
  },
  out_of_scope: {
    chip: 'bg-red-50 text-red-700 border-red-200',
    icon: Info,
    text: 'NGOÀI PHẠM VI',
  },
};

function renderContent(content: string) {
  const parts = content.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((p, i) => {
    if (p.startsWith('**') && p.endsWith('**')) {
      return <strong key={i} className="font-semibold text-on-surface">{p.slice(2, -2)}</strong>;
    }
    return <span key={i}>{p}</span>;
  });
}

export function MessageBubble({ message, onFeedback, onViewCitation }: Props) {
  const [copied, setCopied] = useState(false);
  const isUser = message.role === 'user';
  const status = message.guardrail ? STATUS_STYLES[message.guardrail.status] : null;

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (isUser) {
    return (
      <div className="flex justify-end w-full animate-fade-in-up">
        <div className="max-w-[85%] bg-surface-container-lowest border border-outline-variant rounded-2xl rounded-tr-sm px-lg py-md shadow-card-sm">
          <p className="text-body-md font-body-md text-on-surface">{message.content}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start w-full gap-md animate-fade-in-up">
      <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center shrink-0 mt-1 shadow-sm">
        <Bot className="w-4 h-4 text-on-primary" />
      </div>
      <div className="max-w-[90%] flex flex-col gap-3 min-w-0">
        {/* Capabilities */}
        {message.capabilities.length > 0 && (
          <div className="flex items-center gap-1.5 w-fit flex-wrap">
            {message.capabilities.map((c) => {
              const cap = CAPABILITY_LABELS[c];
              if (!cap) return null;
              const Icon = cap.icon;
              return (
                <span
                  key={c}
                  className="inline-flex items-center gap-1 px-2 py-0.5 bg-primary-container text-on-primary-container rounded font-label-sm text-[10px] uppercase tracking-wider"
                >
                  <Icon className="w-3 h-3" /> {cap.label}
                </span>
              );
            })}
          </div>
        )}

        {/* Main card */}
        <div className="bg-surface-container-low border border-outline-variant rounded-2xl rounded-tl-sm p-lg shadow-card flex flex-col gap-md">
          <div className="font-body-md text-body-md text-on-surface space-y-3 leading-relaxed">
            {message.content.split('\n\n').map((para, i) => (
              <p key={i}>{renderContent(para)}</p>
            ))}
          </div>

          {/* Guardrail box for unverified/out_of_scope */}
          {message.guardrail && (message.guardrail.status === 'unverified' || message.guardrail.status === 'out_of_scope') && (
            <div className="bg-surface-bright border border-outline-variant rounded-lg p-sm flex items-start gap-sm">
              <AlertTriangle className="w-5 h-5 text-amber-600 mt-0.5 shrink-0" />
              <div className="flex flex-col">
                <span className="text-label-sm font-label-sm font-bold text-amber-700 uppercase">{message.guardrail.label}</span>
                <span className="text-label-sm font-label-sm text-on-surface-variant mt-0.5">{message.guardrail.detail}</span>
              </div>
            </div>
          )}

          {/* Citation chips */}
          {message.citations.length > 0 && (
            <div className="pt-3 border-t border-outline-variant flex flex-wrap items-center gap-2">
              {status && (
                <span className={`inline-flex items-center gap-1 px-2 py-0.5 border rounded font-label-sm text-[10px] uppercase font-bold ${status.chip}`}>
                  <status.icon className="w-3.5 h-3.5" /> {status.text}
                </span>
              )}
              {message.citations.map((c) => (
                <button
                  key={c.id}
                  onClick={onViewCitation}
                  className="inline-flex items-center gap-1 px-2 py-1 bg-surface-variant text-on-secondary-fixed rounded text-label-sm font-label-sm hover:bg-surface-container-highest transition-colors border border-tertiary-fixed-dim"
                >
                  <FileText className="w-3.5 h-3.5" />
                  {c.ref} {c.article.split('.')[0]}
                  <ChevronRight className="w-3 h-3 opacity-60" />
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-between items-end mt-1 px-1 gap-2">
          <p className="text-label-sm font-label-sm text-outline italic max-w-[70%]">
            Thông tin dưới đây chỉ có tính chất tham khảo. Vui lòng đối chiếu với văn bản pháp luật hiện hành.
          </p>
          <div className="flex items-center gap-1 shrink-0">
            <button
              onClick={() => onFeedback(message.id, 'up')}
              className={`p-1.5 rounded transition-colors ${message.feedback === 'up' ? 'text-secondary bg-surface-variant' : 'text-on-surface-variant hover:text-secondary hover:bg-surface-variant'}`}
              aria-label="Hữu ích"
            >
              <ThumbsUp className="w-4 h-4" />
            </button>
            <button
              onClick={() => onFeedback(message.id, 'down')}
              className={`p-1.5 rounded transition-colors ${message.feedback === 'down' ? 'text-error bg-error-container/40' : 'text-on-surface-variant hover:text-error hover:bg-error-container/40'}`}
              aria-label="Chưa đúng"
            >
              <ThumbsDown className="w-4 h-4" />
            </button>
            <button
              onClick={handleCopy}
              className="p-1.5 text-on-surface-variant hover:text-primary hover:bg-surface-variant rounded transition-colors"
              aria-label="Sao chép"
            >
              {copied ? <Check className="w-4 h-4 text-emerald-600" /> : <Copy className="w-4 h-4" />}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
