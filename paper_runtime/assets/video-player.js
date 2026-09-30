(() => {
  'use strict';
  const players = new Set();
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  const time = seconds => {
    const value = Math.max(0, Math.floor(Number(seconds) || 0));
    return `${Math.floor(value / 60)}:${String(value % 60).padStart(2, '0')}`;
  };
  let vimeoSDK;
  const loadVimeo = () => {
    if (window.Vimeo?.Player) return Promise.resolve();
    if (!vimeoSDK) vimeoSDK = new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = 'https://player.vimeo.com/api/player.js';
      script.onload = resolve;
      script.onerror = reject;
      document.head.append(script);
    });
    return vimeoSDK;
  };

  function enhance(root, adapter) {
    const play = root.querySelector('.video-toggle');
    const start = root.querySelector('.video-start');
    const mute = root.querySelector('.video-mute');
    const seek = root.querySelector('.video-seek');
    const clock = root.querySelector('.video-time');
    const full = root.querySelector('.video-fullscreen');
    let duration = 0, current = 0, playing = false, muted = true;
    let manualPause = false, resumeOnVisible = false, interactionTimer;
    const paint = () => {
      root.dataset.playing = String(playing);
      root.dataset.muted = String(muted);
      play.setAttribute('aria-label', playing ? root.dataset.labelPause : root.dataset.labelPlay);
      mute.setAttribute('aria-label', muted ? root.dataset.labelUnmute : root.dataset.labelMute);
      mute.setAttribute('aria-pressed', String(!muted));
      clock.textContent = `${time(current)} / ${time(duration)}`;
      seek.disabled = !(duration > 0 && Number.isFinite(duration));
      seek.value = seek.disabled ? '0' : String(current / duration * 100);
      seek.setAttribute('aria-valuetext', `${time(current)} / ${time(duration)}`);
    };
    const reveal = () => {
      root.dataset.recent = '';
      clearTimeout(interactionTimer);
      interactionTimer = setTimeout(() => delete root.dataset.recent, 2200);
    };
    const error = () => {
      root.dataset.error = '';
      root.querySelector('.video-status').textContent = root.dataset.labelError;
    };
    const attemptPlay = async (automatic = false) => {
      try {
        await adapter.play();
      } catch (_) {
        // An autoplay denial is recoverable through the visible play button.
        playing = false;
        paint();
        if (!automatic) error();
      }
    };
    const toggle = () => {
      manualPause = playing;
      if (playing) adapter.pause().catch(error);
      else { delete root.dataset.error; attemptPlay(); }
      reveal();
    };
    const toggleMute = () => adapter.setMuted(!muted).catch(error);
    const collapse = () => {
      delete root.dataset.expanded;
      document.body.classList.remove('paper-video-expanded');
      full.focus();
    };
    const fullscreen = async () => {
      if ('expanded' in root.dataset) { collapse(); return; }
      try {
        if (document.fullscreenElement) await document.exitFullscreen();
        else if (root.requestFullscreen) await root.requestFullscreen();
        else if (adapter.fullscreen) await adapter.fullscreen();
        else throw new Error('Fullscreen is unavailable');
      } catch (_) {
        // Embedded browsers can deny fullscreen; keep an in-page expanded view.
        root.dataset.expanded = '';
        document.body.classList.add('paper-video-expanded');
      }
      reveal();
    };
    adapter.onPlay(() => {
      playing = true;
      delete root.dataset.error;
      for (const other of players) if (other !== adapter) other.pause().catch(() => {});
      paint();
      reveal();
    });
    adapter.onPause(() => { playing = false; paint(); });
    adapter.onTime((seconds, total) => { current = seconds; duration = total; paint(); });
    adapter.onMute(value => { muted = value; paint(); });
    adapter.onError(error);
    play.addEventListener('click', toggle);
    start.addEventListener('click', toggle);
    mute.addEventListener('click', toggleMute);
    seek.addEventListener('input', () => {
      if (!seek.disabled) adapter.seek(Number(seek.value) / 100 * duration).catch(error);
      reveal();
    });
    full.addEventListener('click', fullscreen);
    root.addEventListener('pointermove', reveal);
    root.addEventListener('pointerdown', event => {
      if (event.pointerType !== 'mouse') reveal();
    });
    root.addEventListener('keydown', event => {
      if (event.target.matches('button, input, a')) return;
      if ([' ', 'k', 'm', 'f', 'ArrowLeft', 'ArrowRight'].includes(event.key)) event.preventDefault();
      if (event.key === ' ' || event.key === 'k') toggle();
      else if (event.key === 'm') toggleMute();
      else if (event.key === 'f') fullscreen();
      else if ((event.key === 'ArrowLeft' || event.key === 'ArrowRight') && duration > 0) {
        adapter.seek(Math.min(duration, Math.max(0, current + (event.key === 'ArrowLeft' ? -5 : 5)))).catch(error);
      }
      reveal();
    });
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) adapter.pause().catch(() => {});
    });
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && 'expanded' in root.dataset) collapse();
    });
    const observer = typeof IntersectionObserver === 'function' ? new IntersectionObserver(entries => {
      for (const entry of entries) {
        const visible = entry.isIntersecting && entry.intersectionRatio >= .35;
        if (!visible) {
          resumeOnVisible = playing && !manualPause;
          adapter.pause().catch(() => {});
        } else if (!document.hidden && !manualPause && !reducedMotion.matches && (resumeOnVisible || root.dataset.autoplay === 'true')) {
          attemptPlay(true);
          resumeOnVisible = false;
        }
      }
    }, { threshold: [0, .35] }) : null;
    paint();
    root.dataset.enhanced = '';
    players.add(adapter);
    adapter.hideControls();
    observer?.observe(root);
  }

  function nativePlayer(root) {
    const video = root.querySelector('video');
    const on = (name, callback) => video.addEventListener(name, callback);
    const size = () => {
      if (!root.style.getPropertyValue('--video-ratio') && video.videoWidth && video.videoHeight) {
        root.style.setProperty('--video-ratio', `${video.videoWidth} / ${video.videoHeight}`);
      }
    };
    on('loadedmetadata', size);
    size();
    enhance(root, {
      play: () => video.play(),
      pause: async () => video.pause(),
      setMuted: async value => { video.muted = value; },
      seek: async value => { video.currentTime = value; },
      fullscreen: video.webkitEnterFullscreen ? async () => video.webkitEnterFullscreen() : null,
      hideControls: () => { video.controls = false; },
      onPlay: callback => on('play', callback),
      onPause: callback => { on('pause', callback); on('ended', callback); },
      onTime: callback => {
        const update = () => callback(video.currentTime, video.duration);
        on('timeupdate', update); on('loadedmetadata', update); on('durationchange', update);
        update();
      },
      onMute: callback => on('volumechange', () => callback(video.muted || video.volume === 0)),
      onError: callback => { on('error', callback); if (video.error) callback(); },
    });
  }

  async function vimeoPlayer(root) {
    const iframe = root.querySelector('iframe');
    const fallback = iframe.src;
    let player;
    try {
      await loadVimeo();
      const source = new URL(fallback);
      source.searchParams.set('controls', '0');
      iframe.src = source.href;
      player = new window.Vimeo.Player(iframe);
      await Promise.race([player.ready(), new Promise((_, reject) => setTimeout(reject, 15000))]);
      const [duration, width, height] = await Promise.all([player.getDuration(), player.getVideoWidth(), player.getVideoHeight()]);
      if (!root.style.getPropertyValue('--video-ratio') && width && height) root.style.setProperty('--video-ratio', `${width} / ${height}`);
      enhance(root, {
        play: () => player.play(), pause: () => player.pause(),
        setMuted: value => player.setMuted(value), seek: value => player.setCurrentTime(value),
        fullscreen: () => player.requestFullscreen(), hideControls: () => {},
        onPlay: callback => player.on('play', callback),
        onPause: callback => { player.on('pause', callback); player.on('ended', callback); },
        onTime: callback => { player.on('timeupdate', data => callback(data.seconds, data.duration)); callback(0, duration); },
        onMute: callback => player.on('volumechange', () => player.getMuted().then(callback).catch(() => {})),
        onError: callback => player.on('error', callback),
      });
    } catch (_) {
      // Keep the platform's usable native player if its SDK or API is blocked.
      delete root.dataset.enhanced;
      iframe.src = fallback;
    }
  }
  for (const root of document.querySelectorAll('.paper-video')) {
    root.tabIndex = 0;
    if (root.dataset.provider === 'native') nativePlayer(root);
    else vimeoPlayer(root);
  }
})();
