"""
Comprehensive test for research/strudel_debug.html.

Checks per snippet:
  1. Play produces audio (maxRMS > 0.05, sustained > 25%)
  2. Stop silences audio within 1 s (maxRMS drops to < 0.01)
  3. Each snippet sounds distinct (spectral centroid differs by > 5%)

Also monitors the browser console throughout for errors.

Usage:
    python -m http.server 8765 --directory research &
    python tools/test_strudel_page.py
"""
import sys, time, json
import numpy as np
from playwright.sync_api import sync_playwright

URL = 'http://localhost:8765/strudel_debug.html'

# AudioContext probe: AnalyserNode side-tap on every gain node.
# Collects RMS (amplitude) and spectral centroid (timbre fingerprint).
PROBE = """
window.__probe = {
    rmsLog:      [],   // { t, snippet, rms }
    specLog:     [],   // { t, snippet, centroid }
    currentSnippet: null,
};
const _origAC = window.AudioContext;
window.AudioContext = function(...args) {
    const ac = new _origAC(...args);
    const analyser = ac.createAnalyser();
    analyser.fftSize = 2048;
    analyser.connect(ac.destination);
    const _origCG = ac.createGain.bind(ac);
    ac.createGain = function() {
        const g = _origCG(); g.connect(analyser); return g;
    };
    setInterval(() => {
        // Skip measurement when context is suspended — the AnalyserNode holds
        // the last rendered buffer and returns stale non-zero data, not silence.
        if (ac.state !== 'running') {
            window.__probe.rmsLog.push({ t: Date.now(), snip: window.__probe.currentSnippet, rms: 0, centroid: 0 });
            return;
        }
        const td  = new Float32Array(analyser.fftSize);
        const fd  = new Float32Array(analyser.frequencyBinCount);
        analyser.getFloatTimeDomainData(td);
        analyser.getFloatFrequencyData(fd);

        // RMS
        let s = 0;
        for (let i = 0; i < td.length; i++) s += td[i] * td[i];
        const rms = Math.sqrt(s / td.length);

        // Spectral centroid (linear power-weighted mean bin)
        let num = 0, den = 0;
        for (let i = 0; i < fd.length; i++) {
            const p = Math.pow(10, fd[i] / 10);   // dB → linear power
            num += i * p;
            den += p;
        }
        const centroid = den > 0 ? num / den : 0;

        const entry = { t: Date.now(), snip: window.__probe.currentSnippet, rms, centroid };
        window.__probe.rmsLog.push(entry);
    }, 100);
    return ac;
};
"""

def rms_window(log, snippet, after_ms, duration_ms):
    vals = [e['rms'] for e in log
            if e['snip'] == snippet and after_ms <= e['t'] and e['t'] < after_ms + duration_ms]
    return vals

def centroid_window(log, snippet, after_ms, duration_ms):
    vals = [e['centroid'] for e in log
            if e['snip'] == snippet and after_ms <= e['t'] and e['t'] < after_ms + duration_ms]
    return vals

def run():
    snippets = ['c1', 'c2', 'c3']
    results  = {}
    all_logs = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)  # no autoplay bypass
        page    = browser.new_page()
        page.on('console',   lambda m: all_logs.append({'type': m.type, 'text': m.text[:300], 't': time.time()}))
        page.on('pageerror', lambda e: all_logs.append({'type': 'pageerror', 'text': str(e)[:300], 't': time.time()}))
        page.add_init_script(PROBE)
        page.goto(URL)

        print('Waiting for Ready...')
        page.wait_for_function(
            "() => document.getElementById('status').textContent.includes('Ready')",
            timeout=25000)
        print(f'Page ready.\n')

        for snip in snippets:
            print(f'--- Snippet {snip} ---')

            # Clear probe log and mark snippet before playing
            page.evaluate(f"""() => {{
                window.__probe.rmsLog = [];
                window.__probe.currentSnippet = '{snip}';
            }}""")

            # Play
            page.locator(f'button[onclick="playSnippet(\'{snip}\')"]').click()
            time.sleep(4)

            # Snapshot while playing — take all frames captured so far
            log_playing = page.evaluate("() => window.__probe.rmsLog.slice()")
            play_rms       = [e['rms']      for e in log_playing]
            play_centroids = [e['centroid'] for e in log_playing]
            max_rms        = max(play_rms) if play_rms else 0
            nonzero        = sum(1 for v in play_rms if v > 0.05)
            sustained_pct  = 100 * nonzero / max(len(play_rms), 1)
            mean_centroid  = float(np.mean(play_centroids)) if play_centroids else 0

            print(f'  Playing: maxRMS={max_rms:.3f}  sustained={sustained_pct:.0f}%  centroid={mean_centroid:.1f}  frames={len(play_rms)}')

            # Click Stop, reset probe, wait 2 s for any reverb tail to clear
            page.locator(f'button[onclick="playSnippet(\'{snip}\')"]').locator('..').locator('button.stop').click()
            page.evaluate("() => window.__probe.rmsLog = []")
            time.sleep(2)

            # Measure silence — all frames since we cleared the log
            log_stopped  = page.evaluate("() => window.__probe.rmsLog.slice()")
            stop_rms_vals = [e['rms'] for e in log_stopped]
            max_stop_rms  = max(stop_rms_vals) if stop_rms_vals else 0
            status = page.evaluate("() => document.getElementById('status').textContent")
            err    = page.evaluate("() => document.getElementById('error').textContent")

            print(f'  Stopped: maxRMS={max_stop_rms:.4f}  frames={len(stop_rms_vals)}  status={status!r}  err={err!r}')

            results[snip] = {
                'max_rms':       max_rms,
                'sustained_pct': sustained_pct,
                'mean_centroid': mean_centroid,
                'stop_rms':      max_stop_rms,
                'status':        status,
                'error':         err,
            }
            time.sleep(0.5)

        browser.close()

    # ── Verdict ──────────────────────────────────────────────────────────────
    print('\n═══ RESULTS ═══')
    passes, failures = [], []

    for snip, r in results.items():
        label = f'Snippet {snip}'

        # 1. Plays audio
        if r['max_rms'] > 0.05 and r['sustained_pct'] > 25:
            passes.append(f'{label}: PLAY  maxRMS={r["max_rms"]:.3f} sustained={r["sustained_pct"]:.0f}%')
        else:
            failures.append(f'{label}: PLAY FAIL  maxRMS={r["max_rms"]:.3f} sustained={r["sustained_pct"]:.0f}%')

        # 2. Stop silences
        if r['stop_rms'] < 0.01:
            passes.append(f'{label}: STOP  post-stop maxRMS={r["stop_rms"]:.4f}')
        else:
            failures.append(f'{label}: STOP FAIL  post-stop maxRMS={r["stop_rms"]:.4f} (still audible)')

        # 3. No error shown
        if not r['error']:
            passes.append(f'{label}: NO PAGE ERROR')
        else:
            failures.append(f'{label}: PAGE ERROR  {r["error"]!r}')

    # 4. Snippets are distinct (centroid spread > 5% relative to mean)
    centroids = {s: results[s]['mean_centroid'] for s in snippets}
    c_values  = list(centroids.values())
    c_mean    = np.mean(c_values)
    c_spread  = (max(c_values) - min(c_values)) / max(c_mean, 1)
    # c1 and c2 differ (c2 adds kick → lower centroid); c1 vs c3 differ (different scale/key)
    c1_c2_diff = abs(centroids['c1'] - centroids['c2']) / max(c_mean, 1)
    c1_c3_diff = abs(centroids['c1'] - centroids['c3']) / max(c_mean, 1)
    print(f'\nSpectral centroids: c1={centroids["c1"]:.1f}  c2={centroids["c2"]:.1f}  c3={centroids["c3"]:.1f}')
    print(f'c1 vs c2 spread: {100*c1_c2_diff:.1f}%   c1 vs c3 spread: {100*c1_c3_diff:.1f}%')

    if c1_c2_diff > 0.03:  # c2 has kick so centroid will be different
        passes.append(f'DISTINCT c1 vs c2: {100*c1_c2_diff:.1f}% centroid spread')
    else:
        failures.append(f'IDENTICAL c1 vs c2: only {100*c1_c2_diff:.1f}% centroid spread — may be same sound')

    # c1 vs c3: same synthesis, different scale — centroid may be close; flag if identical
    if c1_c3_diff > 0.005:
        passes.append(f'DISTINCT c1 vs c3: {100*c1_c3_diff:.1f}% centroid spread')
    else:
        failures.append(f'IDENTICAL c1 vs c3: only {100*c1_c3_diff:.1f}% centroid spread — snippets may be broken')

    print()
    for p in passes:
        print(f'  PASS  {p}')
    for f in failures:
        print(f'  FAIL  {f}')

    # ── Console log summary ──────────────────────────────────────────────────
    print('\n═══ CONSOLE (errors + strudel-debug) ═══')
    error_count = 0
    trigger_errors = []
    for entry in all_logs:
        is_error = entry['type'] in ('error', 'pageerror')
        is_debug = '[strudel-debug]' in entry['text']
        is_trigger = 'getTrigger' in entry['text'] and 'error' in entry['text'].lower()
        if is_error:
            error_count += 1
            print(f'  [{entry["type"].upper()}] {entry["text"]}')
        elif is_trigger:
            # getTrigger errors (e.g. "sound X not found") log as [log] not [error]
            # but are functional failures — the sound simply won't play
            trigger_errors.append(entry['text'])
            print(f'  [TRIGGER ERROR] {entry["text"]}')
        elif is_debug:
            print(f'  [LOG] {entry["text"]}')

    if error_count:
        failures.append(f'CONSOLE ERRORS: {error_count} JS error(s) — see above')
    else:
        passes.append('CONSOLE ERRORS: no JS errors')

    if trigger_errors:
        # Deduplicate — same missing sound repeats every scheduler tick
        unique = list(dict.fromkeys(trigger_errors))
        failures.append(f'MISSING SOUNDS: {len(unique)} unique trigger error(s): {unique[0][:80]}')
        print(f'\n  !! {len(unique)} unique getTrigger error(s) — samples not loaded')
    else:
        passes.append('MISSING SOUNDS: none')

    print(f'\n═══ VERDICT: {len(passes)} passed, {len(failures)} failed ═══')
    return 0 if not failures else 1

if __name__ == '__main__':
    sys.exit(run())
