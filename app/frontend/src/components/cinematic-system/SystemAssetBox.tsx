import { Database, FileText, HardDrive, Zap } from 'lucide-react';
import type { DbInfo, HealthState } from './systemTypes';

interface SystemAssetBoxProps {
  dbInfo: DbInfo | null;
  health: HealthState;
}

function statText(value: string | number | undefined | null) {
  if (value === undefined || value === null || value === '') return '--';
  return value;
}

export function SystemAssetBox({ dbInfo, health }: SystemAssetBoxProps) {
  const fileCount = (key: string) => dbInfo?.files?.[key]?.count ?? 0;
  const groups = [
    {
      label: '主库',
      meta: dbInfo?.database.file || 'intelligence.sqlite',
      icon: Database,
      tone: 'violet',
      items: [
        { label: '体量', value: dbInfo?.database.size_display || statText(health.data?.database?.size_mb ? `${health.data.database.size_mb} MB` : null) },
        { label: 'WAL', value: dbInfo ? `${dbInfo.database.page_count.toLocaleString()}p` : '--' },
        { label: '页', value: dbInfo ? `${Math.round(dbInfo.database.page_size / 1024)}KB` : '--' },
      ],
    },
    {
      label: '采集',
      meta: 'INGEST',
      icon: FileText,
      tone: 'cyan',
      items: [
        { label: '转写', value: fileCount('transcripts').toLocaleString() },
        { label: '文档', value: fileCount('documents').toLocaleString() },
        { label: '事件', value: statText(health.data?.database?.event_count) },
      ],
    },
    {
      label: 'AI 产物',
      meta: 'INTEL',
      icon: Zap,
      tone: 'gold',
      items: [
        { label: '总结', value: fileCount('summaries').toLocaleString() },
        { label: '脑暴', value: fileCount('brainstorm').toLocaleString() },
        { label: '摘要', value: fileCount('digests').toLocaleString() },
        { label: '概念', value: fileCount('concepts').toLocaleString() },
      ],
    },
    {
      label: '媒体',
      meta: 'MEDIA',
      icon: HardDrive,
      tone: 'blue',
      items: [
        { label: '视频', value: fileCount('videos').toLocaleString() },
        { label: '音频', value: fileCount('audio').toLocaleString() },
      ],
    },
  ];

  return (
    <div className="laser-media-box system-core-box">
      <div className="system-core-title">
        <span>SYSTEM CORE</span>
        <b>系统资产</b>
        <small>DATABASE / PIPELINE</small>
      </div>
      <div className="system-asset-groups" aria-label="系统资产">
        {groups.map((group) => {
          const Icon = group.icon;
          return (
            <div key={group.label} className={`system-asset-group is-${group.tone}`}>
              <header>
                <Icon size={14} />
                <span>{group.label}</span>
                <small>{group.meta}</small>
              </header>
              <div>
                {group.items.map((item) => (
                  <span key={item.label}>
                    <small>{item.label}</small>
                    <b>{item.value}</b>
                  </span>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
