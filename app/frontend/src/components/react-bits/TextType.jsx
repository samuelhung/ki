import React, { createElement, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import './TextType.css';

export default function TextType({
  text,
  texts,
  as: Component = 'div',
  typingSpeed = 50,
  initialDelay = 0,
  pauseDuration = 2000,
  deletingSpeed = 30,
  loop = true,
  className = '',
  showCursor = true,
  hideCursorWhileTyping = false,
  cursorCharacter = '|',
  cursorClassName = '',
  cursorBlinkDuration = 0.5,
  textColors = [],
  variableSpeed,
  onSentenceComplete,
  startOnVisible = false,
  reverseMode = false,
  ...props
}) {
  const [displayedText, setDisplayedText] = useState('');
  const [currentCharIndex, setCurrentCharIndex] = useState(0);
  const [isDeleting, setIsDeleting] = useState(false);
  const [currentTextIndex, setCurrentTextIndex] = useState(0);
  const [isVisible, setIsVisible] = useState(!startOnVisible);
  const containerRef = useRef(null);

  const sourceText = text ?? texts ?? '';
  const textArray = useMemo(() => (Array.isArray(sourceText) ? sourceText : [sourceText]), [sourceText]);

  const getRandomSpeed = useCallback(() => {
    if (!variableSpeed) return typingSpeed;
    const { min, max } = variableSpeed;
    return Math.random() * (max - min) + min;
  }, [typingSpeed, variableSpeed]);

  useEffect(() => {
    if (!startOnVisible || !containerRef.current) return undefined;

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) setIsVisible(true);
        });
      },
      { threshold: 0.1 },
    );

    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, [startOnVisible]);

  useEffect(() => {
    setDisplayedText('');
    setCurrentCharIndex(0);
    setIsDeleting(false);
    setCurrentTextIndex(0);
  }, [textArray]);

  useEffect(() => {
    if (!isVisible || textArray.length === 0) return undefined;

    let timeout;
    const currentText = textArray[currentTextIndex] || '';
    const processedText = reverseMode ? currentText.split('').reverse().join('') : currentText;

    if (isDeleting) {
      if (displayedText === '') {
        if (onSentenceComplete) onSentenceComplete(textArray[currentTextIndex], currentTextIndex);
        if (currentTextIndex === textArray.length - 1 && !loop) return undefined;
        timeout = setTimeout(() => {
          setIsDeleting(false);
          setCurrentTextIndex((prev) => (prev + 1) % textArray.length);
          setCurrentCharIndex(0);
        }, pauseDuration);
      } else {
        timeout = setTimeout(() => {
          setDisplayedText((prev) => prev.slice(0, -1));
        }, deletingSpeed);
      }
    } else if (currentCharIndex < processedText.length) {
      timeout = setTimeout(
        () => {
          setDisplayedText((prev) => prev + processedText[currentCharIndex]);
          setCurrentCharIndex((prev) => prev + 1);
        },
        currentCharIndex === 0 && displayedText === '' ? initialDelay : (variableSpeed ? getRandomSpeed() : typingSpeed),
      );
    } else if (loop || currentTextIndex < textArray.length - 1) {
      timeout = setTimeout(() => setIsDeleting(true), pauseDuration);
    }

    return () => clearTimeout(timeout);
  }, [
    currentCharIndex,
    currentTextIndex,
    deletingSpeed,
    displayedText,
    getRandomSpeed,
    initialDelay,
    isDeleting,
    isVisible,
    loop,
    onSentenceComplete,
    pauseDuration,
    reverseMode,
    textArray,
    typingSpeed,
    variableSpeed,
  ]);

  const currentColor = textColors.length > 0 ? textColors[currentTextIndex % textColors.length] : undefined;
  const shouldHideCursor =
    hideCursorWhileTyping && (currentCharIndex < (textArray[currentTextIndex] || '').length || isDeleting);

  return createElement(
    Component,
    {
      ref: containerRef,
      className: `text-type ${className}`,
      style: { '--cursor-blink-duration': `${cursorBlinkDuration}s`, ...props.style },
      ...props,
    },
    <span className="text-type__content" style={{ color: currentColor || 'inherit' }}>
      {displayedText}
    </span>,
    showCursor && (
      <span className={`text-type__cursor ${cursorClassName} ${shouldHideCursor ? 'text-type__cursor--hidden' : ''}`}>
        {cursorCharacter}
      </span>
    ),
  );
}
