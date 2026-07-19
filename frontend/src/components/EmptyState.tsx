import { Clock, FileText, Search, AlertTriangle } from 'lucide-react';

type Props = {
  onSuggestion: (text: string) => void;
  isThinking: boolean;
};

const SUGGESTIONS = [
  { icon: Clock, text: 'Nghỉ việc cần báo trước bao lâu?' },
  { icon: FileText, text: 'Hợp đồng xác định thời hạn tối đa bao nhiêu tháng?' },
  { icon: Search, text: 'Tìm nội dung Điều 35' },
  { icon: AlertTriangle, text: 'Những trường hợp nào không cần báo trước?' },
];

export function EmptyState({ onSuggestion, isThinking }: Props) {
  return (
    <section className="flex-1 flex flex-col items-center justify-center relative bg-surface-bright overflow-y-auto p-container-padding">
      <div className="max-w-chat-max-width w-full flex flex-col items-center text-center mt-[-6vh] pb-lg">
        <div className="w-[80px] h-[80px] rounded-2xl bg-surface-container-low flex items-center justify-center mb-xl border border-outline-variant/30 shadow-card-sm">
          <span className="material-symbols-outlined fill text-[40px] text-primary">description</span>
        </div>
        <h2 className="text-headline-lg font-headline-lg text-primary mb-sm leading-tight max-w-[600px]">
          Bạn cần tra cứu nội dung nào trong Bộ luật Lao động?
        </h2>
        <p className="text-body-md font-body-md text-on-surface-variant max-w-[600px] mb-xl opacity-90">
          Hãy mô tả tình huống hoặc nhập số Điều, Khoản cần tìm. Hệ thống sẽ trả lời dựa trên nguồn luật đã được truy hồi và kiểm chứng.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-md w-full max-w-[700px] mb-xl">
          {SUGGESTIONS.map((s, i) => (
            <button
              key={i}
              disabled={isThinking}
              onClick={() => onSuggestion(s.text)}
              className="bg-surface p-md rounded-xl border border-outline-variant/40 text-left hover:bg-surface-container-low hover:border-secondary-container/50 hover:shadow-card transition-all group flex flex-col gap-xs disabled:opacity-60"
            >
              <s.icon className="w-5 h-5 text-secondary group-hover:scale-110 transition-transform" />
              <span className="text-label-md font-label-md text-primary">{s.text}</span>
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}
