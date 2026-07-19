import { Menu, BookText, CheckCircle2, ChevronDown } from 'lucide-react';

type Props = {
  onMenuClick: () => void;
  onEvidenceClick: () => void;
  hasCitations: boolean;
};

export function TopBar({ onMenuClick, onEvidenceClick, hasCitations }: Props) {
  return (
    <header className="bg-surface border-b border-outline-variant flex justify-between items-center px-md sm:px-lg py-sm h-14 sm:h-[64px] shrink-0 z-10">
      {/* Left */}
      <div className="flex items-center gap-sm flex-1 min-w-0">
        <button
          onClick={onMenuClick}
          className="lg:hidden p-2 text-on-surface-variant hover:bg-surface-container-low transition-colors rounded-full -ml-1"
          aria-label="Menu"
        >
          <Menu className="w-5 h-5" />
        </button>
        <div className="flex items-center gap-2 min-w-0">
          <span className="material-symbols-outlined fill text-primary text-[22px] hidden sm:inline-block">gavel</span>
          <span className="text-[17px] sm:text-headline-md font-bold text-primary truncate">Trợ lý Luật Lao động</span>
        </div>
      </div>

      {/* Right */}
      <div className="flex items-center gap-sm flex-1 justify-end">
        <div className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 bg-surface-container-lowest border border-outline-variant rounded-full shadow-card-sm">
          <CheckCircle2 className="w-4 h-4 text-secondary fill-secondary/10" />
          <span className="text-label-md font-label-md text-secondary">Hệ thống sẵn sàng</span>
        </div>
        <div className="sm:hidden flex items-center gap-1 px-2 py-1 bg-surface-container-low rounded-full border border-outline-variant">
          <div className="w-2 h-2 rounded-full bg-emerald-500" />
        </div>
        <button
          onClick={onEvidenceClick}
          className={`xl:hidden flex items-center gap-1.5 px-3 py-2 rounded-full border transition-all ${
            hasCitations
              ? 'bg-secondary text-on-secondary border-secondary shadow-sm'
              : 'bg-surface-container-lowest text-on-surface-variant border-outline-variant'
          }`}
          aria-label="Căn cứ pháp lý"
        >
          <BookText className="w-4 h-4" />
          <span className="text-label-sm font-label-sm hidden sm:inline">Căn cứ</span>
          {hasCitations && <ChevronDown className="w-3.5 h-3.5" />}
        </button>
      </div>
    </header>
  );
}
