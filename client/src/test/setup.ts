import '@testing-library/jest-dom';
import { vi } from 'vitest';

// Mock matchMedia for Ant Design
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

// Mock ResizeObserver
global.ResizeObserver = vi.fn().mockImplementation(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn(),
}));

// Mock scrollTo
window.scrollTo = vi.fn() as unknown as typeof window.scrollTo;

// @xterm/xterm probes canvas colors during module initialization. jsdom does
// not implement CanvasRenderingContext2D, so provide the tiny subset xterm and
// chart-like components need in unit tests.
const canvas2dContextMock = {
  canvas: null,
  fillStyle: '#000000',
  strokeStyle: '#000000',
  font: '10px sans-serif',
  fillRect: vi.fn(),
  clearRect: vi.fn(),
  getImageData: vi.fn(() => ({
    data: new Uint8ClampedArray([0, 0, 0, 255]),
    width: 1,
    height: 1,
    colorSpace: 'srgb',
  })),
  putImageData: vi.fn(),
  createImageData: vi.fn(() => ({
    data: new Uint8ClampedArray([0, 0, 0, 255]),
    width: 1,
    height: 1,
    colorSpace: 'srgb',
  })),
  measureText: vi.fn((text: string) => ({
    width: text.length * 7,
    actualBoundingBoxAscent: 8,
    actualBoundingBoxDescent: 2,
  })),
  beginPath: vi.fn(),
  closePath: vi.fn(),
  moveTo: vi.fn(),
  lineTo: vi.fn(),
  stroke: vi.fn(),
  fill: vi.fn(),
  save: vi.fn(),
  restore: vi.fn(),
  translate: vi.fn(),
  scale: vi.fn(),
  rotate: vi.fn(),
  setTransform: vi.fn(),
  resetTransform: vi.fn(),
};

Object.defineProperty(window.HTMLCanvasElement.prototype, 'getContext', {
  writable: true,
  value: vi.fn((contextId: string) => (contextId === '2d' ? canvas2dContextMock : null)),
});

// rc-table / antd may request computed styles with pseudo elements in jsdom.
const originalGetComputedStyle = window.getComputedStyle.bind(window);
window.getComputedStyle = ((element: Element, pseudoElt?: string | null) => {
  if (pseudoElt) {
    return {
      getPropertyValue: () => '',
      overflow: 'auto',
      overflowX: 'auto',
      overflowY: 'auto',
      width: '0px',
      height: '0px',
    } as unknown as CSSStyleDeclaration;
  }
  return originalGetComputedStyle(element);
}) as typeof window.getComputedStyle;

// Mock localStorage
const localStorageMock = {
  getItem: vi.fn(),
  setItem: vi.fn(),
  removeItem: vi.fn(),
  clear: vi.fn(),
};
Object.defineProperty(window, 'localStorage', { value: localStorageMock });

// Mock URL.createObjectURL
global.URL.createObjectURL = vi.fn(() => 'blob:mock-url');
global.URL.revokeObjectURL = vi.fn();
