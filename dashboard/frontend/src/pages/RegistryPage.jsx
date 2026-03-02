import React, { useState, useEffect } from 'react'
import { authFetch } from '../utils/authFetch'
import { fmtDate, statusVariant } from '../utils/fmt'

var e = React.createElement;

function RegistryPage() {
  var tabState = useState('files');
  var tab = tabState[0], setTab = tabState[1];

  return e('div', null,
    e('div', { className: 'glass-page-header' },
      e('h1', null, 'Registry'),
      e('p', null, 'Configuration artifacts, builds, robots, and scenes')
    ),
    e('div', { className: 'glass-tabs' },
      ['files', 'builds', 'robots', 'scenes'].map(function(t) {
        return e('button', {
          key: t, className: 'glass-tab' + (tab === t ? ' glass-tab--active' : ''),
          onClick: function() { setTab(t); }
        }, t.charAt(0).toUpperCase() + t.slice(1));
      })
    ),
    tab === 'files' ? e(FilesTab) : null,
    tab === 'builds' ? e(BuildsTab) : null,
    tab === 'robots' ? e(RobotsTab) : null,
    tab === 'scenes' ? e(ScenesTab) : null
  );
}

function FilesTab() {
  var dataState = useState([]);
  var data = dataState[0], setData = dataState[1];
  var loadingState = useState(true);
  var loading = loadingState[0], setLoading = loadingState[1];
  var filterStatus = useState('');
  var status = filterStatus[0], setStatus = filterStatus[1];
  var filterType = useState('');
  var fileType = filterType[0], setFileType = filterType[1];
  var expandedState = useState(null);
  var expanded = expandedState[0], setExpanded = expandedState[1];

  useEffect(function() {
    var params = '?limit=50';
    if (status) params += '&status=' + status;
    if (fileType) params += '&file_type=' + fileType;
    authFetch('/mc/api/registry/files' + params)
      .then(function(r) { return r.json(); })
      .then(function(d) { setData(d.items || d); setLoading(false); })
      .catch(function() { setLoading(false); });
  }, [status, fileType]);

  function promoteFile(fileId) {
    authFetch('/mc/api/registry/files/' + fileId + '/status', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: 'promoted' })
    }).then(function() {
      setData(data.map(function(f) { return (f.file_id || f.id) === fileId ? Object.assign({}, f, { status: 'promoted' }) : f; }));
    }).catch(function() {});
  }

  if (loading) return e('div', { className: 'glass-card', style: { padding: '40px', textAlign: 'center', color: 'var(--text-dim)' } }, 'Loading...');

  return e('div', null,
    e('div', { className: 'glass-filter-row' },
      e('select', { value: status, onChange: function(ev) { setStatus(ev.target.value); } },
        e('option', { value: '' }, 'All statuses'),
        e('option', { value: 'draft' }, 'Draft'),
        e('option', { value: 'validated' }, 'Validated'),
        e('option', { value: 'promoted' }, 'Promoted')
      ),
      e('select', { value: fileType, onChange: function(ev) { setFileType(ev.target.value); } },
        e('option', { value: '' }, 'All types'),
        e('option', { value: 'urdf' }, 'URDF'),
        e('option', { value: 'usd' }, 'USD'),
        e('option', { value: 'yaml' }, 'YAML'),
        e('option', { value: 'launch' }, 'Launch')
      ),
      e('span', { className: 'glass-filter-row__count' }, data.length + ' files')
    ),
    e('table', { className: 'glass-table' },
      e('thead', null,
        e('tr', null,
          e('th', null, 'File'),
          e('th', null, 'Type'),
          e('th', null, 'Robot'),
          e('th', null, 'Status'),
          e('th', null, 'Hash'),
          e('th', null, 'Created'),
          e('th', null, '')
        )
      ),
      e('tbody', null,
        data.length === 0
          ? e('tr', null, e('td', { colSpan: 7, style: { textAlign: 'center', color: 'var(--text-dim)', padding: '30px' } }, 'No files registered'))
          : data.map(function(f) {
              var isExp = expanded === (f.file_id || f.id);
              return e(React.Fragment, { key: f.file_id || f.id },
                e('tr', {
                  className: isExp ? 'glass-table__row--expanded' : '',
                  onClick: function() { setExpanded(isExp ? null : (f.file_id || f.id)); },
                  style: { cursor: 'pointer' }
                },
                  e('td', { className: 'mono', style: { maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis' } }, f.file_path || f.filename || f.id),
                  e('td', null, f.file_type || '—'),
                  e('td', null, f.robot_id || '—'),
                  e('td', null, e('span', { className: 'glass-pill glass-pill--' + statusVariant(f.status) }, f.status)),
                  e('td', { className: 'mono', style: { fontSize: '9px' } }, f.file_hash ? f.file_hash.slice(0, 12) : '—'),
                  e('td', null, fmtDate(f.created_at)),
                  e('td', null,
                    f.status === 'validated' ? e('button', {
                      className: 'glass-btn glass-btn--sm',
                      onClick: function(ev) { ev.stopPropagation(); promoteFile(f.file_id || f.id); }
                    }, 'Promote') : null
                  )
                ),
                isExp ? e('tr', { className: 'glass-table__detail-row' },
                  e('td', { colSpan: 7 },
                    e('div', { className: 'glass-log' },
                      e('pre', null, JSON.stringify(f, null, 2))
                    )
                  )
                ) : null
              );
            })
      )
    )
  );
}

function BuildsTab() {
  var dataState = useState([]);
  var data = dataState[0], setData = dataState[1];
  var loadingState = useState(true);
  var loading = loadingState[0], setLoading = loadingState[1];
  var expandedState = useState(null);
  var expanded = expandedState[0], setExpanded = expandedState[1];
  var filesState = useState({});
  var buildFiles = filesState[0], setBuildFiles = filesState[1];

  useEffect(function() {
    authFetch('/mc/api/builds?limit=50')
      .then(function(r) { return r.json(); })
      .then(function(d) { setData(d.items || d); setLoading(false); })
      .catch(function() { setLoading(false); });
  }, []);

  function loadBuildFiles(buildId) {
    if (buildFiles[buildId]) return;
    authFetch('/mc/api/builds/' + buildId + '/files')
      .then(function(r) { return r.json(); })
      .then(function(d) {
        var next = Object.assign({}, buildFiles);
        next[buildId] = d.items || d;
        setBuildFiles(next);
      })
      .catch(function() {});
  }

  if (loading) return e('div', { className: 'glass-card', style: { padding: '40px', textAlign: 'center', color: 'var(--text-dim)' } }, 'Loading...');

  return e('table', { className: 'glass-table' },
    e('thead', null,
      e('tr', null,
        e('th', null, 'Build'),
        e('th', null, 'Robot'),
        e('th', null, 'Process'),
        e('th', null, 'Status'),
        e('th', null, 'Created')
      )
    ),
    e('tbody', null,
      data.length === 0
        ? e('tr', null, e('td', { colSpan: 5, style: { textAlign: 'center', color: 'var(--text-dim)', padding: '30px' } }, 'No builds'))
        : data.map(function(b) {
            var isExp = expanded === (b.build_id || b.id);
            return e(React.Fragment, { key: b.build_id || b.id },
              e('tr', {
                className: isExp ? 'glass-table__row--expanded' : '',
                onClick: function() { setExpanded(isExp ? null : (b.build_id || b.id)); if (!isExp) loadBuildFiles(b.build_id || b.id); },
                style: { cursor: 'pointer' }
              },
                e('td', { className: 'mono' }, String(b.build_id || b.id).slice(0, 8)),
                e('td', null, b.robot_id || '—'),
                e('td', null, b.process || '—'),
                e('td', null, e('span', { className: 'glass-pill glass-pill--' + statusVariant(b.status) }, b.status)),
                e('td', null, fmtDate(b.created_at))
              ),
              isExp ? e('tr', { className: 'glass-table__detail-row' },
                e('td', { colSpan: 5 },
                  b.steps ? e('div', { className: 'glass-log', style: { marginBottom: '8px' } },
                    e('strong', null, 'Steps:'),
                    e('pre', null, typeof b.steps === 'string' ? b.steps : JSON.stringify(b.steps, null, 2))
                  ) : null,
                  b.null_report ? e('div', { className: 'glass-log', style: { marginBottom: '8px' } },
                    e('strong', null, 'NULL Report:'),
                    e('pre', null, typeof b.null_report === 'string' ? b.null_report : JSON.stringify(b.null_report, null, 2))
                  ) : null,
                  buildFiles[b.build_id || b.id] ? e('div', null,
                    e('div', { style: { fontSize: '10px', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '4px' } }, 'Associated Files:'),
                    (buildFiles[b.build_id || b.id] || []).map(function(f, i) {
                      return e('div', { key: i, style: { fontSize: '10px', fontFamily: 'var(--font-mono)', color: 'var(--text)', padding: '2px 0' } },
                        e('span', { className: 'glass-pill glass-pill--' + statusVariant(f.status), style: { marginRight: '6px' } }, f.status),
                        f.file_path || f.filename || f.id
                      );
                    })
                  ) : e('div', { style: { fontSize: '10px', color: 'var(--text-dim)' } }, 'Loading files...')
                )
              ) : null
            );
          })
    )
  );
}

function RobotsTab() {
  var dataState = useState([]);
  var data = dataState[0], setData = dataState[1];
  var loadingState = useState(true);
  var loading = loadingState[0], setLoading = loadingState[1];

  useEffect(function() {
    authFetch('/mc/api/registry/robots')
      .then(function(r) { return r.json(); })
      .then(function(d) { setData(d.items || d); setLoading(false); })
      .catch(function() { setLoading(false); });
  }, []);

  if (loading) return e('div', { className: 'glass-card', style: { padding: '40px', textAlign: 'center', color: 'var(--text-dim)' } }, 'Loading...');

  return data.length === 0
    ? e('div', { className: 'glass-card', style: { padding: '40px', textAlign: 'center', color: 'var(--text-dim)' } }, 'No robots registered')
    : e('div', { className: 'glass-card-grid' },
        data.map(function(r) {
          return e('div', { key: r.id || r.robot_id, className: 'glass-card' },
            e('div', { className: 'glass-card__header' },
              e('div', null,
                e('div', { className: 'glass-card__title' }, r.name || r.robot_id),
                e('div', { className: 'glass-card__sub' }, r.manufacturer || '')
              ),
              e('span', { className: 'glass-pill glass-pill--accent' }, r.robot_type || 'robot')
            ),
            e('div', { className: 'glass-card__body' },
              e('div', { className: 'glass-card__field' }, e('span', null, 'DOF: '), e('strong', null, r.dof || '—')),
              e('div', { className: 'glass-card__field' }, e('span', null, 'Reach: '), e('strong', null, r.reach_mm ? r.reach_mm + 'mm' : '—')),
              e('div', { className: 'glass-card__field' }, e('span', null, 'Payload: '), e('strong', null, r.payload_kg ? r.payload_kg + 'kg' : '—'))
            )
          );
        })
      );
}

function ScenesTab() {
  var dataState = useState([]);
  var data = dataState[0], setData = dataState[1];
  var loadingState = useState(true);
  var loading = loadingState[0], setLoading = loadingState[1];

  useEffect(function() {
    authFetch('/mc/api/registry/scenes')
      .then(function(r) { return r.json(); })
      .then(function(d) { setData(d.items || d); setLoading(false); })
      .catch(function() { setLoading(false); });
  }, []);

  if (loading) return e('div', { className: 'glass-card', style: { padding: '40px', textAlign: 'center', color: 'var(--text-dim)' } }, 'Loading...');

  return data.length === 0
    ? e('div', { className: 'glass-card', style: { padding: '40px', textAlign: 'center', color: 'var(--text-dim)' } }, 'No scenes registered')
    : e('div', { className: 'glass-card-grid' },
        data.map(function(s) {
          return e('div', { key: s.id || s.scene_id, className: 'glass-card' },
            e('div', { className: 'glass-card__header' },
              e('div', null,
                e('div', { className: 'glass-card__title' }, s.name || s.scene_id),
                e('div', { className: 'glass-card__sub' }, s.description || '')
              )
            ),
            s.usd_path ? e('div', { className: 'glass-card__field', style: { marginTop: '6px' } },
              e('span', { style: { fontSize: '9px', color: 'var(--text-dim)' } }, s.usd_path)
            ) : null
          );
        })
      );
}

export { RegistryPage }
