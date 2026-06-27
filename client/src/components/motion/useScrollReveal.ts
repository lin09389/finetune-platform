import { useAnimation, useInView } from 'framer-motion';
import { useEffect, useRef } from 'react';

type InViewOptions = NonNullable<Parameters<typeof useInView>[1]>;
type InViewMargin = InViewOptions['margin'];

/**
 * useScrollReveal 配置项
 */
interface ScrollRevealOptions {
  /** 触发动画的阈值，0 表示只要有一点出现就触发，1 表示完全出现才触发 */
  amount?: 'some' | 'all' | number;
  /** 元素距离视口多远开始触发动画，如 "-100px" */
  margin?: string;
  /** 是否只触发一次 */
  once?: boolean;
}

/**
 * useScrollReveal:
 * 当元素滚动进入视口时，触发动画。
 * 返回 ref 绑定到目标元素，并返回 framer-motion 的 animation controls 传递给 animate 属性。
 */
export function useScrollReveal(options: ScrollRevealOptions = {}) {
  const { amount = 'some', margin = '0px', once = true } = options;
  
  // 绑定到目标元素
  const ref = useRef<HTMLElement | null>(null);
  
  // 监听是否在视口中
  const isInView = useInView(ref, {
    amount,
    margin: margin as InViewMargin,
    once,
  });

  // 手动控制动画状态
  const controls = useAnimation();

  useEffect(() => {
    if (isInView) {
      // 元素出现，播放 animate 变体
      controls.start('animate');
    } else if (!once) {
      // 如果不是只触发一次，且元素离开视口，则重置为 initial 变体
      controls.start('initial');
    }
  }, [isInView, controls, once]);

  return { ref, controls, isInView };
}
