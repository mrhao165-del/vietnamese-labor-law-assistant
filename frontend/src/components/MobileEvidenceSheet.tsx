import { X } from 'lucide-react';
import { FileText, ShieldCheck, Warning, ErrorOutline, Info } from './Icons';
import type { Citation, Guardrail } from '../lib/supabase';

type Props = {
  open: boolean;
  onClose: () => void;
  citations: Citation[];
  guardrail: Guardrail | null;
};

export function MobileEvidenceSheet({ open, onClose, citations, guardrail }: Props) {
  if (!open) return null;
  const tone =
    guardrail?.status === 'verified' ? 'emerald' :
    guardrail?.status === 'unverified' ? 'amber' : 'red';
  const toneClasses: Record<string, string> = {
    emerald: 'bg-emerald-50/60 border-emerald-200 text-emerald-700',
    amber: 'bg-amber-50/60 border-amber-200 text-amber-700',
    red: 'bg-red-50/60 border-red-200 text-red-700',
  };
  const Icon = guardrail?.status === 'verified' ? ShieldCheck : guardrail?.status === 'unverified' ? Warning : ErrorOutline;

  return (
    <div className="xl:hidden fixed inset-0 z-50 flex flex-col justify-end">
      <div className="absolute inset-0 bg-black/40 animate-fade-in" onClick={onClose} />
      <div className="relative bg-surface border-t border-outline-variant rounded-t-xl shadow-panel flex flex-col max-h-[80vh] animate-slide-up">
        <div className="flex justify-between items-center p-3 border-b border-outline-variant shrink-0">
          <h3 className="font-label-md text-label-md font-bold text-primary">Căn cứ pháp lý & Kiểm chứng</h3>
          <button
            onClick={onClose}
            className="p-1.5 text-on-surface-variant hover:bg-surface-container-highest rounded-full"
            aria-label="Đóng"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-md overflow-y-auto hide-scroll flex-1 flex flex-col gap-md">
          {guardrail && (
            <div className={`p-md rounded-xl border flex flex-col gap-2 ${toneClasses[tone]}`}>
              <div className="flex items-center gap-2 font-bold">
                <Icon className="w-5 h-5" />
                <span>{guardrail.label}</span>
              </div>
              {guardrail.checks && guardrail.checks.length > 0 && (
                <div className="flex flex-col gap-2 mt-1">
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
              <p className="text-label-sm text-on-surface-variant leading-relaxed">{guardrail.detail}</p>
            </div>
          )}

          {citations.length === 0 ? (
            <div className="flex flex-col items-center justify-center p-lg text-center opacity-70">
              <Info className="w-8 h-8 text-outline mb-2" />
              <p className="text-body-md text-on-surface-variant">Chưa có căn cứ pháp lý được trả về.</p>
            </div>
          ) : (
            citations.map((c) => (
              <div key={c.id} className="rounded-lg p-3 bg-surface-bright border border-outline-variant">
                <div className="flex items-center gap-2 mb-2">
                  <span className="bg-secondary text-on-secondary text-xs px-1.5 py-0.5 rounded font-bold">{c.ref}</span>
                  <h4 className="font-label-md text-label-md font-bold text-on-surface leading-snug">{c.article}</h4>
                </div>
                <p className="font-body-md text-[14px] text-on-surface-variant mb-2 leading-relaxed">{c.text}</p>
                <div className="mt-2 text-xs text-outline text-right border-t border-outline-variant/50 pt-2">{c.law}</div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
