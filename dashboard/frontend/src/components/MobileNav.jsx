import React from 'react'
import { NavContext } from '../contexts/NavContext'
import { Icon } from './Icon'

var e = React.createElement;

function MobileNav() {
  var nav = React.useContext(NavContext);
  var currentPage = nav.page;
  var links = [
    { page: 'lab', icon: 'home', label: 'Control' },
    { page: 'fleet', icon: 'server', label: 'Fleet' },
    { page: 'mc-agents', icon: 'pipeline', label: 'Pipeline' },
    { page: 'workflows', icon: 'workflow', label: 'Workflows' },
    { page: 'registry', icon: 'registry', label: 'Registry' },
    { page: 'infra', icon: 'infra', label: 'Infra' }
  ];
  return e('nav', { className: 'mobile-nav' },
    links.map(function(l) {
      return e('a', {
        key: l.page, href: '#',
        className: 'mobile-nav__link' + (currentPage === l.page ? ' mobile-nav__link--active' : ''),
        onClick: function(ev) { ev.preventDefault(); nav.navigate(l.page, l.params); }
      }, Icon(l.icon), e('span', null, l.label));
    })
  );
}

export { MobileNav }
