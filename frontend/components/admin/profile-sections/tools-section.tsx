'use client';

import { useState } from 'react';
import type { HttpMethod, ParamType, UseProfileFormReturn } from '@/hooks/use-profile-form';
import { HTTP_METHODS, PARAM_TYPES } from '@/hooks/use-profile-form';
import { AUTO_MOUNTED_TOOL_NAMES } from '@/lib/agent-graph';
import { CollapsibleSection } from '../collapsible-section';

const inputClass =
  'border-border bg-background text-foreground w-full rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40';

interface ToolsSectionProps {
  form: UseProfileFormReturn;
}

export function ToolsSection({ form }: ToolsSectionProps) {
  const {
    availableTools,
    builtinSelected,
    httpTools,
    httpToolIndices,
    toggleTool,
    addHttpTool,
    updateHttpTool,
    removeHttpTool,
    updateHttpToolParam,
    addHttpToolParam,
    removeHttpToolParam,
  } = form;

  const badgeText = `${builtinSelected.size + httpTools.length}`;
  const rawBuiltinCount = (form.known.tools || []).filter((t) => !t.endpoint).length;

  return (
    <CollapsibleSection
      title="Tools"
      id="section-tools"
      badge={badgeText}
      defaultOpen={rawBuiltinCount + httpTools.length > 0}
    >
      <div className="space-y-4">
        {/* Built-in Tools */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-foreground/70 text-xs font-medium">Built-in</span>
            <span className="text-foreground/50 text-xs">
              {builtinSelected.size}/{availableTools.length}
            </span>
          </div>
          {availableTools.length === 0 ? (
            <p className="text-foreground/50 text-xs">無法載入工具清單</p>
          ) : (
            <div className="grid grid-cols-1 gap-1.5">
              {availableTools
                .filter((n) => !AUTO_MOUNTED_TOOL_NAMES.includes(n))
                .map((toolName) => {
                  const checked = builtinSelected.has(toolName);
                  return (
                    <label
                      key={toolName}
                      className={`flex cursor-pointer items-center gap-2 rounded-md border px-3 py-1.5 text-xs transition-colors ${
                        checked
                          ? 'border-primary/50 bg-primary/5'
                          : 'border-border hover:bg-foreground/5'
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggleTool(toolName)}
                        className="size-3"
                      />
                      <span className="font-mono">{toolName}</span>
                    </label>
                  );
                })}
            </div>
          )}
        </div>

        {/* HTTP Tools */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-foreground/70 text-xs font-medium">HTTP Tools</span>
            <button
              type="button"
              onClick={addHttpTool}
              className="border-border hover:bg-foreground/5 rounded border px-2 py-0.5 text-xs"
            >
              + Add
            </button>
          </div>
          {httpTools.length === 0 && (
            <p className="text-foreground/50 rounded-md border border-dashed py-3 text-center text-xs">
              尚無 HTTP 工具
            </p>
          )}
          <div className="space-y-2">
            {httpTools.map((tool, htIdx) => {
              const realIdx = httpToolIndices[htIdx];
              return (
                <HttpToolCard
                  key={realIdx}
                  tool={tool}
                  realIdx={realIdx}
                  updateHttpTool={updateHttpTool}
                  removeHttpTool={removeHttpTool}
                  updateHttpToolParam={updateHttpToolParam}
                  addHttpToolParam={addHttpToolParam}
                  removeHttpToolParam={removeHttpToolParam}
                />
              );
            })}
          </div>
        </div>
      </div>
    </CollapsibleSection>
  );
}

// ─── HTTP Tool Card ───────────────────────────────────────────────

function HttpToolCard({
  tool,
  realIdx,
  updateHttpTool,
  removeHttpTool,
  updateHttpToolParam,
  addHttpToolParam,
  removeHttpToolParam,
}: {
  tool: UseProfileFormReturn['httpTools'][number];
  realIdx: number;
  updateHttpTool: UseProfileFormReturn['updateHttpTool'];
  removeHttpTool: UseProfileFormReturn['removeHttpTool'];
  updateHttpToolParam: UseProfileFormReturn['updateHttpToolParam'];
  addHttpToolParam: UseProfileFormReturn['addHttpToolParam'];
  removeHttpToolParam: UseProfileFormReturn['removeHttpToolParam'];
}) {
  const [open, setOpen] = useState(false);
  const paramCount = (tool.parameters || []).length;

  return (
    <div className="border-border bg-foreground/5 rounded-md border">
      <div className="flex items-stretch">
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="hover:bg-foreground/5 flex flex-1 items-center gap-2 px-2 py-1.5 text-left"
        >
          <span className="text-foreground/50 w-3 text-xs">{open ? '▾' : '▸'}</span>
          <span
            className={`shrink-0 rounded px-1 py-0.5 font-mono text-[9px] ${
              tool.method === 'GET'
                ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300'
                : tool.method === 'DELETE'
                  ? 'bg-red-500/15 text-red-700 dark:text-red-300'
                  : 'bg-blue-500/15 text-blue-700 dark:text-blue-300'
            }`}
          >
            {tool.method || 'POST'}
          </span>
          <span className="flex-1 truncate font-mono text-xs">{tool.name || '未命名'}</span>
          <span className="text-foreground/40 shrink-0 text-xs">{paramCount}p</span>
        </button>
        <button
          type="button"
          onClick={() => removeHttpTool(realIdx)}
          className="border-border hover:bg-foreground/10 min-h-8 min-w-8 border-l px-2 text-xs text-red-500"
        >
          ✕
        </button>
      </div>
      {open && (
        <div className="border-border space-y-2 border-t p-2">
          <input
            type="text"
            placeholder="tool_name (snake_case)"
            value={tool.name}
            onChange={(e) => updateHttpTool(realIdx, { name: e.target.value })}
            className={`${inputClass} font-mono text-xs`}
          />
          <input
            type="text"
            placeholder="Description（給 LLM 看）"
            value={tool.description || ''}
            onChange={(e) => updateHttpTool(realIdx, { description: e.target.value })}
            className={`${inputClass} text-xs`}
          />
          <div className="grid grid-cols-[1fr_80px] gap-2">
            <input
              type="text"
              placeholder="https://api.example.com/path"
              value={tool.endpoint || ''}
              onChange={(e) => updateHttpTool(realIdx, { endpoint: e.target.value })}
              className={`${inputClass} text-xs`}
            />
            <select
              value={tool.method || 'POST'}
              onChange={(e) => updateHttpTool(realIdx, { method: e.target.value as HttpMethod })}
              className={`${inputClass} text-xs`}
            >
              {HTTP_METHODS.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </div>
          <input
            type="text"
            placeholder="Auth Header (e.g. Bearer ${API_KEY})"
            value={tool.auth_header || ''}
            onChange={(e) => updateHttpTool(realIdx, { auth_header: e.target.value })}
            className={`${inputClass} font-mono text-xs`}
          />
          {/* Parameters */}
          <div>
            <div className="mb-1 flex items-center justify-between">
              <span className="text-foreground/70 text-xs">Parameters</span>
              <button
                type="button"
                onClick={() => addHttpToolParam(realIdx)}
                className="text-foreground/60 hover:text-foreground min-h-8 min-w-8 text-xs"
              >
                + Add
              </button>
            </div>
            <div className="space-y-1.5">
              {(tool.parameters || []).map((param, pIdx) => (
                <div key={pIdx} className="space-y-0.5">
                  <div className="flex items-center gap-1">
                    <input
                      type="text"
                      placeholder="name"
                      value={param.name}
                      onChange={(e) => updateHttpToolParam(realIdx, pIdx, { name: e.target.value })}
                      className="border-border bg-background min-w-0 flex-1 rounded border px-1.5 py-0.5 font-mono text-xs"
                    />
                    <select
                      value={param.type}
                      onChange={(e) =>
                        updateHttpToolParam(realIdx, pIdx, { type: e.target.value as ParamType })
                      }
                      className="border-border bg-background w-16 rounded border px-1 py-0.5 text-xs"
                    >
                      {PARAM_TYPES.map((t) => (
                        <option key={t} value={t}>
                          {t}
                        </option>
                      ))}
                    </select>
                    <label className="flex items-center gap-0.5 text-xs">
                      <input
                        type="checkbox"
                        checked={!!param.required}
                        onChange={(e) =>
                          updateHttpToolParam(realIdx, pIdx, { required: e.target.checked })
                        }
                        className="size-2.5"
                      />
                      req
                    </label>
                    <button
                      type="button"
                      onClick={() => removeHttpToolParam(realIdx, pIdx)}
                      className="text-foreground/40 text-xs hover:text-red-500"
                    >
                      ✕
                    </button>
                  </div>
                  <input
                    type="text"
                    placeholder="Description（給 LLM 看，選填）"
                    value={param.description || ''}
                    onChange={(e) =>
                      updateHttpToolParam(realIdx, pIdx, {
                        description: e.target.value || undefined,
                      })
                    }
                    className="border-border bg-background text-foreground/70 w-full rounded border px-1.5 py-0.5 text-xs"
                  />
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
