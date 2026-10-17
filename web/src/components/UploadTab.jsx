import { useRef } from 'react'

/**
 * The upload box at the top of the dashboard. An uploaded logbook is combined with Fleet A and Fleet B
 * (POST /api/upload) and shown on the Combined tab. `upload` = { busy, error, info }, where info =
 * { dataset, name, n_drones, n_flights, sources, notes } once a file is loaded.
 */
export function UploadBar({ upload, onFile, onReset }) {
  const input = useRef(null)
  const choose = (e) => {
    const file = e.target.files?.[0]
    if (file) onFile(file)
    e.target.value = ''
  }
  const info = upload.info
  return (
    <div className="panel upload-bar">
      <div className="upload-row">
        <span className="upload-title">Check your own logbook</span>
        <button type="button" className="upload-btn" disabled={upload.busy} onClick={() => input.current?.click()}>
          {upload.busy ? 'Loading…' : 'Upload a file'}
        </button>
        <input ref={input} className="upload-input" type="file" onChange={choose} tabIndex={-1} aria-hidden="true"
               accept=".xlsx,.xlsm,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" />
        <a className="upload-example" href="./example_logbook.xlsx" download>Download the example workbook</a>
        {info && <button type="button" className="upload-close" onClick={onReset}>Remove the upload</button>}
      </div>
      {info ? (
        <p className="upload-now">Added <b>{info.name}</b> to Fleet A and Fleet B: see the <a href="#combined">Combined tab</a>{' '}
          ({info.n_drones} drones, {info.n_flights.toLocaleString('en-US')} flights). The other tabs still show the test fleets.</p>
      ) : (
        <p className="rule-note upload-intro">An Excel workbook with <b>flights</b> and <b>components</b> sheets (optional:{' '}
          <b>maintenance</b>), with the same columns as the test fleets. It is combined with Fleet A and Fleet B on a new
          Combined tab.</p>
      )}
      {info?.notes?.map((n) => <p key={n} className="rule-note upload-intro">{n}</p>)}
      {upload.error && <div className="upload-error">Couldn't use that file: {upload.error.message}</div>}
    </div>
  )
}
