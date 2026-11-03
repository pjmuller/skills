// capture_js (bw_once.capture_js fills in the config): runs in the agent's tab via preview_evaluate, finds the new key or
// password, POSTs it to the broker's one-time loopback URL and returns only {ok, kind, length, source} or a named
// error with the next step. It never returns, logs or throws the value (exception text could carry it).
(async () => {
  const config = __CONFIG__;
  const fail = (error, next) => ({ ok: false, error, next });
  const again = 'run the same bw-once create/update again for a new capture_js';
  try {
    if (location.origin !== config.origin) {
      return fail('wrong_origin', `tab is on ${location.origin}, the capture is pinned to ${config.origin}`);
    }
    if (Date.now() > config.deadline) return fail('expired', again);
    const otpauth = (text) => (/^otpauth:\/\/totp\//i.test((text || '').trim()) ? text.trim() : null);
    const qr = async (element) => {
      if (typeof BarcodeDetector !== 'function') return [];
      let source = element;
      if (element instanceof SVGElement) {  // Inline SVG QR codes (common in React apps): rasterize via an <img>.
        source = new Image();
        source.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(new XMLSerializer().serializeToString(element));
        await source.decode();
      }
      try {
        const codes = await new BarcodeDetector({ formats: ['qr_code'] }).detect(source);
        return codes.map((code) => otpauth(code.rawValue)).filter(Boolean);
      } catch { return []; }  // Cross-origin image, undecodable: not this one.
    };
    const visual = (element) => element.matches('img, canvas, svg');
    let found = [];
    let source = 'selector';
    if (config.selector) {
      const elements = document.querySelectorAll(config.selector);
      if (elements.length !== 1) {
        return fail('no_field', `${elements.length} elements match --capture-selector; it must name exactly one`);
      }
      const element = elements[0];
      if (config.kind === 'totp' && visual(element)) found = await qr(element);
      // An input's value is exact; text shown on the page carries layout whitespace around it.
      else if ('value' in element && element.value) found = [element.value];
      else found = [(element.getAttribute('href') || element.textContent || '').trim()];
      found = found.filter(Boolean);
    } else if (config.kind === 'totp') {
      source = 'otpauth';
      for (const element of document.querySelectorAll('[href], [value], [data-uri], [data-value]')) {
        for (const name of ['href', 'value', 'data-uri', 'data-value']) {
          const value = otpauth(element.getAttribute(name));
          if (value) found.push(value);
        }
      }
      if (!found.length) {
        source = 'qr';
        for (const element of document.querySelectorAll('img, canvas, svg')) {
          const box = element.getBoundingClientRect();
          if (box.width >= 64 && box.height >= 64) found.push(...await qr(element));
        }
      }
    } else {
      return fail('no_selector', 'a password capture needs --capture-selector (the element showing it)');
    }
    found = [...new Set(found)];
    if (found.length !== 1) {
      return fail(found.length ? 'ambiguous' : 'not_found', found.length
        ? 'several different keys on the page: pass --capture-selector'
        : 'no key found: show the QR code (or pass --capture-selector for the element holding the key); never read the key yourself');
    }
    let csp = false;
    const seen = (event) => { if (event.disposition === 'enforce' && event.blockedURI.startsWith(new URL(config.url).origin)) csp = true; };
    window.addEventListener('securitypolicyviolation', seen);
    const answer = await fetch(config.url, {
      method: 'POST', body: JSON.stringify({ value: found[0] }), headers: { 'Content-Type': 'text/plain' },
      cache: 'no-store', credentials: 'omit',
    }).catch(() => null);
    if (!answer) await new Promise((done) => setTimeout(done, 200));
    window.removeEventListener('securitypolicyviolation', seen);
    if (csp) return fail('csp', 'this site blocks loopback requests: rerun with --totp ask / --password ask (the human pastes it in the window)');
    if (!answer) return fail('blocked', 'the browser refused loopback, or the capture expired: ' + again + ', or use ask');
    const result = await answer.json().catch(() => ({}));
    if (!result.ok) return fail(result.error || 'refused', 'the broker refused this value (not a valid key?): try --capture-selector, or ask');
    return { ok: true, kind: result.kind, length: result.length, source };
  } catch {
    return fail('error', 'capture failed on this page: use ask');
  }
})()
