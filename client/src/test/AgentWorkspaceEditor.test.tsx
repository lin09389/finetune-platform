import { render, screen, fireEvent } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AgentWorkspaceEditor from "../components/chat/AgentWorkspaceEditor";
import type { OpenedFile } from "../components/chat/AgentWorkspaceEditor";
import { parseDiffHunks, buildPartialDiff } from "../utils/diffHunks";
import type { DiffHunk } from "../utils/diffHunks";

vi.mock("@monaco-editor/react", () => ({
  default: ({ value }: { value?: string }) => (
    <div data-testid="monaco-editor">{value}</div>
  ),
  DiffEditor: ({ original, modified, onMount }: { original?: string; modified?: string; onMount?: (e: any) => void }) => {
    onMount?.({
      getModifiedEditor: () => ({ revealLineInCenter: vi.fn() }),
    });
    return (
      <div data-testid="monaco-diff-editor">
        <span data-testid="original">{original}</span>
        <span data-testid="modified">{modified}</span>
      </div>
    );
  },
}));

vi.mock("../theme", () => ({
  useTheme: () => ({ theme: "dark", toggleTheme: vi.fn(), setTheme: vi.fn() }),
}));

/* ── fixtures ──────────────────────────────────────────────── */

const DIFF = [
  "--- a/src/Bar.tsx",
  "+++ b/src/Bar.tsx",
  "@@ -1,1 +1,1 @@",
  "-const a = 1;",
  "+const a = 2;",
  "@@ -5,1 +5,1 @@",
  "-const b = 1;",
  "+const b = 2;",
].join("\n");

const HUNKS: DiffHunk[] = parseDiffHunks("src/Bar.tsx", DIFF);

const ADDED_FILE: OpenedFile = {
  path: "src/Foo.tsx",
  name: "Foo.tsx",
  content: "export const Foo = () => null;",
  status: "added",
};

const MODIFIED_FILE: OpenedFile = {
  path: "src/Bar.tsx",
  name: "Bar.tsx",
  content: "const a = 2;\nconst b = 2;",
  original: "const a = 1;\nconst b = 1;",
  status: "modified",
  hunks: HUNKS,
};

const DELETED_FILE: OpenedFile = {
  path: "src/old.ts",
  name: "old.ts",
  content: "",
  status: "deleted",
};

/* ── helpers ───────────────────────────────────────────────── */

function renderEditor(props: Partial<React.ComponentProps<typeof AgentWorkspaceEditor>> = {}) {
  const onTabChange = vi.fn();
  const onTabClose = vi.fn();
  const result = render(
    <AgentWorkspaceEditor
      openedFiles={[]}
      activeFilePath={null}
      onTabChange={onTabChange}
      onTabClose={onTabClose}
      {...props}
    />,
  );
  return { ...result, onTabChange, onTabClose };
}

/* ══════════════════════════════════════════════════════════════
   diffHunks utility
═══════════════════════════════════════════════════════════════ */

describe("parseDiffHunks", () => {
  it("parses the correct number of hunks", () => {
    expect(HUNKS).toHaveLength(2);
  });

  it("assigns sequential IDs", () => {
    expect(HUNKS[0]?.id).toBe("src/Bar.tsx:0");
    expect(HUNKS[1]?.id).toBe("src/Bar.tsx:1");
  });

  it("reads hunk header coordinates", () => {
    expect(HUNKS[0]?.newStart).toBe(1);
    expect(HUNKS[1]?.newStart).toBe(5);
  });

  it("defaults all hunks to pending", () => {
    expect(HUNKS.every((h) => h.status === "pending")).toBe(true);
  });

  it("returns empty array for empty diff", () => {
    expect(parseDiffHunks("x.ts", "")).toHaveLength(0);
  });
});

describe("buildPartialDiff", () => {
  it("returns empty string when no hunks are accepted", () => {
    expect(buildPartialDiff(DIFF, HUNKS)).toBe("");
  });

  it("includes only accepted hunks", () => {
    const modified = HUNKS.map((h, i) =>
      i === 0 ? { ...h, status: "accepted" as const } : h
    );
    const out = buildPartialDiff(DIFF, modified);
    expect(out).toContain(HUNKS[0]!.header);
    expect(out).not.toContain(HUNKS[1]!.header);
  });
});

/* ══════════════════════════════════════════════════════════════
   AgentWorkspaceEditor – editor rendering
═══════════════════════════════════════════════════════════════ */

describe("AgentWorkspaceEditor", () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it("shows empty state when no files are opened", () => {
    renderEditor();
    expect(screen.getByLabelText("编辑器空状态")).toBeInTheDocument();
    expect(screen.getByText("暂无打开的文件")).toBeInTheDocument();
  });

  it("renders a regular editor for an added file", () => {
    renderEditor({ openedFiles: [ADDED_FILE], activeFilePath: ADDED_FILE.path });
    expect(screen.getByTestId("monaco-editor")).toBeInTheDocument();
    expect(screen.queryByTestId("monaco-diff-editor")).not.toBeInTheDocument();
  });

  it("renders a regular editor for a deleted file", () => {
    renderEditor({ openedFiles: [DELETED_FILE], activeFilePath: DELETED_FILE.path });
    expect(screen.getByTestId("monaco-editor")).toBeInTheDocument();
  });

  it("renders a diff editor for a modified file with original content", () => {
    renderEditor({ openedFiles: [MODIFIED_FILE], activeFilePath: MODIFIED_FILE.path });
    expect(screen.getByTestId("monaco-diff-editor")).toBeInTheDocument();
    expect(screen.queryByTestId("monaco-editor")).not.toBeInTheDocument();
  });

  it("renders a regular editor for a modified file without original", () => {
    const f: OpenedFile = { ...MODIFIED_FILE, original: undefined };
    renderEditor({ openedFiles: [f], activeFilePath: f.path });
    expect(screen.getByTestId("monaco-editor")).toBeInTheDocument();
  });

  /* ── tabs ─────────────────────────────────────────────────── */

  it("renders a tab for each opened file", () => {
    renderEditor({ openedFiles: [ADDED_FILE, MODIFIED_FILE], activeFilePath: ADDED_FILE.path });
    expect(screen.getAllByText("Foo.tsx").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Bar.tsx").length).toBeGreaterThan(0);
  });

  it("calls onTabChange when a tab is clicked", () => {
    const { onTabChange } = renderEditor({
      openedFiles: [ADDED_FILE, MODIFIED_FILE],
      activeFilePath: ADDED_FILE.path,
    });
    fireEvent.click(screen.getByText("Bar.tsx"));
    expect(onTabChange).toHaveBeenCalledWith(MODIFIED_FILE.path);
  });

  it("calls onTabClose and not onTabChange when the close button is clicked", () => {
    const { onTabChange, onTabClose } = renderEditor({
      openedFiles: [ADDED_FILE, MODIFIED_FILE],
      activeFilePath: ADDED_FILE.path,
    });
    fireEvent.click(screen.getByLabelText(`关闭 ${ADDED_FILE.name}`));
    expect(onTabClose).toHaveBeenCalledWith(ADDED_FILE.path);
    expect(onTabChange).not.toHaveBeenCalled();
  });

  it("marks the active tab as aria-selected=true", () => {
    renderEditor({ openedFiles: [ADDED_FILE, MODIFIED_FILE], activeFilePath: MODIFIED_FILE.path });
    const tabs = screen.getAllByRole("tab");
    const active = tabs.find((t) => t.getAttribute("aria-selected") === "true");
    expect(active).toBeDefined();
    expect(active).toHaveTextContent("Bar.tsx");
  });

  /* ── review toolbar ───────────────────────────────────────── */

  it("shows the AI Code Review toolbar for every file", () => {
    renderEditor({ openedFiles: [ADDED_FILE], activeFilePath: ADDED_FILE.path });
    expect(screen.getByText("Editor")).toBeInTheDocument();
  });

  it("shows file path in review toolbar", () => {
    renderEditor({ openedFiles: [MODIFIED_FILE], activeFilePath: MODIFIED_FILE.path });
    expect(screen.getByText(MODIFIED_FILE.path)).toBeInTheDocument();
  });

  /* ── hunk navigator ───────────────────────────────────────── */

  it("shows hunk navigator toolbar when the active file has hunks", () => {
    renderEditor({ openedFiles: [MODIFIED_FILE], activeFilePath: MODIFIED_FILE.path });
    expect(screen.getByRole("toolbar", { name: "Hunk 导航" })).toBeInTheDocument();
    expect(screen.getByText(/Hunk 1 \/ 2/)).toBeInTheDocument();
  });

  it("does not show hunk navigator for a file without hunks", () => {
    renderEditor({ openedFiles: [ADDED_FILE], activeFilePath: ADDED_FILE.path });
    expect(screen.queryByRole("toolbar", { name: "Hunk 导航" })).not.toBeInTheDocument();
  });

  it("Prev button is disabled on the first hunk", () => {
    renderEditor({ openedFiles: [MODIFIED_FILE], activeFilePath: MODIFIED_FILE.path });
    expect(screen.getByLabelText("上一个 hunk")).toBeDisabled();
  });

  it("Next button navigates to the next hunk", () => {
    renderEditor({ openedFiles: [MODIFIED_FILE], activeFilePath: MODIFIED_FILE.path });
    fireEvent.click(screen.getByLabelText("下一个 hunk"));
    expect(screen.getByText(/Hunk 2 \/ 2/)).toBeInTheDocument();
  });

  it("Next button is disabled on the last hunk", () => {
    renderEditor({ openedFiles: [MODIFIED_FILE], activeFilePath: MODIFIED_FILE.path });
    fireEvent.click(screen.getByLabelText("下一个 hunk"));
    expect(screen.getByLabelText("下一个 hunk")).toBeDisabled();
  });

  it("calls onAcceptHunk with the correct arguments", () => {
    const onAcceptHunk = vi.fn();
    renderEditor({
      openedFiles: [MODIFIED_FILE],
      activeFilePath: MODIFIED_FILE.path,
      onAcceptHunk,
    });
    fireEvent.click(screen.getByLabelText("接受当前 hunk"));
    expect(onAcceptHunk).toHaveBeenCalledWith(MODIFIED_FILE.path, HUNKS[0]!.id);
  });

  it("accepts all hunks with Alt+Shift+A", () => {
    const onAcceptAll = vi.fn();
    renderEditor({
      openedFiles: [MODIFIED_FILE],
      activeFilePath: MODIFIED_FILE.path,
      onAcceptAll,
    });
    fireEvent.keyDown(document, { key: "A", altKey: true, shiftKey: true });
    expect(onAcceptAll).toHaveBeenCalledWith(MODIFIED_FILE.path);
  });

  it("calls onRejectHunk with the correct arguments", () => {
    const onRejectHunk = vi.fn();
    renderEditor({
      openedFiles: [MODIFIED_FILE],
      activeFilePath: MODIFIED_FILE.path,
      onRejectHunk,
    });
    fireEvent.click(screen.getByLabelText("拒绝当前 hunk"));
    expect(onRejectHunk).toHaveBeenCalledWith(MODIFIED_FILE.path, HUNKS[0]!.id);
  });

  it("disables Accept/Reject buttons when the current hunk is not pending", () => {
    const accepted: OpenedFile = {
      ...MODIFIED_FILE,
      hunks: HUNKS.map((h) => ({ ...h, status: "accepted" as const })),
    };
    renderEditor({ openedFiles: [accepted], activeFilePath: accepted.path });
    expect(screen.getByLabelText("接受当前 hunk")).toBeDisabled();
    expect(screen.getByLabelText("拒绝当前 hunk")).toBeDisabled();
  });

  it("shows pending dot on tab when file has pending hunks", () => {
    renderEditor({ openedFiles: [MODIFIED_FILE], activeFilePath: MODIFIED_FILE.path });
    expect(document.querySelector('[title="有待确认时的 hunk"]')).toBeInTheDocument();
  });
});
