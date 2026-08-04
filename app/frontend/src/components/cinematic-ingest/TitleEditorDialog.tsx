import { useRef } from 'react';
import { Loader2, Sparkles } from 'lucide-react';
import Modal from '../Modal';
import { normalizeDisplayTitle } from './titleEditorRuntime';

interface TitleEditorDialogProps {
  open: boolean;
  input: string;
  suggestions: string[];
  selectedTitle: string | null;
  generating: boolean;
  saving: boolean;
  error: string;
  validationError: string;
  onInputChange: (value: string) => void;
  onSelectSuggestion: (value: string) => void;
  onGenerate: () => void;
  onSave: () => void;
  onClose: () => void;
}

export function TitleEditorDialog({
  open,
  input,
  suggestions,
  selectedTitle,
  generating,
  saving,
  error,
  validationError,
  onInputChange,
  onSelectSuggestion,
  onGenerate,
  onSave,
  onClose,
}: TitleEditorDialogProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const handleClose = () => {
    if (!saving) onClose();
  };

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title="修改标题"
      maxWidth="md"
      dismissible={!saving}
      initialFocusRef={inputRef}
    >
      <div className="title-editor-dialog space-y-4">
        <label className="block">
          <span className="mb-1 block text-sm text-gray-400">显示标题</span>
          <input
            ref={inputRef}
            value={input}
            onChange={(event) => onInputChange(event.target.value)}
            disabled={saving}
            className="w-full rounded-lg border border-[#2A2B30] bg-[#0B0C10] px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-purple-500/50 focus:outline-none disabled:opacity-50"
          />
        </label>

        <div className="title-editor-controls flex items-center justify-between gap-3">
          <span className="title-editor-count text-xs text-gray-500">{Array.from(normalizeDisplayTitle(input)).length}/20</span>
          <button
            type="button"
            onClick={onGenerate}
            disabled={generating || saving}
            className="title-editor-generate inline-flex items-center gap-1.5 rounded-lg border border-purple-500/30 bg-purple-500/15 px-3 py-1.5 text-xs text-purple-300 disabled:opacity-50"
          >
            {generating ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
            {generating ? '生成中' : 'AI 生成'}
          </button>
        </div>

        {suggestions.length > 0 && (
          <div className="title-editor-suggestions space-y-2">
            {suggestions.map((suggestion) => (
              <button
                key={suggestion}
                type="button"
                className={`title-editor-suggestion${selectedTitle === suggestion ? ' is-selected' : ''}`}
                aria-pressed={selectedTitle === suggestion}
                onClick={() => onSelectSuggestion(suggestion)}
                disabled={saving}
              >
                {suggestion}
              </button>
            ))}
          </div>
        )}

        {error && <p className="text-xs text-red-400">{error}</p>}
        {validationError && <p className="text-xs text-red-400">{validationError}</p>}

        <div className="title-editor-footer flex justify-end gap-2">
          <button
            type="button"
            onClick={handleClose}
            disabled={saving}
            className="rounded-lg px-4 py-2 text-sm text-gray-400 hover:text-white disabled:opacity-50"
          >
            取消
          </button>
          <button
            type="button"
            onClick={onSave}
            disabled={generating || saving || Boolean(validationError)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-purple-500/30 bg-purple-500/20 px-4 py-2 text-sm font-medium text-purple-300 disabled:opacity-50"
          >
            {saving ? <Loader2 size={13} className="animate-spin" /> : null}
            {saving ? '保存中' : '保存标题'}
          </button>
        </div>
      </div>
    </Modal>
  );
}
