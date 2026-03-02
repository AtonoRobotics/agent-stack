// Shared formatters for Mission Control pages

function fmtDuration(seconds) {
  if (seconds == null) return '—';
  if (seconds < 60) return seconds.toFixed(1) + 's';
  var m = Math.floor(seconds / 60);
  var s = Math.round(seconds % 60);
  return m + 'm ' + s + 's';
}

function fmtDate(iso) {
  if (!iso) return '—';
  var d = new Date(iso);
  var now = new Date();
  var diff = (now - d) / 1000;
  if (diff < 60) return 'just now';
  if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
  if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ' ' +
    d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
}

function fmtPct(value) {
  if (value == null) return '—';
  return (value * 100).toFixed(1) + '%';
}

function fmtBytes(gb) {
  if (gb == null) return '—';
  if (gb >= 1000) return (gb / 1000).toFixed(1) + ' TB';
  return gb.toFixed(1) + ' GB';
}

function statusVariant(status) {
  if (!status) return 'neutral';
  var s = status.toLowerCase();
  if (s === 'success' || s === 'completed' || s === 'promoted' || s === 'running' || s === 'pass') return 'success';
  if (s === 'failed' || s === 'error' || s === 'fail' || s === 'critical') return 'danger';
  if (s === 'pending' || s === 'queued' || s === 'draft') return 'warning';
  if (s === 'in_progress' || s === 'active' || s === 'validated') return 'accent';
  return 'neutral';
}

export { fmtDuration, fmtDate, fmtPct, fmtBytes, statusVariant }
