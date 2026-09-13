import { useSearchParams } from 'react-router-dom'

export interface ProfessionalScope { jobId: string; planId: string; graphId: string }

/** URL-backed scope prevents management pages from silently using a fixed job. */
export function useProfessionalScope(): [ProfessionalScope, (next: Partial<ProfessionalScope>) => void] {
  const [search, setSearch] = useSearchParams()
  const scope = { jobId: search.get('job_id') ?? '', planId: search.get('plan_id') ?? '', graphId: search.get('graph_id') ?? '' }
  const setScope = (next: Partial<ProfessionalScope>) => {
    const result = new URLSearchParams(search)
    const pairs: [keyof ProfessionalScope, string][] = [['jobId', 'job_id'], ['planId', 'plan_id'], ['graphId', 'graph_id']]
    pairs.forEach(([property, key]) => {
      const value = next[property]
      if (value === undefined) return
      if (value) result.set(key, value)
      else result.delete(key)
    })
    setSearch(result, { replace: true })
  }
  return [scope, setScope]
}
