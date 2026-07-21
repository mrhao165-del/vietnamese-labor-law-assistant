export function TypingIndicator() {
  return <div className="flex items-center gap-1.5 py-1"><span className="w-2 h-2 rounded-full bg-on-surface-variant/60 typing-dot" /><span className="w-2 h-2 rounded-full bg-on-surface-variant/60 typing-dot" style={{ animationDelay: '0.2s' }} /><span className="w-2 h-2 rounded-full bg-on-surface-variant/60 typing-dot" style={{ animationDelay: '0.4s' }} /></div>;
}
