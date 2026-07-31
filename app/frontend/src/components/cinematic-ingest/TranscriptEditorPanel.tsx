import { Loader2, Save } from 'lucide-react';

interface TranscriptEditorPanelProps {
  value: string;
  saving: boolean;
  error: string;
  onChange: (value: string) => void;
  onSave: () => void;
}

export function TranscriptEditorPanel({
  value,
  saving,
  error,
  onChange,
  onSave,
}: TranscriptEditorPanelProps) {
  return <>
    <div className="transcript-editor-field">
      <textarea autoFocus value={value} onChange={(event) => onChange(event.target.value)}
        spellCheck={false} aria-label="转写原文编辑器" />
      {error && <p className="transcript-dialog-error">{error}</p>}
    </div>
    <footer className="transcript-workspace-footer">
      <span>保存后将新增一个人工修正版，原始转写不会被覆盖。</span>
      <div>
        <button type="button" className="is-primary" onClick={onSave} disabled={saving}>
          {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
          保存人工修正版
        </button>
      </div>
    </footer>
  </>;
}
