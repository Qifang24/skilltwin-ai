import type { ImportRowState, OptimizationSuggestion, SuggestionState } from '@/types/professional'

export interface TagPresentation { color: string; label: string }

export function importRowPresentation(state: ImportRowState): TagPresentation {
  const values: Record<ImportRowState, TagPresentation> = {
    valid: { color: 'blue', label: '可导入' },
    warning: { color: 'gold', label: '警告' },
    error: { color: 'red', label: '失败' },
    duplicate: { color: 'orange', label: '重复' },
    imported: { color: 'green', label: '已导入' },
    filtered: { color: 'default', label: '已过滤' },
  }
  return values[state]
}

export function coveragePresentation(status: string): TagPresentation {
  const values: Record<string, TagPresentation> = {
    covered: { color: 'green', label: '已覆盖' }, practice: { color: 'green', label: '已覆盖' },
    partial: { color: 'gold', label: '部分覆盖' }, introduced: { color: 'gold', label: '部分覆盖' },
    uncovered: { color: 'red', label: '未覆盖' }, unmapped: { color: 'red', label: '未覆盖' },
  }
  return values[status] ?? { color: 'default', label: status }
}

export function filterSuggestions(items: OptimizationSuggestion[], filter: 'all' | SuggestionState): OptimizationSuggestion[] {
  return filter === 'all' ? items : items.filter((item) => item.state === filter)
}

export function nextSuggestionState(action: 'adopt' | 'ignore'): SuggestionState {
  return action === 'adopt' ? 'adopted' : 'ignored'
}
