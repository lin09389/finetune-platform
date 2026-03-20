import { useState, useEffect, useRef, useCallback, useImperativeHandle, forwardRef } from 'react'

export interface TypewriterTextProps {
  text: string
  speed?: number
  onComplete?: () => void
  showCursor?: boolean
  paused?: boolean
  className?: string
  cursorChar?: string
}

export interface TypewriterTextRef {
  pause: () => void
  resume: () => void
  reset: () => void
  isComplete: boolean
  displayedLength: number
}

const TypewriterText = forwardRef<TypewriterTextRef, TypewriterTextProps>(
  (
    {
      text,
      speed = 50,
      onComplete,
      showCursor = true,
      paused = false,
      className = '',
      cursorChar = '▋',
    },
    ref
  ) => {
    const [displayedText, setDisplayedText] = useState('')
    const [isComplete, setIsComplete] = useState(false)
    const [isPaused, setIsPaused] = useState(paused)

    const charIndexRef = useRef(0)
    const lastTimeRef = useRef(0)
    const animationRef = useRef<number>(0)
    const onCompleteRef = useRef(onComplete)

    useEffect(() => {
      onCompleteRef.current = onComplete
    }, [onComplete])

    const interval = 1000 / speed

    const reset = useCallback(() => {
      charIndexRef.current = 0
      lastTimeRef.current = 0
      setDisplayedText('')
      setIsComplete(false)
    }, [])

    const pause = useCallback(() => {
      setIsPaused(true)
    }, [])

    const resume = useCallback(() => {
      setIsPaused(false)
    }, [])

    useImperativeHandle(
      ref,
      () => ({
        pause,
        resume,
        reset,
        isComplete,
        displayedLength: displayedText.length,
      }),
      [pause, resume, reset, isComplete, displayedText.length]
    )

    useEffect(() => {
      if (paused !== isPaused) {
        setIsPaused(paused)
      }
    }, [paused])

    useEffect(() => {
      reset()
    }, [text, reset])

    useEffect(() => {
      if (isPaused || isComplete) {
        if (animationRef.current) {
          cancelAnimationFrame(animationRef.current)
          animationRef.current = 0
        }
        return
      }

      const animate = (time: number) => {
        if (isPaused || isComplete) {
          return
        }

        if (time - lastTimeRef.current >= interval) {
          const currentLength = charIndexRef.current

          if (currentLength < text.length) {
            const nextLength = currentLength + 1
            charIndexRef.current = nextLength
            setDisplayedText(text.slice(0, nextLength))
            lastTimeRef.current = time
          } else {
            setIsComplete(true)
            onCompleteRef.current?.()
            return
          }
        }

        animationRef.current = requestAnimationFrame(animate)
      }

      animationRef.current = requestAnimationFrame(animate)

      return () => {
        if (animationRef.current) {
          cancelAnimationFrame(animationRef.current)
          animationRef.current = 0
        }
      }
    }, [text, interval, isPaused, isComplete])

    return (
      <span className={`typewriter-text ${className}`}>
        <span className="typewriter-content">{displayedText}</span>
        {showCursor && !isComplete && (
          <span className="typewriter-cursor">{cursorChar}</span>
        )}

        <style>{`
          .typewriter-text {
            display: inline;
          }

          .typewriter-content {
            white-space: pre-wrap;
            word-break: break-word;
          }

          .typewriter-cursor {
            display: inline-block;
            color: var(--primary-500, #1890ff);
            font-weight: 300;
            animation: cursor-blink 1s step-end infinite;
            margin-left: 1px;
            vertical-align: baseline;
          }

          @keyframes cursor-blink {
            0%, 50% {
              opacity: 1;
            }
            51%, 100% {
              opacity: 0;
            }
          }
        `}</style>
      </span>
    )
  }
)

TypewriterText.displayName = 'TypewriterText'

export default TypewriterText
