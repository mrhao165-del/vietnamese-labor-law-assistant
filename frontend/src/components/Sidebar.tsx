import { useState } from 'react';
import { Plus, MessageCircle, History, HelpCircle, Info, ShieldCheck, Trash2, Scale } from 'lucide-react';
import type { Conversation } from '../api/types';

type Props = {
  conversations: Conversation[];
  currentId: string | null;
  loading: boolean;
  onNewChat: () => void;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
};

export function Sidebar({ conversations, currentId, loading, onNewChat, onSelect, onDelete }: Props) {
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  const today = new Date(); today.setHours(0, 0, 0, 0);
  const todayConvs = conversations.filter(c => new Date(c.updated_at) >= today);
  const earlierConvs = conversations.filter(c => new Date(c.updated_at) < today);

  return (
    <nav className="flex flex-col h-full w-sidebar-width bg-surface-container-low border-r border-outline-variant p-md gap-sm shrink-0">
      {/* Header */}
      <div className="flex items-center gap-sm px-xs mb-lg pt-sm">
        <div className="w-9 h-9 rounded-xl bg-primary flex items-center justify-center shrink-0 shadow-sm">
          <Scale className="w-5 h-5 text-on-primary" />
        </div>
        <div className="min-w-0">
          <h2 className="text-[15px] font-bold text-primary leading-tight">Trợ lý Luật</h2>
          <p className="text-label-sm font-label-sm text-on-surface-variant">Lịch sử trò chuyện</p>
        </div>
      </div>

      {/* CTA */}
      <button
        onClick={onNewChat}
        className="w-full flex items-center justify-center gap-sm bg-primary text-on-primary py-2.5 px-4 rounded-lg font-label-md text-label-md hover:bg-primary-container transition-all shadow-sm mb-sm hover:shadow active:scale-[0.98]"
      >
        <Plus className="w-[18px] h-[18px]" />
        <span>Cuộc trò chuyện mới</span>
      </button>

      {/* Conversation list */}
      <div className="flex-1 overflow-y-auto flex flex-col gap-xs mt-sm hide-scroll">
        {todayConvs.length > 0 && (
          <>
            <div className="text-label-sm font-label-sm text-on-surface-variant px-sm py-xs mt-sm uppercase tracking-wider">Hôm nay</div>
            {todayConvs.map(c => (
              <ConversationItem
                key={c.id}
                conv={c}
                active={c.id === currentId}
                confirmDelete={confirmDelete}
                onSelect={onSelect}
                onDelete={onDelete}
                onConfirm={setConfirmDelete}
              />
            ))}
          </>
        )}
        {earlierConvs.length > 0 && (
          <>
            <div className="text-label-sm font-label-sm text-on-surface-variant px-sm py-xs mt-md uppercase tracking-wider">Trước đó</div>
            {earlierConvs.map(c => (
              <ConversationItem
                key={c.id}
                conv={c}
                active={c.id === currentId}
                confirmDelete={confirmDelete}
                onSelect={onSelect}
                onDelete={onDelete}
                onConfirm={setConfirmDelete}
              />
            ))}
          </>
        )}
        {!loading && conversations.length === 0 && (
          <div className="text-center py-lg px-sm">
            <History className="w-7 h-7 text-outline mx-auto mb-sm" />
            <p className="text-label-sm text-on-surface-variant">Chưa có cuộc trò chuyện nào.</p>
          </div>
        )}
      </div>

      {/* Static nav */}
      <div className="mt-auto border-t border-outline-variant pt-sm flex flex-col gap-xs">
        <NavIcon icon={<HelpCircle className="w-5 h-5" />} label="Hệ thống có thể làm gì?" />
        <NavIcon icon={<Info className="w-5 h-5" />} label="Phạm vi dữ liệu" />
        <NavIcon icon={<ShieldCheck className="w-5 h-5" />} label="Tuyên bố miễn trừ trách nhiệm" />
        <NavIcon icon={<HelpCircle className="w-5 h-5" />} label="Phiên bản ứng dụng" />
      </div>
    </nav>
  );
}

function NavIcon({ icon, label }: { icon: React.ReactNode; label: string }) {
  return (
    <a
      href="#"
      onClick={(e) => e.preventDefault()}
      className="flex items-center gap-sm px-sm py-2 text-on-surface-variant hover:bg-surface-container-high rounded-lg font-label-md text-label-md transition-all"
    >
      {icon}
      <span className="truncate">{label}</span>
    </a>
  );
}

function ConversationItem({
  conv, active, confirmDelete, onSelect, onDelete, onConfirm,
}: {
  conv: Conversation;
  active: boolean;
  confirmDelete: string | null;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  onConfirm: (id: string | null) => void;
}) {
  return (
    <div
      className={`group flex items-center gap-sm px-sm py-2 rounded-lg font-label-md text-label-md transition-all cursor-pointer ${
        active
          ? 'bg-secondary-container text-on-secondary-container shadow-sm'
          : 'text-on-surface-variant hover:bg-surface-container-highest'
      }`}
      onClick={() => onSelect(conv.id)}
    >
      <MessageCircle className={`w-[20px] h-[20px] shrink-0 ${active ? 'text-on-secondary-container' : ''}`} />
      <span className="truncate flex-1">{conv.title}</span>
      {confirmDelete === conv.id ? (
        <div className="flex items-center gap-1">
          <button
            onClick={(e) => { e.stopPropagation(); onDelete(conv.id); onConfirm(null); }}
            className="p-1 text-error hover:bg-error-container rounded"
            aria-label="Xác nhận xoá"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); onConfirm(null); }}
            className="text-[11px] px-1 text-on-surface-variant"
          >
            Huỷ
          </button>
        </div>
      ) : (
        <button
          onClick={(e) => { e.stopPropagation(); onConfirm(conv.id); }}
          className="p-1 text-on-surface-variant opacity-0 group-hover:opacity-100 hover:text-error rounded transition-all"
          aria-label="Xoá"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      )}
    </div>
  );
}
