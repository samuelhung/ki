import {
  Activity,
  AudioLines,
  Database,
  FileText,
  Gauge,
  HardDrive,
  Lightbulb,
  MessageSquareText,
  RefreshCw,
  ScrollText,
  Sparkles,
  Video,
  Zap,
} from 'lucide-react';
import type { DbInfo, HealthState } from './systemTypes';

interface SystemAssetBoxProps {
  dbInfo: DbInfo | null;
  health: HealthState;
}

interface SystemAssetsPanelProps extends SystemAssetBoxProps {
  loading?: boolean;
}

function statText(value: string | number | undefined | null) {
  if (value === undefined || value === null || value === '') return '--';
  return value;
}

function buildAssetGroups(dbInfo: DbInfo | null, health: HealthState) {
  const fileCount = (key: string) => dbInfo?.files?.[key]?.count ?? 0;
  return [
    {
      label: '主库',
      meta: dbInfo?.database.file || 'intelligence.sqlite',
      icon: Database,
      tone: 'violet',
      items: [
        { label: '体量', value: dbInfo?.database.size_display || statText(health.data?.database?.size_mb ? `${health.data.database.size_mb} MB` : null), icon: HardDrive, tone: 'violet' },
        { label: 'WAL', value: dbInfo ? `${dbInfo.database.page_count.toLocaleString()}p` : '--', icon: Activity, tone: 'cyan' },
        { label: '页', value: dbInfo ? `${Math.round(dbInfo.database.page_size / 1024)}KB` : '--', icon: FileText, tone: 'blue' },
      ],
    },
    {
      label: '采集',
      meta: 'INGEST',
      icon: FileText,
      tone: 'cyan',
      items: [
        { label: '转写', value: fileCount('transcripts').toLocaleString(), icon: ScrollText, tone: 'cyan' },
        { label: '文档', value: fileCount('documents').toLocaleString(), icon: FileText, tone: 'blue' },
        { label: '事件', value: statText(health.data?.database?.event_count), icon: Activity, tone: 'gold' },
      ],
    },
    {
      label: 'AI 产物',
      meta: 'INTEL',
      icon: Zap,
      tone: 'gold',
      items: [
        { label: '总结', value: fileCount('summaries').toLocaleString(), icon: Sparkles, tone: 'gold' },
        { label: '脑暴', value: fileCount('brainstorm').toLocaleString(), icon: MessageSquareText, tone: 'violet' },
        { label: '概念', value: fileCount('concepts').toLocaleString(), icon: Lightbulb, tone: 'gold' },
      ],
    },
    {
      label: '媒体',
      meta: 'MEDIA',
      icon: HardDrive,
      tone: 'blue',
      items: [
        { label: '视频', value: fileCount('videos').toLocaleString(), icon: Video, tone: 'blue' },
        { label: '音频', value: fileCount('audio').toLocaleString(), icon: AudioLines, tone: 'rose' },
      ],
    },
  ];
}

function AssetGroups({ dbInfo, health }: SystemAssetBoxProps) {
  const groups = buildAssetGroups(dbInfo, health);

  return (
    <div className="system-asset-groups" aria-label="资产台账">
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
              {group.items.map((item) => {
                const ItemIcon = item.icon;
                return (
                  <span key={item.label} className={`system-asset-item is-${item.tone}`}>
                    <ItemIcon size={13} aria-hidden="true" />
                    <small>{item.label}</small>
                    <b>{item.value}</b>
                  </span>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function SystemAssetsPanel({ dbInfo, health, loading = false }: SystemAssetsPanelProps) {
  const summaryItems = [
    { label: '主库状态', value: health.data?.database?.ok ? '正常' : health.data ? '异常' : '检测中', icon: Database, tone: health.data?.database?.ok ? 'cyan' : health.data ? 'rose' : 'violet' },
    { label: '数据库体量', value: dbInfo?.database.size_display || '--', icon: Gauge, tone: 'violet' },
    { label: '事件总数', value: statText(health.data?.database?.event_count), icon: Activity, tone: 'gold' },
    { label: '资产扫描', value: loading ? '刷新中' : dbInfo ? '已同步' : '等待数据', icon: RefreshCw, tone: loading ? 'violet' : dbInfo ? 'blue' : 'rose' },
  ];

  return (
    <div className="system-assets-panel">
      <div className="system-assets-summary">
        {summaryItems.map((item) => {
          const Icon = item.icon;
          return (
            <span key={item.label} className={`system-assets-summary-item is-${item.tone}`}>
              <Icon size={15} />
              <small>{item.label}</small>
              <b>{item.value}</b>
            </span>
          );
        })}
      </div>
      <AssetGroups dbInfo={dbInfo} health={health} />
    </div>
  );
}

export function SystemAssetBox({ dbInfo, health }: SystemAssetBoxProps) {
  return (
    <div className="laser-media-box system-core-box">
      <div className="system-core-title">
        <span>SYSTEM CORE</span>
        <b>资产台账</b>
        <small>DATABASE / INVENTORY</small>
      </div>
      <AssetGroups dbInfo={dbInfo} health={health} />
    </div>
  );
}
