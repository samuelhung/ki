import { Loader2 } from 'lucide-react';
import { useNavigate, useParams } from 'react-router-dom';
import StudyLessonPanel from '../components/cinematic-study/StudyLessonPanel';
import StudyMaterialPanel from '../components/cinematic-study/StudyMaterialPanel';
import type { StudyMaterial } from '../components/cinematic-study/studyDetailFormat';
import { useStudyDetail } from '../components/cinematic-study/useStudyDetail';

export type { StudyMaterial } from '../components/cinematic-study/studyDetailFormat';

interface StudyDetailProps {
  embedded?: boolean;
  materialId?: string;
  onMaterialChange?: (material: StudyMaterial) => void;
  onMaterialEvicted?: (materialId: string) => void;
  onDeleted?: (materialId: string) => void;
  initialMaterial?: StudyMaterial;
}

export default function StudyDetail({
  embedded = false, materialId, onMaterialChange, onMaterialEvicted, onDeleted, initialMaterial,
}: StudyDetailProps) {
  const { id: routeId } = useParams<{ id: string }>();
  const id = materialId || routeId;
  const navigate = useNavigate();
  const detail = useStudyDetail({ id, embedded, initialMaterial, navigate, onMaterialChange, onMaterialEvicted, onDeleted });
  const {
    material, loading, error, version, setVersion, format, setFormat, generating, deleting, reviewing, mutationLocked,
    expandedLessons, expandedUnits, previewUrl, reviewOpen, setReviewOpen, reviewForm, setReviewForm,
    isReady, isTextbook, showTabs, lessons, hasLessons, lessonMap, textbookUnits, showAppendix,
    showVersionTabs, genLabel, emptyLabel, mdSource, handleGenerate, handleDelete, handleReview,
    toggleLesson, toggleUnit,
  } = detail;

  if (loading) return <div className={`${embedded ? 'study-detail-legacy-embedded is-loading' : 'flex-1 bg-[#0B0C10]'} flex items-center justify-center`}><Loader2 size={24} className="animate-spin text-gray-500" /></div>;
  if (error || !material) return <div className={`${embedded ? 'study-detail-legacy-embedded is-error' : 'flex-1 bg-[#0B0C10]'} flex items-center justify-center`}>
    <div className="text-center"><p className="text-red-400 text-sm">{error || '资料不存在'}</p>
      <button onClick={() => navigate('/study')} className="mt-4 text-xs text-gray-500 hover:text-gray-300">返回辅导中心</button>
    </div>
  </div>;

  const lessonPanel = <StudyLessonPanel
    lessons={lessons}
    lessonMap={lessonMap}
    textbookUnits={textbookUnits}
    expandedLessons={expandedLessons}
    expandedUnits={expandedUnits}
    showAppendix={showAppendix}
    onToggleUnit={toggleUnit}
    onToggleLesson={toggleLesson}
  />;

  return <StudyMaterialPanel
    material={material}
    embedded={embedded}
    version={version}
    format={format}
    generating={generating}
    deleting={deleting}
    reviewing={reviewing}
    mutationLocked={mutationLocked}
    previewUrl={previewUrl}
    reviewOpen={reviewOpen}
    reviewForm={reviewForm}
    isReady={isReady}
    isTextbook={isTextbook}
    showTabs={showTabs}
    hasLessons={hasLessons}
    showVersionTabs={showVersionTabs}
    lessonCount={lessons.length}
    genLabel={genLabel}
    emptyLabel={emptyLabel}
    mdSource={mdSource}
    lessonPanel={lessonPanel}
    onBack={() => navigate('/study')}
    onGenerate={handleGenerate}
    onDelete={handleDelete}
    onReview={handleReview}
    onVersionChange={setVersion}
    onFormatChange={setFormat}
    onReviewOpenChange={setReviewOpen}
    onReviewFormChange={setReviewForm}
  />;
}
