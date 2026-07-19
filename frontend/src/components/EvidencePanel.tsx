import { useState } from 'react';
import { FileText, MenuBook, ErrorOutline, ShieldCheck, Warning, Info } from './Icons';
import type { Citation, Guardrail } from '../lib/supabase';

type Props = {
  citations: Citation[];
  guardrail: Guardrail | null;
  activeTab: 'citations' | 'process' | 'verify';
  onTabChange: (t: 'citations' | 'process' | 'verify') => void;
  hasConversation: boolean;
};

export function EvidencePanel({ citations, guardrail, activeTab, onTabChange, hasConversation }: Props) {
  const tabs: { id: typeof activeTab; label: string }[] = [
    { id: 'citations', label: 'Căn cứ pháp lý' },
    { id: 'process', label: 'Quy trình xử lý' },
    { id: 'verify', label: 'Kiểm chứng' },
  ];

  return (
    <aside className="w-[350px] bg-surface-bright border-l border-outline-variant flex flex-col shrink-0 h-full">
      <div className="flex px-md pt-sm border-b border-outline-variant bg-surface flex-none">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => onTabChange(t.id)}
            className={`px-3 py-3 text-label-md font-label-md transition-colors relative -mb-px ${
              activeTab === t.id
                ? 'font-bold text-primary border-b-2 border-primary'
                : 'text-on-surface-variant hover:text-primary'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto p-md flex flex-col gap-md">
        {activeTab === 'citations' && <CitationsTab citations={citations} hasConversation={hasConversation} />}
        {activeTab === 'process' && <ProcessTab hasConversation={hasConversation} />}
        {activeTab === 'verify' && <VerifyTab guardrail={guardrail} hasConversation={hasConversation} />}
      </div>
    </aside>
  );
}

function EmptyPanel({ icon, text }: { icon: React.ReactNode; text: string }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center p-lg text-center opacity-70">
      <div className="w-16 h-16 rounded-full bg-surface-container-high flex items-center justify-center mb-md border border-outline-variant/30">
        {icon}
      </div>
      <p className="text-body-md font-body-md text-on-surface-variant">{text}</p>
    </div>
  );
}

function CitationsTab({ citations, hasConversation }: { citations: Citation[]; hasConversation: boolean }) {
  if (!citations.length) {
    return (
      <EmptyPanel
        icon={<MenuBook className="w-8 h-8 text-outline" />}
        text={hasConversation ? 'Tin nhắn này không có căn cứ pháp lý.' : 'Chưa có căn cứ pháp lý được trả về.'}
      />
    );
  }
  return (
    <>
      {citations.map((c) => (
        <div key={c.id} className="level-1-card rounded-xl p-md bg-surface-container-lowest border border-outline-variant shadow-card-sm">
          <div className="flex items-center gap-2 mb-2">
            <span className="bg-secondary text-on-secondary text-xs px-1.5 py-0.5 rounded font-bold">{c.ref}</span>
            <h4 className="font-label-md text-label-md font-bold text-on-surface leading-snug">{c.article}</h4>
          </div>
          <p className="font-body-md text-[14px] text-on-surface-variant mb-2 leading-relaxed">{c.text}</p>
          <div className="mt-2 text-xs text-outline text-right border-t border-outline-variant/50 pt-2">{c.law}</div>
        </div>
      ))}
    </>
  );
}

function ProcessTab({ hasConversation }: { hasConversation: boolean }) {
  if (!hasConversation) {
    return <EmptyPanel icon={<Info className="w-8 h-8 text-outline" />} text="Quy trình xử lý sẽ hiển thị sau khi bạn đặt câu hỏi." />;
  }
  const steps = [
    { label: 'Tiếp nhận câu hỏi', detail: 'Phân tích ý định và từ khoá pháp lý.' },
    { label: 'Truy hồi nguồn luật', detail: 'Tìm trong Bộ luật Lao động 2019.' },
    { label: 'Suy luận kết luận', detail: 'Tổng hợp điều khoản liên quan.' },
    { label: 'Kiểm chứng trích dẫn', detail: 'Xác minh citation khớp ngữ cảnh.' },
    { label: 'Trả kết quả', detail: 'Hiển thị đáp án kèm căn cứ.' },
  ];
  return (
    <div className="flex flex-col gap-xs">
      {steps.map((s, i) => (
        <div key={i} className="flex items-start gap-sm p-sm rounded-lg bg-surface-container-lowest border border-outline-variant/60">
          <div className="w-6 h-6 rounded-full bg-secondary text-on-secondary text-[11px] font-bold flex items-center justify-center shrink-0 mt-0.5">
            {i + 1}
          </div>
          <div className="flex flex-col">
            <span className="text-label-md font-label-md text-on-surface font-semibold">{s.label}</span>
            <span className="text-label-sm text-on-surface-variant">{s.detail}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

function VerifyTab({ guardrail, hasConversation }: { guardrail: Guardrail | null; hasConversation: boolean }) {
  if (!guardrail) {
    return <EmptyPanel icon={<ShieldCheck className="w-8 h-8 text-outline" />} text={hasConversation ? 'Chưa có thông tin kiểm chứng.' : 'Kiểm chứng sẽ hiển thị sau câu trả lời đầu tiên.'} />;
  }
  const tone =
    guardrail.status === 'verified' ? 'emerald' :
    guardrail.status === 'unverified' ? 'amber' : 'red';
  const toneClasses: Record<string, string> = {
    emerald: 'bg-emerald-50/60 border-emerald-200 text-emerald-700',
    amber: 'bg-amber-50/60 border-amber-200 text-amber-700',
    red: 'bg-red-50/60 border-red-200 text-red-700',
  };
  const Icon = guardrail.status === 'verified' ? ShieldCheck : guardrail.status === 'unverified' ? Warning : ErrorOutline;
  return (
    <div className={`p-md rounded-xl border flex flex-col gap-md ${toneClasses[tone]}`}>
      <div className="flex items-center gap-2 font-bold">
        <Icon className="w-5 h-5" />
        <span>{guardrail.label}</span>
      </div>
      {guardrail.checks && guardrail.checks.length > 0 && (
        <div className="flex flex-col gap-3 mt-2">
          {guardrail.checks.map((ck, i) => (
            <div key={i} className="flex items-center justify-between text-label-md">
              <span className="text-on-surface-variant">{ck.label}</span>
              <span className={`font-bold ${ck.passed ? 'text-emerald-700' : 'text-red-600'}`}>
                {ck.passed ? 'Đạt' : 'Không đạt'}
              </span>
            </div>
          ))}
        </div>
      )}
      <div className="mt-4 pt-4 border-t border-outline-variant/30">
        <p className="text-label-sm text-on-surface-variant leading-relaxed">{guardrail.detail}</p>
      </div>
    </div>
  );
}
