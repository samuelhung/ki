import { useEffect } from 'react';
import { Loader2, Save, X } from 'lucide-react';

interface TranscriptEditorDialogProps {
  open: boolean;
  value: string;
  originalValue: string;
  saving: boolean;
  error: string;
  onChange: (value: string) => void;
  onSave: () => void;
  onClose: () => void;
}

export function TranscriptEditorDialog({
  open,
  value,
  originalValue,
  saving,
  error,
  onChange,
  onSave,
  onClose,
}: TranscriptEditorDialogProps) {
  const unsaved = value !== originalValue;

  useEffect(() => {
    if (!open || !unsaved) return undefined;
    const beforeunload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', beforeunload);
    return () => window.removeEventListener('beforeunload', beforeunload);
  }, [open, unsaved]);

  useEffect(() => {
    if (!open) return undefined;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') requestClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  });

  function requestClose() {
    if (saving) return;
    if (unsaved && !window.confirm('有未保存的人工修正，确认放弃吗？')) return;
    onClose();
  }

  if (!open) return null;
  return <div className="transcript-dialog-backdrop" onMouseDown={(event) => {
    if (event.target === event.currentTarget) requestClose();
  }}>
    <section className="transcript-dialog transcript-editor-dialog" role="dialog" aria-modal="true" aria-labelledby="transcript-editor-title">
      <header>
        <div><span>HUMAN REVIEW</span><h2 id="transcript-editor-title">人工修正</h2></div>
        <button type="button" className="transcript-dialog-close" onClick={requestClose} disabled={saving} aria-label="关闭">
          <X size={18} />
        </button>
      </header>
      <div className="transcript-dialog-body">
        <textarea autoFocus value={value} onChange={(event) => onChange(event.target.value)}
          spellCheck={false} aria-label="转写原文编辑器" />
        {error && <p className="transcript-dialog-error">{error}</p>}
      </div>
      <footer>
        <span>保存后将新增一个人工修正版，原始转写不会被覆盖。</span>
        <div>
          <button type="button" onClick={requestClose} disabled={saving}>取消</button>
          <button type="button" className="is-primary" onClick={onSave} disabled={saving}>
            {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
            保存人工修正版
          </button>
        </div>
      </footer>
    </section>
  </div>;
}
