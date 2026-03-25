/* ═══════════════════════════════════════════════════════════════
   Auto Youtuber — Core Application JavaScript
   ═══════════════════════════════════════════════════════════════ */

const AY = {
  // ── Toast Notification System ───────────────────────────────
  toast: {
    container: null,

    init() {
      this.container = document.getElementById('toast-container');
      // Render any server-side flash messages as toasts
      document.querySelectorAll('.ay-flash-data').forEach(el => {
        this.show(el.dataset.message, el.dataset.category || 'info');
        el.remove();
      });
    },

    show(message, type = 'info', duration = 5000) {
      if (!this.container) return;

      const icons = {
        success: 'bi-check-circle-fill',
        error: 'bi-exclamation-triangle-fill',
        warning: 'bi-exclamation-circle-fill',
        info: 'bi-info-circle-fill'
      };

      const toast = document.createElement('div');
      toast.className = `ay-toast ${type}`;
      toast.innerHTML = `
        <i class="bi ${icons[type] || icons.info} ay-toast-icon"></i>
        <div class="ay-toast-content">${this.esc(message)}</div>
        <button class="ay-toast-close" onclick="AY.toast.dismiss(this.parentElement)">
          <i class="bi bi-x"></i>
        </button>
        <div class="ay-toast-progress" style="animation-duration: ${duration}ms"></div>
      `;

      this.container.appendChild(toast);

      // Auto-dismiss (errors stay longer)
      const autoDur = type === 'error' ? duration * 2 : duration;
      setTimeout(() => this.dismiss(toast), autoDur);

      // Sound
      AY.sound.play(type === 'success' ? 'success' : type === 'error' ? 'error' : 'notification');

      return toast;
    },

    dismiss(toast) {
      if (!toast || !toast.parentElement) return;
      toast.classList.add('removing');
      setTimeout(() => toast.remove(), 300);
    },

    esc(s) {
      const d = document.createElement('div');
      d.textContent = s;
      return d.innerHTML;
    }
  },

  // ── Sound Effects System (Web Audio API) ────────────────────
  sound: {
    enabled: false,
    ctx: null,

    init() {
      this.enabled = localStorage.getItem('ay_sounds') === 'true';
    },

    toggle() {
      this.enabled = !this.enabled;
      localStorage.setItem('ay_sounds', this.enabled);
      if (this.enabled) this.play('notification');
      return this.enabled;
    },

    play(type) {
      if (!this.enabled) return;
      try {
        if (!this.ctx) this.ctx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = this.ctx.createOscillator();
        const gain = this.ctx.createGain();
        osc.connect(gain);
        gain.connect(this.ctx.destination);
        gain.gain.value = 0.08;

        if (type === 'success') {
          osc.frequency.value = 523.25; // C5
          osc.type = 'sine';
          gain.gain.exponentialRampToValueAtTime(0.001, this.ctx.currentTime + 0.3);
          osc.start();
          osc.stop(this.ctx.currentTime + 0.3);
          // Second note
          setTimeout(() => {
            const o2 = this.ctx.createOscillator();
            const g2 = this.ctx.createGain();
            o2.connect(g2); g2.connect(this.ctx.destination);
            g2.gain.value = 0.08;
            o2.frequency.value = 659.25; // E5
            o2.type = 'sine';
            g2.gain.exponentialRampToValueAtTime(0.001, this.ctx.currentTime + 0.3);
            o2.start(); o2.stop(this.ctx.currentTime + 0.3);
          }, 150);
        } else if (type === 'error') {
          osc.frequency.value = 200;
          osc.type = 'sawtooth';
          gain.gain.exponentialRampToValueAtTime(0.001, this.ctx.currentTime + 0.4);
          osc.start();
          osc.stop(this.ctx.currentTime + 0.4);
        } else {
          osc.frequency.value = 440;
          osc.type = 'sine';
          gain.gain.exponentialRampToValueAtTime(0.001, this.ctx.currentTime + 0.15);
          osc.start();
          osc.stop(this.ctx.currentTime + 0.15);
        }
      } catch (e) { /* Audio not available */ }
    }
  },

  // ── Confetti System ─────────────────────────────────────────
  confetti: {
    canvas: null,
    ctx: null,

    fire() {
      if (!this.canvas) {
        this.canvas = document.getElementById('confetti-canvas');
        if (!this.canvas) return;
        this.ctx = this.canvas.getContext('2d');
      }

      this.canvas.width = window.innerWidth;
      this.canvas.height = window.innerHeight;

      const particles = [];
      const colors = ['#FF0033', '#00C853', '#FFB300', '#00B0FF', '#E040FB', '#FF6D00', '#76FF03'];
      const count = 120;

      for (let i = 0; i < count; i++) {
        particles.push({
          x: window.innerWidth / 2 + (Math.random() - 0.5) * 200,
          y: window.innerHeight / 2,
          vx: (Math.random() - 0.5) * 16,
          vy: Math.random() * -18 - 4,
          color: colors[Math.floor(Math.random() * colors.length)],
          size: Math.random() * 8 + 3,
          rotation: Math.random() * 360,
          rotSpeed: (Math.random() - 0.5) * 10,
          gravity: 0.4,
          drag: 0.98,
          opacity: 1
        });
      }

      const animate = () => {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        let alive = false;

        particles.forEach(p => {
          p.vy += p.gravity;
          p.vx *= p.drag;
          p.x += p.vx;
          p.y += p.vy;
          p.rotation += p.rotSpeed;
          p.opacity -= 0.008;

          if (p.opacity <= 0) return;
          alive = true;

          this.ctx.save();
          this.ctx.translate(p.x, p.y);
          this.ctx.rotate(p.rotation * Math.PI / 180);
          this.ctx.globalAlpha = p.opacity;
          this.ctx.fillStyle = p.color;
          this.ctx.fillRect(-p.size / 2, -p.size / 2, p.size, p.size * 0.6);
          this.ctx.restore();
        });

        if (alive) requestAnimationFrame(animate);
        else this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
      };

      animate();
      AY.sound.play('success');
    }
  },

  // ── Command Palette ─────────────────────────────────────────
  cmd: {
    overlay: null,
    input: null,
    list: null,
    items: [],
    activeIndex: 0,

    commands: [
      { label: 'Go to Dashboard', icon: 'bi-grid-1x2-fill', action: () => location.href = '/', shortcut: 'G D' },
      { label: 'Submit URL', icon: 'bi-plus-circle', action: () => location.href = '/submit', shortcut: 'G S' },
      { label: 'View History', icon: 'bi-clock-history', action: () => location.href = '/history', shortcut: 'G H' },
      { label: 'Open Settings', icon: 'bi-gear', action: () => location.href = '/settings', shortcut: 'G E' },
      { label: 'View Logs', icon: 'bi-terminal', action: () => location.href = '/logs', shortcut: 'G L' },
      { label: 'Open YouTube Studio', icon: 'bi-box-arrow-up-right', action: () => window.open('https://studio.youtube.com', '_blank'), shortcut: '' },
      { label: 'Toggle Dark/Light Mode', icon: 'bi-moon-fill', action: () => AY.theme.toggle(), shortcut: '' },
      { label: 'Toggle Sound Effects', icon: 'bi-volume-up-fill', action: () => { const on = AY.sound.toggle(); AY.toast.show(`Sounds ${on ? 'enabled' : 'disabled'}`, 'info', 2000); }, shortcut: '' },
      { label: 'Grab Viral Videos', icon: 'bi-lightning-fill', action: () => { const f = document.getElementById('form-grab'); if (f) f.submit(); else location.href = '/'; }, shortcut: '' },
      { label: 'Start Processing', icon: 'bi-play-fill', action: () => { const f = document.getElementById('form-start'); if (f) f.submit(); }, shortcut: '' },
    ],

    init() {
      this.overlay = document.getElementById('cmd-overlay');
      this.input = document.getElementById('cmd-input');
      this.list = document.getElementById('cmd-list');
      if (!this.overlay) return;

      this.render(this.commands);

      this.input.addEventListener('input', () => {
        const q = this.input.value.toLowerCase();
        const filtered = this.commands.filter(c => c.label.toLowerCase().includes(q));
        this.activeIndex = 0;
        this.render(filtered);
      });

      this.input.addEventListener('keydown', e => {
        const items = this.list.querySelectorAll('.ay-cmd-item');
        if (e.key === 'ArrowDown') { e.preventDefault(); this.activeIndex = Math.min(this.activeIndex + 1, items.length - 1); this.highlight(items); }
        else if (e.key === 'ArrowUp') { e.preventDefault(); this.activeIndex = Math.max(this.activeIndex - 1, 0); this.highlight(items); }
        else if (e.key === 'Enter') { e.preventDefault(); if (items[this.activeIndex]) items[this.activeIndex].click(); }
        else if (e.key === 'Escape') { this.close(); }
      });

      this.overlay.addEventListener('click', e => { if (e.target === this.overlay) this.close(); });
    },

    render(cmds) {
      this.items = cmds;
      this.list.innerHTML = cmds.map((c, i) => `
        <div class="ay-cmd-item ${i === this.activeIndex ? 'active' : ''}" data-index="${i}">
          <i class="bi ${c.icon}"></i>
          <span>${c.label}</span>
          ${c.shortcut ? `<span class="ay-cmd-item-shortcut">${c.shortcut}</span>` : ''}
        </div>
      `).join('');

      this.list.querySelectorAll('.ay-cmd-item').forEach(el => {
        el.addEventListener('click', () => {
          const idx = parseInt(el.dataset.index);
          this.close();
          if (this.items[idx]) this.items[idx].action();
        });
        el.addEventListener('mouseenter', () => {
          this.activeIndex = parseInt(el.dataset.index);
          this.highlight(this.list.querySelectorAll('.ay-cmd-item'));
        });
      });
    },

    highlight(items) {
      items.forEach((el, i) => el.classList.toggle('active', i === this.activeIndex));
    },

    open() {
      this.overlay.classList.add('open');
      this.input.value = '';
      this.activeIndex = 0;
      this.render(this.commands);
      setTimeout(() => this.input.focus(), 50);
    },

    close() {
      this.overlay.classList.remove('open');
    },

    toggle() {
      if (this.overlay.classList.contains('open')) this.close();
      else this.open();
    }
  },

  // ── Keyboard Shortcuts ──────────────────────────────────────
  keys: {
    buffer: '',
    bufferTimeout: null,

    init() {
      document.addEventListener('keydown', e => {
        // Ignore when typing in inputs
        if (['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName)) return;

        // Cmd/Ctrl + K for command palette
        if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
          e.preventDefault();
          AY.cmd.toggle();
          return;
        }

        // ? for shortcut help
        if (e.key === '?') {
          AY.cmd.open();
          return;
        }

        // Sequence shortcuts (G then D, G then S, etc.)
        clearTimeout(this.bufferTimeout);
        this.buffer += e.key.toUpperCase();
        this.bufferTimeout = setTimeout(() => { this.buffer = ''; }, 800);

        const seqs = { 'GD': '/', 'GS': '/submit', 'GH': '/history', 'GE': '/settings', 'GL': '/logs' };
        if (seqs[this.buffer]) {
          location.href = seqs[this.buffer];
          this.buffer = '';
        }

        // N for new submit
        if (this.buffer === 'N') {
          location.href = '/submit';
          this.buffer = '';
        }
      });
    }
  },

  // ── Theme Toggle ────────────────────────────────────────────
  theme: {
    init() {
      const saved = localStorage.getItem('ay_theme') || 'dark';
      document.documentElement.setAttribute('data-theme', saved);
      this.updateIcon(saved);
    },

    toggle() {
      const current = document.documentElement.getAttribute('data-theme') || 'dark';
      const next = current === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      localStorage.setItem('ay_theme', next);
      this.updateIcon(next);
    },

    updateIcon(theme) {
      const icon = document.getElementById('theme-icon');
      if (icon) {
        icon.className = 'bi ' + (theme === 'dark' ? 'bi-moon-fill' : 'bi-sun-fill');
      }
      const label = document.getElementById('theme-label');
      if (label) label.textContent = theme === 'dark' ? 'Dark Mode' : 'Light Mode';
    }
  },

  // ── Sidebar ─────────────────────────────────────────────────
  sidebar: {
    el: null,
    backdrop: null,

    init() {
      this.el = document.getElementById('sidebar');
      this.backdrop = document.getElementById('sidebar-backdrop');
      if (!this.el) return;

      const collapsed = localStorage.getItem('ay_sidebar_collapsed') === 'true';
      if (collapsed) this.el.classList.add('collapsed');

      const toggle = document.getElementById('sidebar-toggle');
      if (toggle) toggle.addEventListener('click', () => this.toggle());

      const mobileToggle = document.getElementById('mobile-toggle');
      if (mobileToggle) mobileToggle.addEventListener('click', () => this.mobileToggle());

      if (this.backdrop) this.backdrop.addEventListener('click', () => this.mobileClose());
    },

    toggle() {
      this.el.classList.toggle('collapsed');
      localStorage.setItem('ay_sidebar_collapsed', this.el.classList.contains('collapsed'));
    },

    mobileToggle() {
      this.el.classList.toggle('mobile-open');
      this.backdrop.classList.toggle('visible');
    },

    mobileClose() {
      this.el.classList.remove('mobile-open');
      this.backdrop.classList.remove('visible');
    }
  },

  // ── Confirmation Modal ──────────────────────────────────────
  confirm: {
    overlay: null,

    init() {
      this.overlay = document.getElementById('confirm-overlay');
    },

    show(title, body, onConfirm, confirmLabel = 'Confirm', confirmClass = 'ay-btn-primary') {
      if (!this.overlay) return;
      document.getElementById('confirm-title').textContent = title;
      document.getElementById('confirm-body').textContent = body;
      const btn = document.getElementById('confirm-btn');
      btn.textContent = confirmLabel;
      btn.className = 'ay-btn ' + confirmClass;
      btn.onclick = () => { this.hide(); onConfirm(); };
      this.overlay.classList.add('open');
    },

    hide() {
      if (this.overlay) this.overlay.classList.remove('open');
    }
  },

  // ── Browser Notifications ───────────────────────────────────
  notify: {
    enabled: false,

    init() {
      if ('Notification' in window && Notification.permission === 'granted') {
        this.enabled = true;
      }
    },

    async requestPermission() {
      if ('Notification' in window) {
        const perm = await Notification.requestPermission();
        this.enabled = perm === 'granted';
        return this.enabled;
      }
      return false;
    },

    send(title, body, url) {
      if (!this.enabled || document.hasFocus()) return;
      const n = new Notification(title, { body, icon: '/static/favicon.svg' });
      if (url) n.onclick = () => { window.focus(); window.open(url, '_blank'); };
    }
  },

  // ── Relative Time Formatting ────────────────────────────────
  timeago(dateStr) {
    if (!dateStr) return '';
    const date = new Date(dateStr.replace(' ', 'T'));
    if (isNaN(date.getTime())) return dateStr;

    const now = new Date();
    const diff = (now - date) / 1000;

    if (diff < 60) return 'just now';
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`;
    return dateStr.split(' ')[0]; // Return date part
  },

  // ── Subreddit Color Assignment ──────────────────────────────
  subColors: {},
  subColorIndex: 0,

  getSubColor(subreddit) {
    if (!this.subColors[subreddit]) {
      this.subColors[subreddit] = this.subColorIndex % 8;
      this.subColorIndex++;
    }
    return 'sub-' + this.subColors[subreddit];
  },

  // ── HTML Escaping ───────────────────────────────────────────
  esc(s) {
    if (!s) return '';
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  },

  // ── Onboarding / First Run ──────────────────────────────────
  onboarding: {
    init() {
      // Check if this is first visit
      if (!localStorage.getItem('ay_visited')) {
        localStorage.setItem('ay_visited', 'true');
        // Show welcome toast
        setTimeout(() => {
          AY.toast.show('Welcome to Auto Youtuber! Press Cmd+K to open the command palette.', 'info', 8000);
        }, 1000);
      }
    }
  },

  // ── Initialize Everything ───────────────────────────────────
  init() {
    this.theme.init();
    this.sidebar.init();
    this.toast.init();
    this.sound.init();
    this.cmd.init();
    this.keys.init();
    this.confirm.init();
    this.notify.init();
    this.onboarding.init();

    // Page fade-in
    document.body.classList.add('loaded');
  }
};

// Boot
document.addEventListener('DOMContentLoaded', () => AY.init());
