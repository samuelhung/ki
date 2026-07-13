import CircularGallery, { type CircularGalleryItem } from '../components/react-bits/CircularGallery';
import './CircularGalleryDemo.css';

const ITEMS: CircularGalleryItem[] = [
  { image: 'https://picsum.photos/seed/cg-bridge/1200/900', text: 'Bridge' },
  { image: 'https://picsum.photos/seed/cg-studio/1200/900', text: 'Studio' },
  { image: 'https://picsum.photos/seed/cg-water/1200/900', text: 'Waterfall' },
  { image: 'https://picsum.photos/seed/cg-field/1200/900', text: 'Wild Field' },
  { image: 'https://picsum.photos/seed/cg-depth/1200/900', text: 'Deep Water' },
  { image: 'https://picsum.photos/seed/cg-rail/1200/900', text: 'Train Track' },
  { image: 'https://picsum.photos/seed/cg-coast/1200/900', text: 'Coastline' },
  { image: 'https://picsum.photos/seed/cg-night/1200/900', text: 'Night Lights' },
  { image: 'https://picsum.photos/seed/cg-city/1200/900', text: 'New York' },
  { image: 'https://picsum.photos/seed/cg-desert/1200/900', text: 'Desert Air' },
  { image: 'https://picsum.photos/seed/cg-island/1200/900', text: 'Santorini' },
  { image: 'https://picsum.photos/seed/cg-palm/1200/900', text: 'Palm Trees' },
];

export default function CircularGalleryDemo() {
  return (
    <main className="circular-gallery-demo">
      <header className="circular-gallery-demo__header">
        <div><span>REACT BITS / OGL</span><h1>Circular Gallery</h1></div>
        <dl><div><dt>RADIUS</dt><dd>0.1</dd></div><div><dt>SPEED</dt><dd>2.7</dd></div><div><dt>EASE</dt><dd>0.12</dd></div></dl>
      </header>
      <section className="circular-gallery-demo__stage" aria-label="Circular Gallery 演示舞台">
        <CircularGallery items={ITEMS} bend={3} borderRadius={0.1} scrollSpeed={2.7} scrollEase={0.12} textColor="#f6f3ff" />
      </section>
      <footer className="circular-gallery-demo__footer"><span>12 / LOOP</span><i /></footer>
    </main>
  );
}
