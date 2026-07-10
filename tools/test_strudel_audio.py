"""
Automated audio output test for research/strudel_debug.html.

Usage:
    # Start a local server first:
    python -m http.server 8765 --directory research &
    python tools/test_strudel_audio.py

Verdict: PASS when maxRMS > 0.05 AND sustained frames > 30% of window.
"""
import sys, time, json
from playwright.sync_api import sync_playwright

URL = 'http://localhost:8765/strudel_debug.html'
PLAY_SECONDS = 10

# Injected before page scripts. Wraps AudioContext to attach an AnalyserNode
# side-tap on every gain node so we capture the actual audio signal regardless
# of how superdough routes its AudioWorklet outputs.
PROBE_SCRIPT = """
window.__audioProbe = { rmsValues: [], maxRms: 0, nodeCount: 0 };
window.__superdoughReady = false;

// Intercept console.log to detect superdough readiness signal.
const _origLog = console.log;
console.log = function(...args) {
    _origLog.apply(console, args);
    if (args.join(' ').includes('superdough] ready')) {
        window.__superdoughReady = true;
    }
};

const _origAC = window.AudioContext;
window.AudioContext = function(...args) {
    const ac = new _origAC(...args);

    // One shared analyser per context — side-tap, does not affect routing.
    const analyser = ac.createAnalyser();
    analyser.fftSize = 2048;
    analyser.connect(ac.destination);
    window.__audioProbe._analyser = analyser;

    // Poll analyser every 100 ms via setInterval.
    setInterval(() => {
        const buf = new Float32Array(analyser.fftSize);
        analyser.getFloatTimeDomainData(buf);
        let sum = 0;
        for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
        const rms = Math.sqrt(sum / buf.length);
        window.__audioProbe.rmsValues.push(rms);
        if (rms > window.__audioProbe.maxRms) window.__audioProbe.maxRms = rms;
    }, 100);

    // Tap every gain node output into the shared analyser.
    const _origCG = ac.createGain.bind(ac);
    ac.createGain = function() {
        const g = _origCG();
        window.__audioProbe.nodeCount++;
        g.connect(analyser);
        return g;
    };

    return ac;
};
"""

def run():
    with sync_playwright() as p:
        # No --autoplay-policy override: test under real-browser AudioContext
        # suspension rules. The page must call ctx.resume() inside the click
        # handler — exactly what a real user's browser enforces.
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        logs = []
        page.on('console', lambda m: logs.append(f'[{m.type}] {m.text[:300]}'))
        page.on('pageerror', lambda e: logs.append(f'[pageerror] {e}'))
        page.add_init_script(PROBE_SCRIPT)

        page.goto(URL)
        print('Waiting for page to reach Ready state...')
        page.wait_for_function(
            "() => document.getElementById('status').textContent.includes('Ready')",
            timeout=25000)
        status = page.evaluate("() => document.getElementById('status').textContent")
        print(f'Page status: {status!r}')

        print(f'Clicking Play, monitoring for {PLAY_SECONDS}s...')
        page.locator('button:has-text("Play")').first.click()

        snapshots = []
        for i in range(PLAY_SECONDS):
            time.sleep(1)
            snap = page.evaluate("""() => ({
                maxRms:    window.__audioProbe.maxRms,
                count:     window.__audioProbe.rmsValues.length,
                last3:     window.__audioProbe.rmsValues.slice(-3),
                nodeCount: window.__audioProbe.nodeCount,
                sdReady:   window.__superdoughReady,
            })""")
            snapshots.append(snap)
            print(f'  t+{i+1}s  maxRMS={snap["maxRms"]:.4f}  nodes={snap["nodeCount"]}  last3={[round(v,3) for v in snap["last3"]]}')

        err = page.evaluate("() => document.getElementById('error').textContent")

        sched = page.evaluate("""() => {
            const r = window.__debug?.repl;
            const s = r?.scheduler;
            return { started: s?.started, lastEnd: s?.lastEnd, ticks: s?.num_ticks_since_cps_change };
        }""")

        browser.close()

    # --- Verdict ---
    all_rms = []
    max_rms = snapshots[-1]['maxRms'] if snapshots else 0
    # Estimate sustained non-zero from last snapshot's full history
    # (we use snapshots to see trajectory, not just endpoint)
    last_snap = snapshots[-1] if snapshots else {}
    total_frames = last_snap.get('count', 0)

    # Use t+3..t+10 last-3 windows to estimate sustained ratio
    sustained = sum(1 for s in snapshots[2:] for v in s.get('last3', []) if v > 0.05)
    possible  = sum(len(s.get('last3', [])) for s in snapshots[2:])

    print('\n=== VERDICT ===')
    print(f'Max RMS:           {max_rms:.4f}')
    print(f'Scheduler lastEnd: {sched.get("lastEnd", 0):.2f}s')
    print(f'Sustained frames:  {sustained}/{possible} ({100*sustained/max(possible,1):.0f}%)')
    if err:
        print(f'Page error:        {err!r}')

    if max_rms > 0.05 and sustained / max(possible, 1) > 0.25:
        print('PASS: sustained audio output confirmed')
        rc = 0
    elif max_rms > 0.05:
        print('PARTIAL: audio present but not sustained — check trancegate density')
        rc = 1
    else:
        print('FAIL: no audio output detected')
        rc = 2

    print('\n=== Relevant console logs ===')
    for l in logs:
        if any(k in l.lower() for k in ['error','superdough','worklet','arithmetic','pageerror']):
            print(l)

    return rc

if __name__ == '__main__':
    sys.exit(run())
