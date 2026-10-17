import { useEffect, useState } from 'react'

/** Fetch once per `key`: returns { data, error } (both null while loading). */
export default function useApi(fetcher, key) {
  const [state, setState] = useState({ data: null, error: null })
  useEffect(() => {
    let live = true
    setState({ data: null, error: null })
    fetcher().then((data) => live && setState({ data, error: null }),
      (error) => live && setState({ data: null, error }))
    return () => { live = false }
  }, [key]) // eslint-disable-line react-hooks/exhaustive-deps
  return state
}
