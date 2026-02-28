import React from 'react'
import { NavContext } from '../contexts/NavContext'
import { AuthContext } from '../contexts/AuthContext'
import { Icon } from './Icon'
import { StatusDot } from './StatusDot'

var e = React.createElement;

function Sidebar(props) {
  var nav = React.useContext(NavContext);
  var authCtx = React.useContext(AuthContext);
  var currentPage = nav.page;

  var links = [
    { page: 'lab', icon: 'home', label: 'Mission Control' },
    { page: 'robot', icon: 'robot', label: 'Robots', params: { id: 'dobot_cr10' } },
    { page: 'fleet', icon: 'server', label: 'Fleet' },
    { page: 'simulations', icon: 'play', label: 'Simulations' },
    { page: 'demos', icon: 'activity', label: 'Demos' },
    { page: 'training', icon: 'brain', label: 'Training' },
    { page: 'agents', icon: 'users', label: 'Agents' }
  ];

  function isActive(linkPage) {
    return currentPage === linkPage;
  }

  return e('aside', { className: 'sidebar' },
    e('div', { className: 'sidebar__logo' },
      e('div', { className: 'sidebar__logo-symbol' }, '\u03B1'),
      e('div', { className: 'sidebar__logo-text-wrap' },
        e('div', { className: 'sidebar__logo-name' }, 'MISSION CONTROL'),
        e('div', { className: 'sidebar__logo-company' }, 'by Alpha')
      )
    ),
    e('nav', { className: 'sidebar__nav' },
      links.map(function(l) {
        return e('a', {
          key: l.page, href: '#',
          className: 'sidebar__link' + (isActive(l.page) ? ' sidebar__link--active' : ''),
          onClick: function(ev) { ev.preventDefault(); nav.navigate(l.page, l.params); }
        }, Icon(l.icon), e('span', null, l.label));
      })
    ),
    e('div', { className: 'sidebar__footer' },
      authCtx.user ? e('div', { className: 'sidebar__user' },
        e('div', { className: 'sidebar__user-info' },
          e('div', { className: 'sidebar__user-name' }, authCtx.user.username),
          e('div', { className: 'sidebar__user-role' }, authCtx.user.role)
        ),
        e('button', { className: 'sidebar__logout-btn', onClick: authCtx.logout }, 'Logout')
      ) : null,
      e('div', null, 'Mission Control v1.0'),
      e('div', { style: { fontSize: '9px', color: 'var(--text-dim)', marginTop: '2px' } }, '\u00A9 2026 Alpha. All rights reserved.'),
      e('div', { className: 'ws-status' },
        e(StatusDot, { status: props.wsStatus === 'connected' ? 'online' : 'offline', large: false }),
        e('span', null, props.wsStatus === 'connected' ? 'Live connected' : 'Reconnecting...')
      )
    )
  );
}

export { Sidebar }
