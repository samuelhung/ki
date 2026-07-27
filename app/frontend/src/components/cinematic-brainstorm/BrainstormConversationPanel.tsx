import { useEffect, useRef, type RefObject } from 'react';
import { Send } from 'lucide-react';

import { renderMarkdownWithRefs } from './BrainstormAnswerPanel';
import type { BrainstormConversationMessage, BrainstormEventItem } from './useBrainstormDetail';

interface BrainstormConversationPanelProps {
  contentClassName: string;
  messages: BrainstormConversationMessage[];
  lockedEventIds: string[];
  availableEvents: BrainstormEventItem[];
  followUpText: string;
  sendingFollowUp: boolean;
  error: string;
  followUpInputRef: RefObject<HTMLTextAreaElement | null>;
  onFollowUpTextChange: (value: string) => void;
  onStartConversation: () => void;
  onSendFollowUp: () => void;
  onReferenceClick: (eventId: string) => void;
}

export default function BrainstormConversationPanel(props: BrainstormConversationPanelProps) {
  const chatEndRef = useRef<HTMLDivElement>(null);
  const eventTitleMap = new Map(props.availableEvents.map((event) => [event.id, event.title_cn || event.title]));

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [props.messages]);

  function autoResize(element: HTMLTextAreaElement) {
    element.style.height = 'auto';
    element.style.height = `${Math.min(element.scrollHeight, 120)}px`;
  }

  return (
    <>
      <div className={props.contentClassName}>
        <div className="space-y-4">
          {props.messages.length === 0 ? (
            <div className="py-12 text-center">
              <p className="text-xs text-gray-500">在"参考文档"中勾选文档，然后点击右上角「发起问答」</p>
            </div>
          ) : props.messages.map((message) => (
            <div key={message.id} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[80%] rounded-xl px-4 py-3 ${
                message.role === 'user'
                  ? 'bg-purple-500/15 text-white text-sm'
                  : 'bg-[#141518] border border-[#2A2B30] text-gray-200'
              }`}>
                {message.role === 'assistant'
                  ? renderMarkdownWithRefs(message.content, props.lockedEventIds, eventTitleMap, props.onReferenceClick, 'text-sm')
                  : <div className="text-sm">{message.content}</div>}
                {message.role === 'assistant' && message.created_at && (
                  <div className="mt-1.5 text-[10px] text-gray-600">{message.created_at.slice(0, 16).replace('T', ' ')}</div>
                )}
              </div>
            </div>
          ))}
          <div ref={chatEndRef} />
        </div>
      </div>

      {props.error && <div className="mt-4 px-3 py-1.5 rounded bg-red-500/10 border border-red-500/20 text-red-400 text-[11px]">{props.error}</div>}
      {props.messages.length > 0 && (
        <div className="mt-4 pt-4 border-t border-[#2A2B30]">
          <div className="flex gap-2">
            <textarea
              ref={props.followUpInputRef}
              value={props.followUpText}
              onChange={(event) => { props.onFollowUpTextChange(event.target.value); autoResize(event.target); }}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); props.onSendFollowUp(); }
              }}
              placeholder="输入追问... Shift+Enter 换行"
              rows={1}
              disabled={props.sendingFollowUp}
              className="flex-1 px-3 py-2 rounded-lg bg-[#141518] border border-[#2A2B30] text-sm text-white placeholder-gray-600 focus:outline-none focus:border-purple-500/50 disabled:opacity-50 resize-none"
              style={{ minHeight: '42px', maxHeight: '120px' }}
            />
            <button onClick={props.onSendFollowUp} disabled={props.sendingFollowUp || !props.followUpText.trim()}
              className="px-4 py-2 rounded-lg bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 border border-purple-500/30 transition-colors disabled:opacity-40 disabled:cursor-not-allowed shrink-0">
              <Send size={16} />
            </button>
          </div>
        </div>
      )}
    </>
  );
}
