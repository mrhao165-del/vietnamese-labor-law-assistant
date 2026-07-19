import { useState, useEffect, useRef, useCallback } from 'react';
import { supabase, type Conversation, type Message as MessageType } from './lib/supabase';
import { getAIResponse } from './lib/mockAI';
import { Sidebar } from './components/Sidebar';
import { TopBar } from './components/TopBar';
import { ChatView } from './components/ChatView';
import { EmptyState } from './components/EmptyState';
import { EvidencePanel } from './components/EvidencePanel';
import { MobileEvidenceSheet } from './components/MobileEvidenceSheet';
import { MessageInput } from './components/MessageInput';
import { X } from 'lucide-react';

export default function App() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [currentId, setCurrentId] = useState<string | null>(null);
  const [messages, setMessages] = useState<MessageType[]>([]);
  const [loadingConvs, setLoadingConvs] = useState(true);
  const [isThinking, setIsThinking] = useState(false);
  const [activeCitations, setActiveCitations] = useState<any[]>([]);
  const [activeGuardrail, setActiveGuardrail] = useState<any | null>(null);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [mobileEvidenceOpen, setMobileEvidenceOpen] = useState(false);
  const [evidenceTab, setEvidenceTab] = useState<'citations' | 'process' | 'verify'>('citations');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const loadConversations = useCallback(async () => {
    setLoadingConvs(true);
    const { data, error } = await supabase
      .from('conversations')
      .select('*')
      .order('updated_at', { ascending: false });
    if (!error && data) setConversations(data as Conversation[]);
    setLoadingConvs(false);
  }, []);

  useEffect(() => {
    loadConversations();
  }, [loadConversations]);

  const loadMessages = useCallback(async (convId: string) => {
    const { data, error } = await supabase
      .from('messages')
      .select('*')
      .eq('conversation_id', convId)
      .order('created_at', { ascending: true });
    if (!error && data) {
      const msgs = data as MessageType[];
      setMessages(msgs);
      const lastAssistant = [...msgs].reverse().find(m => m.role === 'assistant');
      if (lastAssistant) {
        setActiveCitations(lastAssistant.citations || []);
        setActiveGuardrail(lastAssistant.guardrail || null);
      } else {
        setActiveCitations([]);
        setActiveGuardrail(null);
      }
    }
  }, []);

  useEffect(() => {
    if (currentId) loadMessages(currentId);
    else {
      setMessages([]);
      setActiveCitations([]);
      setActiveGuardrail(null);
    }
  }, [currentId, loadMessages]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isThinking]);

  const createConversation = useCallback(async (firstMessage?: string): Promise<string | null> => {
    const title = firstMessage
      ? firstMessage.slice(0, 40) + (firstMessage.length > 40 ? '…' : '')
      : 'Cuộc trò chuyện mới';
    const { data, error } = await supabase
      .from('conversations')
      .insert({ title })
      .select()
      .single();
    if (error || !data) return null;
    const conv = data as Conversation;
    setConversations(prev => [conv, ...prev]);
    return conv.id;
  }, []);

  const handleNewChat = useCallback(() => {
    setCurrentId(null);
    setMessages([]);
    setActiveCitations([]);
    setActiveGuardrail(null);
    setMobileSidebarOpen(false);
  }, []);

  const handleSelectConversation = useCallback((id: string) => {
    setCurrentId(id);
    setMobileSidebarOpen(false);
  }, []);

  const handleDeleteConversation = useCallback(async (id: string) => {
    const { error } = await supabase.from('conversations').delete().eq('id', id);
    if (!error) {
      setConversations(prev => prev.filter(c => c.id !== id));
      if (currentId === id) handleNewChat();
    }
  }, [currentId, handleNewChat]);

  const persistMessage = useCallback(async (convId: string, msg: Omit<MessageType, 'id' | 'conversation_id' | 'created_at'>) => {
    const { data, error } = await supabase
      .from('messages')
      .insert({
        conversation_id: convId,
        role: msg.role,
        content: msg.content,
        citations: msg.citations,
        capabilities: msg.capabilities,
        guardrail: msg.guardrail,
        feedback: msg.feedback,
      })
      .select()
      .single();
    if (!error && data) return data as MessageType;
    return null;
  }, []);

  const handleSend = useCallback(async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || isThinking) return;

    let convId = currentId;
    if (!convId) {
      convId = await createConversation(trimmed);
      if (!convId) return;
      setCurrentId(convId);
    } else if (messages.length === 1) {
      await supabase.from('conversations').update({ title: trimmed.slice(0, 40) + (trimmed.length > 40 ? '…' : '') }).eq('id', convId);
      loadConversations();
    }

    const tempUser: MessageType = {
      id: 'temp-user-' + Date.now(),
      conversation_id: convId,
      role: 'user',
      content: trimmed,
      citations: [],
      capabilities: [],
      guardrail: null,
      feedback: null,
      created_at: new Date().toISOString(),
    };
    setMessages(prev => [...prev, tempUser]);
    setIsThinking(true);

    const ai = await getAIResponse(trimmed);
    const persistedUser = await persistMessage(convId, {
      role: 'user', content: trimmed, citations: [], capabilities: [], guardrail: null, feedback: null,
    });
    const persistedAssistant = await persistMessage(convId, {
      role: 'assistant',
      content: ai.content,
      citations: ai.citations,
      capabilities: ai.capabilities,
      guardrail: ai.guardrail,
      feedback: null,
    });

    setMessages(prev => {
      const without = prev.filter(m => m.id !== tempUser.id);
      const next = [...without];
      if (persistedUser) next.push(persistedUser);
      if (persistedAssistant) next.push(persistedAssistant);
      return next.sort((a, b) => a.created_at.localeCompare(b.created_at));
    });
    setActiveCitations(ai.citations);
    setActiveGuardrail(ai.guardrail);
    setIsThinking(false);
    loadConversations();
  }, [currentId, isThinking, messages.length, createConversation, persistMessage, loadConversations]);

  const handleFeedback = useCallback(async (msgId: string, feedback: 'up' | 'down') => {
    setMessages(prev => prev.map(m => {
      if (m.id !== msgId) return m;
      const newFb = m.feedback === feedback ? null : feedback;
      supabase.from('messages').update({ feedback: newFb }).eq('id', msgId).then();
      return { ...m, feedback: newFb };
    }));
  }, []);

  const handleViewCitation = useCallback(() => {
    setMobileEvidenceOpen(true);
  }, []);

  const hasConversation = messages.length > 0;

  return (
    <div className="flex h-full w-full bg-background text-on-background overflow-hidden">
      {/* Desktop Sidebar */}
      <div className="hidden lg:block">
        <Sidebar
          conversations={conversations}
          currentId={currentId}
          loading={loadingConvs}
          onNewChat={handleNewChat}
          onSelect={handleSelectConversation}
          onDelete={handleDeleteConversation}
        />
      </div>

      {/* Mobile Sidebar Drawer */}
      {mobileSidebarOpen && (
        <div className="lg:hidden fixed inset-0 z-50 animate-fade-in">
          <div className="absolute inset-0 bg-black/40" onClick={() => setMobileSidebarOpen(false)} />
          <div className="absolute left-0 top-0 bottom-0 w-[280px] max-w-[80vw] bg-surface-container-low shadow-2xl animate-slide-up">
            <Sidebar
              conversations={conversations}
              currentId={currentId}
              loading={loadingConvs}
              onNewChat={handleNewChat}
              onSelect={handleSelectConversation}
              onDelete={handleDeleteConversation}
            />
            <button
              className="absolute top-4 right-4 p-2 rounded-full bg-surface-container-high text-on-surface hover:bg-surface-container-highest"
              onClick={() => setMobileSidebarOpen(false)}
              aria-label="Đóng"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>
      )}

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-w-0 bg-surface-bright">
        <TopBar
          onMenuClick={() => setMobileSidebarOpen(true)}
          onEvidenceClick={() => setMobileEvidenceOpen(true)}
          hasCitations={activeCitations.length > 0}
        />

        <div className="flex-1 flex overflow-hidden relative">
          {/* Chat + Input column */}
          <div className="flex-1 flex flex-col min-w-0 h-full">
            {hasConversation ? (
              <ChatView
                messages={messages}
                isThinking={isThinking}
                onFeedback={handleFeedback}
                onViewCitation={handleViewCitation}
                endRef={messagesEndRef}
              />
            ) : (
              <EmptyState onSuggestion={handleSend} isThinking={isThinking} />
            )}
            <MessageInput onSend={handleSend} disabled={isThinking} />
          </div>

          {/* Desktop Evidence Panel */}
          <div className="hidden xl:flex">
            <EvidencePanel
              citations={activeCitations}
              guardrail={activeGuardrail}
              activeTab={evidenceTab}
              onTabChange={setEvidenceTab}
              hasConversation={hasConversation}
            />
          </div>
        </div>
      </div>

      {/* Mobile Evidence Sheet */}
      <MobileEvidenceSheet
        open={mobileEvidenceOpen}
        onClose={() => setMobileEvidenceOpen(false)}
        citations={activeCitations}
        guardrail={activeGuardrail}
      />
    </div>
  );
}


