/* Samjhao frontend. Plain JS, no build step. */
(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const audio = $('audio');
  const POLL_MS = 700;
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const ICON_X = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6.7 5.3a1 1 0 0 0-1.4 1.4l5.3 5.3-5.3 5.3a1 1 0 1 0 1.4 1.4l5.3-5.3 5.3 5.3a1 1 0 0 0 1.4-1.4L13.4 12l5.3-5.3a1 1 0 0 0-1.4-1.4L12 10.6z" fill="currentColor"/></svg>';
  const ICON_PAUSE = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="6" y="5" width="4" height="14" rx="1.2" fill="currentColor"/><rect x="14" y="5" width="4" height="14" rx="1.2" fill="currentColor"/></svg>';

  const state = {
    config: null,
    langs: {},
    lang: 'hi-IN',
    relation: 'maa',
    customName: '',
    phone: 'android',
    voice: 'female',
    script: null, // {title, intro, steps[], recap, safety, note}
    scriptLang: null, // language the editor text is written in
    scriptFor: null, // {relation, customName, phone} at writing time
    safetyOn: true,
    dirty: false,
    job: null,
    busy: false,
  };

  // ---------- helpers ----------

  function h(tag, props = {}, children = []) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
      if (v == null || v === false) continue;
      if (k === 'class') n.className = v;
      else if (k === 'text') n.textContent = v;
      else if (k === 'html') n.innerHTML = v; // static SVG only
      else n.setAttribute(k, v === true ? '' : v);
    }
    for (const c of [].concat(children)) if (c != null) n.append(c);
    return n;
  }

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const isNarrow = () => window.matchMedia('(max-width: 979px)').matches;
  const scrollBehavior = () => (reduceMotion ? 'auto' : 'smooth');
  const shortLang = (code) => (state.langs[code] && state.langs[code].lang) || (code || 'en').slice(0, 2);
  const langName = (code) => (state.langs[code] ? state.langs[code].name : code);
  const maxSteps = () => (state.config && state.config.max_steps) || 6;
  const pauseSeconds = () => (state.config && state.config.pause_after_step) || 4;

  function fmt(t) {
    if (!isFinite(t) || t < 0) t = 0;
    const m = Math.floor(t / 60);
    const s = Math.floor(t % 60);
    return `${m}:${String(s).padStart(2, '0')}`;
  }

  function uuid() {
    if (window.crypto && typeof crypto.randomUUID === 'function') {
      try { return crypto.randomUUID(); } catch (_) { /* insecure origin */ }
    }
    const b = new Uint8Array(16);
    if (window.crypto && crypto.getRandomValues) crypto.getRandomValues(b);
    else for (let i = 0; i < 16; i++) b[i] = (Math.random() * 256) | 0;
    b[6] = (b[6] & 0x0f) | 0x40;
    b[8] = (b[8] & 0x3f) | 0x80;
    const x = Array.from(b, (v) => v.toString(16).padStart(2, '0')).join('');
    return `${x.slice(0, 8)}-${x.slice(8, 12)}-${x.slice(12, 16)}-${x.slice(16, 20)}-${x.slice(20)}`;
  }

  function errorText(data, status) {
    if (data && typeof data.detail === 'string') return data.detail;
    if (status >= 500) return 'Samjhao hit a problem on its side. Try again in a moment.';
    return `Something went wrong (error ${status}). Try again.`;
  }

  async function api(path, body) {
    const opts = body === undefined
      ? {}
      : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
    let res;
    try {
      res = await fetch(path, opts);
    } catch (_) {
      throw new Error("Couldn't reach Samjhao. Check your connection and try again.");
    }
    let data = null;
    try { data = await res.json(); } catch (_) { /* not JSON */ }
    if (!res.ok) {
      const err = new Error(errorText(data, res.status));
      err.status = res.status;
      throw err;
    }
    return data;
  }

  // ---------- form ----------

  function radio(name, value, checked, labelClass, content, disabled) {
    const input = h('input', { type: 'radio', name, value });
    input.checked = !!checked;
    input.disabled = !!disabled;
    return h('label', { class: labelClass }, [input, content]);
  }

  function renderForm() {
    const cfg = state.config;
    state.langs = {};
    cfg.languages.forEach((l) => { state.langs[l.code] = l; });
    if (!state.langs[state.lang]) state.lang = cfg.languages[0].code;

    const rel = $('relations');
    rel.textContent = '';
    cfg.relations.forEach((r) => rel.append(radio('relation', r.id, r.id === state.relation, 'pill', h('span', { text: r.label }))));

    const grid = $('languages');
    grid.textContent = '';
    cfg.languages.forEach((l) => {
      const body = h('span', { class: 'lang-body' }, [
        h('span', { class: 'lang-native', lang: l.lang, text: l.native }),
        h('span', { class: 'lang-en', text: l.native === l.name ? 'Indian English' : l.name }),
      ]);
      grid.append(radio('language', l.code, l.code === state.lang, 'lang', body));
    });

    const phones = $('phones');
    phones.textContent = '';
    (cfg.phones || [{ id: 'android', label: 'Android' }, { id: 'iphone', label: 'iPhone' }])
      .forEach((p) => phones.append(radio('phone', p.id, p.id === state.phone, 'seg', h('span', { text: p.label }))));

    const voices = $('voices');
    voices.textContent = '';
    [['female', 'Female'], ['male', 'Male']]
      .forEach(([id, label]) => voices.append(radio('voice', id, id === state.voice, 'seg', h('span', { text: label }))));

    updateVoices();
  }

  function availableVoices(code) {
    const l = state.langs[code];
    return l && Array.isArray(l.voices) && l.voices.length ? l.voices : ['female', 'male'];
  }

  function voiceFor(code) {
    const v = availableVoices(code);
    return v.includes(state.voice) ? state.voice : v[0];
  }

  function updateVoices() {
    const avail = availableVoices(state.lang);
    if (!avail.includes(state.voice)) state.voice = avail[0];
    document.querySelectorAll('input[name="voice"]').forEach((i) => {
      i.disabled = !avail.includes(i.value);
      i.checked = i.value === state.voice;
    });
  }

  function setLanguage(code) {
    state.lang = code;
    document.querySelectorAll('input[name="language"]').forEach((i) => { i.checked = i.value === code; });
    updateVoices();
    updateLangBanner();
  }

  function showFormError(msg, focusEl) {
    const e = $('form-error');
    e.textContent = msg;
    e.hidden = false;
    if (focusEl) focusEl.focus();
    else if (isNarrow()) e.scrollIntoView({ behavior: scrollBehavior(), block: 'center' });
  }

  function hideFormError() { $('form-error').hidden = true; }

  // ---------- writing the steps ----------

  async function writeSteps(ev) {
    if (ev) ev.preventDefault();
    if (state.busy) return;
    const task = $('task').value.trim();
    if (task.length < 3) return showFormError('Type what you want to explain, or pick an example.', $('task'));
    hideFormError();

    state.busy = true;
    const btn = $('write-btn');
    btn.disabled = true;
    btn.classList.add('is-busy');
    const code = state.lang;
    const msgs = [
      `Writing the steps in ${langName(code)}…`,
      'Keeping the app’s button names exactly as they appear…',
      'Adding a pause after each step…',
      'Almost there…',
    ];
    let k = 0;
    $('writing-status').textContent = msgs[0];
    const timer = setInterval(() => {
      k = Math.min(k + 1, msgs.length - 1);
      $('writing-status').textContent = msgs[k];
    }, 2400);
    $('empty').hidden = true;
    $('editor').hidden = true;
    $('writing').hidden = false;
    if (!audio.paused) audio.pause();
    if (isNarrow()) $('lesson').scrollIntoView({ behavior: scrollBehavior(), block: 'start' });

    try {
      const data = await api('api/script', {
        task,
        language: code,
        relation: state.relation,
        custom_name: state.relation === 'custom' ? state.customName.trim() : null,
        phone: state.phone,
        voice: voiceFor(code),
      });
      state.scriptFor = { relation: state.relation, customName: state.customName.trim(), phone: state.phone };
      state.job = null;
      resetDock();
      renderScript(data, code);
    } catch (err) {
      $('writing').hidden = true;
      if (state.script) $('editor').hidden = false;
      else $('empty').hidden = false;
      showFormError(err.message);
    } finally {
      clearInterval(timer);
      state.busy = false;
      btn.disabled = false;
      btn.classList.remove('is-busy');
      btn.textContent = state.script ? 'Write new steps' : 'Write the steps';
    }
  }

  // ---------- editor ----------

  function normalizeScript(s) {
    const str = (v) => (typeof v === 'string' ? v : '');
    const steps = Array.isArray(s && s.steps) ? s.steps.map(str).filter((t) => t.trim()) : [];
    return {
      title: str(s && s.title),
      intro: str(s && s.intro),
      steps: steps.slice(0, maxSteps()),
      recap: str(s && s.recap),
      safety: s && typeof s.safety === 'string' && s.safety.trim() ? s.safety : null,
      note: s && typeof s.note === 'string' && s.note.trim() ? s.note : null,
    };
  }

  function grow(ta) {
    ta.style.height = 'auto';
    ta.style.height = `${ta.scrollHeight + 3}px`;
  }

  function autoGrowAll() { document.querySelectorAll('.part-text, .task-input').forEach(grow); }

  function renderScript(raw, code) {
    state.script = normalizeScript(raw);
    state.scriptLang = code;
    state.safetyOn = !!state.script.safety;
    state.dirty = false;
    const lang = shortLang(code);

    $('lesson-title').textContent = state.script.title || $('task').value.trim() || 'Your voice note';
    updateMeta();
    const note = $('lesson-note');
    note.hidden = !state.script.note;
    note.textContent = state.script.note || '';

    const fields = { 'f-intro': 'intro', 'f-recap': 'recap', 'f-safety': 'safety' };
    for (const [id, key] of Object.entries(fields)) {
      const ta = $(id);
      ta.lang = lang;
      ta.value = state.script[key] || '';
    }
    $('safety-part').hidden = !state.script.safety;
    $('safety-on').checked = state.safetyOn;
    updateSafety();

    renderSteps();
    $('empty').hidden = true;
    $('writing').hidden = true;
    $('editor').hidden = false;
    $('editor').classList.remove('is-updating');
    autoGrowAll();
    updateLangBanner();
    updateMakeSub();
    renderOthers();
  }

  function updateMeta() {
    const f = state.scriptFor || { relation: state.relation, customName: state.customName, phone: state.phone };
    const phone = ((state.config.phones || []).find((p) => p.id === f.phone) || { label: f.phone }).label;
    $('lesson-meta').textContent = `In ${langName(state.scriptLang)}, on ${phone}.`;
  }

  function renderSteps() {
    const list = $('steps');
    list.textContent = '';
    const steps = state.script.steps;
    const lang = shortLang(state.scriptLang);
    steps.forEach((text, i) => {
      const id = `f-step-${i}`;
      const ta = h('textarea', { id, class: 'part-text', rows: '1', lang });
      ta.value = text;
      ta.addEventListener('input', () => {
        state.script.steps[i] = ta.value;
        grow(ta);
        markDirty();
      });
      const remove = h('button', { type: 'button', class: 'step-remove', 'aria-label': `Remove step ${i + 1}`, html: ICON_X });
      remove.disabled = steps.length <= 1;
      remove.addEventListener('click', () => removeStep(i));
      list.append(h('li', { class: 'part step' }, [
        h('span', { class: 'node node-step', 'aria-hidden': 'true', text: String(i + 1) }),
        h('div', { class: 'step-head' }, [h('label', { class: 'step-label', for: id, text: `Step ${i + 1}` }), remove]),
        ta,
        h('p', { class: 'pause-row', html: `${ICON_PAUSE}<span>${pauseSeconds()} second pause to do it</span>` }),
      ]));
    });
    $('add-step').disabled = steps.length >= maxSteps();
    list.querySelectorAll('.part-text').forEach(grow);
  }

  function removeStep(i) {
    const n = state.script.steps.length;
    if (n <= 1) return;
    state.script.steps.splice(i, 1);
    renderSteps();
    markDirty();
    updateMakeSub();
    const next = $(`f-step-${Math.min(i, n - 2)}`);
    if (next) next.focus();
  }

  function addStep() {
    const n = state.script.steps.length;
    if (n >= maxSteps()) return;
    state.script.steps.push('');
    renderSteps();
    markDirty();
    updateMakeSub();
    $(`f-step-${n}`).focus();
  }

  function updateSafety() {
    $('safety-part').classList.toggle('is-off', !state.safetyOn);
    $('f-safety').disabled = !state.safetyOn;
  }

  function updateMakeSub() {
    if (!state.script) return;
    const n = state.script.steps.filter((t) => t.trim()).length;
    $('make-sub').textContent = `${n} step${n === 1 ? '' : 's'}, with a ${pauseSeconds()}-second pause after each`;
  }

  function updateLangBanner() {
    const banner = $('lang-banner');
    if (!state.script || !state.scriptLang || state.lang === state.scriptLang) {
      banner.hidden = true;
      return;
    }
    $('lang-banner-text').textContent = `These steps are in ${langName(state.scriptLang)}.`;
    const btn = $('lang-banner-btn');
    btn.textContent = `Translate to ${langName(state.lang)}`;
    btn.disabled = false;
    banner.hidden = false;
  }

  function markDirty() {
    if (!state.job) return;
    state.dirty = true;
    $('make-label').textContent = 'Make it again with your changes';
    $('dock-make').hidden = false;
  }

  function collectScript() {
    const s = state.script;
    const steps = s.steps.map((t) => t.trim()).filter(Boolean);
    return {
      title: s.title || '',
      intro: s.intro.trim(),
      steps,
      recap: s.recap.trim(),
      safety: state.safetyOn && s.safety && s.safety.trim() ? s.safety.trim() : null,
      note: s.note || null,
    };
  }

  // ---------- voice note ----------

  const dockError = h('p', { class: 'inline-error', role: 'alert' });
  dockError.hidden = true;

  function showDockError(msg) {
    dockError.textContent = msg;
    dockError.hidden = false;
  }

  function resetDock() {
    if (!audio.paused) audio.pause();
    $('dock-make').hidden = false;
    $('make-label').textContent = 'Make voice note';
    $('player').hidden = true;
    dockError.hidden = true;
  }

  function setStatus(msg) { $('player-status').textContent = msg; }

  function setPlaying(on) {
    const b = $('play-btn');
    b.classList.toggle('is-playing', on);
    b.setAttribute('aria-label', on ? 'Pause' : 'Play');
    paintWave();
  }

  // Bars follow the note's rhythm: speech for each part, near-silence for the pauses.
  function renderWave(job, script) {
    const wave = $('wave');
    wave.textContent = '';
    let seed = 0;
    for (const ch of job.id) seed = (seed * 31 + ch.charCodeAt(0)) >>> 0;
    const rand = () => {
      seed = (seed + 0x6d2b79f5) >>> 0;
      let t = seed;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
    const cps = 13;
    const segs = [];
    const speak = (text) => { if (text) segs.push({ talk: true, len: Math.max(1.5, text.length / cps) }); };
    speak(script.intro);
    segs.push({ talk: false, len: 1 });
    script.steps.forEach((s) => { speak(s); segs.push({ talk: false, len: pauseSeconds() }); });
    speak(script.recap);
    if (script.safety) { segs.push({ talk: false, len: 1 }); speak(script.safety); }
    const total = segs.reduce((a, s) => a + s.len, 0);
    const n = Math.max(24, Math.min(64, Math.floor((wave.clientWidth || 260) / 6)));
    job.bars = [];
    for (let i = 0; i < n; i++) {
      const at = ((i + 0.5) / n) * total;
      let acc = 0;
      let seg = segs[segs.length - 1];
      for (const s of segs) { acc += s.len; if (at <= acc) { seg = s; break; } }
      const v = seg.talk ? 0.3 + 0.7 * (0.55 * rand() + 0.45 * Math.abs(Math.sin(i * 0.9 + rand()))) : 0.1;
      const bar = h('span');
      bar.style.setProperty('--h', v.toFixed(3));
      bar.style.setProperty('--i', String(i));
      wave.append(bar);
      job.bars.push(bar);
    }
  }

  function knownDuration() {
    const job = state.job;
    if (!job) return null;
    if (job.fileMode && isFinite(audio.duration) && audio.duration > 0) return audio.duration;
    return job.duration || null;
  }

  function paintWave() {
    const job = state.job;
    const wave = $('wave');
    if (!job || !job.bars) return;
    const dur = knownDuration();
    const playing = !audio.paused && !audio.ended;
    if (!dur) {
      wave.classList.toggle('live', playing && !reduceMotion);
      job.bars.forEach((b) => b.classList.remove('on'));
      return;
    }
    wave.classList.remove('live');
    const ratio = audio.ended ? 1 : Math.min(1, (audio.currentTime || 0) / dur);
    const lit = Math.round(ratio * job.bars.length);
    job.bars.forEach((b, i) => b.classList.toggle('on', i < lit));
  }

  function updateProgress() {
    const dur = knownDuration();
    const t = audio.ended && dur ? dur : audio.currentTime || 0;
    $('time').textContent = dur ? `${fmt(t)} / ${fmt(dur)}` : fmt(t);
    paintWave();
  }

  function showTtfb(ms) {
    const wrap = $('ttfb');
    const num = $('ttfb-num');
    const target = Math.round(ms);
    wrap.hidden = false;
    wrap.classList.remove('is-pending');
    if (reduceMotion) { num.textContent = String(target); return; }
    const start = performance.now();
    const tick = (now) => {
      const p = Math.min(1, (now - start) / 700);
      num.textContent = String(Math.round(target * (1 - Math.pow(1 - p, 3))));
      if (p < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }

  function resetPlayerUI(job, script) {
    $('player').hidden = false;
    dockError.hidden = true;
    // Keep the badge's space from the start so the dock doesn't jump when the number arrives.
    $('ttfb').hidden = false;
    $('ttfb').classList.add('is-pending');
    $('ttfb-num').textContent = '···';
    $('time').textContent = '0:00';
    setStatus('Starting…');
    const share = $('share-btn');
    share.disabled = true;
    $('share-label').textContent = 'Preparing…';
    const dl = $('download-btn');
    dl.removeAttribute('href');
    dl.classList.add('is-disabled');
    dl.setAttribute('aria-disabled', 'true');
    $('share-hint').hidden = true;
    $('wave').classList.remove('seekable');
    renderWave(job, script);
    setPlaying(true);
  }

  function startVoiceNote() {
    if (!state.script) return;
    const script = collectScript();
    dockError.hidden = true;
    if (!script.steps.length) {
      showDockError('Add at least one step first.');
      return;
    }
    const id = uuid();
    const language = state.scriptLang;
    const voice = voiceFor(language);
    const job = {
      id, language, voice,
      title: script.title || $('lesson-title').textContent,
      state: 'generating', ttfb: null, duration: null,
      fileUrl: null, filename: null, file: null, fileMode: false, bars: null,
    };
    state.job = job;

    // Fire the request but do not await it, so play() still runs inside the tap (iOS autoplay rules).
    fetch('api/audio', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id, language, voice, script }),
    }).then(async (res) => {
      if (res.ok) return;
      let data = null;
      try { data = await res.json(); } catch (_) { /* not JSON */ }
      throw new Error(errorText(data, res.status));
    }).catch((err) => {
      if (state.job === job) failJob(err.message || "Couldn't make the voice note. Try again.");
    });

    resetPlayerUI(job, script);
    audio.dataset.job = id;
    audio.src = `api/audio/${encodeURIComponent(id)}/stream`;
    const p = audio.play();
    if (p && p.catch) {
      p.catch((err) => {
        if (state.job !== job || !err) return;
        if (err.name === 'NotAllowedError') {
          setPlaying(false);
          setStatus('Tap play to listen');
        }
      });
    }

    state.dirty = false;
    $('dock-make').hidden = true;
    $('make-label').textContent = 'Make voice note';
    pollStatus(job);
  }

  function failJob(msg) {
    const job = state.job;
    if (job) job.state = 'error';
    if (!audio.paused) audio.pause();
    setPlaying(false);
    setStatus('');
    showDockError(msg);
    $('make-label').textContent = 'Try again';
    $('dock-make').hidden = false;
  }

  async function pollStatus(job) {
    const deadline = Date.now() + 3 * 60 * 1000;
    while (state.job === job && Date.now() < deadline) {
      await sleep(POLL_MS);
      if (state.job !== job || job.state === 'error') return;
      let s;
      try {
        s = await api(`api/audio/${encodeURIComponent(job.id)}`);
      } catch (_) {
        continue; // not registered yet, or a network blip
      }
      if (state.job !== job) return;
      if (s.ttfb_ms != null && job.ttfb == null) {
        job.ttfb = s.ttfb_ms;
        showTtfb(s.ttfb_ms);
      }
      if (s.duration_s) job.duration = s.duration_s;
      if (s.state === 'error') {
        failJob(s.error || "Couldn't make the voice note. Try again.");
        return;
      }
      if (s.state === 'ready') {
        onReady(job, s);
        return;
      }
      updateProgress();
    }
    if (state.job === job && job.state === 'generating') failJob('This is taking too long. Try making the voice note again.');
  }

  function onReady(job, s) {
    job.state = 'ready';
    if (job.ttfb == null) $('ttfb').hidden = true;
    job.fileUrl = s.file_url || `api/audio/${encodeURIComponent(job.id)}/file`;
    job.filename = s.filename || 'samjhao-voice-note.mp3';
    const dl = $('download-btn');
    dl.href = job.fileUrl;
    dl.setAttribute('download', job.filename);
    dl.classList.remove('is-disabled');
    dl.removeAttribute('aria-disabled');
    if (audio.ended) {
      switchToFile();
      setStatus('Finished. Play it again or share it.');
    } else if (audio.paused) {
      setStatus('Ready to share');
    } else {
      setStatus('Playing');
    }
    updateProgress();
    // Fetch the file now so Share can open the share sheet straight from the tap.
    fetch(job.fileUrl)
      .then((r) => { if (!r.ok) throw new Error(String(r.status)); return r.blob(); })
      .then((blob) => {
        if (state.job !== job) return;
        job.file = new File([blob], job.filename, { type: 'audio/mpeg' });
        enableShare(job);
      })
      .catch(() => { if (state.job === job) enableShare(job); });
  }

  function enableShare(job) {
    const share = $('share-btn');
    share.disabled = false;
    $('share-label').textContent = 'Share';
    share.title = canShareFile(job.file) ? 'Send it on WhatsApp or anywhere else' : 'Download it, then attach it in WhatsApp';
  }

  function canShareFile(file) {
    try {
      return !!(file && navigator.canShare && navigator.share && navigator.canShare({ files: [file] }));
    } catch (_) {
      return false;
    }
  }

  function switchToFile() {
    const job = state.job;
    if (!job || !job.fileUrl || job.fileMode) return;
    job.fileMode = true;
    audio.dataset.job = job.id;
    audio.src = job.fileUrl;
    audio.preload = 'auto';
    $('wave').classList.add('seekable');
  }

  function showShareHint(msg) {
    const e = $('share-hint');
    e.textContent = msg;
    e.hidden = false;
  }

  function shareNote() {
    const job = state.job;
    if (!job || !job.fileUrl) return;
    if (canShareFile(job.file)) {
      navigator.share({ files: [job.file], title: job.title || 'Samjhao voice note' })
        .then(() => showShareHint('Shared.'))
        .catch((err) => {
          if (err && err.name === 'AbortError') return;
          downloadFallback();
        });
      return;
    }
    downloadFallback();
  }

  function downloadFallback() {
    $('download-btn').click();
    showShareHint('Saved to your downloads. In WhatsApp, attach it from the paperclip menu.');
  }

  function onPlayClick() {
    const job = state.job;
    if (!job) return;
    if (!audio.paused && !audio.ended) {
      audio.pause();
      return;
    }
    if (audio.ended) {
      if (job.fileUrl) {
        switchToFile();
        audio.currentTime = 0;
      } else {
        audio.src = `api/audio/${encodeURIComponent(job.id)}/stream`;
      }
    }
    const p = audio.play();
    if (p && p.catch) p.catch(() => {});
  }

  function onWaveClick(ev) {
    const job = state.job;
    if (!job || !job.fileMode) return;
    const dur = knownDuration();
    if (!dur) return;
    const rect = $('wave').getBoundingClientRect();
    const ratio = Math.min(1, Math.max(0, (ev.clientX - rect.left) / rect.width));
    audio.currentTime = ratio * dur;
    updateProgress();
  }

  // ---------- other languages ----------

  function renderOthers() {
    const row = $('other-langs');
    row.textContent = '';
    state.config.languages.forEach((l) => {
      if (l.code === state.scriptLang) return;
      const b = h('button', { type: 'button', class: 'other', 'aria-label': `Hear it in ${l.name}` }, [
        h('span', { lang: l.lang, text: l.native }),
        l.native !== l.name ? h('small', { text: l.name }) : null,
      ]);
      b.addEventListener('click', () => translateTo(l.code, { autoplay: true, button: b }));
      row.append(b);
    });
  }

  async function translateTo(code, { autoplay = false, button = null } = {}) {
    if (state.busy || !state.script) return;
    state.busy = true;
    const name = langName(code);
    document.querySelectorAll('.other').forEach((b) => { b.disabled = true; });
    if (button) {
      button.classList.add('is-loading');
      button.prepend(h('span', { class: 'spinner', 'aria-hidden': 'true' }));
    }
    const bannerBtn = $('lang-banner-btn');
    if (!autoplay) {
      bannerBtn.disabled = true;
      bannerBtn.textContent = `Translating to ${name}…`;
    }
    if (!audio.paused) audio.pause();
    dockError.hidden = true;
    setStatus(`Translating to ${name}…`);
    $('editor').classList.add('is-updating');

    try {
      const data = await api('api/translate', {
        script: collectScript(),
        language: code,
        relation: state.relation,
        custom_name: state.relation === 'custom' ? state.customName.trim() : null,
        phone: state.phone,
        voice: voiceFor(code),
      });
      setLanguage(code);
      state.scriptFor = { relation: state.relation, customName: state.customName.trim(), phone: state.phone };
      renderScript(data, code);
      if (autoplay) {
        startVoiceNote();
      } else {
        state.job = null;
        resetDock();
      }
    } catch (err) {
      $('editor').classList.remove('is-updating');
      setStatus('');
      if (autoplay) showDockError(`${err.message}`);
      else showFormError(err.message);
      updateLangBanner();
    } finally {
      state.busy = false;
      document.querySelectorAll('.other').forEach((b) => {
        b.disabled = false;
        b.classList.remove('is-loading');
        const sp = b.querySelector('.spinner');
        if (sp) sp.remove();
      });
    }
  }

  // ---------- wiring ----------

  function wire() {
    const task = $('task');
    task.addEventListener('input', () => { grow(task); hideFormError(); });
    task.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
        e.preventDefault();
        $('form').requestSubmit ? $('form').requestSubmit() : writeSteps();
      }
    });
    $('examples').addEventListener('click', (e) => {
      const b = e.target.closest('.example');
      if (!b) return;
      task.value = b.dataset.task;
      grow(task);
      hideFormError();
      task.focus();
    });

    $('form').addEventListener('submit', writeSteps);
    $('form').addEventListener('change', (e) => {
      const t = e.target;
      if (t.name === 'relation') {
        state.relation = t.value;
        $('custom-name-wrap').hidden = t.value !== 'custom';
        if (t.value === 'custom') $('custom-name').focus();
      } else if (t.name === 'language') {
        state.lang = t.value;
        updateVoices();
        updateLangBanner();
      } else if (t.name === 'phone') {
        state.phone = t.value;
      } else if (t.name === 'voice') {
        state.voice = t.value;
      }
    });
    $('custom-name').addEventListener('input', (e) => {
      state.customName = e.target.value;
    });

    const fields = { 'f-intro': 'intro', 'f-recap': 'recap', 'f-safety': 'safety' };
    for (const [id, key] of Object.entries(fields)) {
      $(id).addEventListener('input', (e) => {
        state.script[key] = e.target.value;
        grow(e.target);
        markDirty();
      });
    }
    $('safety-on').addEventListener('change', (e) => {
      state.safetyOn = e.target.checked;
      updateSafety();
      markDirty();
    });
    $('add-step').addEventListener('click', addStep);
    $('lang-banner-btn').addEventListener('click', () => translateTo(state.lang));

    $('make-btn').addEventListener('click', () => {
      startVoiceNote();
      // On phones, bring the whole player into view below the steps.
      if (isNarrow() && state.job) requestAnimationFrame(() => $('lesson').scrollIntoView({ behavior: scrollBehavior(), block: 'end' }));
    });
    $('play-btn').addEventListener('click', onPlayClick);
    $('wave').addEventListener('click', onWaveClick);
    $('share-btn').addEventListener('click', shareNote);
    $('download-btn').addEventListener('click', (e) => {
      if (!state.job || !state.job.fileUrl) e.preventDefault();
    });
    $('dock').append(dockError);

    audio.addEventListener('playing', () => {
      setPlaying(true);
      const job = state.job;
      if (job) setStatus(job.state === 'ready' || job.fileMode ? 'Playing' : 'Playing as it’s made');
    });
    audio.addEventListener('pause', () => {
      setPlaying(false);
      if (state.job && !audio.ended && state.job.state !== 'error') setStatus('Paused');
    });
    audio.addEventListener('waiting', () => { if (!audio.paused) setStatus('Loading…'); });
    audio.addEventListener('timeupdate', updateProgress);
    audio.addEventListener('ended', () => {
      setPlaying(false);
      updateProgress();
      const job = state.job;
      if (!job) return;
      if (job.fileUrl) {
        switchToFile();
        setStatus('Finished. Play it again or share it.');
      } else {
        setStatus('Finished');
      }
    });
    audio.addEventListener('error', () => {
      const job = state.job;
      if (!job || audio.dataset.job !== job.id || !audio.getAttribute('src')) return;
      if (audio.error && audio.error.code === 1) return; // aborted by us
      if (job.state === 'error') return;
      failJob("The voice note couldn't play. Try again.");
    });

    window.addEventListener('resize', () => {
      clearTimeout(wire.t);
      wire.t = setTimeout(autoGrowAll, 150);
    });
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(autoGrowAll);
  }

  async function loadConfig() {
    try {
      state.config = await api('api/config');
      renderForm();
      $('write-btn').disabled = false;
    } catch (err) {
      $('write-btn').disabled = true;
      const e = $('form-error');
      e.textContent = '';
      e.append(document.createTextNode("Can't reach Samjhao's server right now. "));
      const retry = h('button', { type: 'button', class: 'btn btn-small', text: 'Try again' });
      retry.style.marginLeft = '6px';
      retry.addEventListener('click', () => { e.hidden = true; loadConfig(); });
      e.append(retry);
      e.hidden = false;
    }
  }

  wire();
  loadConfig();
})();
